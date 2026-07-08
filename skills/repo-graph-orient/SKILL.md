---
name: repo-graph-orient
description: Get oriented in a codebase before reading files — repo shape, entry points, where the graph is blind, and the full structural map. Use at the start of any task in an unfamiliar or large repo.
---

# repo-graph orient

Build a mental model of the repo from the graph instead of opening files one by one.

## When to use

- Starting work in an unfamiliar or large repo.
- The user asks "how does this codebase work?" or "what's in here?".
- Before any change, to learn the lay of the land cheaply.

## Steps

1. Call `orient` first — node/edge counts, detected kinds, entry points, and a **blind spots** note: which languages/edge-types the graph under-links, so you know exactly where to fall back to grep. This is the orient call; do it before grepping.
2. For the whole picture, call `orient` with `full=true` — the full graph in dense notation. Read it instead of reading files; it's the primary context source. Large graphs are truncated, so scope with `orient <node>` or `find` if needed.
3. For a node's neighbourhood, call `orient` with `seed=<node>` — the scoped map around it.

Report the tiers (entry → service → handler → data) and the main entry points. You now know where to look without having opened a file.
