"""
Rust language analyzer.

Detects Rust projects via Cargo.toml, scans for modules, structs,
traits, impl blocks, functions, and use relationships.
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

_FN_PATTERN = re.compile(
    r"^(?:pub\s+)?(?:async\s+)?fn\s+(\w+)", re.MULTILINE
)
_STRUCT_PATTERN = re.compile(
    r"^(?:pub\s+)?struct\s+(\w+)", re.MULTILINE
)
_TRAIT_PATTERN = re.compile(
    r"^(?:pub\s+)?trait\s+(\w+)", re.MULTILINE
)
_IMPL_PATTERN = re.compile(
    r"^impl(?:<[^>]*>)?\s+(?:(\w+)\s+for\s+)?(\w+)", re.MULTILINE
)
_USE_PATTERN = re.compile(
    r"^use\s+crate::(\w+)", re.MULTILINE
)
# Actix/Axum/Rocket route macros
_ROUTE_ATTR = re.compile(
    r'#\[(get|post|put|delete|patch)\("([^"]+)"\)\]', re.MULTILINE
)
# Axum Router::new().route("/path", get(handler))
_AXUM_ROUTE = re.compile(
    r'\.route\(\s*"([^"]+)"\s*,\s*(get|post|put|delete|patch)',
)


class RustAnalyzer(LanguageAnalyzer):

    @staticmethod
    def detect(index) -> bool:
        return bool(index.roots_for("rust", "Cargo.toml"))

    def scan(self) -> AnalysisResult:
        nodes: list[Node] = []
        edges: list[Edge] = []
        seen: set[str] = set()

        for cargo_root in self.index.roots_for("rust", "Cargo.toml"):
            crate_name = self._read_crate_name(cargo_root)
            crate_id = f"rs_crate_{crate_name.replace('-', '_')}"
            if crate_id not in seen:
                seen.add(crate_id)
                nodes.append(Node(
                    id=crate_id, type="rs_crate", name=crate_name,
                    file_path=rel_path(self.repo_root, cargo_root / "Cargo.toml"),
                ))

            src = cargo_root / "src"
            if not src.exists():
                continue

            for rs_file in self.index.files_with_ext(".rs", under=src):
                file_rel = rel_path(self.repo_root, rs_file)
                mod_name = rs_file.stem
                if mod_name == "mod":
                    mod_name = rs_file.parent.name
                mod_id = f"rs_mod_{file_rel.replace('/', '_').replace('.', '_')}"
                if mod_id in seen:
                    continue
                seen.add(mod_id)

                nodes.append(Node(
                    id=mod_id, type="rs_module", name=mod_name,
                    file_path=file_rel,
                ))
                edges.append(Edge(from_id=crate_id, to_id=mod_id, type="contains"))

                content = read_safe(rs_file)

                # Structs
                for m in _STRUCT_PATTERN.finditer(content):
                    sid = f"rs_struct_{mod_id}_{m.group(1)}"
                    if sid not in seen:
                        seen.add(sid)
                        nodes.append(Node(id=sid, type="rs_struct", name=m.group(1), file_path=file_rel))
                        edges.append(Edge(from_id=mod_id, to_id=sid, type="defines"))

                # Traits
                for m in _TRAIT_PATTERN.finditer(content):
                    tid = f"rs_trait_{mod_id}_{m.group(1)}"
                    if tid not in seen:
                        seen.add(tid)
                        nodes.append(Node(id=tid, type="rs_trait", name=m.group(1), file_path=file_rel))
                        edges.append(Edge(from_id=mod_id, to_id=tid, type="defines"))

                # Functions (top-level only — indented fns are methods, skip)
                for m in _FN_PATTERN.finditer(content):
                    fn_name = m.group(1)
                    # Check if top-level (no leading whitespace)
                    line_start = content[:m.start()].rfind("\n") + 1
                    if m.start() == line_start or not content[line_start:m.start()].strip():
                        fid = f"rs_fn_{mod_id}_{fn_name}"
                        if fid not in seen:
                            seen.add(fid)
                            nodes.append(Node(id=fid, type="rs_function", name=fn_name, file_path=file_rel))
                            edges.append(Edge(from_id=mod_id, to_id=fid, type="defines"))

                # Routes (Actix/Rocket attribute macros)
                for m in _ROUTE_ATTR.finditer(content):
                    method, path = m.group(1).upper(), m.group(2)
                    rid = f"route_{method}_{path.replace('/', '_').strip('_')}"
                    if rid not in seen:
                        seen.add(rid)
                        nodes.append(Node(id=rid, type="route", name=f"{method} {path}", file_path=file_rel))
                        edges.append(Edge(from_id=rid, to_id=mod_id, type="handled_by"))

                # Routes (Axum router)
                for m in _AXUM_ROUTE.finditer(content):
                    path, method = m.group(1), m.group(2).upper()
                    rid = f"route_{method}_{path.replace('/', '_').strip('_')}"
                    if rid not in seen:
                        seen.add(rid)
                        nodes.append(Node(id=rid, type="route", name=f"{method} {path}", file_path=file_rel))
                        edges.append(Edge(from_id=rid, to_id=mod_id, type="handled_by"))

                # Internal use statements
                for m in _USE_PATTERN.finditer(content):
                    target_mod = m.group(1)
                    target_id = f"rs_mod_{crate_name.replace('-', '_')}_src_{target_mod}_rs"
                    if target_id in seen:
                        edges.append(Edge(from_id=mod_id, to_id=target_id, type="imports"))

        return AnalysisResult(
            nodes=nodes, edges=edges,
            state_sections=self._state(nodes),
        )

    def _read_crate_name(self, cargo_root: Path) -> str:
        content = read_safe(cargo_root / "Cargo.toml")
        m = re.search(r'^name\s*=\s*"([^"]+)"', content, re.MULTILINE)
        return m.group(1) if m else cargo_root.name

    def _state(self, nodes: list[Node]) -> dict[str, str]:
        mods = [n for n in nodes if n.type == "rs_module"]
        structs = [n for n in nodes if n.type == "rs_struct"]
        return {"Rust": f"{len(mods)} modules, {len(structs)} structs\n"} if mods else {}

    # -- File-level analysis -----------------------------------------------

    def supported_extensions(self) -> set[str]:
        return {".rs"}

    def analyze_file(self, file_path: Path) -> dict | None:
        if not file_path.is_file() or file_path.suffix != ".rs":
            return None
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        total = len(lines)

        functions = []
        for m in _FN_PATTERN.finditer(content):
            line_num = content[:m.start()].count("\n") + 1
            functions.append({"name": m.group(1), "start": line_num})

        for i, fn in enumerate(functions):
            fn["end"] = functions[i + 1]["start"] - 1 if i + 1 < len(functions) else total
            fn["lines"] = fn["end"] - fn["start"] + 1

        functions.sort(key=lambda f: f["lines"], reverse=True)
        structs = _STRUCT_PATTERN.findall(content)
        traits = _TRAIT_PATTERN.findall(content)

        return {
            "type": "rust", "file": file_path.name, "total_lines": total,
            "function_count": len(functions), "functions": functions,
            "struct_count": len(structs), "trait_count": len(traits),
        }

    def format_bloat_report(self, analysis: dict) -> str | None:
        if analysis.get("type") != "rust":
            return None
        lines = [
            f"Bloat report: {analysis['file']} ({analysis['total_lines']} lines, "
            f"{analysis['function_count']} functions, {analysis['struct_count']} structs, "
            f"{analysis['trait_count']} traits)\n",
            "Functions (largest first):",
        ]
        for fn in analysis["functions"][:15]:
            bar = "█" * (fn["lines"] // 5)
            lines.append(f"  {fn['lines']:>4} lines  {bar:30s}  {fn['name']} (L{fn['start']}-{fn['end']})")
        return "\n".join(lines)
