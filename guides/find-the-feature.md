---
title: "Find where a feature lives, fast"
description: "Locate a feature's cluster of code from a couple of seed terms using repo-graph's find and activate, then flow to see it end to end."
tags: [repo-graph, mcp, code-navigation, ai-coding, pagerank]
---

# Find where a feature lives, fast

You know the feature by name. You don't know which 15 files it touches. The usual move is grep, read, grep, read until you've reconstructed the shape of it in your head. repo-graph skips that. It hands your AI assistant a structural graph of the codebase, so it navigates straight to the cluster instead of reading everything first.

Here's the three-tool path: `find` to anchor, `activate` to grow the cluster, `flow` to see it end to end.

## Orient first

Before anything, get the lay of the land. Ask your assistant:

> "Give me a quick status of this repo."

That calls `status`, which tells the model what languages, tiers, and entry points exist. Cheap, and it stops the model guessing.

## 1. find — anchor on a couple of seed terms

You rarely know exact node names. You know words. Start there:

> "Find the nodes for 'groups'."

That calls `find`, which matches nodes by name or qname. You'll get back the handful of real nodes: a `GroupsController`, a `groups` route, a `GroupService`, whatever exists. These are your seeds.

## 2. activate — grow the cluster

One node isn't a feature. A feature is a cluster of nodes that light up together. Feed your seeds into `activate`:

> "Activate from the groups controller and service and show me what's connected."

`activate` runs spreading activation (Personalized PageRank) out from the seed nodes. It ranks the rest of the graph by how strongly each node connects back to your seeds. The top results are the feature's real footprint: handlers, the data layer it hits, the models it touches, the frontend that calls it. Nodes that share a name but aren't actually wired in stay cold.

That's the bit grep can't do. Substring search finds the word "groups" everywhere; `activate` finds what's structurally part of the groups feature.

## 3. flow — see it end to end

Now you want the path, not just the set. Ask:

> "Show me the flow for the groups feature."

`flow` traces entry to service to data for a feature: route to handler to query. That's the spine. Two reads instead of fifteen.

## A real one

On quokka-stack, a Go + Angular monorepo (~566 nodes / 620 edges), the task was a reversed comparison operator. Same bug, same model, same prompt, run twice.

- **Without repo-graph:** 75,308 tokens, 4m36s, ~15 files explored. Grep, read, grep, read.
- **With repo-graph:** 29,838 tokens, ~30s, 2 files. A flow lookup, then the handler.

The only difference between the runs was whether repo-graph was installed.

## When you want more

- `trace` — shortest path between two nodes. "Where does the groups action hit the backend?"
- `neighbours` — direct one-hop connections from a node.
- `dense_text` — the whole graph as one dense dump when you want full context, not a slice.

Same idea throughout: read only what matters, burn less context, guess less.

## Try it

```bash
uvx mcp-repo-graph --repo .
```

More at [repo-graph.com](https://repo-graph.com).
