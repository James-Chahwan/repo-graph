"""Tests for `repo-graph-init` — the first-run bootstrapper.

Verifies .mcp.json gets created/updated and CLAUDE.md gets the marker block.
Idempotency is part of the contract.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from repo_graph.init import init, CLAUDE_MD_MARKER


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def target_repo(tmp_path):
    """Fresh copy of py_smoke to run init against."""
    dst = tmp_path / "target"
    shutil.copytree(FIXTURES_DIR / "py_smoke", dst)
    return dst


def test_init_creates_mcp_json(target_repo, capsys):
    init(target_repo)

    mcp_path = target_repo / ".mcp.json"
    assert mcp_path.exists()

    config = json.loads(mcp_path.read_text())
    assert "mcpServers" in config
    assert "repo-graph" in config["mcpServers"]
    entry = config["mcpServers"]["repo-graph"]
    # init now delegates to the shared installer -> zero-install uvx launch.
    assert entry["command"] == "uvx"
    assert "mcp-repo-graph" in entry["args"]
    assert "--repo" in entry["args"]


def test_init_creates_claude_md(target_repo, capsys):
    init(target_repo)

    claude_md = target_repo / "CLAUDE.md"
    assert claude_md.exists()

    content = claude_md.read_text()
    assert CLAUDE_MD_MARKER in content
    assert "repo-graph" in content
    assert "orient" in content  # core tool reference


def test_init_is_idempotent(target_repo, capsys):
    init(target_repo)
    mcp_content_first = (target_repo / ".mcp.json").read_text()
    claude_content_first = (target_repo / "CLAUDE.md").read_text()

    init(target_repo)
    mcp_content_second = (target_repo / ".mcp.json").read_text()
    claude_content_second = (target_repo / "CLAUDE.md").read_text()

    assert mcp_content_first == mcp_content_second, "init mutated .mcp.json on second run"
    assert claude_content_first == claude_content_second, "init mutated CLAUDE.md on second run"


def test_init_preserves_existing_claude_md(target_repo, capsys):
    """If CLAUDE.md already has content, init should append, not overwrite."""
    claude_md = target_repo / "CLAUDE.md"
    claude_md.write_text("# Project notes\n\nKeep this intact.\n")

    init(target_repo)

    content = claude_md.read_text()
    assert "Keep this intact." in content
    assert CLAUDE_MD_MARKER in content


def test_init_preserves_other_mcp_servers(target_repo, capsys):
    """Adding repo-graph should leave existing mcpServers entries untouched."""
    mcp_path = target_repo / ".mcp.json"
    mcp_path.write_text(json.dumps({
        "mcpServers": {
            "other-server": {"command": "other", "args": []}
        }
    }))

    init(target_repo)

    config = json.loads(mcp_path.read_text())
    assert "other-server" in config["mcpServers"]
    assert "repo-graph" in config["mcpServers"]
