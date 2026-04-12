"""
C/C++ analyzer.

Detects C/C++ projects via CMakeLists.txt, Makefile, meson.build, or .vcxproj.
Scans for structs, classes, functions, typedefs, and header includes.
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
    scan_project_dirs,
)

# C/C++ patterns
_FUNC_PATTERN = re.compile(
    r"^(?:static\s+|inline\s+|extern\s+|virtual\s+)*"
    r"(?:const\s+)?[\w:*&<>\s]+[\s*&]\s*(\w+)\s*\([^;]*\)\s*\{",
    re.MULTILINE,
)
_CLASS_PATTERN = re.compile(
    r"^(?:class|struct)\s+(?:__attribute__\([^)]*\)\s+)?(\w+)\s*"
    r"(?:final\s*)?(?::\s*(?:public|private|protected)\s+\w+(?:::\w+)*\s*)?[{]",
    re.MULTILINE,
)
_STRUCT_PATTERN = re.compile(
    r"^(?:typedef\s+)?struct\s+(\w+)", re.MULTILINE
)
_TYPEDEF_PATTERN = re.compile(
    r"^typedef\s+[\w\s*]+\s+(\w+)\s*;", re.MULTILINE
)
_ENUM_PATTERN = re.compile(
    r"^(?:typedef\s+)?enum\s+(?:class\s+)?(\w+)", re.MULTILINE
)
_INCLUDE_LOCAL = re.compile(r'^#include\s+"([^"]+)"', re.MULTILINE)
_NAMESPACE_PATTERN = re.compile(r"^namespace\s+(\w+)", re.MULTILINE)

_BUILD_MARKERS = {"CMakeLists.txt", "Makefile", "makefile", "meson.build"}
_EXTENSIONS = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}
_SOURCE_EXTENSIONS = {".c", ".cc", ".cpp", ".cxx"}


def _find_c_roots(repo_root: Path) -> list[Path]:
    roots = []
    for d in scan_project_dirs(repo_root):
        if any((d / m).exists() for m in _BUILD_MARKERS):
            roots.append(d)
        elif any(d.glob("*.vcxproj")):
            roots.append(d)
    # Fallback: if repo root has src/ with C/C++ files and no marker was found
    if not roots:
        src = repo_root / "src"
        if src.is_dir() and any(src.rglob("*.c")) or any(src.rglob("*.h")):
            roots.append(repo_root)
    return roots


class CppAnalyzer(LanguageAnalyzer):

    @staticmethod
    def detect(repo_root: Path) -> bool:
        return bool(_find_c_roots(repo_root))

    def scan(self) -> AnalysisResult:
        nodes: list[Node] = []
        edges: list[Edge] = []
        seen: set[str] = set()

        for project_root in _find_c_roots(self.repo_root):
            proj_name = project_root.name
            proj_id = f"cpp_proj_{proj_name.replace('-', '_').replace('.', '_')}"
            if proj_id not in seen:
                seen.add(proj_id)
                marker = next(
                    (m for m in _BUILD_MARKERS if (project_root / m).exists()),
                    "",
                )
                fp = (
                    rel_path(self.repo_root, project_root / marker)
                    if marker
                    else rel_path(self.repo_root, project_root)
                )
                nodes.append(Node(id=proj_id, type="cpp_project", name=proj_name, file_path=fp))

            src_dirs = [
                project_root / "src",
                project_root / "lib",
                project_root / "include",
                project_root,
            ]
            for src_dir in src_dirs:
                if not src_dir.exists():
                    continue
                for src_file in sorted(src_dir.rglob("*")):
                    if src_file.suffix not in _EXTENSIONS:
                        continue
                    file_rel = rel_path(self.repo_root, src_file)
                    if "/build/" in file_rel or "/cmake-build" in file_rel:
                        continue
                    if "/test/" in file_rel.lower() or "/tests/" in file_rel.lower():
                        continue
                    if "/third_party/" in file_rel or "/vendor/" in file_rel:
                        continue
                    fid = f"cpp_file_{file_rel.replace('/', '_').replace('.', '_')}"
                    if fid in seen:
                        continue
                    seen.add(fid)

                    is_header = src_file.suffix in {".h", ".hh", ".hpp", ".hxx"}
                    ftype = "cpp_header" if is_header else "cpp_source"
                    nodes.append(Node(id=fid, type=ftype, name=src_file.name, file_path=file_rel))
                    edges.append(Edge(from_id=proj_id, to_id=fid, type="contains"))

                    content = read_safe(src_file)

                    # Namespaces
                    for m in _NAMESPACE_PATTERN.finditer(content):
                        ns_name = m.group(1)
                        ns_id = f"cpp_ns_{proj_id}_{ns_name}"
                        if ns_id not in seen:
                            seen.add(ns_id)
                            nodes.append(Node(id=ns_id, type="cpp_namespace", name=ns_name, file_path=file_rel))
                            edges.append(Edge(from_id=proj_id, to_id=ns_id, type="defines"))

                    # Classes (C++)
                    for m in _CLASS_PATTERN.finditer(content):
                        cls_name = m.group(1)
                        cid = f"cpp_class_{fid}_{cls_name}"
                        if cid not in seen:
                            seen.add(cid)
                            nodes.append(Node(id=cid, type="cpp_class", name=cls_name, file_path=file_rel))
                            edges.append(Edge(from_id=fid, to_id=cid, type="defines"))

                    # Structs (C-style)
                    for m in _STRUCT_PATTERN.finditer(content):
                        s_name = m.group(1)
                        sid = f"cpp_struct_{fid}_{s_name}"
                        if sid not in seen:
                            seen.add(sid)
                            nodes.append(Node(id=sid, type="cpp_struct", name=s_name, file_path=file_rel))
                            edges.append(Edge(from_id=fid, to_id=sid, type="defines"))

                    # Enums
                    for m in _ENUM_PATTERN.finditer(content):
                        e_name = m.group(1)
                        eid = f"cpp_enum_{fid}_{e_name}"
                        if eid not in seen:
                            seen.add(eid)
                            nodes.append(Node(id=eid, type="cpp_enum", name=e_name, file_path=file_rel))
                            edges.append(Edge(from_id=fid, to_id=eid, type="defines"))

                    # Local includes → edges
                    for m in _INCLUDE_LOCAL.finditer(content):
                        inc_path = m.group(1)
                        inc_slug = inc_path.replace("/", "_").replace(".", "_")
                        # Try to find the target file node
                        target_id = f"cpp_file_{inc_slug}"
                        # Best-effort: connect if target was already seen
                        for nid in seen:
                            if nid.endswith(inc_slug):
                                edge_key = f"{fid}->>{nid}"
                                if edge_key not in seen:
                                    seen.add(edge_key)
                                    edges.append(Edge(from_id=fid, to_id=nid, type="includes"))
                                break

        return AnalysisResult(
            nodes=nodes, edges=edges,
            state_sections=self._state(nodes),
        )

    def _state(self, nodes: list[Node]) -> dict[str, str]:
        sources = [n for n in nodes if n.type == "cpp_source"]
        headers = [n for n in nodes if n.type == "cpp_header"]
        classes = [n for n in nodes if n.type in ("cpp_class", "cpp_struct")]
        if not sources and not headers:
            return {}
        return {
            "C/C++": f"{len(sources)} sources, {len(headers)} headers, {len(classes)} types\n"
        }

    # -- File-level analysis -----------------------------------------------

    def supported_extensions(self) -> set[str]:
        return _EXTENSIONS

    def analyze_file(self, file_path: Path) -> dict | None:
        if not file_path.is_file() or file_path.suffix not in _EXTENSIONS:
            return None
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        total = len(lines)

        functions = []
        for m in _FUNC_PATTERN.finditer(content):
            fn_name = m.group(1)
            # Filter false positives
            if fn_name in ("if", "for", "while", "switch", "return", "sizeof", "typeof", "catch"):
                continue
            line_num = content[: m.start()].count("\n") + 1
            functions.append({"name": fn_name, "line": line_num})

        for i, fn in enumerate(functions):
            fn["end"] = functions[i + 1]["line"] - 1 if i + 1 < len(functions) else total
            fn["lines"] = fn["end"] - fn["line"] + 1

        functions.sort(key=lambda f: f["lines"], reverse=True)
        classes = _CLASS_PATTERN.findall(content)
        structs = _STRUCT_PATTERN.findall(content)

        return {
            "type": "c_cpp",
            "file": file_path.name,
            "total_lines": total,
            "function_count": len(functions),
            "functions": functions,
            "class_count": len(classes),
            "struct_count": len(structs),
        }

    def format_bloat_report(self, analysis: dict) -> str | None:
        if analysis.get("type") != "c_cpp":
            return None
        lines = [
            f"Bloat report: {analysis['file']} ({analysis['total_lines']} lines, "
            f"{analysis['function_count']} functions, {analysis['class_count']} classes, "
            f"{analysis['struct_count']} structs)\n",
            "Functions (largest first):",
        ]
        for fn in analysis["functions"][:15]:
            bar = "\u2588" * (fn["lines"] // 5)
            lines.append(
                f"  {fn['lines']:>4} lines  {bar:30s}  {fn['name']} (L{fn['line']}-{fn['end']})"
            )
        return "\n".join(lines)
