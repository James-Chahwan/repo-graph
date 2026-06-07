---
title: "Understand a new repo before you touch it"
description: "Onboard to an unfamiliar codebase without reading every file. Use repo-graph's status, dense_text, flow, and graph_view to orient and drill in."
tags: [onboarding, mcp, code-navigation, ai-assistants, repo-graph]
---

# Understand a new repo before you touch it

You've cloned a repo you've never seen. The usual move is grep, read, grep, read, until you've burned an hour and most of your context window guessing at structure. repo-graph skips that. It hands your AI assistant a structural map of the codebase (entities, relationships, feature flows) so the model goes to the right files instead of reading everything first. Works across 20+ languages and frameworks, frontend to backend.

Here's the order that works.

## 1. status — orient first

Before any grepping, ask your assistant to call `status`. You get a read on the graph: what's there, the shape of it, where the weight sits. It's the "where am I" step.

> "What does this codebase look like? Run status."

## 2. dense_text — the whole-repo map

`dense_text` is the primary context dump: the full graph as dense text. One call gives the model the structure of the repo without it opening a single source file. This is the move that saves the most context.

> "Give me the full map of this repo."

The model now knows the entities and how they connect. It can answer architecture questions straight away.

## 3. flow — drill into one feature

Once you're oriented, scope down. `flow` traces a feature from entry to service to data, so you can follow one path without reading the files it touches.

> "Show me the flow for user authentication."

You get the entry point, the services it calls, the data it hits. That's the feature, end to end.

## 4. graph_view — a tree when you want one

`graph_view` gives an ASCII overview or a node tree. Handy when you want to eyeball the hierarchy under a node rather than read prose.

> "Show me a tree view of the payments module."

## A real example

A Go + Angular monorepo, quokka-stack: ~566 nodes, 620 edges. The bug was a reversed comparison operator in a backend handler.

The question you'd actually type:

> "Where does the groups action hit the backend?"

That's a `trace` — the shortest path between two nodes. It lands the model on the handler file, which it reads. Two files, not fifteen.

The numbers, same bug, same model, same prompt:

- **Without repo-graph:** 75,308 tokens, 4m36s, ~15 files explored.
- **With repo-graph:** 29,838 tokens, ~30s, 2 files.

The only difference between the two runs is whether repo-graph is installed.

## The other tools, briefly

You've got 11 across four tiers. Beyond the four above: `generate` (scan and build the graph, from a local path or a git URL), `impact` (blast radius up and down the tiers), `neighbours` (one-hop connections), `activate` (spreading activation from seed nodes), `find` (match nodes by name), `reload` (re-scan after you change code).

The habit to build: before grepping or reading files, `status` to orient, then `dense_text` for full context, or `find` / `activate` / `flow` to scope in.

## Try it

```bash
uvx mcp-repo-graph --repo .
```

Or wire it into your client:

```bash
claude mcp add repo-graph -- uvx mcp-repo-graph --repo .
```

More at [repo-graph.com](https://repo-graph.com).
