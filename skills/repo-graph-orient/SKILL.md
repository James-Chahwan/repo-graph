---
name: repo-graph-orient
description: Get oriented in a codebase before reading files — repo shape, the full structural map, and a visual tree. Use at the start of any task in an unfamiliar or large repo.
---

# repo-graph orient

Build a mental model of the repo from the graph instead of opening files one by one.

## When to use

- Starting work in an unfamiliar or large repo.
- The user asks "how does this codebase work?" or "what's in here?".
- Before any change, to learn the lay of the land cheaply.

## Steps

1. Call `status` first — node/edge counts, detected kinds, entry points, and a dense-text preview. This is the orient call; do it before grepping.
2. For the whole picture, call `dense_text` — the full graph in dense notation. Read it instead of reading files; it's the primary context source. Large graphs are truncated, so scope with `find`/`activate`/`flow` if needed.
3. For a visual, call `graph_view` — no argument for an overview, or a node name for a tree around it.

Report the tiers (entry → service → handler → data) and the main entry points. You now know where to look without having opened a file.
