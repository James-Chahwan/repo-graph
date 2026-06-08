---
name: repo-graph-impact
description: Blast radius before a change — everything downstream a node affects, or upstream it depends on, grouped by tier. Plus the one-hop view of direct connections.
---

# repo-graph impact

Know what a change touches before you make it.

## When to use

- Before modifying or deleting a function, route, or component.
- "What breaks if I change this?"

## Steps

1. Call `impact` with `node=<name>`. Default `direction=downstream` (what it affects); use `upstream` for what it depends on; `depth` is 1–10.
2. For just the immediate wiring, call `neighbours` with `node=<name>` — direct callers and callees one hop out.
3. Report affected nodes by tier (entry / service / handler / data), and call out anything a plain grep would miss — transitive and cross-file dependents.
