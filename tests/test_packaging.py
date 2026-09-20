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


# ── Claude submission contract: every tool needs title + a read/destructive hint ──


async def test_all_tools_have_submission_annotations():
    tools = await srv.mcp.list_tools()
    assert len(tools) == 6
    for t in tools:
        ann = t.annotations
        assert ann is not None and ann.title, f"{t.name} missing annotations.title"
        assert (ann.read_only_hint is not None) or (ann.destructive_hint is not None), (
            f"{t.name} needs read_only_hint or destructive_hint"
        )


def test_mcp_sdk_floor_is_2():
    """The 1.x/2.x split is a hard fork of the server class: 1.x has `FastMCP`
    and 2.x has `MCPServer`, and `mcp.server.fastmcp` in 2.x is a stub that
    raises on import. server.py imports `MCPServer`, so the floor must be >=2 —
    an unpinned or 1.x-allowing range crashes every fresh install, which is
    exactly what an uncapped `mcp>=1` did for two months from 2026-07-28."""
    deps = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]
    spec = next(d for d in deps if d.startswith("mcp")).replace(" ", "")
    assert ">=2" in spec, f"mcp dependency must require 2.x: {spec!r}"
    assert "<2" not in spec, f"the <2 cap predates the MCPServer port: {spec!r}"


def test_every_dependency_caps_its_major():
    """A published package resolves its dependencies fresh on the user's machine,
    so an uncapped major is a time bomb: `mcp>=1` let 2.0 in and broke every
    fresh install for two months before anyone noticed. Each cap is lifted by
    hand, after the port."""
    deps = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]
    uncapped = [d for d in deps if "<" not in d]
    assert not uncapped, (
        f"these dependencies have no upper bound: {uncapped}. A breaking major "
        "upstream would reach users as a runtime crash.")


def test_server_uses_the_2x_server_class():
    """Guard the rename itself — if someone reverts to FastMCP the dependency
    floor above stops matching the code."""
    src = (ROOT / "repo_graph" / "server.py").read_text()
    assert "from mcp.server.mcpserver import MCPServer" in src
    assert "FastMCP" not in src


# ── Every distribution manifest carries the same version ────────────────────

#: Each client/marketplace reads its own manifest, so a bump has to touch all of
#: them. Historically only pyproject↔server.json were tested and the other four
#: drifted silently (the VS Code extension sat a release behind through 0.5.0).
_VERSIONED_MANIFESTS = {
    "server.json": ("version",),
    ".plugin/plugin.json": ("version",),                        # Open Plugins / cursor.directory
    "claude-plugin/.claude-plugin/plugin.json": ("version",),   # Claude marketplace
    "mcpb/manifest.json": ("version",),                         # MCPB bundle / Smithery
    "vscode-extension/package.json": ("version",),              # VS Code Marketplace
}


def test_all_distribution_manifests_version_synced():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    drifted = {}
    for rel, (key,) in _VERSIONED_MANIFESTS.items():
        path = ROOT / rel
        if not path.exists():
            continue
        got = json.loads(path.read_text()).get(key)
        if got != version:
            drifted[rel] = got
    assert not drifted, (
        f"manifest version drift against pyproject {version}: {drifted}. "
        "Every one of these is read by a different client/marketplace — bump them together."
    )


def test_mcpb_manifest_tools_match_server_registry():
    """The MCPB bundle advertises its tool list to Claude Desktop and Smithery,
    so a tool-surface change has to reach it too."""
    from repo_graph.installer.constants import TOOL_NAMES

    manifest = json.loads((ROOT / "mcpb" / "manifest.json").read_text())
    declared = {t["name"] for t in manifest.get("tools", [])}
    assert declared == set(TOOL_NAMES), (
        f"mcpb/manifest.json tools drifted: missing={set(TOOL_NAMES) - declared}, "
        f"extra={declared - set(TOOL_NAMES)}"
    )
