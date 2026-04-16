"""
Terraform / OpenTofu analyzer.

Detects via any .tf files. Scans resources, data sources, modules,
variables, outputs, and module source edges.
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

_RESOURCE_PATTERN = re.compile(
    r'^\s*resource\s+"([^"]+)"\s+"([^"]+)"\s*\{', re.MULTILINE,
)
_DATA_PATTERN = re.compile(
    r'^\s*data\s+"([^"]+)"\s+"([^"]+)"\s*\{', re.MULTILINE,
)
_MODULE_PATTERN = re.compile(
    r'^\s*module\s+"([^"]+)"\s*\{', re.MULTILINE,
)
_MODULE_SOURCE = re.compile(
    r'source\s*=\s*"([^"]+)"', re.MULTILINE,
)
_VAR_PATTERN = re.compile(
    r'^\s*variable\s+"([^"]+)"\s*\{', re.MULTILINE,
)
_OUTPUT_PATTERN = re.compile(
    r'^\s*output\s+"([^"]+)"\s*\{', re.MULTILINE,
)
# References: module.foo.bar / var.baz / data.aws_x.y / resource refs like aws_instance.foo
_MODULE_REF = re.compile(r"\bmodule\.(\w+)\b")
_RESOURCE_REF = re.compile(r"\b([a-z][a-z0-9_]+)\.([a-z][a-z0-9_\-]+)\b")

_TF_SKIP = {"terraform.tfstate.d"}


def _find_tf_roots(index) -> list[Path]:
    """Find directories containing .tf files — each dir with .tf is a Terraform module."""
    roots: set[Path] = set()
    for tf in index.files_with_ext(".tf"):
        rel_parts = tf.relative_to(index.repo_root).parts[:-1]
        if any(part in _TF_SKIP for part in rel_parts):
            continue
        roots.add(tf.parent)
    return sorted(roots | set(index.extra_roots("terraform")))


class TerraformAnalyzer(LanguageAnalyzer):

    @staticmethod
    def detect(index) -> bool:
        return bool(_find_tf_roots(index))

    def scan(self) -> AnalysisResult:
        nodes: list[Node] = []
        edges: list[Edge] = []
        seen: set[str] = set()

        tf_roots = _find_tf_roots(self.index)
        for tf_dir in tf_roots:
            mod_name = rel_path(self.repo_root, tf_dir)
            if mod_name == ".":
                mod_name = "root"
            mod_id = f"tf_mod_{mod_name.replace('/', '_').replace('-', '_').replace('.', '_')}"
            if mod_id not in seen:
                seen.add(mod_id)
                nodes.append(Node(
                    id=mod_id, type="tf_module", name=mod_name, file_path=mod_name,
                ))

            for tf_file in self.index.files_with_ext(".tf", under=tf_dir):
                if tf_file.parent != tf_dir:
                    continue
                self._scan_file(tf_file, mod_id, nodes, edges, seen)

        return AnalysisResult(
            nodes=nodes, edges=edges,
            state_sections=self._state(nodes),
        )

    def _scan_file(
        self, tf_file: Path, mod_id: str,
        nodes: list[Node], edges: list[Edge], seen: set[str],
    ) -> None:
        file_rel = rel_path(self.repo_root, tf_file)
        content = read_safe(tf_file)

        for m in _RESOURCE_PATTERN.finditer(content):
            rtype, rname = m.group(1), m.group(2)
            rid = f"tf_res_{mod_id}_{rtype}_{rname}"
            if rid not in seen:
                seen.add(rid)
                nodes.append(Node(
                    id=rid, type="tf_resource", name=f"{rtype}.{rname}",
                    file_path=file_rel,
                ))
                edges.append(Edge(from_id=mod_id, to_id=rid, type="contains"))

        for m in _DATA_PATTERN.finditer(content):
            dtype, dname = m.group(1), m.group(2)
            did = f"tf_data_{mod_id}_{dtype}_{dname}"
            if did not in seen:
                seen.add(did)
                nodes.append(Node(
                    id=did, type="tf_data", name=f"data.{dtype}.{dname}",
                    file_path=file_rel,
                ))
                edges.append(Edge(from_id=mod_id, to_id=did, type="contains"))

        for m in _MODULE_PATTERN.finditer(content):
            sub_name = m.group(1)
            sub_id = f"tf_modcall_{mod_id}_{sub_name}"
            if sub_id not in seen:
                seen.add(sub_id)
                nodes.append(Node(
                    id=sub_id, type="tf_module_call", name=sub_name,
                    file_path=file_rel,
                ))
                edges.append(Edge(from_id=mod_id, to_id=sub_id, type="contains"))

            # Extract source = "..." from the block
            block_start = m.end()
            block_end = self._find_matching_brace(content, block_start - 1)
            block = content[block_start:block_end] if block_end > 0 else ""
            src_match = _MODULE_SOURCE.search(block)
            if src_match:
                source = src_match.group(1)
                # Local module: ./modules/foo → try resolving
                if source.startswith("./") or source.startswith("../"):
                    resolved = (tf_file.parent / source).resolve()
                    try:
                        rel = rel_path(self.repo_root, resolved)
                        target_id = f"tf_mod_{rel.replace('/', '_').replace('-', '_').replace('.', '_')}"
                        edges.append(Edge(from_id=sub_id, to_id=target_id, type="sources"))
                    except Exception:
                        pass
                else:
                    # Remote source — stub node
                    src_id = f"tf_remote_{source.replace('/', '_').replace(':', '_').replace('.', '_')}"
                    if src_id not in seen:
                        seen.add(src_id)
                        nodes.append(Node(
                            id=src_id, type="tf_remote_module", name=source,
                            file_path=file_rel,
                        ))
                    edges.append(Edge(from_id=sub_id, to_id=src_id, type="sources"))

        for m in _VAR_PATTERN.finditer(content):
            vname = m.group(1)
            vid = f"tf_var_{mod_id}_{vname}"
            if vid not in seen:
                seen.add(vid)
                nodes.append(Node(
                    id=vid, type="tf_variable", name=vname, file_path=file_rel,
                ))
                edges.append(Edge(from_id=mod_id, to_id=vid, type="contains"))

        for m in _OUTPUT_PATTERN.finditer(content):
            oname = m.group(1)
            oid = f"tf_out_{mod_id}_{oname}"
            if oid not in seen:
                seen.add(oid)
                nodes.append(Node(
                    id=oid, type="tf_output", name=oname, file_path=file_rel,
                ))
                edges.append(Edge(from_id=mod_id, to_id=oid, type="contains"))

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
        mods = [n for n in nodes if n.type == "tf_module"]
        resources = [n for n in nodes if n.type == "tf_resource"]
        module_calls = [n for n in nodes if n.type == "tf_module_call"]
        if not mods:
            return {}
        parts = [f"{len(mods)} modules", f"{len(resources)} resources"]
        if module_calls:
            parts.append(f"{len(module_calls)} module calls")
        return {"Terraform": ", ".join(parts) + "\n"}

    # -- File-level analysis -----------------------------------------------

    def supported_extensions(self) -> set[str]:
        return {".tf"}

    def analyze_file(self, file_path: Path) -> dict | None:
        if not file_path.is_file() or file_path.suffix != ".tf":
            return None
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        total = len(lines)

        resources = [
            {"name": f"{m.group(1)}.{m.group(2)}",
             "line": content[:m.start()].count("\n") + 1}
            for m in _RESOURCE_PATTERN.finditer(content)
        ]
        for i, r in enumerate(resources):
            r["end"] = resources[i + 1]["line"] - 1 if i + 1 < len(resources) else total
            r["lines"] = r["end"] - r["line"] + 1
        resources.sort(key=lambda r: r["lines"], reverse=True)

        return {
            "type": "terraform", "file": file_path.name, "total_lines": total,
            "resource_count": len(resources), "resources": resources,
            "variable_count": len(_VAR_PATTERN.findall(content)),
            "output_count": len(_OUTPUT_PATTERN.findall(content)),
        }

    def format_bloat_report(self, analysis: dict) -> str | None:
        if analysis.get("type") != "terraform":
            return None
        lines = [
            f"Bloat report: {analysis['file']} ({analysis['total_lines']} lines, "
            f"{analysis['resource_count']} resources, "
            f"{analysis['variable_count']} vars, "
            f"{analysis['output_count']} outputs)\n",
            "Resources (largest first):",
        ]
        for r in analysis["resources"][:15]:
            bar = "\u2588" * (r["lines"] // 5)
            lines.append(f"  {r['lines']:>4} lines  {bar:30s}  {r['name']} (L{r['line']}-{r['end']})")
        return "\n".join(lines)
