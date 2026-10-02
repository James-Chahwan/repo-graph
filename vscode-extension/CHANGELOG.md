# Change Log

## 0.5.2

- Tracks `mcp-repo-graph` 0.5.2, which moves onto the **glia 0.5.1** engine,
  pinned exactly. Same six tools; the graph is richer (on our Go + Angular demo
  repo, 2,939 → 3,466 nodes and 5,129 → 6,869 edges). Mounted Go routes carry
  their prefix, frontend endpoints pair through their base URL, and many more
  Go / Swift / C++ / Dart / TS calls resolve.
- `read` on a WebSocket / gRPC / GraphQL / tRPC client now shows the host it
  dials, instead of listing it as a caller.
- The server holds its memory over long sessions. It used to grow on every
  background rebuild (2.4 GB after two days on a busy repo); it now levels off.
- The cached graph rebuilds once on first start after the upgrade.

## 0.5.1

- Tracks `mcp-repo-graph` 0.5.1, which moves the server onto the **MCP Python SDK
  2.x** (`FastMCP` becomes `MCPServer`). The `mcp[cli]<2` cap is lifted. This is a
  server-side change only. The protocol and the tool schemas on the wire are
  byte-identical, so no client or config is affected.

## 0.5.0

- Tracks `mcp-repo-graph` 0.5.0, which moves onto the **glia 0.5.0** engine
  (the engine package is renamed `repo-graph-py` → `glia-py`). Same six tools,
  better answers:
  - **Empty answers now explain themselves.** When nothing matches, the engine
    returns why: the reason, whether it's a fact or a heuristic, and which
    extractions are partial for that mechanism. Better than a bare "not found".
  - **`impact` takes a whole diff in one call.** Many seeds, one walk, one
    ranking. Names that don't resolve come back listed rather than failing the
    call.
  - **`trace` returns ranked distinct paths** across the stack, and a two-node
    trace follows real mechanism-labelled hops instead of a structural
    shortest path.
  - **Declared components and services are labelled as such.** An Angular
    component reads as `component`, not `class`.
  - Entry points, liveness and cell labels all come from the engine's own
    tables, so the extension can't drift from the engine's vocabulary.
  - The graph cache moved from `.ai/repo-graph/` to `.glia/graph/`, which
    ignores itself so it never shows up in `git status`.
- No config change — the provider command is unchanged.

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
