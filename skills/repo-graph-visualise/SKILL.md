---
name: repo-graph-visualise
description: Render an ASCII map of the repo or a specific node's neighbourhood. Use for a quick orientation sketch or to show a subgraph in context.
---

# repo-graph visualise

Prints an ASCII tree / layered view of the graph. Useful for orientation
before deep-diving, and for sharing context with the user in one glance.

## When to use

- User asks "give me a map", "show me the structure", "what's in this repo?"
- Before explaining architecture — render once, annotate from the map.
- User wants to see a specific flow as a diagram.

## Steps

1. With no args: call `graph_view` with `mode=overview`. That prints:
   - Node count by kind
   - Top-level modules/packages
   - Entrypoint summary (routes, CLI, gRPC, queues)

2. For a node neighbourhood: call `graph_view` with `mode=tree node=<id>
   depth=2`.

3. For a feature: call `graph_view` with `mode=flow feature=<slug>`. This
   renders the flow as a layered diagram.

## Tips

- Keep `depth` ≤ 3 for trees — deeper gets noisy fast.
- Icons in the output encode confidence: ● strong, · medium, ⚠ weak.
- Flow kinds are tagged in square brackets: `[http]`, `[page]`, `[cli]`,
  `[grpc]`, `[queue]`.
