"""
Clojure analyzer.

Detects via project.clj (Leiningen), deps.edn (tools.deps), or build.boot.
Scans for namespaces, defn, defprotocol, defrecord, and routes from
Compojure, Reitit, and Ring middleware.
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

_NS_PATTERN = re.compile(r"\(ns\s+([\w.\-]+)", re.MULTILINE)
_DEFN_PATTERN = re.compile(r"\(defn-?\s+(\S+)", re.MULTILINE)
_DEFPROTOCOL = re.compile(r"\(defprotocol\s+(\S+)", re.MULTILINE)
_DEFRECORD = re.compile(r"\(defrecord\s+(\S+)", re.MULTILINE)
_DEFMACRO = re.compile(r"\(defmacro\s+(\S+)", re.MULTILINE)
_REQUIRE = re.compile(r":require\s+\[([^\]]+)\]", re.MULTILINE)

# Compojure: (GET "/foo/:id" [id] handler) or (context "/api" [] ...)
_COMPOJURE = re.compile(
    r'\((GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS|ANY)\s+"([^"]+)"',
    re.MULTILINE,
)
# Reitit: ["/api/foo" {:get handler :post handler2}]
_REITIT = re.compile(
    r'\["([^"]+)"\s*\{(?:[^}]*?:(get|post|put|delete|patch))',
    re.MULTILINE | re.IGNORECASE,
)

_CLJ_MARKERS = {"project.clj", "deps.edn", "build.boot", "shadow-cljs.edn"}
_CLJ_SKIP = {"target", ".cpcache", ".shadow-cljs", ".lsp"}
_CLJ_EXTS = {".clj", ".cljc", ".cljs"}


def _find_clj_roots(index) -> list[Path]:
    marker_roots = index.dirs_with_any(_CLJ_MARKERS)
    if not marker_roots and index.files_with_ext(_CLJ_EXTS):
        marker_roots = [index.repo_root]
    return sorted(set(marker_roots) | set(index.extra_roots("clojure")))


class ClojureAnalyzer(LanguageAnalyzer):

    @staticmethod
    def detect(index) -> bool:
        return bool(_find_clj_roots(index))

    def scan(self) -> AnalysisResult:
        nodes: list[Node] = []
        edges: list[Edge] = []
        seen: set[str] = set()

        for project_root in _find_clj_roots(self.index):
            proj_name = project_root.name
            proj_id = f"clj_proj_{proj_name.replace('-', '_').replace('.', '_')}"
            if proj_id not in seen:
                seen.add(proj_id)
                marker = next(
                    (m for m in _CLJ_MARKERS if (project_root / m).exists()),
                    "deps.edn",
                )
                nodes.append(Node(
                    id=proj_id, type="clj_project", name=proj_name,
                    file_path=rel_path(self.repo_root, project_root / marker),
                ))

            for src_root in self._find_src_roots(project_root):
                for clj_file in self.index.files_with_ext(
                    {".clj", ".cljs", ".cljc", ".edn"}, under=src_root,
                ):
                    if clj_file.suffix == ".edn" and clj_file.name in _CLJ_MARKERS:
                        continue
                    self._scan_file(clj_file, proj_id, nodes, edges, seen)

        return AnalysisResult(
            nodes=nodes, edges=edges,
            state_sections=self._state(nodes),
        )

    def _find_src_roots(self, project_root: Path) -> list[Path]:
        candidates = [
            project_root / "src",
            project_root / "src" / "main" / "clojure",
            project_root / "src" / "clj",
        ]
        roots = [c for c in candidates if c.exists()]
        return roots if roots else [project_root]

    def _should_skip(self, file_rel: str) -> bool:
        return (
            any(f"/{s}/" in f"/{file_rel}" for s in _CLJ_SKIP)
            or "/test/" in file_rel
            or file_rel.endswith("_test.clj")
            or file_rel.endswith("_test.cljs")
            or file_rel.endswith("_test.cljc")
        )

    def _scan_file(
        self, clj_file: Path, proj_id: str,
        nodes: list[Node], edges: list[Edge], seen: set[str],
    ) -> None:
        file_rel = rel_path(self.repo_root, clj_file)
        if self._should_skip(file_rel):
            return

        content = read_safe(clj_file)
        ns_match = _NS_PATTERN.search(content)
        if not ns_match:
            return
        ns_name = ns_match.group(1)
        ns_id = f"clj_ns_{ns_name.replace('.', '_').replace('-', '_')}"
        if ns_id not in seen:
            seen.add(ns_id)
            nodes.append(Node(
                id=ns_id, type="clj_namespace", name=ns_name, file_path=file_rel,
            ))
            edges.append(Edge(from_id=proj_id, to_id=ns_id, type="contains"))

        for pattern, node_type in (
            (_DEFN_PATTERN, "clj_fn"),
            (_DEFPROTOCOL, "clj_protocol"),
            (_DEFRECORD, "clj_record"),
            (_DEFMACRO, "clj_macro"),
        ):
            for m in pattern.finditer(content):
                name = m.group(1)
                nid = f"{node_type}_{ns_id}_{name.replace('-', '_').replace('!', '').replace('?', '')}"
                if nid not in seen:
                    seen.add(nid)
                    nodes.append(Node(
                        id=nid, type=node_type, name=name, file_path=file_rel,
                    ))
                    edges.append(Edge(from_id=ns_id, to_id=nid, type="defines"))

        # Compojure routes
        for m in _COMPOJURE.finditer(content):
            method, path = m.group(1), m.group(2)
            if method == "ANY":
                method = "ANY"
            self._add_route(method, path, file_rel, ns_id, nodes, edges, seen)

        # Reitit routes
        for m in _REITIT.finditer(content):
            path, method = m.group(1), m.group(2).upper()
            self._add_route(method, path, file_rel, ns_id, nodes, edges, seen)

        # Requires → edges
        for m in _REQUIRE.finditer(content):
            for req in re.findall(r"\[([\w.\-]+)", m.group(1)):
                target_id = f"clj_ns_{req.replace('.', '_').replace('-', '_')}"
                if target_id in seen:
                    edges.append(Edge(from_id=ns_id, to_id=target_id, type="requires"))

    def _add_route(
        self, method: str, path: str, file_rel: str, ns_id: str,
        nodes: list[Node], edges: list[Edge], seen: set[str],
    ) -> None:
        slug = re.sub(r"[^a-zA-Z0-9]", "_", path.lstrip("/")).strip("_") or "root"
        rid = f"route_{method}_{slug}"
        if rid not in seen:
            seen.add(rid)
            nodes.append(Node(
                id=rid, type="route", name=f"{method} {path}", file_path=file_rel,
            ))
            edges.append(Edge(from_id=rid, to_id=ns_id, type="handled_by"))

    def _state(self, nodes: list[Node]) -> dict[str, str]:
        nss = [n for n in nodes if n.type == "clj_namespace"]
        fns = [n for n in nodes if n.type == "clj_fn"]
        if not nss:
            return {}
        return {"Clojure": f"{len(nss)} namespaces, {len(fns)} functions\n"}

    # -- File-level analysis -----------------------------------------------

    def supported_extensions(self) -> set[str]:
        return {".clj", ".cljs", ".cljc"}

    def analyze_file(self, file_path: Path) -> dict | None:
        if not file_path.is_file() or file_path.suffix not in (".clj", ".cljs", ".cljc"):
            return None
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        total = len(lines)

        fns = []
        for m in _DEFN_PATTERN.finditer(content):
            name = m.group(1)
            line_num = content[:m.start()].count("\n") + 1
            fns.append({"name": name, "line": line_num})
        for i, f in enumerate(fns):
            f["end"] = fns[i + 1]["line"] - 1 if i + 1 < len(fns) else total
            f["lines"] = f["end"] - f["line"] + 1
        fns.sort(key=lambda f: f["lines"], reverse=True)

        return {
            "type": "clojure", "file": file_path.name, "total_lines": total,
            "fn_count": len(fns), "fns": fns,
        }

    def format_bloat_report(self, analysis: dict) -> str | None:
        if analysis.get("type") != "clojure":
            return None
        lines = [
            f"Bloat report: {analysis['file']} ({analysis['total_lines']} lines, "
            f"{analysis['fn_count']} defns)\n",
            "Functions (largest first):",
        ]
        for f in analysis["fns"][:15]:
            bar = "\u2588" * (f["lines"] // 5)
            lines.append(f"  {f['lines']:>4} lines  {bar:30s}  {f['name']} (L{f['line']}-{f['end']})")
        return "\n".join(lines)
