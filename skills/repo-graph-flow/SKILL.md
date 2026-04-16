---
name: repo-graph-flow
description: List or inspect a named flow (http / page / cli / grpc / queue). Use to see end-to-end request paths for a feature.
---

# repo-graph flow

Lists the pre-built flows for this repo, or expands a specific flow showing
every step from entrypoint to leaf.

## When to use

- User asks "what features exist?" or "what endpoints does this expose?"
- User asks about a specific route, command, or queue worker by name.
- Before planning a change that touches a user-facing feature — read the
  flow first so you know every file involved.

## Steps

1. With no argument: call `flow` with no feature — it prints the overview
   (flow count by kind + confidence, per-flow one-liners).

2. With a feature slug: call `flow` with `feature=<slug>`. Report:
   - Kind (http/page/cli/grpc/queue) and confidence tier
   - Each step: file_path:node_name
   - Whether the flow touches external data sources

3. Optional filters: `kind=http` to narrow, `min_confidence=strong` to skip
   test/example routes.

## Tips

- Flow kinds tell you stack role: `page` = frontend route, `http` = backend
  API, `cli` = CLI command, `grpc` = gRPC method, `queue` = job consumer.
- A `weak` flow usually means the route was defined in a test/example file.
