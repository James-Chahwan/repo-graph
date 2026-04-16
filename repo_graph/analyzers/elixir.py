"""
Elixir analyzer.

Detects via mix.exs. Scans for modules, public functions, GenServers,
and Phoenix router scopes / routes.
"""

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

_MODULE_PATTERN = re.compile(r"^\s*defmodule\s+([\w.]+)\s+do", re.MULTILINE)
_DEF_PATTERN = re.compile(r"^\s*def\s+(\w+)", re.MULTILINE)
_DEFP_PATTERN = re.compile(r"^\s*defp\s+(\w+)", re.MULTILINE)
_USE_PATTERN = re.compile(r"^\s*use\s+([\w.]+)", re.MULTILINE)
_ALIAS_PATTERN = re.compile(r"^\s*alias\s+([\w.]+)", re.MULTILINE)

# Phoenix router: get "/users", UserController, :index
_PHOENIX_ROUTE = re.compile(
    r'^\s*(get|post|put|patch|delete|options|head|live|resources)\s+'
    r'"([^"]+)"(?:\s*,\s*(\w+))?',
    re.MULTILINE,
)
# scope "/api", MyAppWeb do ... end
_PHOENIX_SCOPE = re.compile(
    r'^\s*scope\s+"([^"]+)"', re.MULTILINE,
)

_ELIXIR_SKIP = {"_build", "deps", ".elixir_ls", "cover"}


def _find_elixir_roots(index) -> list[Path]:
    return index.roots_for("elixir", "mix.exs")


class ElixirAnalyzer(LanguageAnalyzer):

    @staticmethod
    def detect(index) -> bool:
        return bool(_find_elixir_roots(index))

    def scan(self) -> AnalysisResult:
        nodes: list[Node] = []
        edges: list[Edge] = []
        seen: set[str] = set()

        for project_root in _find_elixir_roots(self.index):
            proj_name = project_root.name
            proj_id = f"ex_proj_{proj_name.replace('-', '_').replace('.', '_')}"
            if proj_id not in seen:
                seen.add(proj_id)
                nodes.append(Node(
                    id=proj_id, type="elixir_project", name=proj_name,
                    file_path=rel_path(self.repo_root, project_root / "mix.exs"),
                ))

            for src_root in self._find_src_roots(project_root):
                for ex_file in self.index.files_with_ext({".ex", ".exs"}, under=src_root):
                    if ex_file.name == "mix.exs":
                        continue
                    self._scan_file(ex_file, proj_id, nodes, edges, seen)

        return AnalysisResult(
            nodes=nodes, edges=edges,
            state_sections=self._state(nodes),
        )

    def _find_src_roots(self, project_root: Path) -> list[Path]:
        roots = [d for d in (project_root / "lib", project_root / "apps") if d.exists()]
        return roots if roots else [project_root]

    def _should_skip(self, file_rel: str) -> bool:
        return (
            any(f"/{s}/" in f"/{file_rel}" for s in _ELIXIR_SKIP)
            or "/test/" in file_rel
            or file_rel.endswith("_test.exs")
        )

    def _scan_file(
        self, ex_file: Path, proj_id: str,
        nodes: list[Node], edges: list[Edge], seen: set[str],
    ) -> None:
        file_rel = rel_path(self.repo_root, ex_file)
        if self._should_skip(file_rel):
            return
        content = read_safe(ex_file)

        module_ids: list[str] = []
        for m in _MODULE_PATTERN.finditer(content):
            mod_name = m.group(1)
            mod_id = f"ex_mod_{mod_name.replace('.', '_')}"
            if mod_id not in seen:
                seen.add(mod_id)
                nodes.append(Node(
                    id=mod_id, type="elixir_module", name=mod_name, file_path=file_rel,
                ))
                edges.append(Edge(from_id=proj_id, to_id=mod_id, type="contains"))
            module_ids.append(mod_id)

        if not module_ids:
            return
        primary_mod = module_ids[0]

        for m in _DEF_PATTERN.finditer(content):
            fn_name = m.group(1)
            fn_id = f"ex_fn_{primary_mod}_{fn_name}"
            if fn_id not in seen:
                seen.add(fn_id)
                nodes.append(Node(
                    id=fn_id, type="elixir_function", name=fn_name, file_path=file_rel,
                ))
                edges.append(Edge(from_id=primary_mod, to_id=fn_id, type="defines"))

        # Alias edges
        for m in _ALIAS_PATTERN.finditer(content):
            alias_target = m.group(1)
            target_id = f"ex_mod_{alias_target.replace('.', '_')}"
            if target_id in seen and target_id != primary_mod:
                edges.append(Edge(from_id=primary_mod, to_id=target_id, type="uses"))

        # Phoenix routes — track scope prefix
        if "Phoenix.Router" in content or _PHOENIX_ROUTE.search(content):
            self._scan_phoenix_routes(content, primary_mod, file_rel, nodes, edges, seen)

    def _scan_phoenix_routes(
        self, content: str, mod_id: str, file_rel: str,
        nodes: list[Node], edges: list[Edge], seen: set[str],
    ) -> None:
        # Find all scope and route positions; build prefix stack by position
        scopes: list[tuple[int, str]] = [
            (m.start(), m.group(1)) for m in _PHOENIX_SCOPE.finditer(content)
        ]
        for m in _PHOENIX_ROUTE.finditer(content):
            method = m.group(1).upper()
            if method == "RESOURCES":
                method = "ANY"
            elif method == "LIVE":
                method = "PAGE"
            path = m.group(2)
            # Find nearest preceding scope (best-effort prefix)
            pos = m.start()
            prefix = ""
            for sp, sval in scopes:
                if sp < pos:
                    prefix = sval.rstrip("/") + ("/" + path.lstrip("/") if path != "/" else "")
            full_path = prefix if prefix else path
            slug = full_path.replace("/", "_").strip("_") or "root"
            rid = f"route_{method}_{slug}"
            if rid not in seen:
                seen.add(rid)
                nodes.append(Node(
                    id=rid, type="route", name=f"{method} {full_path}",
                    file_path=file_rel,
                ))
                edges.append(Edge(from_id=rid, to_id=mod_id, type="handled_by"))

    def _state(self, nodes: list[Node]) -> dict[str, str]:
        mods = [n for n in nodes if n.type == "elixir_module"]
        fns = [n for n in nodes if n.type == "elixir_function"]
        if not mods:
            return {}
        return {"Elixir": f"{len(mods)} modules, {len(fns)} functions\n"}

    # -- File-level analysis -----------------------------------------------

    def supported_extensions(self) -> set[str]:
        return {".ex", ".exs"}

    def analyze_file(self, file_path: Path) -> dict | None:
        if not file_path.is_file() or file_path.suffix not in (".ex", ".exs"):
            return None
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        total = len(lines)

        fns = []
        for pattern, kind in ((_DEF_PATTERN, "public"), (_DEFP_PATTERN, "private")):
            for m in pattern.finditer(content):
                line_num = content[:m.start()].count("\n") + 1
                fns.append({"name": m.group(1), "line": line_num, "kind": kind})
        fns.sort(key=lambda f: f["line"])
        for i, f in enumerate(fns):
            f["end"] = fns[i + 1]["line"] - 1 if i + 1 < len(fns) else total
            f["lines"] = f["end"] - f["line"] + 1
        fns.sort(key=lambda f: f["lines"], reverse=True)

        modules = _MODULE_PATTERN.findall(content)
        return {
            "type": "elixir", "file": file_path.name, "total_lines": total,
            "function_count": len(fns), "functions": fns,
            "module_count": len(modules),
        }

    def format_bloat_report(self, analysis: dict) -> str | None:
        if analysis.get("type") != "elixir":
            return None
        lines = [
            f"Bloat report: {analysis['file']} ({analysis['total_lines']} lines, "
            f"{analysis['function_count']} functions, {analysis['module_count']} modules)\n",
            "Functions (largest first):",
        ]
        for f in analysis["functions"][:15]:
            bar = "\u2588" * (f["lines"] // 5)
            lines.append(
                f"  {f['lines']:>4} lines  {bar:30s}  {f['name']} "
                f"[{f['kind']}] (L{f['line']}-{f['end']})"
            )
        return "\n".join(lines)
