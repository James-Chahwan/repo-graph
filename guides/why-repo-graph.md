---
title: "Your AI assistant reads too much. Give it a map."
description: "AI coding assistants grep and read across a repo before they answer. A structural map lets the model read only what matters. Proof in the numbers."
tags: [mcp, ai-coding-assistants, developer-tools, context-window, code-navigation]
---

Watch your AI assistant work on an unfamiliar repo and you'll see the same loop: grep, read a file, grep again, read another, repeat. It's reconstructing the structure of your codebase from scratch, one file at a time, on every task. That's tokens spent, time spent, and a model still partly guessing when it finally edits something.

The fix isn't a bigger context window. It's giving the model the map up front.

## What repo-graph does

repo-graph is an MCP server that builds a structural graph of your codebase: the entities, how they connect, and the feature flows that run frontend to backend. The model queries the graph to find the right files instead of reading everything to find them. The engine is Rust and tree-sitter, and it handles 20+ languages and frameworks, cross-stack.

It exposes 6 verbs, each one a Rust engine primitive that returns a complete, ranked, located result in a single call. A few carry most of the day-to-day load:

- **`orient`** — call it first. The shape of the repo before anything else, plus a "blind spots" note: which languages and edge-types the graph under-links, so you know where to fall back to grep.
- **`orient full=true`** — the whole graph as dense text. The primary context dump.
- **`find`** — match nodes by name, or with `expand=true` run spreading activation (Personalized PageRank) from seed nodes, so the model pulls in what's actually related to the thing it's working on.
- **`find` → `read`** — paste a stacktrace, failing test, or diff into `find` to jump straight to the relevant nodes, then `read` to pull their exact source. The debugging on-ramp.

The pattern is simple: before grepping or reading files, call `orient` first, then `orient full=true` for full context, or `find` to scope down.

## How it reads in practice

You ask your assistant questions in plain English. Behind the scenes it picks the tool:

- "Where does the groups action hit the backend?" → `trace` finds the shortest path from the frontend node to the handler.
- "What's the request flow for creating a group?" → `trace` returns entry → service → data for that whole feature.
- "If I change this handler, what breaks?" → `impact` gives the blast radius by tier, and flags likely-dead code with `⊘`.
- "What's directly wired to this function?" → `impact` at depth 1 for the one-hop connections.

No reading fifteen files to answer any of them.

## The numbers

We ran the same bug twice on quokka-stack, a Go + Angular monorepo (~566 nodes / 620 edges). A reversed comparison operator. Same model, same prompt, both runs.

**Without repo-graph:** 75,308 tokens, 4m36s, ~15 files explored. Grep, read, grep, read, narrowing in.

**With repo-graph:** 29,838 tokens, ~30s, 2 files touched — one trace lookup to locate the handler, then the handler file itself.

Same bug, same model, same prompt. The only difference is whether repo-graph is installed.

## Install

Zero-install with `uvx`:

```bash
uvx mcp-repo-graph --repo .
```

Or pin it:

```bash
pip install mcp-repo-graph
```

Wire it into your assistant:

```bash
claude mcp add repo-graph -- uvx mcp-repo-graph --repo .
codex mcp add repo-graph -- uvx mcp-repo-graph --repo .
gemini mcp add repo-graph uvx mcp-repo-graph --repo .
```

For Cursor, Windsurf, Antigravity, or any MCP client, add an `mcpServers` block:

```json
{
  "mcpServers": {
    "repo-graph": {
      "command": "uvx",
      "args": ["mcp-repo-graph", "--repo", "."]
    }
  }
}
```

VS Code has an extension (`code --install-extension james-chahwan.repo-graph`), and Claude Desktop has the `.mcpb` desktop extension.

Point `refresh` at a local path or a git URL and it'll scan and build the graph. Run it again after you change code.

**Try it:** `uvx mcp-repo-graph --repo .` — more at [repo-graph.com](https://repo-graph.com).
