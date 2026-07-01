"""Tests for `repo-graph install` / `uninstall`.

Covers the marker engine, config file IO, per-agent config writing (native
format/key per agent), instruction injection, permissions, idempotency,
non-destructive merges, and clean uninstall. HOME is redirected to a tmp dir so
user-scope writes never touch the real home.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from repo_graph.installer import (
    install,
    uninstall,
    resolve_targets,
    REGISTRY,
    all_targets,
)
from repo_graph.installer import core, targets as targets_mod
from repo_graph.installer.constants import SERVER_NAME, TOOL_NAMES, instructions_block
from repo_graph.installer.markers import upsert_section, remove_section, has_section
from repo_graph.installer import fileio


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Redirect HOME/USERPROFILE/APPDATA to a tmp dir; yield a fresh repo dir."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("APPDATA", str(home / "AppData/Roaming"))
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo


# ── surface lock ──────────────────────────────────────────────────────────────


async def test_tool_names_match_server_registry():
    """The installer's TOOL_NAMES must mirror the live MCP tool registry, so the
    auto-allow lists it writes never drift from what the server exposes."""
    import repo_graph.server as srv

    tools = await srv.mcp.list_tools()
    assert set(t.name for t in tools) == set(TOOL_NAMES)


def test_registry_has_nine_agents():
    assert len(all_targets()) == 9
    assert set(REGISTRY) == {
        "claude-code", "claude-desktop", "cursor", "windsurf", "vscode",
        "codex", "gemini", "opencode", "kiro",
    }


# ── markers ───────────────────────────────────────────────────────────────────


def test_marker_upsert_lifecycle():
    block = instructions_block()
    content, status = upsert_section("", block)
    assert status == "created" and has_section(content)

    same, status = upsert_section(content, block)
    assert status == "unchanged" and same == content

    changed, status = upsert_section(content, block.replace("structural map", "structural map v2"))
    assert status == "updated"

    removed, status = remove_section(changed)
    assert status == "removed" and not has_section(removed)

    _, status = remove_section("no markers here")
    assert status == "not-found"


def test_marker_preserves_surrounding_content():
    original = "# My project\n\nKeep me.\n"
    injected, _ = upsert_section(original, instructions_block())
    assert "Keep me." in injected
    stripped, _ = remove_section(injected)
    assert "Keep me." in stripped
    assert not has_section(stripped)


# ── fileio ────────────────────────────────────────────────────────────────────


def test_jsonc_tolerant_load(tmp_path):
    p = tmp_path / "c.json"
    p.write_text('{\n  // a comment\n  "mcpServers": {},\n}\n')
    assert fileio.load_json(p) == {"mcpServers": {}}


def test_toml_render_and_remove():
    block = fileio.render_toml_table("mcp_servers.repo-graph",
                                     {"command": "uvx", "args": ["mcp-repo-graph", "--repo", "."]})
    parsed = tomllib.loads(block)
    assert parsed["mcp_servers"]["repo-graph"]["command"] == "uvx"

    text = "[other]\nx = 1\n\n" + block
    new, removed = fileio.remove_toml_table(text, "mcp_servers.repo-graph")
    assert removed
    assert "repo-graph" not in new
    assert tomllib.loads(new)["other"]["x"] == 1


# ── resolve_targets ───────────────────────────────────────────────────────────


def test_resolve_targets_variants(monkeypatch):
    assert len(resolve_targets("all")) == 9
    assert resolve_targets("none") == []
    ids = [t.id for t in resolve_targets("cursor,codex")]
    assert ids == ["cursor", "codex"]
    with pytest.raises(ValueError):
        resolve_targets("cursor,bogus")


def test_resolve_auto_falls_back_to_claude(monkeypatch):
    monkeypatch.setattr(core, "detected_targets", lambda: [])
    got = resolve_targets("auto")
    assert [t.id for t in got] == ["claude-code"]


# ── install: per-agent native formats ─────────────────────────────────────────


def test_install_claude_code(sandbox):
    install(sandbox, [REGISTRY["claude-code"]], scope="project", dry=False)
    cfg = json.loads((sandbox / ".mcp.json").read_text())
    assert cfg["mcpServers"][SERVER_NAME]["args"] == ["mcp-repo-graph", "--repo", "."]
    assert has_section((sandbox / "CLAUDE.md").read_text())
    perms = json.loads((sandbox / ".claude/settings.json").read_text())
    assert f"mcp__{SERVER_NAME}__*" in perms["permissions"]["allow"]


def test_install_vscode_uses_servers_key(sandbox):
    install(sandbox, [REGISTRY["vscode"]], scope="project", dry=False)
    cfg = json.loads((sandbox / ".vscode/mcp.json").read_text())
    assert "servers" in cfg and "mcpServers" not in cfg
    assert cfg["servers"][SERVER_NAME]["type"] == "stdio"


def test_install_codex_writes_toml(sandbox):
    install(sandbox, [REGISTRY["codex"]], scope="project", dry=False)
    parsed = tomllib.loads((sandbox / ".codex/config.toml").read_text())
    assert parsed["mcp_servers"][SERVER_NAME]["command"] == "uvx"
    assert (sandbox / "AGENTS.md").is_file()


def test_install_opencode_mcp_key_and_array(sandbox):
    install(sandbox, [REGISTRY["opencode"]], scope="project", dry=False)
    cfg = json.loads((sandbox / "opencode.json").read_text())
    entry = cfg["mcp"][SERVER_NAME]
    assert entry["type"] == "local"
    assert entry["command"] == ["uvx", "mcp-repo-graph", "--repo", "."]
    assert cfg["permission"][f"{SERVER_NAME}*"] == "allow"


def test_install_per_entry_permissions(sandbox):
    install(sandbox, [REGISTRY["gemini"], REGISTRY["kiro"], REGISTRY["windsurf"]],
            scope="project", dry=False)
    gem = json.loads((sandbox / ".gemini/settings.json").read_text())
    assert gem["mcpServers"][SERVER_NAME]["trust"] is True
    kiro = json.loads((sandbox / ".kiro/settings/mcp.json").read_text())
    assert kiro["mcpServers"][SERVER_NAME]["autoApprove"] == ["*"]
    # Windsurf is user-scope only; alwaysAllow lists every tool.
    ws = json.loads((Path.home() / ".codeium/windsurf/mcp_config.json").read_text())
    assert ws["mcpServers"][SERVER_NAME]["alwaysAllow"] == list(TOOL_NAMES)


def test_install_cursor_mdc_frontmatter(sandbox):
    install(sandbox, [REGISTRY["cursor"]], scope="project", dry=False)
    mdc = (sandbox / ".cursor/rules/repo-graph.mdc").read_text()
    assert mdc.startswith("---")
    assert "alwaysApply: true" in mdc
    assert has_section(mdc)


def test_claude_desktop_user_scope_absolute_repo(sandbox):
    install(sandbox, [REGISTRY["claude-desktop"]], scope="project", dry=False)
    cfg_path = Path.home() / ".config/Claude/claude_desktop_config.json"
    cfg = json.loads(cfg_path.read_text())
    # No project cwd for a desktop app -> absolute --repo.
    assert cfg["mcpServers"][SERVER_NAME]["args"][-1] == str(sandbox)


# ── flags ─────────────────────────────────────────────────────────────────────


def test_no_permissions_no_instructions(sandbox):
    install(sandbox, [REGISTRY["claude-code"]], scope="project",
            permissions=False, instructions=False, dry=False)
    assert (sandbox / ".mcp.json").is_file()
    assert not (sandbox / "CLAUDE.md").exists()
    assert not (sandbox / ".claude/settings.json").exists()


def test_dry_run_writes_nothing(sandbox):
    changes = install(sandbox, all_targets(), scope="project", dry=True)
    assert changes  # reports intended changes
    assert not (sandbox / ".mcp.json").exists()
    assert not (sandbox / "CLAUDE.md").exists()


# ── idempotency ───────────────────────────────────────────────────────────────


def test_install_is_idempotent(sandbox):
    install(sandbox, all_targets(), scope="project", dry=False)
    second = install(sandbox, all_targets(), scope="project", dry=False)
    assert all(c.action == "unchanged" for c in second), \
        [c for c in second if c.action != "unchanged"]


# ── non-destructive ───────────────────────────────────────────────────────────


def test_preserves_existing_servers_and_content(sandbox):
    (sandbox / ".mcp.json").write_text(json.dumps(
        {"mcpServers": {"other": {"command": "x", "args": []}}}))
    (sandbox / "CLAUDE.md").write_text("# Notes\n\nDo not lose this.\n")

    install(sandbox, [REGISTRY["claude-code"]], scope="project", dry=False)

    cfg = json.loads((sandbox / ".mcp.json").read_text())
    assert "other" in cfg["mcpServers"] and SERVER_NAME in cfg["mcpServers"]
    md = (sandbox / "CLAUDE.md").read_text()
    assert "Do not lose this." in md and has_section(md)


# ── uninstall ─────────────────────────────────────────────────────────────────


def test_uninstall_reverses_everything(sandbox):
    install(sandbox, all_targets(), scope="project", dry=False)
    uninstall(sandbox, all_targets(), dry=False)

    # Owned / created-empty files are gone; the marker block is stripped.
    assert not (sandbox / ".mcp.json").exists()
    assert not (sandbox / "CLAUDE.md").exists()
    assert not (sandbox / ".codex/config.toml").exists()
    assert not (sandbox / ".cursor/rules/repo-graph.mdc").exists()
    assert not (sandbox / "opencode.json").exists()
    assert not has_section((sandbox / "AGENTS.md").read_text()) if (sandbox / "AGENTS.md").exists() else True

    settings = sandbox / ".claude/settings.json"
    if settings.exists():
        allow = json.loads(settings.read_text()).get("permissions", {}).get("allow", [])
        assert f"mcp__{SERVER_NAME}__*" not in allow


def test_uninstall_keeps_user_content(sandbox):
    (sandbox / "CLAUDE.md").write_text("# Keep\n\nMine.\n")
    (sandbox / ".mcp.json").write_text(json.dumps(
        {"mcpServers": {"other": {"command": "x", "args": []}}}))
    install(sandbox, [REGISTRY["claude-code"]], scope="project", dry=False)
    uninstall(sandbox, [REGISTRY["claude-code"]], dry=False)

    assert "Mine." in (sandbox / "CLAUDE.md").read_text()
    assert not has_section((sandbox / "CLAUDE.md").read_text())
    cfg = json.loads((sandbox / ".mcp.json").read_text())
    assert "other" in cfg["mcpServers"] and SERVER_NAME not in cfg["mcpServers"]


# ── CLI entry ─────────────────────────────────────────────────────────────────


def test_cli_dry_run_returns_zero(sandbox, capsys):
    rc = core.main(["install", "--repo", str(sandbox), "--agents", "claude-code", "--dry-run"])
    assert rc == 0
    assert "dry-run" in capsys.readouterr().out
    assert not (sandbox / ".mcp.json").exists()


def test_cli_print_config(sandbox, capsys):
    rc = core.main(["install", "--repo", str(sandbox), "--print-config", "vscode"])
    assert rc == 0
    assert '"servers"' in capsys.readouterr().out


def test_cli_unknown_agent_exits_two(sandbox, capsys):
    rc = core.main(["install", "--repo", str(sandbox), "--agents", "bogus", "--yes"])
    assert rc == 2
