# repo-graph — Claude Code plugin

Ships [repo-graph](https://github.com/James-Chahwan/repo-graph) as a Claude Code
plugin. On enable it starts the MCP server (`uvx mcp-repo-graph`) against your
current workspace — the AI gets a structural map of your codebase and navigates by
structure instead of grepping.

## Requirements

- [`uv`](https://docs.astral.sh/uv/) on your `PATH`. `uvx` fetches the package and
  its prebuilt Rust engine wheel on first run — no Python/Rust setup.

## What it provides

An MCP server (`repo-graph`) exposing 6 tools: `orient` (repo shape, entry
points, and where the graph is blind), `find` (any text — symbol, keyword,
stacktrace, failing test, or diff — → the ranked nodes that matter), `impact`
(blast radius, ranked and located, dead code flagged `⊘`), `trace` (a feature
end-to-end, or the path between two nodes), `read` (a node's exact source), and
`refresh` (rebuild). The server maps the workspace it's launched in.

Plus matching skills (`repo-graph-orient`, `-find`, `-impact`, `-trace`,
`-debug`, `-init`) that tell the agent when and how to reach for each tool.

## Validate & submit

```bash
claude plugin validate ./claude-plugin --strict
```

Submit to the official plugin directory at clau.de/plugin-directory-submission
(per claude.com/docs/plugins). See [PRIVACY.md](../PRIVACY.md) for the privacy policy.

MIT licensed.
