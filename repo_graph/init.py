"""repo-graph-init — first-run setup for a target repository.

1. Builds the structural graph and caches it (so the first query is instant)
2. Wires repo-graph into Claude Code via the shared installer: MCP config
   (.mcp.json), the CLAUDE.md usage block, and auto-allow permissions

Idempotent — safe to run multiple times. For other agents (Cursor, VS Code,
Codex, Gemini, ...) or user-scope setup, use `repo-graph install`.
"""

import argparse
import os
import sys
from pathlib import Path

import repo_graph_py

from .installer import install, format_report, REGISTRY
from .installer.constants import MARKER_START

# Back-compat: tests and older callers import this. The installer owns the block.
CLAUDE_MD_MARKER = MARKER_START


def init(repo_root: Path, graph_only: bool = False) -> None:
    repo_root = repo_root.resolve()

    if not repo_root.is_dir():
        print(f"Not a directory: {repo_root}", file=sys.stderr)
        sys.exit(1)

    print(f"Generating graph for {repo_root}...")
    pg = repo_graph_py.generate(str(repo_root))
    # Cache the .gmap so the first server query is instant and the documented
    # pre-commit `git add .ai/repo-graph/` has something to stage.
    if hasattr(pg, "save_to_default"):
        try:
            pg.save_to_default(str(repo_root))
        except Exception:
            pass  # read-only fs / perms shouldn't fail the bootstrap
    print(f"  {pg.node_count()} nodes, {pg.edge_count()} edges, "
          f"{pg.cross_edge_count()} cross-stack edges")
    print(f"  Engine: repo-graph-py {repo_graph_py.version()}")

    if graph_only:
        # Used by the pre-commit hook: refresh + cache the graph, nothing else.
        return

    # Single code path for config + instructions + permissions (Claude Code).
    targets = [REGISTRY["claude-code"]]
    changes = install(repo_root, targets, scope="project",
                      permissions=True, instructions=True, dry=False)
    print(format_report(changes, targets, dry=False))

    print()
    print("Done. Start a new Claude Code session to use repo-graph.")
    print("Tip: `repo-graph install` also wires up Cursor, VS Code, Codex, Gemini, and more.")


def main():
    parser = argparse.ArgumentParser(
        description="Initialize repo-graph for a repository (build graph + wire Claude Code)"
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("REPO_GRAPH_REPO", os.getcwd()),
        help="Path to the target repository",
    )
    parser.add_argument(
        "--graph-only",
        action="store_true",
        help="Only (re)build and cache the graph; skip agent config/instructions "
             "(used by the pre-commit hook).",
    )
    args = parser.parse_args()
    init(Path(args.repo), graph_only=args.graph_only)


if __name__ == "__main__":
    main()
