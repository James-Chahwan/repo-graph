"""
Vue analyzer.

Detects Vue projects via 'vue' in package.json dependencies.
Scans .vue single-file components, composables (use*), Vue Router routes,
and fetch/axios calls.
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
)

# <script setup lang="ts"> or <script> blocks
_SCRIPT_BLOCK = re.compile(
    r"<script[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE
)
# defineProps, defineEmits, defineOptions
_DEFINE_OPTIONS_NAME = re.compile(
    r"defineOptions\s*\(\s*\{[^}]*name\s*:\s*['\"]([\w-]+)['\"]"
)
# Export default { name: 'Foo' } for Options API
_OPTIONS_NAME = re.compile(
    r"(?:export\s+default\s+(?:defineComponent\s*\()?\s*\{[^}]*?)name\s*:\s*['\"]([\w-]+)['\"]",
    re.DOTALL,
)
# Composables: export function useXxx / const useXxx
_COMPOSABLE = re.compile(
    r"^(?:export\s+)?(?:function|const)\s+(use[A-Z]\w+)", re.MULTILINE
)
_COMPOSABLE_USAGE = re.compile(r"\b(use[A-Z]\w+)\s*\(")

# Vue Router: { path: '/foo', component: Foo }
_ROUTE_OBJ = re.compile(r"path\s*:\s*[\'\"]([^\'\"]+)[\'\"]", re.MULTILINE)
# <router-view /> — not useful alone, skip

# Imports: relative paths
_IMPORT_PATTERN = re.compile(r"""from\s+['"](\.[^'"]+)['"]""", re.MULTILINE)

# HTTP calls
_FETCH_PATTERN = re.compile(
    r'(?:fetch|axios\.(?:get|post|put|delete|patch)|\$fetch|useFetch|useAsyncData)'
    r'\s*\(\s*[`\'"]([^`\'"]+)[`\'"]',
    re.MULTILINE,
)


def _is_vue(d: Path) -> bool:
    pkg_json = d / "package.json"
    if not pkg_json.exists():
        return False
    try:
        pkg = json.loads(read_safe(pkg_json))
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        return "vue" in deps or "nuxt" in deps or "@nuxt/core" in deps
    except (json.JSONDecodeError, TypeError):
        return False


def _find_vue_roots(index) -> list[Path]:
    auto = [d for d in index.dirs_with_file("package.json") if _is_vue(d)]
    return sorted(set(auto) | set(index.extra_roots("vue")))


class VueAnalyzer(LanguageAnalyzer):

    @staticmethod
    def detect(index) -> bool:
        return bool(_find_vue_roots(index))

    def scan(self) -> AnalysisResult:
        nodes: list[Node] = []
        edges: list[Edge] = []
        seen: set[str] = set()
        all_composables: dict[str, str] = {}

        for vue_root in _find_vue_roots(self.index):
            proj_name = vue_root.name
            proj_id = f"vue_proj_{proj_name.replace('-', '_').replace('.', '_')}"
            if proj_id not in seen:
                seen.add(proj_id)
                nodes.append(Node(
                    id=proj_id, type="vue_project", name=proj_name,
                    file_path=rel_path(self.repo_root, vue_root / "package.json"),
                ))

            src_root = self._find_src_root(vue_root)

            for f in self.index.files_with_ext({".vue", ".ts", ".js", ".mjs"}, under=src_root):
                file_rel = rel_path(self.repo_root, f)
                if self._should_skip(file_rel):
                    continue
                mod_id = self._file_to_id(file_rel)
                if mod_id in seen:
                    continue
                seen.add(mod_id)

                content = read_safe(f)
                script_content = self._extract_script(content) if f.suffix == ".vue" else content

                nodes.append(Node(
                    id=mod_id, type="vue_module", name=f.stem, file_path=file_rel,
                ))
                edges.append(Edge(from_id=proj_id, to_id=mod_id, type="contains"))

                # Vue SFC → component node
                if f.suffix == ".vue":
                    comp_name = self._component_name(script_content, f.stem)
                    comp_id = f"vue_comp_{mod_id}"
                    if comp_id not in seen:
                        seen.add(comp_id)
                        nodes.append(Node(
                            id=comp_id, type="vue_component", name=comp_name,
                            file_path=file_rel,
                        ))
                        edges.append(Edge(from_id=mod_id, to_id=comp_id, type="defines"))

                # Composables
                for m in _COMPOSABLE.finditer(script_content):
                    name = m.group(1)
                    cid = f"vue_composable_{mod_id}_{name}"
                    if cid not in seen:
                        seen.add(cid)
                        nodes.append(Node(
                            id=cid, type="vue_composable", name=name, file_path=file_rel,
                        ))
                        edges.append(Edge(from_id=mod_id, to_id=cid, type="defines"))
                        all_composables[name] = cid

                # Vue Router routes — only scan files that look like routers
                is_router_file = (
                    "createRouter" in content
                    or "VueRouter" in content
                    or "createMemoryHistory" in content
                    or "createWebHistory" in content
                )
                if is_router_file:
                    for m in _ROUTE_OBJ.finditer(script_content):
                        path = m.group(1)
                        slug = path.replace("/", "_").strip("_") or "root"
                        rid = f"route_PAGE_{slug}"
                        if rid not in seen:
                            seen.add(rid)
                            nodes.append(Node(
                                id=rid, type="route", name=f"PAGE {path}",
                                file_path=file_rel,
                            ))
                            edges.append(Edge(from_id=rid, to_id=mod_id, type="handled_by"))

                # HTTP calls → endpoint_* IDs (cross-stack linker rewires these)
                for m in _FETCH_PATTERN.finditer(script_content):
                    url = m.group(1)
                    if url.startswith("http") or url.startswith("/"):
                        call_id = f"api_call_{url.replace('/', '_').strip('_')}"
                        if call_id not in seen:
                            seen.add(call_id)
                            nodes.append(Node(
                                id=call_id, type="api_call", name=url,
                                file_path=file_rel,
                            ))
                        edges.append(Edge(from_id=mod_id, to_id=call_id, type="calls"))

                # Relative imports
                for m in _IMPORT_PATTERN.finditer(content):
                    resolved = self._resolve_import(f, m.group(1))
                    if resolved:
                        target_id = self._file_to_id(rel_path(self.repo_root, resolved))
                        if target_id in seen:
                            edges.append(Edge(from_id=mod_id, to_id=target_id, type="imports"))

            # Second pass: composable usage edges
            for f in self.index.files_with_ext({".vue", ".ts", ".js", ".mjs"}, under=src_root):
                file_rel = rel_path(self.repo_root, f)
                if self._should_skip(file_rel):
                    continue
                mod_id = self._file_to_id(file_rel)
                if mod_id not in seen:
                    continue
                content = read_safe(f)
                script_content = self._extract_script(content) if f.suffix == ".vue" else content
                for m in _COMPOSABLE_USAGE.finditer(script_content):
                    name = m.group(1)
                    if name in all_composables:
                        target = all_composables[name]
                        if not target.startswith(f"vue_composable_{mod_id}_"):
                            edges.append(Edge(from_id=mod_id, to_id=target, type="uses"))

        return AnalysisResult(
            nodes=nodes, edges=edges,
            state_sections=self._state(nodes),
        )

    def _extract_script(self, sfc_content: str) -> str:
        blocks = _SCRIPT_BLOCK.findall(sfc_content)
        return "\n".join(blocks)

    def _component_name(self, script: str, default: str) -> str:
        m = _DEFINE_OPTIONS_NAME.search(script) or _OPTIONS_NAME.search(script)
        return m.group(1) if m else default

    def _find_src_root(self, project_root: Path) -> Path:
        for cand in [project_root / "src", project_root / "app", project_root / "pages", project_root]:
            if cand.exists() and self.index.files_with_ext(".vue", under=cand):
                return cand
        return project_root

    def _should_skip(self, file_rel: str) -> bool:
        return (
            ".spec." in file_rel
            or ".test." in file_rel
            or "node_modules" in file_rel
            or "/dist/" in file_rel
            or "/.nuxt/" in file_rel
            or "/.output/" in file_rel
            or "/build/" in file_rel
        )

    def _file_to_id(self, file_rel: str) -> str:
        stem = re.sub(r"\.(vue|[mj]?[jt]sx?)$", "", file_rel)
        return "vue_mod_" + stem.replace("/", "_").replace("-", "_").replace(".", "_")

    def _resolve_import(self, from_file: Path, imp_path: str) -> Path | None:
        base = from_file.parent / imp_path
        for ext in [".vue", ".ts", ".tsx", ".js", ".jsx", ".mjs"]:
            candidate = Path(str(base) + ext)
            if candidate.exists():
                return candidate
        if base.is_dir():
            for idx in ["index.ts", "index.js", "index.vue"]:
                if (base / idx).exists():
                    return base / idx
        return None

    def _state(self, nodes: list[Node]) -> dict[str, str]:
        comps = [n for n in nodes if n.type == "vue_component"]
        composables = [n for n in nodes if n.type == "vue_composable"]
        if not comps:
            return {}
        parts = [f"{len(comps)} components"]
        if composables:
            parts.append(f"{len(composables)} composables")
        return {"Vue": ", ".join(parts) + "\n"}

    # -- File-level analysis -----------------------------------------------

    def supported_extensions(self) -> set[str]:
        return {".vue"}

    def analyze_file(self, file_path: Path) -> dict | None:
        if not file_path.is_file() or file_path.suffix != ".vue":
            return None
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        total = len(lines)
        script = self._extract_script(content)
        script_lines = script.count("\n") + 1 if script else 0

        funcs = []
        for m in re.finditer(r"^\s*(?:export\s+)?(?:async\s+)?(?:function|const)\s+(\w+)", script, re.MULTILINE):
            line_num = script[:m.start()].count("\n") + 1
            funcs.append({"name": m.group(1), "line": line_num})
        for i, f in enumerate(funcs):
            f["end"] = funcs[i + 1]["line"] - 1 if i + 1 < len(funcs) else script_lines
            f["lines"] = f["end"] - f["line"] + 1
        funcs.sort(key=lambda f: f["lines"], reverse=True)

        return {
            "type": "vue", "file": file_path.name, "total_lines": total,
            "script_lines": script_lines, "function_count": len(funcs),
            "functions": funcs,
        }

    def format_bloat_report(self, analysis: dict) -> str | None:
        if analysis.get("type") != "vue":
            return None
        lines = [
            f"Bloat report: {analysis['file']} ({analysis['total_lines']} lines total, "
            f"{analysis['script_lines']} script, {analysis['function_count']} functions)\n",
            "Functions (largest first):",
        ]
        for f in analysis["functions"][:15]:
            bar = "\u2588" * (f["lines"] // 5)
            lines.append(f"  {f['lines']:>4} lines  {bar:30s}  {f['name']} (L{f['line']}-{f['end']})")
        return "\n".join(lines)
