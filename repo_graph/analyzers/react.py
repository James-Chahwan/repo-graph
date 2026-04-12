"""
React analyzer.

Detects React projects via 'react' in package.json dependencies.
Scans for components, hooks, context providers, and React Router routes.
Extends TypeScript analysis with React-specific concepts.
"""

import json
import re
from pathlib import Path

from .base import (
    AnalysisResult,
    Edge,
    LanguageAnalyzer,
    Node,
    read_safe,
    rel_path,
    render_flow_yaml,
    scan_project_dirs,
)

# Component patterns
_COMPONENT_PATTERN = re.compile(
    r"^(?:export\s+)?(?:default\s+)?(?:function|const)\s+(\w+)"
    r".*?(?:=>|{)\s*(?:.*?return\s*)?\(?.*?<",
    re.MULTILINE | re.DOTALL,
)
# Simpler: exported function/const that returns JSX (heuristic — file has JSX)
_EXPORT_FUNC = re.compile(
    r"^(?:export\s+)?(?:default\s+)?(?:function|const)\s+([A-Z]\w+)",
    re.MULTILINE,
)
_HOOK_DEF = re.compile(
    r"^(?:export\s+)?(?:function|const)\s+(use[A-Z]\w+)", re.MULTILINE
)
_HOOK_USAGE = re.compile(r"\b(use[A-Z]\w+)\s*\(")
_CONTEXT_PATTERN = re.compile(
    r"(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:React\.)?createContext", re.MULTILINE
)

# Import patterns
_IMPORT_PATTERN = re.compile(
    r"""from\s+['"](\.[^'"]+)['"]""", re.MULTILINE
)

# React Router routes
_ROUTER_ROUTE = re.compile(
    r'<Route\s+[^>]*path\s*=\s*["\'{]([^"\'{}]+)["\'}]', re.MULTILINE
)
# createBrowserRouter / createRoutesFromElements patterns
_ROUTE_OBJ = re.compile(
    r'path\s*:\s*[\'"]([^\'"]+)[\'"]', re.MULTILINE
)

# HTTP calls (fetch / axios)
_FETCH_PATTERN = re.compile(
    r'(?:fetch|axios\.(?:get|post|put|delete|patch))\s*\(\s*[`\'"]([^`\'"]+)[`\'"]',
    re.MULTILINE,
)


def _is_react(d: Path) -> bool:
    """Check if a directory is a React project."""
    pkg_json = d / "package.json"
    if not pkg_json.exists():
        return False
    try:
        pkg = json.loads(read_safe(pkg_json))
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        # React but not Angular (Angular analyzer handles that)
        return "react" in deps and "@angular/core" not in deps
    except (json.JSONDecodeError, TypeError):
        return False


def _find_react_roots(repo_root: Path) -> list[Path]:
    return [d for d in scan_project_dirs(repo_root) if _is_react(d)]


class ReactAnalyzer(LanguageAnalyzer):

    @staticmethod
    def detect(repo_root: Path) -> bool:
        return bool(_find_react_roots(repo_root))

    def scan(self) -> AnalysisResult:
        nodes: list[Node] = []
        edges: list[Edge] = []
        seen: set[str] = set()
        all_hooks: dict[str, str] = {}  # hook_name -> defining module id
        all_contexts: dict[str, str] = {}  # context_name -> defining module id
        all_components: list[tuple[str, str, str]] = []  # (comp_id, mod_id, file_rel)

        for react_root in _find_react_roots(self.repo_root):
            proj_name = react_root.name
            proj_id = f"react_proj_{proj_name.replace('-', '_').replace('.', '_')}"
            if proj_id not in seen:
                seen.add(proj_id)
                nodes.append(Node(
                    id=proj_id, type="react_project", name=proj_name,
                    file_path=rel_path(self.repo_root, react_root / "package.json"),
                ))

            src_root = self._find_src_root(react_root)
            for ts_file in sorted(src_root.rglob("*")):
                if ts_file.suffix not in (".ts", ".tsx", ".js", ".jsx"):
                    continue
                file_rel = rel_path(self.repo_root, ts_file)
                if self._should_skip(file_rel):
                    continue

                mod_id = self._file_to_id(file_rel)
                if mod_id in seen:
                    continue
                seen.add(mod_id)

                content = read_safe(ts_file)
                has_jsx = "<" in content and ("/>" in content or "</" in content)
                is_tsx = ts_file.suffix in (".tsx", ".jsx")

                nodes.append(Node(
                    id=mod_id, type="react_module", name=ts_file.stem,
                    file_path=file_rel,
                ))
                edges.append(Edge(from_id=proj_id, to_id=mod_id, type="contains"))

                # Components (PascalCase exports in files with JSX)
                if has_jsx or is_tsx:
                    for m in _EXPORT_FUNC.finditer(content):
                        comp_name = m.group(1)
                        comp_id = f"react_comp_{mod_id}_{comp_name}"
                        if comp_id not in seen:
                            seen.add(comp_id)
                            nodes.append(Node(
                                id=comp_id, type="react_component",
                                name=comp_name, file_path=file_rel,
                            ))
                            edges.append(Edge(from_id=mod_id, to_id=comp_id, type="defines"))
                            all_components.append((comp_id, mod_id, file_rel))

                # Custom hooks (useXxx definitions)
                for m in _HOOK_DEF.finditer(content):
                    hook_name = m.group(1)
                    hook_id = f"react_hook_{mod_id}_{hook_name}"
                    if hook_id not in seen:
                        seen.add(hook_id)
                        nodes.append(Node(
                            id=hook_id, type="react_hook",
                            name=hook_name, file_path=file_rel,
                        ))
                        edges.append(Edge(from_id=mod_id, to_id=hook_id, type="defines"))
                        all_hooks[hook_name] = hook_id

                # Context providers
                for m in _CONTEXT_PATTERN.finditer(content):
                    ctx_name = m.group(1)
                    ctx_id = f"react_ctx_{mod_id}_{ctx_name}"
                    if ctx_id not in seen:
                        seen.add(ctx_id)
                        nodes.append(Node(
                            id=ctx_id, type="react_context",
                            name=ctx_name, file_path=file_rel,
                        ))
                        edges.append(Edge(from_id=mod_id, to_id=ctx_id, type="defines"))
                        all_contexts[ctx_name] = ctx_id

                # React Router routes
                for m in _ROUTER_ROUTE.finditer(content):
                    path = m.group(1)
                    rid = f"route_PAGE_{path.replace('/', '_').strip('_') or 'root'}"
                    if rid not in seen:
                        seen.add(rid)
                        nodes.append(Node(
                            id=rid, type="route", name=f"PAGE {path}",
                            file_path=file_rel,
                        ))
                        edges.append(Edge(from_id=rid, to_id=mod_id, type="handled_by"))

                # Route objects (createBrowserRouter style)
                if "createBrowserRouter" in content or "createRoutesFromElements" in content:
                    for m in _ROUTE_OBJ.finditer(content):
                        path = m.group(1)
                        rid = f"route_PAGE_{path.replace('/', '_').strip('_') or 'root'}"
                        if rid not in seen:
                            seen.add(rid)
                            nodes.append(Node(
                                id=rid, type="route", name=f"PAGE {path}",
                                file_path=file_rel,
                            ))
                            edges.append(Edge(from_id=rid, to_id=mod_id, type="handled_by"))

                # HTTP calls (fetch/axios)
                for m in _FETCH_PATTERN.finditer(content):
                    url = m.group(1)
                    if url.startswith("http") or url.startswith("/"):
                        call_id = f"api_call_{url.replace('/', '_').strip('_')}"
                        if call_id not in seen:
                            seen.add(call_id)
                            nodes.append(Node(
                                id=call_id, type="api_call",
                                name=url, file_path=file_rel,
                            ))
                        edges.append(Edge(from_id=mod_id, to_id=call_id, type="calls"))

                # Import relationships
                for m in _IMPORT_PATTERN.finditer(content):
                    imp_path = m.group(1)
                    resolved = self._resolve_import(ts_file, imp_path)
                    if resolved:
                        target_id = self._file_to_id(rel_path(self.repo_root, resolved))
                        if target_id in seen:
                            edges.append(Edge(from_id=mod_id, to_id=target_id, type="imports"))

            # Second pass: connect hook usages to hook definitions
            for ts_file in sorted(src_root.rglob("*")):
                if ts_file.suffix not in (".ts", ".tsx", ".js", ".jsx"):
                    continue
                file_rel = rel_path(self.repo_root, ts_file)
                if self._should_skip(file_rel):
                    continue
                mod_id = self._file_to_id(file_rel)
                if mod_id not in seen:
                    continue
                content = read_safe(ts_file)
                for m in _HOOK_USAGE.finditer(content):
                    hook_name = m.group(1)
                    if hook_name in all_hooks:
                        hook_id = all_hooks[hook_name]
                        # Don't self-edge (the defining file)
                        if not hook_id.startswith(f"react_hook_{mod_id}"):
                            edges.append(Edge(from_id=mod_id, to_id=hook_id, type="uses"))

        return AnalysisResult(
            nodes=nodes, edges=edges,
            flows=self._build_flows(nodes, edges),
            state_sections=self._state(nodes),
        )

    def _find_src_root(self, project_root: Path) -> Path:
        for candidate in [project_root / "src", project_root / "app", project_root]:
            if candidate.exists() and any(
                candidate.rglob("*.tsx")
            ) or any(candidate.rglob("*.jsx")):
                return candidate
        return project_root

    def _should_skip(self, file_rel: str) -> bool:
        return (
            ".spec." in file_rel
            or ".test." in file_rel
            or ".stories." in file_rel
            or "node_modules" in file_rel
            or "/dist/" in file_rel
            or "/build/" in file_rel
            or "/__tests__/" in file_rel
            or "/__mocks__/" in file_rel
        )

    def _file_to_id(self, file_rel: str) -> str:
        stem = re.sub(r"\.[jt]sx?$", "", file_rel)
        return "react_mod_" + stem.replace("/", "_").replace("-", "_").replace(".", "_")

    def _resolve_import(self, from_file: Path, imp_path: str) -> Path | None:
        base = from_file.parent / imp_path
        for ext in [".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.tsx", "/index.js", "/index.jsx"]:
            candidate = base.parent / (base.name + ext)
            if candidate.exists():
                return candidate
        if base.is_dir():
            for idx in ["index.ts", "index.tsx", "index.js", "index.jsx"]:
                if (base / idx).exists():
                    return base / idx
        return None

    def _build_flows(self, nodes: list[Node], edges: list[Edge]) -> dict[str, str]:
        """Build flows from routes through components to API calls."""
        flows: dict[str, str] = {}
        routes = [n for n in nodes if n.type == "route"]
        if not routes:
            return flows

        # Build adjacency for quick lookup
        adj: dict[str, list[tuple[str, str]]] = {}
        for e in edges:
            adj.setdefault(e.from_id, []).append((e.to_id, e.type))
            if e.type == "handled_by":
                adj.setdefault(e.to_id, []).append((e.from_id, f"handles"))

        node_map = {n.id: n for n in nodes}

        for route in routes:
            path_name = route.name.replace("PAGE ", "").strip("/") or "root"
            flow_name = path_name.replace("/", "_").replace(":", "").strip("_") or "root"

            steps = [{"id": route.id, "type": route.type}]

            # Follow handled_by -> module -> (imports/calls) chain
            visited = {route.id}
            frontier = [route.id]
            for _ in range(5):  # max depth
                next_frontier = []
                for nid in frontier:
                    for target, etype in adj.get(nid, []):
                        if target not in visited:
                            visited.add(target)
                            n = node_map.get(target)
                            if n:
                                steps.append({"id": n.id, "type": n.type, "edge": etype})
                                if n.type in ("react_module", "react_component", "react_hook", "api_call"):
                                    next_frontier.append(target)
                frontier = next_frontier
                if not frontier:
                    break

            if len(steps) > 1:
                flows[flow_name] = render_flow_yaml(
                    flow_name,
                    [{"name": flow_name, "steps": steps}],
                )

        return flows

    def _state(self, nodes: list[Node]) -> dict[str, str]:
        components = [n for n in nodes if n.type == "react_component"]
        hooks = [n for n in nodes if n.type == "react_hook"]
        routes = [n for n in nodes if n.type == "route"]
        if not components:
            return {}
        parts = [f"{len(components)} components"]
        if hooks:
            parts.append(f"{len(hooks)} hooks")
        if routes:
            parts.append(f"{len(routes)} routes")
        return {"React": ", ".join(parts) + "\n"}

    # -- File-level analysis -----------------------------------------------

    def supported_extensions(self) -> set[str]:
        return {".tsx", ".jsx"}

    def analyze_file(self, file_path: Path) -> dict | None:
        if not file_path.is_file() or file_path.suffix not in (".tsx", ".jsx"):
            return None
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        total = len(lines)

        functions = []
        for m in re.finditer(r"^\s*(?:export\s+)?(?:async\s+)?(?:function|const)\s+(\w+)", content, re.MULTILINE):
            line_num = content[:m.start()].count("\n") + 1
            functions.append({"name": m.group(1), "line": line_num})

        for i, fn in enumerate(functions):
            fn["end"] = functions[i + 1]["line"] - 1 if i + 1 < len(functions) else total
            fn["lines"] = fn["end"] - fn["line"] + 1

        functions.sort(key=lambda f: f["lines"], reverse=True)
        hooks_used = list(set(_HOOK_USAGE.findall(content)))

        return {
            "type": "react", "file": file_path.name, "total_lines": total,
            "function_count": len(functions), "functions": functions,
            "hooks_used": hooks_used,
        }

    def format_bloat_report(self, analysis: dict) -> str | None:
        if analysis.get("type") != "react":
            return None
        lines = [
            f"Bloat report: {analysis['file']} ({analysis['total_lines']} lines, "
            f"{analysis['function_count']} functions)\n",
        ]
        if analysis.get("hooks_used"):
            lines.append(f"Hooks used: {', '.join(analysis['hooks_used'])}\n")
        lines.append("Functions (largest first):")
        for fn in analysis["functions"][:15]:
            bar = "\u2588" * (fn["lines"] // 5)
            lines.append(f"  {fn['lines']:>4} lines  {bar:30s}  {fn['name']} (L{fn['line']}-{fn['end']})")
        return "\n".join(lines)
