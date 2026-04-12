"""
C# analyzer.

Detects .NET projects via .csproj or .sln files.
Scans for namespaces, classes, interfaces, methods, and ASP.NET routes.
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

_CLASS_PATTERN = re.compile(
    r"^(?:\s*)(?:public|internal|private|protected)?\s*"
    r"(?:static\s+|abstract\s+|sealed\s+|partial\s+)*"
    r"(?:class|interface|struct|record|enum)\s+(\w+)",
    re.MULTILINE,
)
_METHOD_PATTERN = re.compile(
    r"^\s+(?:public|private|protected|internal)\s+(?:static\s+|virtual\s+|override\s+|async\s+)*"
    r"[\w<>\[\]?,\s]+\s+(\w+)\s*\(",
    re.MULTILINE,
)
_NAMESPACE_PATTERN = re.compile(r"^namespace\s+([\w.]+)", re.MULTILINE)
_USING_PATTERN = re.compile(r"^using\s+([\w.]+);", re.MULTILINE)

# ASP.NET attribute routes
_ASPNET_ROUTE = re.compile(
    r'\[Http(Get|Post|Put|Delete|Patch)\(\s*"([^"]*)"', re.MULTILINE,
)
# Minimal API routes: app.MapGet("/path", ...)
_MINIMAL_API = re.compile(
    r'\.Map(Get|Post|Put|Delete|Patch)\(\s*"([^"]+)"',
)


def _find_dotnet_roots(repo_root: Path) -> list[Path]:
    roots = []
    for d in scan_project_dirs(repo_root):
        if any(d.glob("*.csproj")) or any(d.glob("*.sln")) or any(d.glob("*.slnx")):
            roots.append(d)
    return roots


class CSharpAnalyzer(LanguageAnalyzer):

    @staticmethod
    def detect(repo_root: Path) -> bool:
        return bool(_find_dotnet_roots(repo_root))

    def scan(self) -> AnalysisResult:
        nodes: list[Node] = []
        edges: list[Edge] = []
        seen: set[str] = set()

        for project_root in _find_dotnet_roots(self.repo_root):
            proj_name = project_root.name
            proj_id = f"cs_proj_{proj_name.replace('-', '_').replace('.', '_')}"
            if proj_id not in seen:
                seen.add(proj_id)
                csproj = next(project_root.glob("*.csproj"), None)
                fp = rel_path(self.repo_root, csproj) if csproj else rel_path(self.repo_root, project_root)
                nodes.append(Node(id=proj_id, type="cs_project", name=proj_name, file_path=fp))

            for cs_file in sorted(project_root.rglob("*.cs")):
                file_rel = rel_path(self.repo_root, cs_file)
                if "/obj/" in file_rel or "/bin/" in file_rel:
                    continue
                if ".Test" in file_rel or "Tests/" in file_rel:
                    continue
                content = read_safe(cs_file)

                # Namespace
                ns_match = _NAMESPACE_PATTERN.search(content)
                ns_name = ns_match.group(1) if ns_match else "global"
                ns_id = f"cs_ns_{ns_name.replace('.', '_')}"
                if ns_id not in seen:
                    seen.add(ns_id)
                    nodes.append(Node(id=ns_id, type="cs_namespace", name=ns_name, file_path=file_rel))
                    edges.append(Edge(from_id=proj_id, to_id=ns_id, type="contains"))

                # Classes
                for m in _CLASS_PATTERN.finditer(content):
                    class_name = m.group(1)
                    cid = f"cs_class_{ns_id}_{class_name}"
                    if cid not in seen:
                        seen.add(cid)
                        nodes.append(Node(id=cid, type="cs_class", name=class_name, file_path=file_rel))
                        edges.append(Edge(from_id=ns_id, to_id=cid, type="defines"))

                # ASP.NET routes
                for m in _ASPNET_ROUTE.finditer(content):
                    method, path = m.group(1).upper(), m.group(2)
                    if not path:
                        path = "/"
                    rid = f"route_{method}_{path.replace('/', '_').strip('_') or 'root'}"
                    if rid not in seen:
                        seen.add(rid)
                        nodes.append(Node(id=rid, type="route", name=f"{method} {path}", file_path=file_rel))
                        edges.append(Edge(from_id=rid, to_id=ns_id, type="handled_by"))

                # Minimal API routes
                for m in _MINIMAL_API.finditer(content):
                    method, path = m.group(1).upper(), m.group(2)
                    rid = f"route_{method}_{path.replace('/', '_').strip('_')}"
                    if rid not in seen:
                        seen.add(rid)
                        nodes.append(Node(id=rid, type="route", name=f"{method} {path}", file_path=file_rel))
                        edges.append(Edge(from_id=rid, to_id=ns_id, type="handled_by"))

        return AnalysisResult(
            nodes=nodes, edges=edges,
            state_sections=self._state(nodes),
        )

    def _state(self, nodes: list[Node]) -> dict[str, str]:
        ns = [n for n in nodes if n.type == "cs_namespace"]
        classes = [n for n in nodes if n.type == "cs_class"]
        if not ns:
            return {}
        return {"C#/.NET": f"{len(ns)} namespaces, {len(classes)} classes\n"}

    # -- File-level analysis -----------------------------------------------

    def supported_extensions(self) -> set[str]:
        return {".cs"}

    def analyze_file(self, file_path: Path) -> dict | None:
        if not file_path.is_file() or file_path.suffix != ".cs":
            return None
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        total = len(lines)

        methods = []
        for m in _METHOD_PATTERN.finditer(content):
            name = m.group(1)
            if name in ("if", "for", "while", "switch", "catch", "return", "throw"):
                continue
            line_num = content[:m.start()].count("\n") + 1
            methods.append({"name": name, "line": line_num})

        for i, method in enumerate(methods):
            method["end"] = methods[i + 1]["line"] - 1 if i + 1 < len(methods) else total
            method["lines"] = method["end"] - method["line"] + 1

        methods.sort(key=lambda m: m["lines"], reverse=True)
        classes = _CLASS_PATTERN.findall(content)

        return {
            "type": "csharp", "file": file_path.name, "total_lines": total,
            "method_count": len(methods), "methods": methods,
            "class_count": len(classes),
        }

    def format_bloat_report(self, analysis: dict) -> str | None:
        if analysis.get("type") != "csharp":
            return None
        lines = [
            f"Bloat report: {analysis['file']} ({analysis['total_lines']} lines, "
            f"{analysis['method_count']} methods, {analysis['class_count']} classes)\n",
            "Methods (largest first):",
        ]
        for m in analysis["methods"][:15]:
            bar = "█" * (m["lines"] // 5)
            lines.append(f"  {m['lines']:>4} lines  {bar:30s}  {m['name']} (L{m['line']}-{m['end']})")
        return "\n".join(lines)
