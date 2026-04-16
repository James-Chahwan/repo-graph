"""
Solidity analyzer.

Detects via .sol files or hardhat/foundry/truffle config.
Scans contracts, interfaces, libraries, functions, events, and inheritance.
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

_CONTRACT_PATTERN = re.compile(
    r"^\s*(?:abstract\s+)?(contract|interface|library)\s+(\w+)"
    r"(?:\s+is\s+([\w,\s]+?))?\s*\{",
    re.MULTILINE,
)
_FUNCTION_PATTERN = re.compile(
    r"^\s*function\s+(\w+)\s*\(([^)]*)\)\s*([\w\s]*?)(?:returns\s*\([^)]*\))?\s*\{?",
    re.MULTILINE,
)
_EVENT_PATTERN = re.compile(r"^\s*event\s+(\w+)\s*\(", re.MULTILINE)
_MODIFIER_PATTERN = re.compile(r"^\s*modifier\s+(\w+)", re.MULTILINE)
_IMPORT_PATTERN = re.compile(
    r"""^\s*import\s+(?:\{[^}]+\}\s+from\s+)?['"]([^'"]+)['"]""",
    re.MULTILINE,
)

_SOL_CONFIGS = {"hardhat.config.js", "hardhat.config.ts", "foundry.toml",
                "truffle-config.js", "brownie-config.yaml", "remappings.txt"}
_SOL_SKIP = {"node_modules", "artifacts", "cache", "out", "typechain",
             "typechain-types", "lib", "forge-cache"}


def _find_sol_roots(index) -> list[Path]:
    # Deduplicate: if a dir with a config is already covered by an ancestor, skip it.
    candidates = index.dirs_with_any(_SOL_CONFIGS)
    roots: list[Path] = []
    for d in candidates:
        if any(_is_inside(d, r) for r in roots):
            continue
        roots.append(d)
    if not roots:
        # Fallback: any .sol files in the repo → attribute to repo root
        if index.files_with_ext(".sol"):
            roots = [index.repo_root]
    return sorted(set(roots) | set(index.extra_roots("solidity")))


def _is_inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return child != parent
    except ValueError:
        return False


class SolidityAnalyzer(LanguageAnalyzer):

    @staticmethod
    def detect(index) -> bool:
        return bool(_find_sol_roots(index))

    def scan(self) -> AnalysisResult:
        nodes: list[Node] = []
        edges: list[Edge] = []
        seen: set[str] = set()
        # Track contract name → id to resolve inheritance later
        contract_index: dict[str, str] = {}

        for project_root in _find_sol_roots(self.index):
            proj_name = project_root.name
            proj_id = f"sol_proj_{proj_name.replace('-', '_').replace('.', '_')}"
            if proj_id not in seen:
                seen.add(proj_id)
                marker = next(
                    (c for c in _SOL_CONFIGS if (project_root / c).exists()),
                    None,
                )
                marker_path = project_root / marker if marker else project_root
                nodes.append(Node(
                    id=proj_id, type="sol_project", name=proj_name,
                    file_path=rel_path(self.repo_root, marker_path),
                ))

            for src_root in self._find_src_roots(project_root):
                for sol_file in self.index.files_with_ext(".sol", under=src_root):
                    self._scan_file(sol_file, proj_id, nodes, edges, seen, contract_index)

        # Second pass: resolve inheritance references
        resolved: list[Edge] = []
        for edge in edges:
            if edge.type == "inherits" and edge.to_id.startswith("sol_ref_"):
                ref_name = edge.to_id[len("sol_ref_"):]
                actual = contract_index.get(ref_name)
                if actual:
                    resolved.append(Edge(from_id=edge.from_id, to_id=actual, type="inherits"))
                else:
                    resolved.append(edge)
            else:
                resolved.append(edge)

        return AnalysisResult(
            nodes=nodes, edges=resolved,
            state_sections=self._state(nodes),
        )

    def _find_src_roots(self, project_root: Path) -> list[Path]:
        cands = [project_root / "contracts", project_root / "src", project_root]
        return [c for c in cands if c.exists()]

    def _should_skip(self, file_rel: str) -> bool:
        return any(f"/{s}/" in f"/{file_rel}" for s in _SOL_SKIP)

    def _scan_file(
        self, sol_file: Path, proj_id: str,
        nodes: list[Node], edges: list[Edge], seen: set[str],
        contract_index: dict[str, str],
    ) -> None:
        file_rel = rel_path(self.repo_root, sol_file)
        if self._should_skip(file_rel):
            return
        content = read_safe(sol_file)

        for m in _CONTRACT_PATTERN.finditer(content):
            kind, name = m.group(1), m.group(2)
            parents_raw = m.group(3) or ""
            cid = f"sol_{kind}_{name}"
            if cid not in seen:
                seen.add(cid)
                contract_index[name] = cid
                nodes.append(Node(
                    id=cid, type=f"sol_{kind}", name=name, file_path=file_rel,
                ))
                edges.append(Edge(from_id=proj_id, to_id=cid, type="contains"))

            # Inheritance
            for parent in re.split(r"[,\s]+", parents_raw.strip()):
                parent = parent.strip()
                if parent:
                    edges.append(Edge(
                        from_id=cid, to_id=f"sol_ref_{parent}", type="inherits",
                    ))

            # Functions, events, modifiers within the contract block
            block_start = m.end()
            block_end = self._find_matching_brace(content, block_start - 1)
            block = content[block_start:block_end] if block_end > 0 else content[block_start:]

            for fm in _FUNCTION_PATTERN.finditer(block):
                fn_name = fm.group(1)
                if fn_name in ("if", "for", "while", "return"):
                    continue
                fn_id = f"sol_fn_{cid}_{fn_name}"
                if fn_id not in seen:
                    seen.add(fn_id)
                    nodes.append(Node(
                        id=fn_id, type="sol_function", name=fn_name,
                        file_path=file_rel,
                    ))
                    edges.append(Edge(from_id=cid, to_id=fn_id, type="defines"))

            for em in _EVENT_PATTERN.finditer(block):
                ev_name = em.group(1)
                ev_id = f"sol_event_{cid}_{ev_name}"
                if ev_id not in seen:
                    seen.add(ev_id)
                    nodes.append(Node(
                        id=ev_id, type="sol_event", name=ev_name,
                        file_path=file_rel,
                    ))
                    edges.append(Edge(from_id=cid, to_id=ev_id, type="defines"))

            for mm in _MODIFIER_PATTERN.finditer(block):
                mod_name = mm.group(1)
                mod_id = f"sol_mod_{cid}_{mod_name}"
                if mod_id not in seen:
                    seen.add(mod_id)
                    nodes.append(Node(
                        id=mod_id, type="sol_modifier", name=mod_name,
                        file_path=file_rel,
                    ))
                    edges.append(Edge(from_id=cid, to_id=mod_id, type="defines"))

    def _find_matching_brace(self, content: str, open_pos: int) -> int:
        depth = 0
        for i in range(open_pos, len(content)):
            c = content[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return i
        return -1

    def _state(self, nodes: list[Node]) -> dict[str, str]:
        contracts = [n for n in nodes if n.type == "sol_contract"]
        interfaces = [n for n in nodes if n.type == "sol_interface"]
        libs = [n for n in nodes if n.type == "sol_library"]
        fns = [n for n in nodes if n.type == "sol_function"]
        if not (contracts or interfaces or libs):
            return {}
        parts = []
        if contracts: parts.append(f"{len(contracts)} contracts")
        if interfaces: parts.append(f"{len(interfaces)} interfaces")
        if libs: parts.append(f"{len(libs)} libraries")
        if fns: parts.append(f"{len(fns)} functions")
        return {"Solidity": ", ".join(parts) + "\n"}

    # -- File-level analysis -----------------------------------------------

    def supported_extensions(self) -> set[str]:
        return {".sol"}

    def analyze_file(self, file_path: Path) -> dict | None:
        if not file_path.is_file() or file_path.suffix != ".sol":
            return None
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        total = len(lines)

        fns = []
        for m in _FUNCTION_PATTERN.finditer(content):
            name = m.group(1)
            if name in ("if", "for", "while", "return"):
                continue
            line_num = content[:m.start()].count("\n") + 1
            fns.append({"name": name, "line": line_num})
        for i, f in enumerate(fns):
            f["end"] = fns[i + 1]["line"] - 1 if i + 1 < len(fns) else total
            f["lines"] = f["end"] - f["line"] + 1
        fns.sort(key=lambda f: f["lines"], reverse=True)

        contracts = [m.group(2) for m in _CONTRACT_PATTERN.finditer(content)]
        events = _EVENT_PATTERN.findall(content)
        return {
            "type": "solidity", "file": file_path.name, "total_lines": total,
            "function_count": len(fns), "functions": fns,
            "contract_count": len(contracts), "event_count": len(events),
        }

    def format_bloat_report(self, analysis: dict) -> str | None:
        if analysis.get("type") != "solidity":
            return None
        lines = [
            f"Bloat report: {analysis['file']} ({analysis['total_lines']} lines, "
            f"{analysis['contract_count']} contracts, "
            f"{analysis['function_count']} functions, "
            f"{analysis['event_count']} events)\n",
            "Functions (largest first):",
        ]
        for f in analysis["functions"][:15]:
            bar = "\u2588" * (f["lines"] // 5)
            lines.append(f"  {f['lines']:>4} lines  {bar:30s}  {f['name']} (L{f['line']}-{f['end']})")
        return "\n".join(lines)
