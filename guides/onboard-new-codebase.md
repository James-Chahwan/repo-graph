---
title: "Understand a new repo before you touch it"
description: "Onboard to an unfamiliar codebase without reading every file. Use repo-graph's orient and trace to map the shape and drill into features."
tags: [onboarding, mcp, code-navigation, ai-assistants, repo-graph]
---

# Understand a new repo before you touch it

You've cloned a repo you've never seen. The usual move is grep, read, grep, read, until you've burned an hour and most of your context window guessing at structure. repo-graph skips that. It hands your AI assistant a structural map of the codebase (entities, relationships, feature flows) so the model goes to the right files instead of reading everything first. Works across 20+ languages and frameworks, frontend to backend.

Here's the order that works.

## 1. orient — get your bearings first

Before any grepping, ask your assistant to call `orient`. You get a read on the graph: what's there, the shape of it, where the weight sits. It also prints a "blind spots" note — which languages and edge-types the graph under-links, so you know exactly where to fall back to grep. It's the "where am I" step.

> "What does this codebase look like? Run orient."

## 2. orient full=true — the whole-repo map

`orient full=true` is the primary context dump: the full graph as dense text. One call gives the model the structure of the repo without it opening a single source file. This is the move that saves the most context.

> "Give me the full map of this repo."

The model now knows the entities and how they connect. It can answer architecture questions straight away.

## 3. trace — drill into one feature

Once you're oriented, scope down. `trace`, given a single feature, traces it from entry to service to data, so you can follow one path without reading the files it touches.

> "Show me the flow for user authentication."

You get the entry point, the services it calls, the data it hits. That's the feature, end to end.

## 4. orient <node> — a tree when you want one

`orient <node>` gives a tree scoped around a node, and plain `orient` an ASCII overview. Handy when you want to eyeball the hierarchy under a node rather than read prose.

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

You've got 6 verbs total. Beyond the ones above: `find` (match nodes by name, or paste a stacktrace/test/diff to jump to the code; add `expand=true` for the PPR-ranked cluster around your seeds), `impact` (forward/backward blast radius, with a `⊘` marker on likely-dead code), `read` (pull a node's exact source), `refresh` (re-scan after you change code, or from a local path or a git URL).

The habit to build: before grepping or reading files, `orient` first, then `orient full=true` for full context, or `find` / `trace` to scope in.

## Try it

```bash
uvx mcp-repo-graph --repo .
```

Or wire it into your client:

```bash
claude mcp add repo-graph -- uvx mcp-repo-graph --repo .
```

More at [repo-graph.com](https://repo-graph.com).
