"""
repo-graph-init — first-run setup for a target repository.

1. Generates the structural graph (nodes, edges, flows)
2. Adds repo-graph MCP server to .mcp.json
3. Adds usage instructions to CLAUDE.md

Idempotent — safe to run multiple times.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from .generator import generate

# ── CLAUDE.md block ──────────────────────────────────────────────────────────

CLAUDE_MD_MARKER = "<!-- repo-graph -->"

CLAUDE_MD_BLOCK = f"""{CLAUDE_MD_MARKER}
## repo-graph

A structural map of this codebase is available via MCP tools.

1. **Always start** with `status`, then `flow <feature>` or `impact <node>` to find the relevant files.
2. **Trust the results.** Read only the files repo-graph identifies. Do not grep, glob, or explore beyond them unless they don't contain the answer.
3. **Fix and stop.** Do not explore related code, verify call sites, or investigate beyond the immediate task.
<!-- /repo-graph -->"""


# ── .mcp.json ────────────────────────────────────────────────────────────────


def _update_mcp_json(repo_root: Path) -> bool:
    """Add repo-graph to .mcp.json. Returns True if file was modified."""
    mcp_path = repo_root / ".mcp.json"

    if mcp_path.exists():
        try:
            config = json.loads(mcp_path.read_text())
        except (json.JSONDecodeError, OSError):
            config = {}
    else:
        config = {}

    servers = config.setdefault("mcpServers", {})

    if "repo-graph" in servers:
        return False

    servers["repo-graph"] = {
        "type": "stdio",
        "command": "repo-graph",
        "args": ["--repo", str(repo_root)],
    }

    mcp_path.write_text(json.dumps(config, indent=2) + "\n")
    return True


# ── CLAUDE.md ────────────────────────────────────────────────────────────────


def _update_claude_md(repo_root: Path) -> bool:
    """Add repo-graph section to CLAUDE.md. Returns True if file was modified."""
    claude_md = repo_root / "CLAUDE.md"

    if claude_md.exists():
        content = claude_md.read_text()
        if CLAUDE_MD_MARKER in content:
            return False
        # Append to existing file
        if not content.endswith("\n"):
            content += "\n"
        content += "\n" + CLAUDE_MD_BLOCK + "\n"
    else:
        content = CLAUDE_MD_BLOCK + "\n"

    claude_md.write_text(content)
    return True


# ── Main ─────────────────────────────────────────────────────────────────────


def init(repo_root: Path) -> None:
    """Run full init: generate graph, configure MCP, update CLAUDE.md."""
    repo_root = repo_root.resolve()

    if not repo_root.is_dir():
        print(f"Not a directory: {repo_root}", file=sys.stderr)
        sys.exit(1)

    # 1. Generate graph
    print(f"Generating graph for {repo_root}...")
    nodes, edges, flows = generate(repo_root)
    print(f"  {len(nodes)} nodes, {len(edges)} edges, {len(flows)} flows")

    # 2. Configure MCP server
    if _update_mcp_json(repo_root):
        print(f"  Added repo-graph to .mcp.json")
    else:
        print(f"  .mcp.json already configured")

    # 3. Add CLAUDE.md instructions
    if _update_claude_md(repo_root):
        print(f"  Added repo-graph section to CLAUDE.md")
    else:
        print(f"  CLAUDE.md already has repo-graph section")

    print()
    print("Done. Start a new Claude Code session to use repo-graph.")


def main():
    parser = argparse.ArgumentParser(
        description="Initialize repo-graph for a repository"
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("REPO_GRAPH_REPO", os.getcwd()),
        help="Path to the target repository",
    )
    args = parser.parse_args()
    init(Path(args.repo))


if __name__ == "__main__":
    main()
