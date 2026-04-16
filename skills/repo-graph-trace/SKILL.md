---
name: repo-graph-trace
description: Trace the path from an entrypoint (route, CLI command, gRPC method, queue consumer) to its implementation. Use when asked how a feature works end-to-end.
---

# repo-graph trace

Follow a feature from its entrypoint through handlers, helpers, and data
sources. Use this before reading code to orient — it tells you which files
are load-bearing and which are noise.

## When to use

- The user asks "how does X work?", "where is X handled?", "what happens
  when the user clicks Y?"
- Before diving into a bug in a specific feature — trace first, read the
  touched files second.

## Steps

1. Call the `status` MCP tool to see available flows and analyzer state.
   Flows are named by entrypoint (e.g. `get_groups`, `greet_command`).

2. If the user's request matches a known flow, call `flow` with that slug.
   Otherwise call `trace` with the entrypoint node id (look it up with
   `neighbours` if needed).

3. Report the full path in one pass:
   - Entrypoint (kind + confidence icon)
   - Handler module
   - Any data sources the path touches
   - Depth ≤ 4 — if it runs deeper, summarise, don't dump

## Tips

- Prefer `flow` over `trace` when a named flow already exists; it's pre-built.
- Use `--min-confidence strong` to filter out weak test/example paths.
- If a flow is marked `weak`, say so — it probably came from a fixture.
