"""Install-surface contract — the things a marketplace / `uvx` install depends on.

A one-click install (VS Code MCP gallery, Cursor, the MCP registry) launches a
pypi server as `uvx <pypi-name>`, and `uvx <pkg>` runs the console script whose
name equals the package name. If no `mcp-repo-graph` script exists, every such
install fails with "command not found" — so this is a hard contract, not a nicety.

server.json is what those clients read to build the launch command, so it must
stay version-synced with pyproject and declare a runnable spec.
"""

import json
import tomllib
from importlib.metadata import entry_points
from pathlib import Path

import repo_graph.server as srv

ROOT = Path(__file__).resolve().parent.parent


def _console_scripts() -> dict[str, str]:
    group = entry_points().select(group="console_scripts")
    return {e.name: e.value for e in group}


def test_uvx_command_exists():
    """`uvx mcp-repo-graph` only resolves if a script of that exact name exists."""
    scripts = _console_scripts()
    assert "mcp-repo-graph" in scripts, (
        "no `mcp-repo-graph` console script — `uvx mcp-repo-graph` and marketplace "
        "one-click installs would fail. (Reinstall after pyproject edits: pip install -e .)"
    )
    assert scripts["mcp-repo-graph"] == "repo_graph.server:main"


def test_legacy_commands_preserved():
    """Existing .mcp.json configs reference `repo-graph` / `repo-graph-init`."""
    scripts = _console_scripts()
    assert scripts.get("repo-graph") == "repo_graph.server:main"
    assert scripts.get("repo-graph-init") == "repo_graph.init:main"


def test_server_json_synced_and_runnable():
    server = json.loads((ROOT / "server.json").read_text())
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    version = pyproject["project"]["version"]

    assert server["version"] == version
    pkg = server["packages"][0]
    assert pkg["version"] == version
    assert pkg["identifier"] == pyproject["project"]["name"] == "mcp-repo-graph"
    assert pkg["registryType"] == "pypi"
    # runtimeHint tells clients to launch via uvx; the identifier must be a
    # uvx-runnable command — which is exactly what test_uvx_command_exists locks.
    assert pkg["runtimeHint"] == "uvx"
    assert pkg["transport"]["type"] == "stdio"


# ── git-URL repo resolution (--repo accepts a local path OR a git project) ────


def test_git_urls_detected():
    for u in [
        "https://github.com/org/repo",
        "https://github.com/org/repo.git",
        "http://example.com/x.git",
        "git@github.com:org/repo.git",
        "ssh://git@host/org/repo.git",
        "git+https://github.com/org/repo",
    ]:
        assert srv._looks_like_git_url(u), u


def test_local_paths_not_git_urls():
    for p in ["/home/ivy/Code/repo", "./rel", "../up", "plain_dir", "/tmp/x"]:
        assert not srv._looks_like_git_url(p), p


def test_resolve_passes_through_local_path(tmp_path):
    # a local path must be returned untouched (no clone attempted)
    assert srv._resolve_repo(str(tmp_path)) == str(tmp_path)
