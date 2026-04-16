"""
Java/Kotlin analyzer.

Detects via pom.xml, build.gradle, or build.gradle.kts.
Scans for packages, classes, interfaces, methods, and Spring/JAX-RS routes.
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
    r"^(?:public\s+|private\s+|protected\s+)?(?:abstract\s+|final\s+)?"
    r"(?:class|interface|enum|record)\s+(\w+)",
    re.MULTILINE,
)
_METHOD_PATTERN = re.compile(
    r"^\s+(?:public|private|protected)\s+(?:static\s+)?(?:abstract\s+)?"
    r"(?:[\w<>\[\],\s]+)\s+(\w+)\s*\(",
    re.MULTILINE,
)
# Spring @RequestMapping / @GetMapping / etc.
_SPRING_ROUTE = re.compile(
    r'@(?:Get|Post|Put|Delete|Patch|Request)Mapping\(\s*(?:value\s*=\s*)?'
    r'["\']([^"\']+)["\']',
    re.MULTILINE,
)
# JAX-RS @Path + @GET/@POST etc.
_JAXRS_PATH = re.compile(r'@Path\(\s*["\']([^"\']+)["\']\)', re.MULTILINE)
_JAXRS_METHOD = re.compile(r'@(GET|POST|PUT|DELETE|PATCH)\b')

_IMPORT_PATTERN = re.compile(r"^import\s+([\w.]+);", re.MULTILINE)

_JAVA_MARKERS = ["pom.xml", "build.gradle", "build.gradle.kts"]


class JavaAnalyzer(LanguageAnalyzer):

    @staticmethod
    def detect(index) -> bool:
        return bool(index.roots_for("java", _JAVA_MARKERS))

    def scan(self) -> AnalysisResult:
        nodes: list[Node] = []
        edges: list[Edge] = []
        seen: set[str] = set()

        for project_root in self.index.roots_for("java", _JAVA_MARKERS):
            project_name = project_root.name
            proj_id = f"java_proj_{project_name.replace('-', '_')}"
            if proj_id not in seen:
                seen.add(proj_id)
                marker = next((m for m in _JAVA_MARKERS if (project_root / m).exists()), "")
                marker_path = (
                    project_root / marker if marker else project_root
                )
                nodes.append(Node(
                    id=proj_id, type="java_project", name=project_name,
                    file_path=rel_path(self.repo_root, marker_path),
                ))

            # Find source roots
            for src_root in self._find_src_roots(project_root):
                for java_file in self.index.files_with_ext(".java", under=src_root):
                    self._scan_file(java_file, proj_id, nodes, edges, seen)
                for kt_file in self.index.files_with_ext(".kt", under=src_root):
                    self._scan_file(kt_file, proj_id, nodes, edges, seen)

        return AnalysisResult(
            nodes=nodes, edges=edges,
            state_sections=self._state(nodes),
        )

    def _find_src_roots(self, project_root: Path) -> list[Path]:
        candidates = [
            project_root / "src" / "main" / "java",
            project_root / "src" / "main" / "kotlin",
            project_root / "src",
            project_root / "app" / "src" / "main" / "java",
            project_root / "app" / "src" / "main" / "kotlin",
        ]
        return [c for c in candidates if c.exists()]

    def _scan_file(
        self, java_file: Path, proj_id: str,
        nodes: list[Node], edges: list[Edge], seen: set[str],
    ) -> None:
        file_rel = rel_path(self.repo_root, java_file)
        if "test" in file_rel.lower() and "/test/" in file_rel:
            return
        content = read_safe(java_file)

        # Package → node
        pkg_match = re.search(r"^package\s+([\w.]+)", content, re.MULTILINE)
        pkg_name = pkg_match.group(1) if pkg_match else "default"
        pkg_id = f"java_pkg_{pkg_name.replace('.', '_')}"
        if pkg_id not in seen:
            seen.add(pkg_id)
            nodes.append(Node(id=pkg_id, type="java_package", name=pkg_name, file_path=file_rel))
            edges.append(Edge(from_id=proj_id, to_id=pkg_id, type="contains"))

        # Classes/interfaces
        for m in _CLASS_PATTERN.finditer(content):
            class_name = m.group(1)
            cid = f"java_class_{pkg_id}_{class_name}"
            if cid not in seen:
                seen.add(cid)
                nodes.append(Node(id=cid, type="java_class", name=class_name, file_path=file_rel))
                edges.append(Edge(from_id=pkg_id, to_id=cid, type="defines"))

        # Spring routes
        for m in _SPRING_ROUTE.finditer(content):
            path = m.group(1)
            # Determine method from annotation name
            anno_start = content[:m.start()].rfind("@")
            anno_text = content[anno_start:m.start() + 5] if anno_start >= 0 else ""
            method = "ANY"
            for verb in ["Get", "Post", "Put", "Delete", "Patch"]:
                if verb in anno_text:
                    method = verb.upper()
                    break
            rid = f"route_{method}_{path.replace('/', '_').strip('_')}"
            if rid not in seen:
                seen.add(rid)
                nodes.append(Node(id=rid, type="route", name=f"{method} {path}", file_path=file_rel))
                edges.append(Edge(from_id=rid, to_id=pkg_id, type="handled_by"))

        # JAX-RS routes
        for m in _JAXRS_PATH.finditer(content):
            path = m.group(1)
            # Find nearby HTTP method annotation
            nearby = content[max(0, m.start() - 100):m.end() + 200]
            method_match = _JAXRS_METHOD.search(nearby)
            method = method_match.group(1) if method_match else "ANY"
            rid = f"route_{method}_{path.replace('/', '_').strip('_')}"
            if rid not in seen:
                seen.add(rid)
                nodes.append(Node(id=rid, type="route", name=f"{method} {path}", file_path=file_rel))
                edges.append(Edge(from_id=rid, to_id=pkg_id, type="handled_by"))

    def _state(self, nodes: list[Node]) -> dict[str, str]:
        pkgs = [n for n in nodes if n.type == "java_package"]
        classes = [n for n in nodes if n.type == "java_class"]
        if not pkgs:
            return {}
        return {"Java/Kotlin": f"{len(pkgs)} packages, {len(classes)} classes\n"}

    # -- File-level analysis -----------------------------------------------

    def supported_extensions(self) -> set[str]:
        return {".java", ".kt"}

    def analyze_file(self, file_path: Path) -> dict | None:
        if not file_path.is_file() or file_path.suffix not in (".java", ".kt"):
            return None
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        total = len(lines)

        methods = []
        for m in _METHOD_PATTERN.finditer(content):
            name = m.group(1)
            if name in ("if", "for", "while", "switch", "catch", "return"):
                continue
            line_num = content[:m.start()].count("\n") + 1
            methods.append({"name": name, "line": line_num})

        for i, method in enumerate(methods):
            method["end"] = methods[i + 1]["line"] - 1 if i + 1 < len(methods) else total
            method["lines"] = method["end"] - method["line"] + 1

        methods.sort(key=lambda m: m["lines"], reverse=True)
        classes = _CLASS_PATTERN.findall(content)

        return {
            "type": "java", "file": file_path.name, "total_lines": total,
            "method_count": len(methods), "methods": methods,
            "class_count": len(classes),
        }

    def format_bloat_report(self, analysis: dict) -> str | None:
        if analysis.get("type") != "java":
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
