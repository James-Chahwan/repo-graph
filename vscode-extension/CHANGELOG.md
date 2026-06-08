# Change Log

## 0.4.19

- Tracks `mcp-repo-graph` 0.4.19: surface grows to 13 tools — adds `locate`
  (resolve a stacktrace / failing test / diff to the most relevant nodes) and
  `read` (slice a node's source by its line span). `impact` now takes multiple
  comma-separated nodes; `activate` gains edge-weight `profile`s;
  `activate`/`impact`/`locate` gain `mode=prose`; `dense_text` gains `seed=`
  scoping. Incremental parse cache makes `generate`/`reload` re-parse only
  changed files. No config change — the provider command is unchanged.

## 0.4.16

- Initial release. Registers repo-graph as a zero-config MCP server provider:
  provisions `uvx mcp-repo-graph --repo <workspaceFolder>` so the open project is
  mapped automatically. Version tracks the `mcp-repo-graph` package.
