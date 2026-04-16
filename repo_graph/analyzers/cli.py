"""
CLI entrypoint analyzer.

Cross-cutting analyzer that detects CLI command definitions across:
  - Python: @click.command(), @click.group(), @<group>.command("name")
  - JS/TS: commander `.command("name")`, yargs `.command("name", ...)`
  - Go:    cobra.Command{ Use: "name" }
  - Rust:  clap Command::new("name")

Emits `cli_command` nodes and `handled_by` edges back to the file the
command is declared in. Flow kind `cli` applies at generation time.
"""

from __future__ import annotations

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


# Python click: @click.command("name"), @click.command(), @group.command("name")
_PY_CLICK_DECORATOR = re.compile(
    r"@(?:\w+\.)?command\(\s*(?:['\"]([^'\"]+)['\"])?[^)]*\)\s*\n+"
    r"(?:@[^\n]+\n)*\s*def\s+(\w+)",
)
_PY_CLICK_IMPORT = re.compile(r"(?:^|\n)\s*import\s+click|from\s+click\s+import")

# JS/TS commander: .command("name [...]") or program.command("name")
_JS_COMMANDER_CALL = re.compile(
    r"""\.command\(\s*['"`]([A-Za-z0-9_:\-]+)(?:\s+[^'"`]*)?['"`]""",
)
# JS/TS yargs: .command("name", "desc", ...)  — matches above pattern too
# Distinguish by presence of commander or yargs import
_JS_CLI_IMPORT = re.compile(r"""['"`](?:commander|yargs)['"`]""")

# Go cobra: &cobra.Command{ Use: "name", ... }   or   cobra.Command{ Use: "name" }
_GO_COBRA_USE = re.compile(
    r"cobra\.Command\s*\{[^}]*?Use:\s*\"([^\"\s]+)",
    re.DOTALL,
)
_GO_COBRA_IMPORT = re.compile(r'"github\.com/spf13/cobra"')

# Rust clap: Command::new("name") or #[command(name = "...")]
_RS_CLAP_NEW = re.compile(r'Command::new\(\s*"([^"]+)"')
_RS_CLAP_DERIVE = re.compile(r"#\[derive\([^)]*(?:Parser|Subcommand)[^)]*\)\]")
_RS_CLAP_IMPORT = re.compile(r"use\s+clap::")


def _cli_id(name: str, file_rel: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_") or "cmd"
    file_slug = re.sub(r"[^a-zA-Z0-9]+", "_", file_rel).strip("_")
    return f"cli_{slug}__{file_slug}"


class CliEntrypointAnalyzer(LanguageAnalyzer):
    """Cross-cutting CLI command analyzer. Always runs."""

    @staticmethod
    def detect(index) -> bool:
        py_signals = ("import click", "from click")
        js_signals = ("'commander'", '"commander"', "`commander`",
                      "'yargs'", '"yargs"', "`yargs`")
        go_signals = ('"github.com/spf13/cobra"',)
        rs_signals = ("use clap::", "use clap ")

        groups = [
            ((".py",), py_signals),
            ((".ts", ".tsx", ".js", ".jsx", ".mjs"), js_signals),
            ((".go",), go_signals),
            ((".rs",), rs_signals),
        ]
        for exts, signals in groups:
            for ext in exts:
                for f in index.files_with_ext(ext):
                    snippet = read_safe(f)
                    if not snippet:
                        continue
                    if any(sig in snippet for sig in signals):
                        return True
        return False

    def scan(self) -> AnalysisResult:
        nodes: list[Node] = []
        edges: list[Edge] = []
        seen: set[str] = set()

        self._scan_python(nodes, edges, seen)
        self._scan_js(nodes, edges, seen)
        self._scan_go(nodes, edges, seen)
        self._scan_rust(nodes, edges, seen)

        state = self._state(nodes)
        return AnalysisResult(nodes=nodes, edges=edges, state_sections=state)

    def _add_command(
        self,
        name: str,
        file_rel: str,
        target_id: str | None,
        nodes: list[Node],
        edges: list[Edge],
        seen: set[str],
    ) -> None:
        cid = _cli_id(name, file_rel)
        if cid in seen:
            return
        seen.add(cid)
        nodes.append(Node(
            id=cid, type="cli_command", name=name, file_path=file_rel,
        ))
        if target_id:
            edges.append(Edge(from_id=cid, to_id=target_id, type="handled_by"))

    def _file_level_id(self, file_rel: str) -> str:
        """Build a synthetic id pointing at the file; may or may not resolve to
        a real node. Generator's file-anchor resolver rewires it."""
        return f"file::{file_rel}"

    def _scan_python(self, nodes, edges, seen) -> None:
        for py in self.index.files_with_ext(".py"):
            content = read_safe(py)
            if not content or not _PY_CLICK_IMPORT.search(content):
                continue
            file_rel = rel_path(self.repo_root, py)
            for m in _PY_CLICK_DECORATOR.finditer(content):
                cmd_name = m.group(1) or m.group(2)
                self._add_command(
                    cmd_name, file_rel, self._file_level_id(file_rel),
                    nodes, edges, seen,
                )

    def _scan_js(self, nodes, edges, seen) -> None:
        for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs"):
            for f in self.index.files_with_ext(ext):
                content = read_safe(f)
                if not content or not _JS_CLI_IMPORT.search(content):
                    continue
                file_rel = rel_path(self.repo_root, f)
                for m in _JS_COMMANDER_CALL.finditer(content):
                    cmd_name = m.group(1)
                    self._add_command(
                        cmd_name, file_rel, self._file_level_id(file_rel),
                        nodes, edges, seen,
                    )

    def _scan_go(self, nodes, edges, seen) -> None:
        for go in self.index.files_with_ext(".go"):
            content = read_safe(go)
            if not content or not _GO_COBRA_IMPORT.search(content):
                continue
            file_rel = rel_path(self.repo_root, go)
            for m in _GO_COBRA_USE.finditer(content):
                cmd_name = m.group(1)
                self._add_command(
                    cmd_name, file_rel, self._file_level_id(file_rel),
                    nodes, edges, seen,
                )

    def _scan_rust(self, nodes, edges, seen) -> None:
        for rs in self.index.files_with_ext(".rs"):
            content = read_safe(rs)
            if not content or not _RS_CLAP_IMPORT.search(content):
                continue
            file_rel = rel_path(self.repo_root, rs)
            for m in _RS_CLAP_NEW.finditer(content):
                cmd_name = m.group(1)
                self._add_command(
                    cmd_name, file_rel, self._file_level_id(file_rel),
                    nodes, edges, seen,
                )

    def _state(self, nodes: list[Node]) -> dict[str, str]:
        cmds = [n for n in nodes if n.type == "cli_command"]
        if not cmds:
            return {}
        return {"CLI": f"{len(cmds)} commands\n"}
