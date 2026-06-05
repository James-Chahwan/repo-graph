"""Bundled launcher for the repo-graph MCPB.

The manifest's mcp_config launches `uvx mcp-repo-graph` directly (fetches the
package + prebuilt Rust engine wheel on first use). This file is the bundle's
declared entry_point and a fallback launcher: run it directly and it execs the
published server, preferring uvx and falling back to a pip-installed command.
"""
import os
import sys
from shutil import which


def main() -> None:
    repo = (
        os.environ.get("REPO_GRAPH_REPO")
        or (sys.argv[1] if len(sys.argv) > 1 else os.getcwd())
    )
    if which("uvx"):
        os.execvp("uvx", ["uvx", "mcp-repo-graph", "--repo", repo])
    os.execvp("mcp-repo-graph", ["mcp-repo-graph", "--repo", repo])


if __name__ == "__main__":
    main()
