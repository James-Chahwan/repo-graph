"""`repo-graph <tool> ...`: the six MCP tools as one-shot shell commands.

The contract is that a subcommand prints exactly what the MCP tool returns, and
takes exactly the tool's parameters, so the skills can offer either route.
"""

from __future__ import annotations

import inspect
import io
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_graph import cli
from repo_graph.installer.constants import TOOL_NAMES

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _run(capsys, *argv: str) -> tuple[int, str]:
    code = cli.run(list(argv))
    return code, capsys.readouterr().out


def test_subcommands_are_the_tools():
    assert tuple(cli.POSITIONAL) == TOOL_NAMES


@pytest.mark.parametrize("tool", TOOL_NAMES)
def test_every_tool_parameter_is_a_cli_argument(tool):
    from repo_graph import server

    sub = cli.build_parser()._subparsers._group_actions[0].choices[tool]
    dests = {a.dest for a in sub._actions}
    params = set(inspect.signature(getattr(server, tool)).parameters)
    assert params <= dests, f"{tool}: no CLI argument for {params - dests}"
    assert dests - params == {"help", "repo", "verbose"}


@pytest.mark.parametrize("argv, call", [
    (["orient"], ("orient", {})),
    (["orient", "--full", "--budget", "2000"], ("orient", {"full": True, "budget": 2000})),
    (["find", "User"], ("find", {"query": "User"})),
    (["find", "user", "--expand", "--top-k", "5"], ("find", {"query": "user", "expand": True, "top_k": 5})),
    (["impact", "List", "--direction", "backward"], ("impact", {"nodes": "List", "direction": "backward"})),
    (["impact", "List,Get", "--depth", "1"], ("impact", {"nodes": "List,Get", "depth": 1})),
    (["trace", "users"], ("trace", {"from_node": "users"})),
    (["read", "List", "--context-lines", "2"], ("read", {"node": "List", "context_lines": 2})),
])
def test_output_is_the_mcp_tool_output(mcp_server, capsys, argv, call):
    tool, kwargs = call
    want = getattr(mcp_server, tool)(**kwargs)
    code, out = _run(capsys, *argv, "--repo", mcp_server.REPO_PATH)
    assert code == 0
    assert out == want + "\n"


def test_refresh(mcp_server, capsys):
    code, out = _run(capsys, "refresh", "--repo", mcp_server.REPO_PATH)
    assert code == 0
    assert out.startswith("Rebuilt:") and "Engine: glia-py" in out


def test_dash_reads_the_positional_from_stdin(mcp_server, capsys, monkeypatch):
    diff = "diff --git a/backend/users/users.go b/backend/users/users.go\n@@ -1 +1 @@\n"
    want = mcp_server.find(diff, kind="diff")
    monkeypatch.setattr(sys, "stdin", io.StringIO(diff))
    code, out = _run(capsys, "find", "-", "--kind", "diff", "--repo", mcp_server.REPO_PATH)
    assert code == 0
    assert out == want + "\n"


@pytest.mark.parametrize("argv", [
    ["impact", "x", "--depth", "11"],      # MCP schema: le=10
    ["find", "x", "--top-k", "0"],         # ge=1
    ["impact", "x", "--dir", "backward"],  # no abbreviations
    ["trace"],                             # from_node is required
])
def test_rejects_what_the_mcp_schema_rejects(argv):
    with pytest.raises(SystemExit) as e:
        cli.build_parser().parse_args(argv)
    assert e.value.code == 2


def test_missing_repo_is_an_error(capsys, tmp_path):
    assert cli.run(["orient", "--repo", str(tmp_path / "nope")]) == 1
    assert "not a directory" in capsys.readouterr().err


# ── as a real process ─────────────────────────────────────────────────────────


def _console_script() -> str:
    """The `repo-graph` next to the interpreter under test, not whatever's on PATH."""
    candidate = Path(sys.executable).parent / "repo-graph"
    return str(candidate) if candidate.exists() else "repo-graph"


@pytest.fixture
def fresh_repo(tmp_path):
    """A fixture copy with no layout yet, so the first call builds (and logs)."""
    dst = tmp_path / "target"
    shutil.copytree(FIXTURES_DIR / "http_stack_smoke", dst)
    return dst


@pytest.mark.e2e
def test_console_script_answers_quietly(fresh_repo):
    res = subprocess.run([_console_script(), "orient", "--repo", str(fresh_repo)],
                         capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert res.returncode == 0, res.stderr
    assert "Entry points" in res.stdout
    # glia logs ~40 lines from Rust on a cold build, and (0.5.2) one more when
    # the graph is freed. An agent reading the command's output would pay for
    # every one.
    assert res.stderr == ""


@pytest.mark.e2e
def test_console_script_verbose_keeps_engine_log(fresh_repo):
    res = subprocess.run([_console_script(), "orient", "--repo", str(fresh_repo), "--verbose"],
                         capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert res.returncode == 0
    assert "[gmap]" in res.stderr


@pytest.mark.e2e
def test_console_script_sees_an_edit_without_a_watcher(fresh_repo):
    """Each call checks the cached layout first, so a one-shot answer is fresh."""
    exe = [_console_script(), "find", "brandNewHandler", "--repo", str(fresh_repo)]
    before = subprocess.run(exe, capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert "No answer" in before.stdout
    users = fresh_repo / "backend" / "users" / "users.go"
    users.write_text(users.read_text() + "\nfunc brandNewHandler() {}\n")
    after = subprocess.run(exe, capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert "backend/users/users.go" in after.stdout, after.stdout
