# Change Log

## 0.4.20

- Tracks `mcp-repo-graph` 0.4.20: the tool surface collapses from 13 to **6** —
  `orient`, `find`, `impact`, `trace`, `read`, `refresh` — each backed by a Rust
  engine primitive that returns a complete, ranked, located answer in one call.
  `find` now also resolves stacktraces / failing tests / diffs (was `locate`) and
  can fan out to the surrounding neighbourhood (was `activate`); `impact` is
  engine-ranked with likely-dead code flagged `⊘` and subsumes `neighbours`;
  `trace` covers both a feature end-to-end (was `flow`) and the path between two
  nodes; `orient` folds in `status` / `dense_text` / `graph_view` and surfaces a
  blind-spots note. No config change — the provider command is unchanged.

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
