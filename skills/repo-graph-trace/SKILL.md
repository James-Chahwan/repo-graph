---
name: repo-graph-trace
description: Find the shortest path between two nodes — e.g. a frontend action to its backend handler. Links across the stack in one call instead of grepping both sides.
---

# repo-graph trace

Connect two things across modules or the front/back boundary.

## When to use

- "Where does this frontend action hit the backend?"
- "How does X reach Y?" across files, layers, or the stack.

## Steps

1. Identify the two endpoints by name. If you're unsure of the exact names, call `find` first.
2. Call `trace` with `from=<node>` and `to=<node>`. It returns the shortest path with each hop and tier transition (the path may span several hops).
3. Report the path file by file.

If there's no path, the two aren't connected in the graph — say so plainly rather than guessing a link.
