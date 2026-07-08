---
name: repo-graph-impact
description: Blast radius before a change — everything a node affects (forward) or that depends on it (backward), ranked and located, with likely-dead code flagged. Also the one-hop view of direct connections.
---

# repo-graph impact

Know what a change touches before you make it.

## When to use

- Before modifying or deleting a function, route, or component.
- "What breaks if I change this?" / "who uses this?"

## Steps

1. Call `impact` with `nodes=<name>`. `direction=forward` (what it affects, the default sense) / `backward` (what it depends on / who uses it) / `both`; `depth` is 1–10. Pass several comma-separated nodes (e.g. every symbol in a diff) for the unified blast radius in one call. Each row shows a `via <reason>` edge label and a `⊘` marker when the engine finds the node unreachable from any entry point — likely dead code. Add `live_only=true` to drop those.
2. For just the immediate wiring, call `impact` at `depth=1` with `direction=both` — direct callers and callees one hop out (this replaces the old `neighbours` tool).
3. Report affected nodes by tier (entry / service / handler / data), and call out anything a plain grep would miss — transitive and cross-file dependents, and anything flagged `⊘`.
