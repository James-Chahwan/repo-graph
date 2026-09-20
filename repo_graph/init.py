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

import glia_py

from .gitexclude import ensure_cache_excluded
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
    # `incremental=True` explicitly: since glia 0.5.0 the default is False (a
    # cold full reparse), and the bootstrap wants the parse cache.
    pg = glia_py.generate(str(repo_root), incremental=True)
    # `generate` is a pure build now — this save is what gives the first server
    # query a warm layout, and the documented pre-commit `git add .glia/graph`
    # something to stage.
    try:
        pg.save_to_default(str(repo_root))
    except Exception:
        pass  # read-only fs / perms shouldn't fail the bootstrap
    # Keep the layout out of `git status` (skipped if the pre-commit hook commits it).
    ensure_cache_excluded(glia_py.default_gmap_dir(str(repo_root)))
    print(f"  {pg.node_count()} nodes, {pg.edge_count()} edges, "
          f"{pg.cross_edge_count()} cross-stack edges")
    print(f"  Engine: glia-py {glia_py.version()}")

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
