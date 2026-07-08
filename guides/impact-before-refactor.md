---
title: "Know what breaks before you change it"
description: "See the downstream blast radius of a change before editing, grouped by tier, using repo-graph's impact tool."
tags: [repo-graph, mcp, impact-analysis, refactoring, code-graph]
---

# Know what breaks before you change it

Changing a function is easy. Knowing what else moves when you change it is the hard part. Without a map, your AI assistant greps for the symbol, reads a file, greps again, reads another, burning context and still missing call sites it never thought to search for.

repo-graph gives your assistant a structural graph of the codebase, so it reads the blast radius off the graph instead of guessing. One tool does the work here, at two depths:

- **impact** — the forward (or backward) blast radius of a node, grouped by tier. Each row shows a `via <reason>` edge label and flags likely-dead code with `⊘`.
- **impact at depth 1** — the direct one-hop connections, when you only need the immediate ring.

## The pattern

Orient first, then scope. Before any edit, point your assistant at the thing you're about to touch.

```
You: I want to change the signature of validateSession. What breaks?
```

The assistant calls **orient** to get its bearings, then **impact** on `validateSession`. It comes back with every downstream node — handlers, middleware, the routes that hang off them — grouped by tier (entry, service, data). Now it knows the edit isn't local. It's a fan-out.

If you only care about what sits one hop away — say you're renaming a field and want the direct readers, not the whole transitive tail — ask for that instead:

```
You: Who calls getUserRole directly?
```

That's **impact** at depth 1: the immediate ring, no transitive walk.

## A real example

Take quokka-stack, a Go + Angular monorepo (~566 nodes / 620 edges). The bug: a reversed comparison operator in a permissions check.

Without repo-graph, the assistant explored ~15 files (grep, read, grep, read), burned **75,308 tokens**, and took **4m36s**.

With repo-graph, same bug, same model, same prompt: a trace lookup plus the handler file. **2 files**, **29,838 tokens**, ~**30s**.

The difference wasn't a smarter model. It was the model reading only what mattered.

For a change instead of a read, the impact-first version looks like this:

```
You: Before I touch isGroupOpen, show me everything downstream of it.
```

The assistant runs **impact** on `isGroupOpen`, gets the tiered fan-out, and edits with the call sites already in hand. No blind grep sweep.

## Prompts that map to tools

You don't name the tools. You ask the question; the assistant picks the tool.

| You ask | Tool it uses |
|---|---|
| "What breaks if I change this?" | **impact** |
| "Who calls this directly?" | **impact** at depth 1 |
| "Where do I even start?" | **orient** |
| "Where does the groups action hit the backend?" | **trace** |
| "Walk me through the login feature." | **trace** |

The graph is cross-stack and covers 20+ languages, so impact on a backend handler can surface the frontend caller that hits it — the one a call-site grep would miss.

After you've made the change, run **refresh** so the graph reflects the new code before the next question.

## Try it

```bash
claude mcp add repo-graph -- uvx mcp-repo-graph --repo .
```

More at [repo-graph.com](https://repo-graph.com).
