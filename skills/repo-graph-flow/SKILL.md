---
name: repo-graph-flow
description: List or inspect a feature's end-to-end flow (http / page / cli / grpc / queue) — entry point through the service layer to the data store.
---

# repo-graph flow

See every file in a feature's path before you touch it.

## When to use

- "What features or endpoints does this expose?"
- The user names a route, page, command, or queue worker.
- Before changing a user-facing feature — read its flow first.

## Steps

1. No argument: call `flow` with no feature → the overview (flows by kind and confidence, one line each).
2. A specific feature: call `flow` with `feature=<slug>` → entry → service → data, each step as `file_path:node`.
3. If the slug isn't found, the tool lists available entry points — pick the closest and retry.

Report the kind (http/page/cli/grpc/queue), confidence, and each step. That's the full set of files the feature touches.
