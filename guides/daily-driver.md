---
title: "Make your AI assistant navigate by structure"
description: "Teach Claude Code, Cursor, and Codex to call orient before grepping, scope with the right repo-graph tool, and trust the graph."
tags: [repo-graph, mcp, claude-code, ai-coding, code-navigation]
---

# Make your AI assistant navigate by structure

Out of the box, an AI assistant explores a codebase the slow way: grep, read, grep, read, until it stumbles onto the right file. repo-graph hands it a structural map up front: entities, relationships, and feature flows across 20+ languages, frontend to backend. The model goes straight to what matters.

The habit to build: **call `orient` before grepping.** Orient first, then scope, then read only the files the graph points at.

## The tools you'll lean on

`orient` orients you. It's the first call in any session, showing the shape of the repo: how many nodes, the main tiers, where things live, plus a blind-spots note flagging where the graph under-links so you know when to grep.

`trace` walks a feature or connects two nodes. Give it one feature — "how does login work?" — and it returns entry point → service → data layer, the path instead of fifteen file reads. Give it two nodes — "where does the groups action hit the backend?" — and it returns the shortest path between them, connecting the frontend call to the handler.

`impact` shows the blast radius. Ask "what breaks if I change the user model?" and `impact` lists forward and backward dependents by tier before you touch anything, marking likely-dead code with `⊘`.

`find` with `expand=true` runs spreading activation (Personalized PageRank) from seed nodes. Good when you half-know the area: seed a couple of names and it surfaces the related cluster.

Round it out with `find` (match nodes by name or qname, or resolve a stacktrace/test/diff), `read` (pull a node's exact source — comma-separate names to batch-read), `orient full=true` (the full graph as one context dump), and `refresh` (re-scan after you change code).

## What to type, which tool answers

- "Give me the lay of the land." → `orient`
- "How does checkout work, front to back?" → `trace`
- "Where does the groups action hit the backend?" → `trace`
- "What depends on `AuthService`?" → `impact` (backward)
- "Find everything near the billing code." → `find expand=true`
- "Load the full picture, then we'll dig in." → `orient full=true`

## Trust the result

The point of the graph is to stop re-exploring. When `trace` returns three files, those are the three files. Read them, don't grep around to double-check. Re-reading defeats the purpose and burns the context you just saved.

## One real run

quokka-stack is a Go + Angular monorepo: ~566 nodes, 620 edges. The bug was a reversed comparison operator. Same model, same prompt, two runs.

**Without repo-graph:** 75,308 tokens, 4m36s, ~15 files explored. Grep, read, grep, read.

**With repo-graph:** 29,838 tokens, ~30s, 2 files. A `trace` lookup pointed at the handler, then the handler file itself.

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

After your assistant edits code, call `refresh` to rebuild the graph.

**Try it:** `uvx mcp-repo-graph --repo .` — more at [repo-graph.com](https://repo-graph.com)
