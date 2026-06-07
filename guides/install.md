---
title: Install repo-graph in any AI client
description: A 60-second setup that gives your AI coding assistant a structural map of any codebase. Exact command per client, plus how to confirm it loaded.
tags: [mcp, ai-coding, setup, developer-tools, codebase-navigation]
---

# Install repo-graph in any AI client

repo-graph is an MCP server that hands your AI assistant a structural graph of a codebase: entities, relationships, and feature flows. Instead of grepping and reading files until it finds the right one, the model navigates straight to it. Less context burned, fewer wrong guesses, faster answers.

It works across 20+ languages and frameworks, frontend to backend, including cross-stack links. The engine (`repo-graph-py`) is Rust plus tree-sitter.

## Pick your client

Each line below installs the server pointed at the current directory (`--repo .`). `uvx` runs it with zero install.

**Claude Code**
```bash
claude mcp add repo-graph -- uvx mcp-repo-graph --repo .
```

**OpenAI Codex**
```bash
codex mcp add repo-graph -- uvx mcp-repo-graph --repo .
```

**Gemini CLI**
```bash
gemini mcp add repo-graph uvx mcp-repo-graph --repo .
```

**Cursor / Windsurf / Antigravity / any MCP client** — drop this in your `mcpServers` config:
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

**VS Code**
```bash
code --install-extension james-chahwan.repo-graph
```

**Claude Desktop** — install the `.mcpb` desktop extension.

Prefer a pinned install over `uvx`? `pip install mcp-repo-graph`.

## Confirm it loaded

Build the graph, then orient. Tell your assistant:

> Generate the repo-graph, then call status.

`generate` scans the repo and builds the graph. It also takes a git URL if you want to point at a remote repo. `status` reports what it found. If you get a summary back, you're set.

## How you actually use it

The pattern: before grepping or reading files, ask the model to call `status` to orient, then `dense_text` for full context, or `activate` / `find` / `flow` to scope in. Some prompts and the tool that answers them:

- "Where does the groups action hit the backend?" → `trace` (shortest path between two nodes)
- "Walk me through the checkout feature." → `flow` (entry → service → data)
- "What breaks if I change this handler?" → `impact` (downstream/upstream blast radius)
- "What's directly wired to this node?" → `neighbours` (one-hop connections)
- "Find the auth middleware." → `find` (match by name or qname)
- "Give me an ASCII overview." → `graph_view`

After you change code, `reload` rebuilds the graph.

## What it changes

A run on quokka-stack, a Go + Angular monorepo (~566 nodes / 620 edges), fixing a reversed comparison operator. Same bug, same model, same prompt both times:

| | Tokens | Time | Files touched |
|---|---|---|---|
| Without repo-graph | 75,308 | 4m36s | ~15 (grep, read, grep, read...) |
| With repo-graph | 29,838 | ~30s | 2 (a flow lookup + the handler) |

The only difference is whether repo-graph is installed.

## Try it

```bash
uvx mcp-repo-graph --repo .
```

More at [repo-graph.com](https://repo-graph.com).
