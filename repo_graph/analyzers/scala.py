"""
Scala analyzer.

Detects via build.sbt, build.mill, or build.gradle(.kts) containing Scala deps.
Scans for packages, objects, classes, traits, and routes from
Play, Akka HTTP, and http4s.
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

_TYPE_PATTERN = re.compile(
    r"^\s*(?:(?:private|protected|final|sealed|abstract|implicit|case)\s+)*"
    r"(object|class|trait)\s+(\w+)",
    re.MULTILINE,
)
_DEF_PATTERN = re.compile(
    r"^\s+(?:(?:private|protected|final|override|implicit|lazy)\s+)*"
    r"def\s+(\w+)\s*[\[\(:]",
    re.MULTILINE,
)
_PACKAGE_PATTERN = re.compile(r"^package\s+([\w.]+)", re.MULTILINE)

# Play Framework routes file (conf/routes): "GET  /path  controllers.Foo.bar"
_PLAY_ROUTE = re.compile(
    r"^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(\S+)\s+(\S+)",
    re.MULTILINE,
)
# Akka HTTP DSL: path("foo" / "bar") { get { ... } }
_AKKA_PATH = re.compile(r'\bpath\s*\(\s*"([^"]+)"', re.MULTILINE)
_AKKA_METHOD = re.compile(r"\b(get|post|put|delete|patch)\s*\{")
# http4s: case GET -> Root / "foo" / "bar"
_HTTP4S_ROUTE = re.compile(
    r'case\s+(GET|POST|PUT|DELETE|PATCH)\s*->\s*(?:Root)?\s*((?:/\s*"[^"]+"\s*)+)',
    re.MULTILINE,
)

_SCALA_MARKERS = ["build.sbt", "build.mill", "build.gradle", "build.gradle.kts"]
_SKIP_DIRS = {"target", "project/target", ".bloop", ".metals", ".bsp"}


def _find_scala_roots(index) -> list[Path]:
    roots: list[Path] = []
    for d in index.dirs_with_any(_SCALA_MARKERS):
        # Only count Gradle projects if they actually contain .scala files
        if (d / "build.sbt").exists() or (d / "build.mill").exists():
            roots.append(d)
            continue
        if index.files_with_ext(".scala", under=d):
            roots.append(d)
    return sorted(set(roots) | set(index.extra_roots("scala")))


class ScalaAnalyzer(LanguageAnalyzer):

    @staticmethod
    def detect(index) -> bool:
        return bool(_find_scala_roots(index))

    def scan(self) -> AnalysisResult:
        nodes: list[Node] = []
        edges: list[Edge] = []
        seen: set[str] = set()

        for project_root in _find_scala_roots(self.index):
            proj_name = project_root.name
            proj_id = f"scala_proj_{proj_name.replace('-', '_').replace('.', '_')}"
            if proj_id not in seen:
                seen.add(proj_id)
                marker = next(
                    (m for m in _SCALA_MARKERS if (project_root / m).exists()),
                    "build.sbt",
                )
                nodes.append(Node(
                    id=proj_id, type="scala_project", name=proj_name,
                    file_path=rel_path(self.repo_root, project_root / marker),
                ))

            for src_root in self._find_src_roots(project_root):
                for scala_file in self.index.files_with_ext(".scala", under=src_root):
                    self._scan_file(scala_file, proj_id, nodes, edges, seen)

            # Play routes file
            routes_file = project_root / "conf" / "routes"
            if routes_file.exists():
                self._scan_play_routes(routes_file, proj_id, nodes, edges, seen)

        return AnalysisResult(
            nodes=nodes, edges=edges,
            state_sections=self._state(nodes),
        )

    def _find_src_roots(self, project_root: Path) -> list[Path]:
        candidates = [
            project_root / "src" / "main" / "scala",
            project_root / "src",
            project_root / "app",
        ]
        roots = [c for c in candidates if c.exists()]
        return roots if roots else [project_root]

    def _should_skip(self, file_rel: str) -> bool:
        return any(skip in file_rel for skip in _SKIP_DIRS) or "/test/" in file_rel

    def _scan_file(
        self, scala_file: Path, proj_id: str,
        nodes: list[Node], edges: list[Edge], seen: set[str],
    ) -> None:
        file_rel = rel_path(self.repo_root, scala_file)
        if self._should_skip(file_rel):
            return
        content = read_safe(scala_file)

        pkg_match = _PACKAGE_PATTERN.search(content)
        pkg_name = pkg_match.group(1) if pkg_match else "default"
        pkg_id = f"scala_pkg_{pkg_name.replace('.', '_')}"
        if pkg_id not in seen:
            seen.add(pkg_id)
            nodes.append(Node(
                id=pkg_id, type="scala_package", name=pkg_name, file_path=file_rel,
            ))
            edges.append(Edge(from_id=proj_id, to_id=pkg_id, type="contains"))

        for m in _TYPE_PATTERN.finditer(content):
            kind, name = m.group(1), m.group(2)
            tid = f"scala_{kind}_{pkg_id}_{name}"
            if tid not in seen:
                seen.add(tid)
                nodes.append(Node(
                    id=tid, type=f"scala_{kind}", name=name, file_path=file_rel,
                ))
                edges.append(Edge(from_id=pkg_id, to_id=tid, type="defines"))

        # Akka HTTP routes
        for m in _AKKA_PATH.finditer(content):
            path = m.group(1)
            nearby = content[m.end():m.end() + 200]
            method_match = _AKKA_METHOD.search(nearby)
            method = method_match.group(1).upper() if method_match else "ANY"
            self._add_route(method, "/" + path, file_rel, pkg_id, nodes, edges, seen)

        # http4s routes
        for m in _HTTP4S_ROUTE.finditer(content):
            method = m.group(1)
            segments = re.findall(r'"([^"]+)"', m.group(2))
            path = "/" + "/".join(segments)
            self._add_route(method, path, file_rel, pkg_id, nodes, edges, seen)

    def _scan_play_routes(
        self, routes_file: Path, proj_id: str,
        nodes: list[Node], edges: list[Edge], seen: set[str],
    ) -> None:
        file_rel = rel_path(self.repo_root, routes_file)
        content = read_safe(routes_file)
        for m in _PLAY_ROUTE.finditer(content):
            method, path, handler = m.group(1), m.group(2), m.group(3)
            # Handler like "controllers.UserController.show(id: Long)"
            handler_clean = handler.split("(")[0]
            parts = handler_clean.rsplit(".", 1)
            pkg_name = parts[0] if len(parts) == 2 else "default"
            pkg_id = f"scala_pkg_{pkg_name.replace('.', '_')}"
            if pkg_id not in seen:
                seen.add(pkg_id)
                nodes.append(Node(
                    id=pkg_id, type="scala_package", name=pkg_name,
                    file_path=file_rel,
                ))
                edges.append(Edge(from_id=proj_id, to_id=pkg_id, type="contains"))
            self._add_route(method, path, file_rel, pkg_id, nodes, edges, seen)

    def _add_route(
        self, method: str, path: str, file_rel: str, pkg_id: str,
        nodes: list[Node], edges: list[Edge], seen: set[str],
    ) -> None:
        rid = f"route_{method}_{path.replace('/', '_').strip('_') or 'root'}"
        if rid not in seen:
            seen.add(rid)
            nodes.append(Node(
                id=rid, type="route", name=f"{method} {path}", file_path=file_rel,
            ))
            edges.append(Edge(from_id=rid, to_id=pkg_id, type="handled_by"))

    def _state(self, nodes: list[Node]) -> dict[str, str]:
        pkgs = [n for n in nodes if n.type == "scala_package"]
        types = [n for n in nodes if n.type in ("scala_object", "scala_class", "scala_trait")]
        routes = [n for n in nodes if n.type == "route" and n.file_path.endswith(".scala") or
                  (n.type == "route" and "conf/routes" in n.file_path)]
        if not pkgs:
            return {}
        parts = [f"{len(pkgs)} packages", f"{len(types)} types"]
        return {"Scala": ", ".join(parts) + "\n"}

    # -- File-level analysis -----------------------------------------------

    def supported_extensions(self) -> set[str]:
        return {".scala", ".sc"}

    def analyze_file(self, file_path: Path) -> dict | None:
        if not file_path.is_file() or file_path.suffix not in (".scala", ".sc"):
            return None
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        total = len(lines)

        defs = []
        for m in _DEF_PATTERN.finditer(content):
            name = m.group(1)
            line_num = content[:m.start()].count("\n") + 1
            defs.append({"name": name, "line": line_num})
        for i, d in enumerate(defs):
            d["end"] = defs[i + 1]["line"] - 1 if i + 1 < len(defs) else total
            d["lines"] = d["end"] - d["line"] + 1
        defs.sort(key=lambda d: d["lines"], reverse=True)

        types = _TYPE_PATTERN.findall(content)
        return {
            "type": "scala", "file": file_path.name, "total_lines": total,
            "def_count": len(defs), "defs": defs,
            "type_count": len(types),
        }

    def format_bloat_report(self, analysis: dict) -> str | None:
        if analysis.get("type") != "scala":
            return None
        lines = [
            f"Bloat report: {analysis['file']} ({analysis['total_lines']} lines, "
            f"{analysis['def_count']} defs, {analysis['type_count']} types)\n",
            "Defs (largest first):",
        ]
        for d in analysis["defs"][:15]:
            bar = "\u2588" * (d["lines"] // 5)
            lines.append(f"  {d['lines']:>4} lines  {bar:30s}  {d['name']} (L{d['line']}-{d['end']})")
        return "\n".join(lines)
