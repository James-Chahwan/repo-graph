"""The skills in `skills/` are held to the live tool surface.

Skills went stale on every tool change before this (a parameter renamed, a tool
folded into another), and nothing caught it. Since glia 0.5.4 the skills live in
glia and `skills/` is a copy (`make skills`). Each task skill shows a verb as an
MCP call (`find query=<text> expand=true`), a glia CLI command, and a repo-graph
shell command (`uvx mcp-repo-graph find "<text>" --expand`). The two repo-graph
routes are checked here: MCP arguments against the registered tool's signature,
shell commands against the real CLI parser. glia checks its own CLI column. The
`glia` and `glia-overlay` skills are glia CLI references with no repo-graph
route. The Claude Code plugin's copy has to match the source.
"""

from __future__ import annotations

import inspect
import json
import re
import shlex
import typing
from pathlib import Path

import pytest

from repo_graph import cli, server
from repo_graph.installer.constants import TOOL_NAMES
from repo_graph.installer.core import _build_parser as installer_parser

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
PLUGIN = ROOT / "claude-plugin"

SKILL_FILES = sorted(SKILLS.glob("*/SKILL.md"))
# The task skills: the ones that offer repo-graph's routes (MCP and the shell).
TASK_SKILLS = [p for p in SKILL_FILES if "uvx mcp-repo-graph" in p.read_text()]

_FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_SPAN = re.compile(r"`([^`\n]+)`")
_CALL = re.compile(rf"^({'|'.join(TOOL_NAMES)})((?:\s+\w+=\S+)*)$")
_ARG = re.compile(r"^(\w+)=(\S+)$")
_SHELL = re.compile(r"\buvx mcp-repo-graph\b(.*)")
_TOOL_ID = re.compile(r"\bmcp__([\w-]+?)__(\w+\b|<tool>)")


def _params(tool: str) -> dict[str, type]:
    """A tool's parameters and their base types, read off the registered function."""
    fn = getattr(server, tool)
    hints = typing.get_type_hints(fn, include_extras=True)
    return {name: cli._field(hints[name])[0] for name in inspect.signature(fn).parameters}


def _spans(text: str) -> list[str]:
    """Inline code spans outside fenced blocks."""
    return _SPAN.findall(_FENCE.sub("", text))


def _shell_commands(text: str) -> list[str]:
    """Every `uvx mcp-repo-graph ...` invocation, from inline spans and fenced
    blocks, cut at a pipe."""
    candidates = _spans(text)
    for block in _FENCE.findall(text):
        candidates += block.splitlines()
    out = []
    for c in candidates:
        m = _SHELL.search(c)
        if m:
            out.append(m.group(1).split(" | ")[0].strip())
    return out


def _frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert m, "SKILL.md must open with a --- frontmatter block"
    fields = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def test_skills_exist():
    assert len(SKILL_FILES) >= 6, [p.parent.name for p in SKILL_FILES]
    assert len(TASK_SKILLS) >= 6, [p.parent.name for p in TASK_SKILLS]


def test_claude_plugin_ships_the_same_skills():
    """Marketplace installs copy only the plugin's own directory, so the plugin
    can't point at ../skills. It carries a copy, and the copy must be current."""
    want = {p.relative_to(SKILLS): p.read_bytes() for p in SKILLS.rglob("*") if p.is_file()}
    shipped = PLUGIN / "skills"
    have = {p.relative_to(shipped): p.read_bytes() for p in shipped.rglob("*") if p.is_file()}
    assert have == want, "claude-plugin/skills/ is out of date: run `make skills`"


@pytest.mark.parametrize("path", SKILL_FILES, ids=lambda p: p.parent.name)
def test_frontmatter(path):
    fm = _frontmatter(path.read_text())
    assert fm.get("name") == path.parent.name
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", fm["name"]) and len(fm["name"]) <= 64
    # 1,024 is the Agent Skills spec cap; Claude Code truncates its listing later.
    assert 0 < len(fm.get("description", "")) <= 1024


@pytest.mark.parametrize("path", TASK_SKILLS, ids=lambda p: p.parent.name)
def test_mcp_calls_match_tool_signatures(path):
    """`impact nodes=<n> direction=backward` names a real tool and real
    parameters, and a boolean is given as true/false."""
    # A bare `budget=<chars>` span belongs to whichever tool the prose is about.
    any_tool: dict[str, set[type]] = {}
    for t in TOOL_NAMES:
        for name, typ in _params(t).items():
            any_tool.setdefault(name, set()).add(typ)

    checked = 0
    for span in _spans(path.read_text()):
        if call := _CALL.match(span):
            params = {k: {v} for k, v in _params(call.group(1)).items()}
            args, where = call.group(2).split(), call.group(1)
        elif _ARG.match(span):
            params, args, where = any_tool, [span], "any tool"
        else:
            continue
        for arg in args:
            key, value = _ARG.match(arg).groups()
            assert key in params, f"`{span}`: {where} has no parameter {key}"
            if params[key] == {bool}:
                assert value in ("true", "false"), f"`{span}`: {key} is a boolean"
            checked += 1
    assert checked, f"{path.parent.name}: no MCP arguments found to check"


@pytest.mark.parametrize("path", TASK_SKILLS, ids=lambda p: p.parent.name)
def test_shell_commands_parse(path):
    """Every `uvx mcp-repo-graph ...` a skill tells an agent to run is accepted
    by the real parser, so a renamed flag fails here, not in someone's shell."""
    commands = _shell_commands(path.read_text())
    for cmd in commands:
        argv = shlex.split(cmd)
        if not argv or argv == ["<verb>"]:
            continue  # the Transports prose naming the route, not a command
        try:
            if argv[0] in cli.POSITIONAL:
                cli.build_parser().parse_args(argv)
            else:
                assert argv[0] in ("install", "uninstall"), f"unknown subcommand: {cmd}"
                installer_parser().parse_args(argv)
        except SystemExit:
            pytest.fail(f"{path.parent.name}: `uvx mcp-repo-graph {cmd}` does not parse")


def test_every_tool_is_covered_by_a_skill():
    covered = set()
    for path in TASK_SKILLS:
        text = path.read_text()
        covered |= {m.group(1) for s in _spans(text) if (m := _CALL.match(s))}
        covered |= {shlex.split(c)[0] for c in _shell_commands(text) if c and c != "<verb>"}
    assert set(TOOL_NAMES) <= covered, f"no skill shows: {set(TOOL_NAMES) - covered}"


def test_every_skill_shows_both_routes():
    """Each task skill works with the MCP server and without it."""
    for path in TASK_SKILLS:
        text = path.read_text()
        assert any(_CALL.match(s) for s in _spans(text)), f"{path.parent.name}: no MCP call"
        real = [c for c in _shell_commands(text) if c and c != "<verb>"]
        assert real, f"{path.parent.name}: no shell command"


def test_mcp_tool_ids_are_the_ones_clients_register():
    """The skills name the tools as Claude Code lists them: `mcp__<server>__<tool>`
    from a project config, `mcp__plugin_<plugin>_<server>__<tool>` from the
    plugin. A rename of the plugin or the server breaks these silently."""
    server_name = next(iter(json.loads((PLUGIN / ".mcp.json").read_text())["mcpServers"]))
    plugin_name = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["name"]
    prefixes = {server_name, f"plugin_{plugin_name}_{server_name}"}
    seen = 0
    for path in SKILL_FILES:
        for prefix, tool in _TOOL_ID.findall(path.read_text()):
            seen += 1
            assert prefix in prefixes, f"{path.parent.name}: mcp__{prefix}__{tool}"
            assert tool in TOOL_NAMES or tool == "<tool>", f"{path.parent.name}: mcp__{prefix}__{tool}"
    assert seen


def test_skills_have_no_em_dashes():
    """House style for the project's own prose (James, 2026-09-20)."""
    for path in SKILL_FILES:
        assert "\u2014" not in path.read_text(), path.parent.name
