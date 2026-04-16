"""
Go language analyzer.

Detects Go projects via go.mod, scans for packages, functions,
HTTP route registrations, and import relationships.
"""

import re
from pathlib import Path

from .base import (
    AnalysisResult,
    Edge,
    LanguageAnalyzer,
    Node,
    camel_to_snake,
    list_files,
    path_to_slug,
    read_safe,
    rel_path,
)


# HTTP route patterns for common Go frameworks
# Group 1: method (or path for HandleFunc), Group 2: path, Group 3: handler name (optional)
_ROUTE_PATTERNS = [
    # gin/echo/chi: r.GET("/path", handler) or r.GET("/path", pkg.Handler)
    re.compile(r'\.(GET|POST|PUT|DELETE|PATCH|OPTIONS)\(\s*"([^"]+)"\s*,\s*(\w+(?:\.\w+)?)'),
    # gin/echo/chi without named handler (inline func): r.GET("/path", func(...
    re.compile(r'\.(GET|POST|PUT|DELETE|PATCH|OPTIONS)\(\s*"([^"]+)"\s*,\s*func\b'),
    # stdlib/gorilla/mux: http.HandleFunc("/path", handler)
    re.compile(r'HandleFunc\(\s*"([^"]+)"\s*,\s*(\w+(?:\.\w+)?)'),
]

# Function definition
_FUNC_PATTERN = re.compile(r"^func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(", re.MULTILINE)

# Import block
_IMPORT_PATTERN = re.compile(r'^import\s*\(([^)]*)\)', re.MULTILINE | re.DOTALL)
_IMPORT_LINE = re.compile(r'"([^"]+)"')


class GoAnalyzer(LanguageAnalyzer):

    @staticmethod
    def detect(index) -> bool:
        return bool(index.roots_for("go", "go.mod"))

    def scan(self) -> AnalysisResult:
        nodes: list[Node] = []
        edges: list[Edge] = []
        seen_ids: set[str] = set()

        mod_roots = self.index.roots_for("go", "go.mod")

        for mod_root in mod_roots:
            mod_name = self._read_module_name(mod_root)
            mod_id = f"go_mod_{camel_to_snake(mod_root.name)}"
            if mod_id not in seen_ids:
                seen_ids.add(mod_id)
                nodes.append(Node(
                    id=mod_id,
                    type="go_module",
                    name=mod_name or mod_root.name,
                    file_path=rel_path(self.repo_root, mod_root / "go.mod"),
                ))

            self._scan_packages(mod_root, mod_id, nodes, edges, seen_ids)

        return AnalysisResult(
            nodes=nodes,
            edges=edges,
            state_sections=self._state_section(mod_roots),
        )

    def _read_module_name(self, mod_root: Path) -> str | None:
        content = read_safe(mod_root / "go.mod")
        m = re.search(r"^module\s+(\S+)", content, re.MULTILINE)
        return m.group(1) if m else None

    def _scan_packages(
        self,
        mod_root: Path,
        mod_id: str,
        nodes: list[Node],
        edges: list[Edge],
        seen_ids: set[str],
    ) -> None:
        # Two-pass: first collect all functions, then resolve route→handler links
        pending_routes: list[tuple[str, str, str | None, str]] = []  # (route_id, pkg_id, handler_name, pkg_rel)

        for go_file in self.index.files_with_ext(".go", under=mod_root):
            if go_file.name.endswith("_test.go"):
                continue

            pkg_dir = go_file.parent
            pkg_rel = rel_path(self.repo_root, pkg_dir)
            pkg_id = f"go_pkg_{pkg_rel.replace('/', '_').replace('-', '_')}"

            if pkg_id not in seen_ids:
                seen_ids.add(pkg_id)
                nodes.append(Node(
                    id=pkg_id,
                    type="go_package",
                    name=pkg_dir.name,
                    file_path=pkg_rel,
                ))
                edges.append(Edge(from_id=mod_id, to_id=pkg_id, type="contains"))

            content = read_safe(go_file)
            file_rel = rel_path(self.repo_root, go_file)

            # Extract functions
            for m in _FUNC_PATTERN.finditer(content):
                func_name = m.group(1)
                func_id = f"go_func_{pkg_rel.replace('/', '_')}_{camel_to_snake(func_name)}"
                if func_id not in seen_ids:
                    seen_ids.add(func_id)
                    nodes.append(Node(
                        id=func_id,
                        type="go_function",
                        name=func_name,
                        file_path=file_rel,
                    ))
                    edges.append(Edge(from_id=pkg_id, to_id=func_id, type="defines"))

            # Extract HTTP routes (defer handler linking to second pass)
            for pattern in _ROUTE_PATTERNS:
                for match in pattern.finditer(content):
                    groups = match.groups()
                    handler_name = None
                    if len(groups) == 3:
                        method, path, handler_name = groups
                    elif len(groups) == 2:
                        if 'HandleFunc' in pattern.pattern:
                            path, handler_name = groups
                            method = "ANY"
                        else:
                            method, path = groups
                    else:
                        method, path = "ANY", groups[0]

                    route_id = f"route_{method}_{path_to_slug(path)}"
                    if route_id not in seen_ids:
                        seen_ids.add(route_id)
                        nodes.append(Node(
                            id=route_id,
                            type="route",
                            name=f"{method} {path}",
                            file_path=file_rel,
                        ))
                        pending_routes.append((route_id, pkg_id, handler_name, pkg_rel))

            # Extract imports for edge building
            for imp_block in _IMPORT_PATTERN.finditer(content):
                for imp_line in _IMPORT_LINE.finditer(imp_block.group(1)):
                    imp_path = imp_line.group(1)
                    mod_name = self._read_module_name(mod_root)
                    if mod_name and imp_path.startswith(mod_name):
                        rel_imp = imp_path[len(mod_name):].lstrip("/")
                        target_id = f"go_pkg_{mod_root.name}_{rel_imp.replace('/', '_').replace('-', '_')}"
                        if target_id in seen_ids:
                            edges.append(Edge(from_id=pkg_id, to_id=target_id, type="imports"))

        # Second pass: resolve route → specific handler function
        for route_id, pkg_id, handler_name, pkg_rel in pending_routes:
            handler_target = pkg_id  # fallback to package
            if handler_name:
                bare_name = handler_name.split(".")[-1]
                # Try same package first
                func_id = f"go_func_{pkg_rel.replace('/', '_')}_{camel_to_snake(bare_name)}"
                if func_id in seen_ids:
                    handler_target = func_id
                else:
                    # Search all known function IDs (cross-package handler)
                    suffix = f"_{camel_to_snake(bare_name)}"
                    for sid in seen_ids:
                        if sid.startswith("go_func_") and sid.endswith(suffix):
                            handler_target = sid
                            break
            edges.append(Edge(from_id=route_id, to_id=handler_target, type="handled_by"))

    def _state_section(self, mod_roots: list[Path]) -> dict[str, str]:
        if not mod_roots:
            return {}
        lines = []
        for mod_root in mod_roots:
            mod_name = self._read_module_name(mod_root) or mod_root.name
            go_files = self.index.files_with_ext(".go", under=mod_root)
            test_files = [f for f in go_files if f.name.endswith("_test.go")]
            lines.append(
                f"- **{mod_name}** — "
                f"{len(go_files) - len(test_files)} source files, "
                f"{len(test_files)} test files"
            )
        return {"Go Modules": "\n".join(lines) + "\n"}

    # -- File-level analysis -----------------------------------------------

    def supported_extensions(self) -> set[str]:
        return {".go"}

    def analyze_file(self, file_path: Path) -> dict | None:
        if not file_path.is_file() or file_path.suffix != ".go":
            return None

        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        total = len(lines)

        functions = []
        current_func = None
        brace_depth = 0

        for i, line in enumerate(lines, 1):
            m = _FUNC_PATTERN.match(line)
            if m and brace_depth == 0:
                if current_func:
                    current_func["end"] = i - 1
                    current_func["lines"] = current_func["end"] - current_func["start"] + 1
                    functions.append(current_func)
                current_func = {"name": m.group(1), "start": i, "end": total, "lines": 0}
            brace_depth += line.count("{") - line.count("}")

        if current_func:
            current_func["end"] = total
            current_func["lines"] = current_func["end"] - current_func["start"] + 1
            functions.append(current_func)

        functions.sort(key=lambda f: f["lines"], reverse=True)

        return {
            "type": "go",
            "file": file_path.name,
            "total_lines": total,
            "function_count": len(functions),
            "functions": functions,
        }

    def format_bloat_report(self, analysis: dict) -> str | None:
        if analysis.get("type") != "go":
            return None
        lines = [
            f"Bloat report: {analysis['file']} ({analysis['total_lines']} lines, "
            f"{analysis['function_count']} functions)\n",
            "Functions (largest first):",
        ]
        for fn in analysis["functions"][:15]:
            bar = "█" * (fn["lines"] // 5)
            lines.append(
                f"  {fn['lines']:>4} lines  {bar:30s}  {fn['name']} "
                f"(L{fn['start']}-{fn['end']})"
            )
        return "\n".join(lines)

    def suggest_splits(self, file_path: Path, analysis: dict) -> list[dict] | None:
        if analysis.get("type") != "go":
            return None
        functions = analysis.get("functions", [])
        if len(functions) < 4:
            return None

        # Group functions by prefix patterns
        groups: dict[str, list[dict]] = {}
        for fn in functions:
            name = fn["name"]
            prefix = "other"
            for keyword in ["Create", "Update", "Delete", "List", "Get",
                            "Find", "Search", "Handle", "Sync", "Send",
                            "Run", "Init", "New", "Register", "Validate"]:
                if keyword.lower() in name.lower():
                    prefix = keyword.lower()
                    break
            groups.setdefault(prefix, []).append(fn)

        # Merge small groups
        merged: dict[str, list[dict]] = {}
        small: list[dict] = []
        for prefix, fns in groups.items():
            total = sum(f["lines"] for f in fns)
            if total < 80:
                small.extend(fns)
            else:
                merged[prefix] = fns
        if small:
            merged["misc"] = small

        return [
            {
                "suggested_name": f"{file_path.stem}_{prefix}",
                "methods": [f["name"] for f in fns],
                "method_count": len(fns),
                "approx_lines": sum(f["lines"] for f in fns),
                "related_services": [],
            }
            for prefix, fns in merged.items()
        ]

    def format_split_plan(self, file_path: str, analysis: dict, splits: list[dict]) -> str | None:
        if analysis.get("type") != "go":
            return None
        lines = [
            f"Split plan for {file_path} ({analysis['total_lines']} lines, "
            f"{analysis['function_count']} functions):\n"
        ]
        for i, cluster in enumerate(splits, 1):
            lines.append(f"  {i}. {cluster['suggested_name']}.go (~{cluster['approx_lines']} lines)")
            fn_names = cluster["methods"]
            lines.append(f"     Functions: {', '.join(fn_names[:8])}")
            if len(fn_names) > 8:
                lines.append(f"     ... and {len(fn_names) - 8} more")
        return "\n".join(lines)
