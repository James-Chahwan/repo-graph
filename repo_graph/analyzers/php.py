"""
PHP analyzer.

Detects PHP projects via composer.json.
Scans for classes, interfaces, functions, and Laravel/Symfony routes.
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
    r"^(?:abstract\s+|final\s+)?class\s+(\w+)", re.MULTILINE
)
_INTERFACE_PATTERN = re.compile(r"^interface\s+(\w+)", re.MULTILINE)
_FUNCTION_PATTERN = re.compile(
    r"^\s*(?:public|private|protected|static)\s+(?:static\s+)?function\s+(\w+)",
    re.MULTILINE,
)
_NAMESPACE_PATTERN = re.compile(r"^namespace\s+([\w\\]+);", re.MULTILINE)
_USE_PATTERN = re.compile(r"^use\s+([\w\\]+)", re.MULTILINE)

# Laravel routes: Route::get('/path', ...)
_LARAVEL_ROUTE = re.compile(
    r"Route::(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)
# Symfony route annotations: #[Route('/path', methods: ['GET'])]
_SYMFONY_ROUTE = re.compile(
    r"#\[Route\(\s*['\"]([^'\"]+)['\"]", re.MULTILINE
)


def _find_php_roots(index) -> list[Path]:
    roots = index.dirs_with_file("composer.json")
    # Fallback: if no composer.json but repo has .php files at root
    if not roots:
        root = index.repo_root
        if any(f.parent == root for f in index.files_with_ext(".php")):
            roots = [root]
    return sorted(set(roots) | set(index.extra_roots("php")))


class PhpAnalyzer(LanguageAnalyzer):

    @staticmethod
    def detect(index) -> bool:
        return bool(_find_php_roots(index))

    def scan(self) -> AnalysisResult:
        nodes: list[Node] = []
        edges: list[Edge] = []
        seen: set[str] = set()

        for project_root in _find_php_roots(self.index):
            proj_name = project_root.name
            proj_id = f"php_proj_{proj_name.replace('-', '_')}"
            if proj_id not in seen:
                seen.add(proj_id)
                nodes.append(Node(
                    id=proj_id, type="php_project", name=proj_name,
                    file_path=rel_path(self.repo_root, project_root / "composer.json"),
                ))

            src_dirs = [project_root / "src", project_root / "app", project_root]
            for src_dir in src_dirs:
                if not src_dir.exists():
                    continue
                for php_file in self.index.files_with_ext(".php", under=src_dir):
                    file_rel = rel_path(self.repo_root, php_file)
                    if "/vendor/" in file_rel or "/tests/" in file_rel:
                        continue
                    if "/test/" in file_rel or "/cache/" in file_rel:
                        continue
                    content = read_safe(php_file)

                    # Namespace
                    ns_match = _NAMESPACE_PATTERN.search(content)
                    ns_name = ns_match.group(1) if ns_match else "global"
                    ns_id = f"php_ns_{ns_name.replace(chr(92), '_')}"
                    if ns_id not in seen:
                        seen.add(ns_id)
                        nodes.append(Node(id=ns_id, type="php_namespace", name=ns_name, file_path=file_rel))
                        edges.append(Edge(from_id=proj_id, to_id=ns_id, type="contains"))

                    # Classes
                    for m in _CLASS_PATTERN.finditer(content):
                        cid = f"php_class_{ns_id}_{m.group(1)}"
                        if cid not in seen:
                            seen.add(cid)
                            nodes.append(Node(id=cid, type="php_class", name=m.group(1), file_path=file_rel))
                            edges.append(Edge(from_id=ns_id, to_id=cid, type="defines"))

                    # Interfaces
                    for m in _INTERFACE_PATTERN.finditer(content):
                        iid = f"php_iface_{ns_id}_{m.group(1)}"
                        if iid not in seen:
                            seen.add(iid)
                            nodes.append(Node(id=iid, type="php_interface", name=m.group(1), file_path=file_rel))
                            edges.append(Edge(from_id=ns_id, to_id=iid, type="defines"))

            # Laravel routes
            routes_dir = project_root / "routes"
            if routes_dir.exists():
                routes_files = [
                    f for f in self.index.files_with_ext(".php", under=routes_dir)
                    if f.parent == routes_dir
                ]
                for rf in routes_files:
                    content = read_safe(rf)
                    file_rel = rel_path(self.repo_root, rf)
                    for m in _LARAVEL_ROUTE.finditer(content):
                        method, path = m.group(1).upper(), m.group(2)
                        rid = f"route_{method}_{path.replace('/', '_').strip('_')}"
                        if rid not in seen:
                            seen.add(rid)
                            nodes.append(Node(id=rid, type="route", name=f"{method} {path}", file_path=file_rel))
                            edges.append(Edge(from_id=rid, to_id=proj_id, type="handled_by"))

        return AnalysisResult(
            nodes=nodes, edges=edges,
            state_sections=self._state(nodes),
        )

    def _state(self, nodes: list[Node]) -> dict[str, str]:
        ns = [n for n in nodes if n.type == "php_namespace"]
        classes = [n for n in nodes if n.type == "php_class"]
        if not ns:
            return {}
        return {"PHP": f"{len(ns)} namespaces, {len(classes)} classes\n"}

    # -- File-level analysis -----------------------------------------------

    def supported_extensions(self) -> set[str]:
        return {".php"}

    def analyze_file(self, file_path: Path) -> dict | None:
        if not file_path.is_file() or file_path.suffix != ".php":
            return None
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        total = len(lines)

        methods = []
        for m in _FUNCTION_PATTERN.finditer(content):
            name = m.group(1)
            line_num = content[:m.start()].count("\n") + 1
            methods.append({"name": name, "line": line_num})

        for i, method in enumerate(methods):
            method["end"] = methods[i + 1]["line"] - 1 if i + 1 < len(methods) else total
            method["lines"] = method["end"] - method["line"] + 1

        methods.sort(key=lambda m: m["lines"], reverse=True)
        classes = _CLASS_PATTERN.findall(content)

        return {
            "type": "php", "file": file_path.name, "total_lines": total,
            "method_count": len(methods), "methods": methods,
            "class_count": len(classes),
        }

    def format_bloat_report(self, analysis: dict) -> str | None:
        if analysis.get("type") != "php":
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
