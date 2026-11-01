# repo-graph: Claude Code plugin

Ships [repo-graph](https://github.com/James-Chahwan/repo-graph) as a Claude Code
plugin. On enable it starts the MCP server (`uvx mcp-repo-graph`) against your
current workspace. The agent gets a structural map of your codebase and
navigates by structure instead of grepping.

## Install

```
/plugin install repo-graph --marketplace James-Chahwan/repo-graph
```

## Requirements

- [`uv`](https://docs.astral.sh/uv/) on your `PATH`. `uvx` fetches the package and
  its prebuilt Rust engine wheel on first run. No Python or Rust setup.

## What it provides

An MCP server (`repo-graph`) with 6 tools, listed in Claude Code as
`mcp__plugin_repo-graph_repo-graph__<tool>`:

- `orient`: repo shape, entry points, and where the graph is blind.
- `find`: any text (symbol, keyword, stacktrace, failing test or diff) to the
  ranked nodes that matter.
- `impact`: blast radius, ranked and located, with dead code flagged `⊘`.
- `trace`: a feature end to end, or the path between two nodes.
- `read`: a node's source, sliced by its line span.
- `refresh`: rebuild the graph.

Six skills tell the agent when and how to reach for them: `/repo-graph:glia-orient`,
`-find`, `-debug`, `-impact`, `-trace` and `-init`, plus `glia` (the full CLI
reference) and `glia-overlay`. Each task skill also gives the matching shell command
(`glia find ...`, or `uvx mcp-repo-graph find ...`) for a session where the MCP
server isn't connected.

The skills live in glia (`skills/` in the glia repo). The repo's top-level
[`skills/`](../skills) is a copy of them, and `skills/` here is a copy of that,
because a marketplace install copies only this directory. Run `make skills` (with
glia checked out at `../glia`, or `GLIA=<path>`) to take both from glia.
`tests/test_skills.py` fails while the two differ.

## Validate & submit

```bash
claude plugin validate ./claude-plugin --strict
```

Submit to the official plugin directory at clau.de/plugin-directory-submission
(per claude.com/docs/plugins). See [PRIVACY.md](../PRIVACY.md) for the privacy policy.

MIT licensed.
