---
name: repo-graph-init
description: Bootstrap repo-graph for this project — generate the graph, wire the MCP config, add an orientation block to CLAUDE.md. Run once per new project.
---

# repo-graph init

Set up repo-graph for the current working directory. This is a one-shot setup
that prepares the project so future sessions can navigate structurally instead
of grepping from scratch.

## Steps

1. Run `repo-graph-init` in the project root. That command:
   - Runs `repo-graph-generate --repo .` to build `.ai/repo-graph/`
   - Creates `.mcp.json` with the `repo-graph` server entry
   - Appends an orientation block to `CLAUDE.md` telling Claude to trust
     repo-graph output and call `status` / `flow` before grepping

2. After it runs, print a one-line summary of what was created and ask the
   user to restart Claude Code so the MCP server loads.

## Guardrails

- If `.ai/repo-graph/` already exists, stop and ask the user whether to
  regenerate (running generation again is safe but overwrites nodes.json).
- If `CLAUDE.md` already has a `## repo-graph` section, don't duplicate it —
  report that the orientation block is already in place.
- Never edit user code as part of init. Only create `.mcp.json`, `.ai/`, and
  the CLAUDE.md orientation block.
