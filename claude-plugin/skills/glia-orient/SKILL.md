---
name: glia-orient
description: Map a codebase before opening files. Shows the services and how they talk, the entry points and where each flows, and where the glia graph is blind. Use at the start of a task in an unfamiliar or large repo, or when asked how a codebase is laid out or what's in it.
---

# Orient in a codebase

Get the shape of a repo from its structural graph instead of opening files one by one.

## Transports

Use whichever is available, in this order: the repo-graph MCP tools when loaded (`mcp__repo-graph__<tool>`, or `mcp__plugin_repo-graph_repo-graph__<tool>` from the Claude Code plugin; they may be deferred, so search your tool list first); the `glia` CLI when on PATH; else `uvx --from glia-cli glia <command> ..` (no install; the first run downloads the wheel); else `uvx mcp-repo-graph <verb>`. The MCP tools and `uvx mcp-repo-graph` print the same text; the glia CLI answers the same question with `--json` rows (`file`, `line`, tier). Run any of them at the repo root (`.` below).

| Want | MCP tool call | glia CLI | uvx mcp-repo-graph |
|---|---|---|---|
| Can the graph be trusted here? | | `glia health . --json` | |
| Overview | `orient` | `glia arch . --json` and `glia flows . --json` | `uvx mcp-repo-graph orient` |
| Map around one node | `orient seed=<node>` | `glia trace . <node> --json` | `uvx mcp-repo-graph orient "<node>"` |
| Whole-repo map | `orient full=true` | `glia arch . --include-shared --json` | `uvx mcp-repo-graph orient --full` |
| Where the graph is blind | the overview's **Blind spots** | `glia coverage . --json` | `uvx mcp-repo-graph orient` |
| What could not be paired, what looks dead | | `glia gaps . --json` | |

The glia CLI has no `orient` verb: `health`, `arch`, `flows`, `coverage` and `gaps` answer its parts.

## Steps

1. On a repo you have not seen before, run `glia health . --json` first (CLI only). Its `verdict` is the worst row: per boundary mechanism (http, grpc, rpc, graphql, queue, ws) how much of the client and server side the graph pairs (`OK`, `DEGRADED`, `BLIND`, with the reason and the measure, e.g. `servers reached 1% of 436`), then `parse` (code files no parser read), `workspace_unresolved` (in-repo packages imported by name and bound to nothing) and the dead-symbol share. A `BLIND` mechanism means every answer through it (a contract break, an unpaired route, a cross-service trace) is glia not seeing, not an absence: say so in the report and grep that part. A `library` role is never judged on reach.
2. Run the overview. Over MCP it lists node and edge counts, the node kinds, the entry points (routes, CLI commands, handlers, jobs) and a **Blind spots** section. On the CLI, `glia arch . --json` gives the services and the links between them (HTTP, gRPC, queue, event), and `glia flows . --json` the entry points with where each one goes.
3. Read the blind spots before trusting any "not found": `glia coverage . --json` lists the edge kinds and languages this repo's graph under-links, how many it did find, and what to grep instead. Those are the places grep is still needed.
4. `glia gaps . --json` lists what could not be paired (a client call with no server route, a route nothing calls) and the likely-dead symbols.
5. To zoom in on one area, take a node name from the overview or from a `find` and seed the map with it (`orient seed=<node>`, or `glia trace . <node> --json` for the flows through it).

Report the main entry points and how they layer (entry, service, handler, data). Then pick up `glia-find`, `glia-trace` or `glia-impact` for the task itself.

Siblings: `glia-orient`, `glia-find`, `glia-debug`, `glia-impact`, `glia-trace`, `glia-init`; `glia` is the full CLI reference (every command, flag and answer shape).
