---
title: "Make your AI assistant navigate by structure"
description: "Teach Claude Code, Cursor, and Codex to call status before grepping, scope with the right repo-graph tool, and trust the graph."
tags: [repo-graph, mcp, claude-code, ai-coding, code-navigation]
---

# Make your AI assistant navigate by structure

Out of the box, an AI assistant explores a codebase the slow way: grep, read, grep, read, until it stumbles onto the right file. repo-graph hands it a structural map up front: entities, relationships, and feature flows across 20+ languages, frontend to backend. The model goes straight to what matters.

The habit to build: **call `status` before grepping.** Orient first, then scope, then read only the files the graph points at.

## The tools you'll lean on

`status` orients you. It's the first call in any session, showing the shape of the repo: how many nodes, the main tiers, where things live.

`flow` traces a feature end to end, from entry point through service to data layer. Ask "how does login work?" and `flow` returns the path instead of fifteen file reads.

`trace` finds the shortest path between two nodes. Ask "where does the groups action hit the backend?" and `trace` connects the frontend call to the handler.

`impact` shows the blast radius. Ask "what breaks if I change the user model?" and `impact` lists downstream and upstream by tier before you touch anything.

`activate` runs spreading activation (Personalized PageRank) from seed nodes. Good when you half-know the area: seed a couple of names and it surfaces the related cluster.

Round it out with `find` (match nodes by name or qname), `dense_text` (the full graph as one context dump), and `neighbours` (direct one-hop links).

## What to type, which tool answers

- "Give me the lay of the land." → `status`
- "How does checkout work, front to back?" → `flow`
- "Where does the groups action hit the backend?" → `trace`
- "What depends on `AuthService`?" → `impact`
- "Find everything near the billing code." → `activate`
- "Load the full picture, then we'll dig in." → `dense_text`

## Trust the result

The point of the graph is to stop re-exploring. When `flow` returns three files, those are the three files. Read them, don't grep around to double-check. Re-reading defeats the purpose and burns the context you just saved.

## One real run

quokka-stack is a Go + Angular monorepo: ~566 nodes, 620 edges. The bug was a reversed comparison operator. Same model, same prompt, two runs.

**Without repo-graph:** 75,308 tokens, 4m36s, ~15 files explored. Grep, read, grep, read.

**With repo-graph:** 29,838 tokens, ~30s, 2 files. A `flow` lookup pointed at the handler, then the handler file itself.

Same bug, same model, same prompt. The only difference is whether repo-graph was installed.

## Install

```bash
# Claude Code
claude mcp add repo-graph -- uvx mcp-repo-graph --repo .

# OpenAI Codex
codex mcp add repo-graph -- uvx mcp-repo-graph --repo .

# Gemini CLI
gemini mcp add repo-graph uvx mcp-repo-graph --repo .
```

Cursor, Windsurf, Antigravity, or any MCP client: add an `mcpServers` block.

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

VS Code: `code --install-extension james-chahwan.repo-graph`. Claude Desktop: the `.mcpb` desktop extension.

After your assistant edits code, call `reload` to rebuild the graph.

**Try it:** `uvx mcp-repo-graph --repo .` — more at [repo-graph.com](https://repo-graph.com)
