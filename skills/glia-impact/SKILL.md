---
name: glia-impact
description: Blast radius before changing code. Lists everything a function, route, class or whole diff reaches or is reached by, ranked and located, with likely-dead code flagged. Use before a refactor, rename, delete or signature change, for a PR review, and for "who uses this" or "what breaks if I change this".
---

# Impact before a change

Know what a change touches before you make it, including the callers grep can't link: other files, other languages, the other side of an HTTP or queue boundary.

## Transports

Use whichever is available, in this order: the repo-graph MCP tools when loaded (`mcp__repo-graph__<tool>`, or `mcp__plugin_repo-graph_repo-graph__<tool>` from the Claude Code plugin; they may be deferred, so search your tool list first); the `glia` CLI when on PATH; else `uvx --from glia-cli glia <command> ..` (no install; the first run downloads the wheel); else `uvx mcp-repo-graph <verb>`. The MCP tools and `uvx mcp-repo-graph` print the same text; the glia CLI answers the same question with `--json` rows (`file`, `line`, tier). Run any of them at the repo root (`.` below).

| Want | MCP tool call | glia CLI | uvx mcp-repo-graph |
|---|---|---|---|
| Both directions, 4 hops | `impact nodes=<node>` | `glia blast-radius . <node> --json` | `uvx mcp-repo-graph impact "<node>"` |
| Who calls or depends on it (upstream) | `impact nodes=<node> direction=backward` | `glia blast-radius . <node> --direction backward --json` | `uvx mcp-repo-graph impact "<node>" --direction backward` |
| Direct neighbours only | `impact nodes=<node> depth=1` | `glia blast-radius . <node> --depth 1 --json` | `uvx mcp-repo-graph impact "<node>" --depth 1` |
| The uncommitted change | `impact nodes=<a>,<b>,<c>` | `glia diff-impact . --json` | `uvx mcp-repo-graph impact "<a>,<b>,<c>"` |
| A PR, as one report | | `glia review . --base main --title "<PR title>" --json` | |
| Who implements X, who serves a route | | `glia implementors . <node> --json`, `glia serves . "GET /api/orders" --json` | |

## Steps

1. Run it before you edit. Seed it with a name or qname; don't know it yet? Get it from the graph, not grep: `glia find . <word> --json`. Several seeds are one walk and one ranking.
2. Read the rows. They're ranked by relevance to the seeds (the `files` list ranks the files, co-change first when `glia history sync .` has run), and each has `file`, `line`, a `reason` saying why it's in scope (`CALLS`, `HTTP_CALLS`, `HANDLED_BY` ...) and its depth. `live: false` (`⊘`) means no entry point reaches the node, so it's likely dead; `--live-only` drops those.
3. For a change, skip the seeds: `glia diff-impact . --json` reads the uncommitted diff (`--base main` for a branch). For a PR, `glia review . --base main --title "<PR title>" --json` adds the tests to run, the edges by tier, new rule violations and the files the title's ids route to.
4. Report what's affected by tier (entry, service, handler, data). Call out what grep would miss: transitive dependents, callers in another file or service, and anything marked `⊘`.

If a dependency you expected is missing, check `glia coverage . --json` before trusting the gap. A URL built at runtime, or a call through reflection, can hide a real edge.

Siblings: `glia-orient`, `glia-find`, `glia-debug`, `glia-impact`, `glia-trace`, `glia-init`; `glia` is the full CLI reference (every command, flag and answer shape).
