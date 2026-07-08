---
title: "Trace a frontend action to its backend handler"
description: "Follow a feature across the stack with repo-graph trace and find instead of grepping both sides and guessing the link."
tags: [repo-graph, cross-stack, tracing, mcp, debugging]
---

# Trace a frontend action to its backend handler

A button gets clicked in the UI. Somewhere on the backend a route handles it. Between those two points sit an HTTP call, a router definition, a controller, maybe a service. The usual way to find the handler: grep the frontend, read a file, grep the backend, read another, then squint at the path string to guess the link. That burns context and time.

repo-graph already knows the link. It builds a structural graph of the codebase across 20+ languages and frameworks, frontend to backend, and `trace` returns the shortest path between two nodes. Your AI assistant calls the tool instead of reading half the repo.

## The pattern

1. **Orient.** Before grepping anything, the model calls `orient` to see the shape of the codebase: tiers, languages, entry points.
2. **Find the ends.** Use `find` to match the frontend node (the component or action) and the backend node (the route or handler) by name.
3. **Connect them.** `trace` returns the shortest path between the two nodes. That path is the answer.

If you don't know the backend end yet, `trace` with a single argument does the legwork: give it a feature and it returns entry -> service -> data in order.

## Worked example

Say you're chasing a bug in a Go + Angular monorepo. The groups list shows the wrong open/closed state. You suspect a backend comparison.

You type to your assistant:

> Where does the groups action in the UI hit the backend?

The model runs `find` to pin the Angular action and the Go route, then `trace` between them. It comes back with the path: the component, the service call, the route, the handler. No grepping.

Follow up:

> Show me the full flow for the groups feature.

That's `trace` with one argument — entry component, the HTTP service, the route, the handler, the data layer, in order. You open the handler, spot the reversed comparison operator, fix it.

On quokka-stack (~566 nodes / 620 edges) that exact bug, same model and same prompt both runs:

- **Without repo-graph:** 75,308 tokens, 4m36s, ~15 files explored (grep, read, grep, read).
- **With repo-graph:** 29,838 tokens, ~30s, 2 files — a trace lookup and the handler file.

Same bug, same model, same prompt. The only difference is whether repo-graph is installed.

## Prompts and the tool that answers

- "Where does the groups action hit the backend?" -> `trace`
- "Show me the full flow for the groups feature." -> `trace`
- "What's the route node for the groups endpoint?" -> `find`
- "What's the layout of this repo?" -> `orient`
- "What breaks if I change this handler?" -> `impact`

You don't name the tools yourself. You ask the question in plain English; the assistant picks the tool from the graph.

## Set up the graph

Point repo-graph at your repo and let it scan:

```bash
claude mcp add repo-graph -- uvx mcp-repo-graph --repo .
```

Or run it zero-install in any session:

```bash
uvx mcp-repo-graph --repo .
```

After you change code, ask the model to `refresh` so the graph reflects the new source.

More at [repo-graph.com](https://repo-graph.com).
