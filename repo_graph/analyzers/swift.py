"""
Swift analyzer.

Detects Swift projects via Package.swift or .xcodeproj/.xcworkspace.
Scans for structs, classes, protocols, functions, and Vapor routes.
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
    r"^(?:public\s+|internal\s+|private\s+|open\s+|fileprivate\s+)?"
    r"(?:final\s+)?(class|struct|enum|protocol|actor)\s+(\w+)",
    re.MULTILINE,
)
_FUNC_PATTERN = re.compile(
    r"^(?:\s*)(?:public\s+|internal\s+|private\s+|open\s+)?"
    r"(?:static\s+|class\s+)?(?:override\s+)?func\s+(\w+)",
    re.MULTILINE,
)
_IMPORT_PATTERN = re.compile(r"^import\s+(\w+)", re.MULTILINE)

# Vapor routes: app.get("path") { ... }
_VAPOR_ROUTE = re.compile(
    r'\.(get|post|put|patch|delete)\(\s*"([^"]+)"', re.MULTILINE
)


def _find_swift_roots(index) -> list[Path]:
    return index.roots_for("swift", ["Package.swift", "*.xcodeproj", "*.xcworkspace"])


class SwiftAnalyzer(LanguageAnalyzer):

    @staticmethod
    def detect(index) -> bool:
        return bool(_find_swift_roots(index))

    def scan(self) -> AnalysisResult:
        nodes: list[Node] = []
        edges: list[Edge] = []
        seen: set[str] = set()

        for project_root in _find_swift_roots(self.index):
            proj_name = project_root.name
            proj_id = f"swift_proj_{proj_name.replace('-', '_')}"
            if proj_id not in seen:
                seen.add(proj_id)
                marker = "Package.swift" if (project_root / "Package.swift").exists() else ""
                nodes.append(Node(
                    id=proj_id, type="swift_project", name=proj_name,
                    file_path=rel_path(self.repo_root, project_root / marker) if marker else rel_path(self.repo_root, project_root),
                ))

            src_dirs = [project_root / "Sources", project_root / "src", project_root]
            for src_dir in src_dirs:
                if not src_dir.exists():
                    continue
                for swift_file in self.index.files_with_ext(".swift", under=src_dir):
                    file_rel = rel_path(self.repo_root, swift_file)
                    if "/Tests/" in file_rel or "/test/" in file_rel:
                        continue
                    if "/.build/" in file_rel:
                        continue
                    fid = f"swift_file_{file_rel.replace('/', '_').replace('.', '_')}"
                    if fid in seen:
                        continue
                    seen.add(fid)

                    nodes.append(Node(id=fid, type="swift_file", name=swift_file.stem, file_path=file_rel))
                    edges.append(Edge(from_id=proj_id, to_id=fid, type="contains"))

                    content = read_safe(swift_file)

                    # Types (class/struct/enum/protocol/actor)
                    for m in _CLASS_PATTERN.finditer(content):
                        kind, name = m.group(1), m.group(2)
                        tid = f"swift_{kind}_{fid}_{name}"
                        if tid not in seen:
                            seen.add(tid)
                            nodes.append(Node(id=tid, type=f"swift_{kind}", name=name, file_path=file_rel))
                            edges.append(Edge(from_id=fid, to_id=tid, type="defines"))

                    # Vapor routes
                    for m in _VAPOR_ROUTE.finditer(content):
                        method, path = m.group(1).upper(), m.group(2)
                        rid = f"route_{method}_{path.replace('/', '_').strip('_')}"
                        if rid not in seen:
                            seen.add(rid)
                            nodes.append(Node(id=rid, type="route", name=f"{method} {path}", file_path=file_rel))
                            edges.append(Edge(from_id=rid, to_id=fid, type="handled_by"))

        return AnalysisResult(
            nodes=nodes, edges=edges,
            state_sections=self._state(nodes),
        )

    def _state(self, nodes: list[Node]) -> dict[str, str]:
        files = [n for n in nodes if n.type == "swift_file"]
        types = [n for n in nodes if n.type.startswith("swift_") and n.type != "swift_file" and n.type != "swift_project"]
        if not files:
            return {}
        return {"Swift": f"{len(files)} files, {len(types)} types\n"}

    # -- File-level analysis -----------------------------------------------

    def supported_extensions(self) -> set[str]:
        return {".swift"}

    def analyze_file(self, file_path: Path) -> dict | None:
        if not file_path.is_file() or file_path.suffix != ".swift":
            return None
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        total = len(lines)

        functions = []
        for m in _FUNC_PATTERN.finditer(content):
            line_num = content[:m.start()].count("\n") + 1
            functions.append({"name": m.group(1), "line": line_num})

        for i, fn in enumerate(functions):
            fn["end"] = functions[i + 1]["line"] - 1 if i + 1 < len(functions) else total
            fn["lines"] = fn["end"] - fn["line"] + 1

        functions.sort(key=lambda f: f["lines"], reverse=True)
        types = _CLASS_PATTERN.findall(content)

        return {
            "type": "swift", "file": file_path.name, "total_lines": total,
            "function_count": len(functions), "functions": functions,
            "type_count": len(types),
        }

    def format_bloat_report(self, analysis: dict) -> str | None:
        if analysis.get("type") != "swift":
            return None
        lines = [
            f"Bloat report: {analysis['file']} ({analysis['total_lines']} lines, "
            f"{analysis['function_count']} functions, {analysis['type_count']} types)\n",
            "Functions (largest first):",
        ]
        for fn in analysis["functions"][:15]:
            bar = "█" * (fn["lines"] // 5)
            lines.append(f"  {fn['lines']:>4} lines  {bar:30s}  {fn['name']} (L{fn['line']}-{fn['end']})")
        return "\n".join(lines)
