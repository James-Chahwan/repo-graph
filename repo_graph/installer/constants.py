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
    "orient",
    "find",
    "impact",
    "trace",
    "read",
    "refresh",
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
## repo-graph — structural map (use it before grepping)

This project ships a repo-graph map of its own code — entities, relationships,
and cross-stack flows — exposed as six MCP tools. It answers where / what-uses /
how-does-X-reach-Y / what-breaks-if-I-change-this without reading many files.

FIRST, make sure the tools are loaded. If you do NOT see `repo-graph` tools
(`mcp__repo-graph__*`) in your available tools, they may be deferred — search
your tool list and load them before you start, instead of falling back to grep.

Then, for any structural question, use the graph before grepping across files:
- `orient` — first call on the repo: counts, entry points, and a `blind spots`
  note telling you which languages/edges the graph under-links (grep those).
- `find <text>` — turn a symbol, keyword, stacktrace, failing test, or diff into
  the ranked nodes that matter. Every row carries `path:line`.
- `impact <node>` — blast radius: what a change affects / depends on, ranked,
  located, with likely-dead code flagged `⊘`. This is where the graph wins.
- `trace <feature>` — a feature end to end across the stack (or `trace A B` for
  the path between two nodes), with each hop's mechanism labelled.
- `read <node>` — a node's exact source (comma-separate several to read a ranked
  set in one call).
- `refresh` — rebuild after a big refactor (routine edits are auto-picked-up).

Trust the graph's results — don't re-verify every node with grep, except where
`orient`'s blind-spots note says extraction is partial. Only a trivial
single-file lookup is faster with grep; anything structural starts here.

If this project has no `.ai/repo-graph/` directory and the tools aren't connected,
ignore this section."""


def instructions_block() -> str:
    """The full marker-fenced instructions block, ready to upsert into a file."""
    return f"{MARKER_START}\n{INSTRUCTIONS_BODY}\n{MARKER_END}"
