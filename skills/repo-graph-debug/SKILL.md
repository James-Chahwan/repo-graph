---
name: repo-graph-debug
description: Start from a failure, not a filename — turn a stacktrace, failing test, or diff into the exact code that matters, then read it. Use when you have an error and need to know where to look.
---

# repo-graph debug

Paste the error, get the code. The on-ramp when something's broken — instead of grepping file names out of a traceback and opening each one.

## When to use

- You have a stacktrace, a failing-test id (`path::test_name`), or a diff / list of changed files.
- "Where do I even start with this error?"

## Steps

1. Call `find` with `query=<the raw stacktrace / test id / unified diff>`. It sniffs the shape (or pass `kind=stacktrace|test|diff`), resolves the frames/symbols/paths to nodes, then ranks the surrounding subgraph by relevance (Personalized PageRank). Every row carries `path:line`.
2. Call `read` with `node=<top result>` to pull that node's exact source, sliced from its file by the graph's line span — no grep, no scrolling. Add `context_lines=N` for padding around it.
3. Widen if needed: `impact` on the node for blast radius (it takes several comma-separated nodes — feed it the whole changed set) — `direction=both` at `depth=1` for direct callers/callees.

`find` only resolves frames that actually exist in the graph — if it returns nothing, the signal's paths/symbols don't match this repo; fall back to `find` with a plain keyword.
