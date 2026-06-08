# repo-graph — Claude Code plugin

Ships [repo-graph](https://github.com/James-Chahwan/repo-graph) as a Claude Code
plugin. On enable it starts the MCP server (`uvx mcp-repo-graph`) against your
current workspace — the AI gets a structural map of your codebase and navigates by
structure instead of grepping.

## Requirements

- [`uv`](https://docs.astral.sh/uv/) on your `PATH`. `uvx` fetches the package and
  its prebuilt Rust engine wheel on first run — no Python/Rust setup.

## What it provides

An MCP server (`repo-graph`) exposing 13 tools: `status`, `flow`, `trace`,
`impact`, `neighbours`, `read`, `activate`, `find`, `locate`, `dense_text`,
`graph_view`, `generate`, `reload`. `locate` resolves a stacktrace / failing
test / diff to the relevant nodes; `read` slices a node's source. The server
maps the workspace it's launched in.

## Validate & submit

```bash
claude plugin validate ./claude-plugin --strict
```

Submit to the official plugin directory at clau.de/plugin-directory-submission
(per claude.com/docs/plugins). See [PRIVACY.md](../PRIVACY.md) for the privacy policy.

MIT licensed.
