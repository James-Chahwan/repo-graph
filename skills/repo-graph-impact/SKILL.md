---
name: repo-graph-impact
description: Show what depends on a given node — callers, importers, and test files that cover it. Use before changing or removing code.
---

# repo-graph impact

Before modifying or deleting a node, check who depends on it. This covers:
- Inbound `calls` / `imports` / `handles` edges (reverse reach)
- Test files that cover it (via `tests` edges) when `include_tests=True`

## When to use

- User asks "what will break if I change X?" or "who uses X?"
- You're about to rename or delete a function/class/module — always impact
  first.
- Before refactoring — the impact list tells you the test surface to re-run.

## Steps

1. Find the node id via `neighbours` or `status` if not obvious.

2. Call `impact` with the node id. Default includes code callers only.
   Pass `include_tests=True` to also list test files that exercise the node.

3. Report:
   - Count of direct inbound edges
   - Top-N callers grouped by kind (imports vs calls vs handles)
   - Test files covering it — flag if the count is zero (low safety)

## Guardrails

- If impact returns zero inbound edges and no tests, don't silently say
  "safe to remove" — the node may be an entrypoint (CLI / route / queue
  consumer) that's called externally. Check node type first.
