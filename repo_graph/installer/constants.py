"""Shared constants for the `repo-graph install` command.

The tool list here is a *contract*: it must mirror the MCP tools registered in
`repo_graph.server`. `tests/test_installer.py` asserts the two stay in sync so a
tool added/removed in the server can't silently drift the auto-allow lists the
installer writes into each agent's config.
"""

import re

# MCP server name — the key every agent config maps its entry under, and the
# `mcp__<server>__*` permission prefix for Claude Code.
SERVER_NAME = "repo-graph"

# A `--repo` value can be a local path or a git URL (the server clones it). Mirror
# server.py's detection so the installer writes URLs verbatim instead of mangling
# them through Path().resolve().
_GIT_URL_RE = re.compile(r"^(https?://|git@|ssh://|git\+)", re.IGNORECASE)


def looks_like_git_url(spec: str) -> bool:
    """True if `spec` is a git remote URL rather than a local path."""
    return bool(_GIT_URL_RE.match(spec)) or spec.endswith(".git")

# PyPI package launched by `uvx` (also the console-script name).
PACKAGE = "mcp-repo-graph"

# Every MCP tool the server exposes. Kept in registration order. Locked to the
# live registry by the installer test.
TOOL_NAMES = (
    "generate",
    "status",
    "dense_text",
    "flow",
    "trace",
    "impact",
    "neighbours",
    "read",
    "activate",
    "find",
    "locate",
    "graph_view",
    "reload",
)

# Marker sentinels for the injected instructions block. HTML comments so they're
# invisible in rendered markdown and survive the user's own surrounding content.
# An idempotent upsert replaces everything between them; uninstall removes it.
MARKER_START = "<!-- repo-graph:start -->"
MARKER_END = "<!-- repo-graph:end -->"

# The usage block injected into each agent's instructions file. Conditional last
# line makes it a safe no-op at user/global scope: in a repo without a graph the
# agent is told to ignore it.
INSTRUCTIONS_BODY = """\
## repo-graph

This project has a structural map available through the repo-graph MCP tools:
entities, relationships, and feature flows across the whole codebase. When the
tools are available, use them before grep/find/ripgrep or reading files top to
bottom.

- Start with `status` to orient. Then `dense_text` for the full map, or
  `activate` / `find` / `locate` to jump straight to the relevant nodes.
- Debugging an error? Paste the stacktrace, failing-test id, or diff into
  `locate`, then `read` the top node's source. No grepping first.
- Trust the results. Read only what repo-graph points at, and stop once you have
  the answer instead of exploring further.

If this project has no `.ai/repo-graph/` directory and the repo-graph tools are
not connected, ignore this section."""


def instructions_block() -> str:
    """The full marker-fenced instructions block, ready to upsert into a file."""
    return f"{MARKER_START}\n{INSTRUCTIONS_BODY}\n{MARKER_END}"
