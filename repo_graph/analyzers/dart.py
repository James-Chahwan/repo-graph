"""
Dart / Flutter analyzer.

Detects via pubspec.yaml. Scans for classes, Flutter widgets, and routes
from go_router, Navigator, and shelf.
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

_CLASS_PATTERN = re.compile(
    r"^(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?"
    r"(?:\s+(?:implements|with)\s+([\w,\s]+))?",
    re.MULTILINE,
)
_FUNC_PATTERN = re.compile(
    r"^\s*(?:Future<[^>]*>|Stream<[^>]*>|void|Widget|bool|int|String|double|\w+)\s+(\w+)\s*\(",
    re.MULTILINE,
)
_IMPORT_PATTERN = re.compile(
    r"""import\s+['"]package:([^'"/]+)/([^'"]+)['"]""", re.MULTILINE
)
_RELATIVE_IMPORT = re.compile(
    r"""import\s+['"](\.{1,2}/[^'"]+)['"]""", re.MULTILINE
)

# go_router GoRoute(path: '/foo', builder: ...)
_GOROUTE_PATTERN = re.compile(
    r"GoRoute\s*\([^)]*path\s*:\s*['\"]([^'\"]+)['\"]",
    re.MULTILINE | re.DOTALL,
)
# Navigator.pushNamed(context, '/foo')
_NAV_NAMED = re.compile(
    r"""(?:pushNamed|pushReplacementNamed|popAndPushNamed)\s*\([^,]+,\s*['"]([^'"]+)['"]"""
)
# shelf_router: router.get('/foo', handler)
_SHELF_ROUTE = re.compile(
    r"""\.(?:get|post|put|delete|patch|head|all)\s*\(\s*['"]([^'"]+)['"]"""
)

_DART_SKIP = {".dart_tool", "build", ".pub-cache", ".pub"}


def _find_dart_roots(index) -> list[Path]:
    return index.roots_for("dart", "pubspec.yaml")


def _is_flutter(pubspec_path: Path) -> bool:
    content = read_safe(pubspec_path)
    return "flutter:" in content or "sdk: flutter" in content


class DartAnalyzer(LanguageAnalyzer):

    @staticmethod
    def detect(index) -> bool:
        return bool(_find_dart_roots(index))

    def scan(self) -> AnalysisResult:
        nodes: list[Node] = []
        edges: list[Edge] = []
        seen: set[str] = set()

        for project_root in _find_dart_roots(self.index):
            proj_name = project_root.name
            is_flutter = _is_flutter(project_root / "pubspec.yaml")
            proj_type = "flutter_project" if is_flutter else "dart_project"
            proj_id = f"dart_proj_{proj_name.replace('-', '_').replace('.', '_')}"
            if proj_id not in seen:
                seen.add(proj_id)
                nodes.append(Node(
                    id=proj_id, type=proj_type, name=proj_name,
                    file_path=rel_path(self.repo_root, project_root / "pubspec.yaml"),
                ))

            lib_root = project_root / "lib"
            src_root = lib_root if lib_root.exists() else project_root
            for dart_file in self.index.files_with_ext(".dart", under=src_root):
                self._scan_file(dart_file, proj_id, is_flutter, nodes, edges, seen)

        return AnalysisResult(
            nodes=nodes, edges=edges,
            state_sections=self._state(nodes),
        )

    def _should_skip(self, file_rel: str) -> bool:
        return (
            any(f"/{s}/" in f"/{file_rel}" for s in _DART_SKIP)
            or file_rel.endswith("_test.dart")
            or "/test/" in file_rel
            or "/generated/" in file_rel
            or ".g.dart" in file_rel
            or ".freezed.dart" in file_rel
        )

    def _file_to_id(self, file_rel: str) -> str:
        stem = re.sub(r"\.dart$", "", file_rel)
        return "dart_mod_" + stem.replace("/", "_").replace("-", "_").replace(".", "_")

    def _scan_file(
        self, dart_file: Path, proj_id: str, is_flutter: bool,
        nodes: list[Node], edges: list[Edge], seen: set[str],
    ) -> None:
        file_rel = rel_path(self.repo_root, dart_file)
        if self._should_skip(file_rel):
            return

        mod_id = self._file_to_id(file_rel)
        if mod_id in seen:
            return
        seen.add(mod_id)

        content = read_safe(dart_file)
        nodes.append(Node(
            id=mod_id, type="dart_module", name=dart_file.stem, file_path=file_rel,
        ))
        edges.append(Edge(from_id=proj_id, to_id=mod_id, type="contains"))

        for m in _CLASS_PATTERN.finditer(content):
            name = m.group(1)
            extends = m.group(2) or ""
            impls_with = m.group(3) or ""
            all_parents = (extends + " " + impls_with).lower()
            is_widget = is_flutter and (
                "widget" in all_parents or "state" in all_parents
            )
            node_type = "flutter_widget" if is_widget else "dart_class"
            cid = f"dart_class_{mod_id}_{name}"
            if cid not in seen:
                seen.add(cid)
                nodes.append(Node(
                    id=cid, type=node_type, name=name, file_path=file_rel,
                ))
                edges.append(Edge(from_id=mod_id, to_id=cid, type="defines"))
                if extends:
                    parent_ref = f"dart_ref_{extends}"
                    edges.append(Edge(from_id=cid, to_id=parent_ref, type="extends"))

        # go_router / Navigator routes
        for m in _GOROUTE_PATTERN.finditer(content):
            self._add_route("PAGE", m.group(1), file_rel, mod_id, nodes, edges, seen)
        for m in _NAV_NAMED.finditer(content):
            self._add_route("PAGE", m.group(1), file_rel, mod_id, nodes, edges, seen)
        # shelf routes
        for m in _SHELF_ROUTE.finditer(content):
            self._add_route("ANY", m.group(1), file_rel, mod_id, nodes, edges, seen)

        # Relative imports → edges
        for m in _RELATIVE_IMPORT.finditer(content):
            resolved = (dart_file.parent / m.group(1)).resolve()
            try:
                resolved.relative_to(self.repo_root)
            except ValueError:
                continue
            target_id = self._file_to_id(rel_path(self.repo_root, resolved))
            if target_id in seen:
                edges.append(Edge(from_id=mod_id, to_id=target_id, type="imports"))

    def _add_route(
        self, method: str, path: str, file_rel: str, mod_id: str,
        nodes: list[Node], edges: list[Edge], seen: set[str],
    ) -> None:
        slug = path.replace("/", "_").strip("_") or "root"
        rid = f"route_{method}_{slug}"
        if rid not in seen:
            seen.add(rid)
            nodes.append(Node(
                id=rid, type="route", name=f"{method} {path}", file_path=file_rel,
            ))
            edges.append(Edge(from_id=rid, to_id=mod_id, type="handled_by"))

    def _state(self, nodes: list[Node]) -> dict[str, str]:
        modules = [n for n in nodes if n.type == "dart_module"]
        widgets = [n for n in nodes if n.type == "flutter_widget"]
        classes = [n for n in nodes if n.type == "dart_class"]
        if not modules:
            return {}
        parts = [f"{len(modules)} modules", f"{len(classes)} classes"]
        if widgets:
            parts.append(f"{len(widgets)} widgets")
        title = "Flutter" if widgets else "Dart"
        return {title: ", ".join(parts) + "\n"}

    # -- File-level analysis -----------------------------------------------

    def supported_extensions(self) -> set[str]:
        return {".dart"}

    def analyze_file(self, file_path: Path) -> dict | None:
        if not file_path.is_file() or file_path.suffix != ".dart":
            return None
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        total = len(lines)

        funcs = []
        for m in _FUNC_PATTERN.finditer(content):
            name = m.group(1)
            if name in ("if", "for", "while", "switch", "catch", "return"):
                continue
            line_num = content[:m.start()].count("\n") + 1
            funcs.append({"name": name, "line": line_num})
        for i, f in enumerate(funcs):
            f["end"] = funcs[i + 1]["line"] - 1 if i + 1 < len(funcs) else total
            f["lines"] = f["end"] - f["line"] + 1
        funcs.sort(key=lambda f: f["lines"], reverse=True)

        classes = [m.group(1) for m in _CLASS_PATTERN.finditer(content)]
        return {
            "type": "dart", "file": file_path.name, "total_lines": total,
            "function_count": len(funcs), "functions": funcs,
            "class_count": len(classes),
        }

    def format_bloat_report(self, analysis: dict) -> str | None:
        if analysis.get("type") != "dart":
            return None
        lines = [
            f"Bloat report: {analysis['file']} ({analysis['total_lines']} lines, "
            f"{analysis['function_count']} functions, {analysis['class_count']} classes)\n",
            "Functions (largest first):",
        ]
        for f in analysis["functions"][:15]:
            bar = "\u2588" * (f["lines"] // 5)
            lines.append(f"  {f['lines']:>4} lines  {bar:30s}  {f['name']} (L{f['line']}-{f['end']})")
        return "\n".join(lines)
