---
name: repo-graph-init
description: Set up or rebuild the structural graph for a repo — on first use, after a big refactor, or to wire repo-graph into a project permanently.
---

# repo-graph init

Build the graph so the other skills have something to read.

## When to use

- First time using repo-graph in a repo (no graph yet).
- After a large refactor or branch switch — the graph is stale.

## Steps

1. First use: call `generate` (optionally `repo_path=<local path or git URL>`). It scans with tree-sitter, runs the cross-stack resolvers, and caches the result for fast reloads.
2. After code changes: call `reload` to re-generate.
3. To add repo-graph to a project for good, drop an `.mcp.json` at the repo root:

       {"mcpServers":{"repo-graph":{"command":"uvx","args":["mcp-repo-graph","--repo","."]}}}

4. Call `status` to confirm it loaded.
