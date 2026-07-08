---
name: repo-graph-trace
description: Follow the code across boundaries — a feature end-to-end, or the shortest path between two nodes (e.g. a frontend action to its backend handler). Links across the stack in one call instead of grepping both sides.
---

# repo-graph trace

Connect things across modules or the front/back boundary — a whole feature's path, or two specific endpoints.

## When to use

- "How does the checkout feature flow, entry to data store?"
- "Where does this frontend action hit the backend?"
- "How does X reach Y?" across files, layers, or the stack.

## Steps

1. A whole feature: call `trace` with one argument (`from_node=<feature>`) → the ordered path across the stack, each hop labelled with its mechanism (call / HTTP / queue / event), cross-service hops marked. The old separate `flow` tool is folded into this one-argument mode.
2. Two specific nodes: call `trace` with `from_node=<node>` and `to_node=<node>` → the shortest path, hop by hop with tier transitions. If you're unsure of the exact names, call `find` first.
3. Report the path file by file.

If there's no path, the two aren't connected in the graph — say so plainly rather than guessing a link.
