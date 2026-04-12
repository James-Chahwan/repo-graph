"""
Ruby analyzer.

Detects Ruby projects via Gemfile or .gemspec.
Scans for modules, classes, methods, and Rails routes.
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

_CLASS_PATTERN = re.compile(r"^\s*class\s+(\w+)", re.MULTILINE)
_MODULE_PATTERN = re.compile(r"^\s*module\s+(\w+)", re.MULTILINE)
_DEF_PATTERN = re.compile(r"^\s*def\s+(\w+)", re.MULTILINE)
_REQUIRE_PATTERN = re.compile(r"^require(?:_relative)?\s+['\"]([^'\"]+)['\"]", re.MULTILINE)

# Rails routes: get '/path', post '/path', etc.
_RAILS_ROUTE = re.compile(
    r"^\s*(get|post|put|patch|delete)\s+['\"]([^'\"]+)['\"]", re.MULTILINE
)
# Rails resources :name
_RAILS_RESOURCE = re.compile(r"^\s*resources?\s+:(\w+)", re.MULTILINE)


def _find_ruby_roots(repo_root: Path) -> list[Path]:
    return [d for d in scan_project_dirs(repo_root)
            if (d / "Gemfile").exists() or any(d.glob("*.gemspec"))]


class RubyAnalyzer(LanguageAnalyzer):

    @staticmethod
    def detect(repo_root: Path) -> bool:
        return bool(_find_ruby_roots(repo_root))

    def scan(self) -> AnalysisResult:
        nodes: list[Node] = []
        edges: list[Edge] = []
        seen: set[str] = set()

        for project_root in _find_ruby_roots(self.repo_root):
            proj_name = project_root.name
            proj_id = f"rb_proj_{proj_name.replace('-', '_')}"
            if proj_id not in seen:
                seen.add(proj_id)
                nodes.append(Node(
                    id=proj_id, type="rb_project", name=proj_name,
                    file_path=rel_path(self.repo_root, project_root / "Gemfile"),
                ))

            # Scan app/ and lib/ (Rails convention)
            src_dirs = [project_root / "app", project_root / "lib", project_root]
            for src_dir in src_dirs:
                if not src_dir.exists():
                    continue
                for rb_file in sorted(src_dir.rglob("*.rb")):
                    file_rel = rel_path(self.repo_root, rb_file)
                    if "/test/" in file_rel or "/spec/" in file_rel:
                        continue
                    if "/vendor/" in file_rel or "/tmp/" in file_rel:
                        continue
                    mod_id = f"rb_file_{file_rel.replace('/', '_').replace('.', '_')}"
                    if mod_id in seen:
                        continue
                    seen.add(mod_id)

                    nodes.append(Node(id=mod_id, type="rb_file", name=rb_file.stem, file_path=file_rel))
                    edges.append(Edge(from_id=proj_id, to_id=mod_id, type="contains"))

                    content = read_safe(rb_file)

                    # Classes
                    for m in _CLASS_PATTERN.finditer(content):
                        cid = f"rb_class_{mod_id}_{m.group(1)}"
                        if cid not in seen:
                            seen.add(cid)
                            nodes.append(Node(id=cid, type="rb_class", name=m.group(1), file_path=file_rel))
                            edges.append(Edge(from_id=mod_id, to_id=cid, type="defines"))

                    # Modules
                    for m in _MODULE_PATTERN.finditer(content):
                        mid = f"rb_module_{mod_id}_{m.group(1)}"
                        if mid not in seen:
                            seen.add(mid)
                            nodes.append(Node(id=mid, type="rb_module", name=m.group(1), file_path=file_rel))
                            edges.append(Edge(from_id=mod_id, to_id=mid, type="defines"))

            # Rails routes
            routes_file = project_root / "config" / "routes.rb"
            if routes_file.exists():
                content = read_safe(routes_file)
                file_rel = rel_path(self.repo_root, routes_file)
                for m in _RAILS_ROUTE.finditer(content):
                    method, path = m.group(1).upper(), m.group(2)
                    rid = f"route_{method}_{path.replace('/', '_').strip('_')}"
                    if rid not in seen:
                        seen.add(rid)
                        nodes.append(Node(id=rid, type="route", name=f"{method} {path}", file_path=file_rel))
                        edges.append(Edge(from_id=rid, to_id=proj_id, type="handled_by"))

                for m in _RAILS_RESOURCE.finditer(content):
                    resource = m.group(1)
                    rid = f"route_RESOURCE_{resource}"
                    if rid not in seen:
                        seen.add(rid)
                        nodes.append(Node(
                            id=rid, type="route", name=f"resources :{resource}",
                            file_path=file_rel,
                        ))
                        edges.append(Edge(from_id=rid, to_id=proj_id, type="handled_by"))

        return AnalysisResult(
            nodes=nodes, edges=edges,
            state_sections=self._state(nodes),
        )

    def _state(self, nodes: list[Node]) -> dict[str, str]:
        files = [n for n in nodes if n.type == "rb_file"]
        classes = [n for n in nodes if n.type == "rb_class"]
        if not files:
            return {}
        return {"Ruby": f"{len(files)} files, {len(classes)} classes\n"}

    # -- File-level analysis -----------------------------------------------

    def supported_extensions(self) -> set[str]:
        return {".rb"}

    def analyze_file(self, file_path: Path) -> dict | None:
        if not file_path.is_file() or file_path.suffix != ".rb":
            return None
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        total = len(lines)

        methods = []
        for m in _DEF_PATTERN.finditer(content):
            line_num = content[:m.start()].count("\n") + 1
            methods.append({"name": m.group(1), "line": line_num})

        for i, method in enumerate(methods):
            method["end"] = methods[i + 1]["line"] - 1 if i + 1 < len(methods) else total
            method["lines"] = method["end"] - method["line"] + 1

        methods.sort(key=lambda m: m["lines"], reverse=True)
        classes = _CLASS_PATTERN.findall(content)

        return {
            "type": "ruby", "file": file_path.name, "total_lines": total,
            "method_count": len(methods), "methods": methods,
            "class_count": len(classes),
        }

    def format_bloat_report(self, analysis: dict) -> str | None:
        if analysis.get("type") != "ruby":
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
