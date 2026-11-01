---
name: glia-trace
description: Follow a feature end to end across files, languages and services (frontend call, backend route, handler, data), or find the path between two named pieces of code. Use for "how does X work", "how does A reach B", or "which backend handler does this frontend call hit".
---

# Trace a feature across the stack

Connect code across modules and across the front/back boundary in one call, instead of grepping both sides and guessing the link.

## Transports

Use whichever is available, in this order: the repo-graph MCP tools when loaded (`mcp__repo-graph__<tool>`, or `mcp__plugin_repo-graph_repo-graph__<tool>` from the Claude Code plugin; they may be deferred, so search your tool list first); the `glia` CLI when on PATH; else `uvx --from glia-cli glia <command> ..` (no install; the first run downloads the wheel); else `uvx mcp-repo-graph <verb>`. The MCP tools and `uvx mcp-repo-graph` print the same text; the glia CLI answers the same question with `--json` rows (`file`, `line`, tier). Run any of them at the repo root (`.` below).

| Want | MCP tool call | glia CLI | uvx mcp-repo-graph |
|---|---|---|---|
| A feature end to end | `trace from_node=<feature>` | `glia trace . <feature> --json` | `uvx mcp-repo-graph trace "<feature>"` |
| The path from A to B | `trace from_node=<a> to_node=<b>` | `glia trace . <a> --to <b> --json` | `uvx mcp-repo-graph trace "<a>" "<b>"` |
| Why A and B are joined, edge by edge | | `glia why . <a> <b> --json` | |
| Every entry point and where it goes | `orient` | `glia flows . --json` | `uvx mcp-repo-graph orient` |

## Steps

1. One argument traces a feature: a keyword, a route (`GET /api/users`) or an entry point from `glia flows . --json`. You get ranked distinct paths from the entry through the stack, each hop labelled with its mechanism (`CALLS`, `HTTP_CALLS`, `HANDLED_BY`, queue, event, data access), with cross-service hops counted. `--depth` (default 6) caps the hops and `--max-paths` (default 10) the paths: `glia trace . checkout --depth 8 --json`.
2. Two names give the paths between them: `glia trace . <a> --to <b> --json`. Not sure of the names? `glia find . <word> --json` first and use the qnames.
3. To see why one hop exists, `glia why . <a> <b> --json` prints the edge's evidence: its tier, the rule that made it and the site (`file`, `line`) it was read at.
4. Report the path file by file, with `file:line` for each hop.

No path means the two aren't connected in the graph. Say so rather than inventing a link, but check `glia coverage . --json` first: a URL built at runtime or a call through reflection can hide a real one.

Siblings: `glia-orient`, `glia-find`, `glia-debug`, `glia-impact`, `glia-trace`, `glia-init`; `glia` is the full CLI reference (every command, flag and answer shape).
