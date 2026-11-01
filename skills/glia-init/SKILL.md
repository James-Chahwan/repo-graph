---
name: glia-init
description: Build, rebuild or wire up the glia structural map for a repository, with the history its rankings read. Use on first use in a repo, after a large refactor or branch switch, to keep the graph fresh, or to add glia (through the repo-graph MCP server) to a project's coding agents for good.
---

# Set up glia

Build the graph so the other glia skills have something to read, give it the history its rankings use, and wire it into the project's agents.

## Transports

Use whichever is available, in this order: the repo-graph MCP tools when loaded (`mcp__repo-graph__<tool>`, or `mcp__plugin_repo-graph_repo-graph__<tool>` from the Claude Code plugin; they may be deferred, so search your tool list first); the `glia` CLI when on PATH; else `uvx --from glia-cli glia <command> ..` (no install; the first run downloads the wheel); else `uvx mcp-repo-graph <verb>`. The MCP tools and `uvx mcp-repo-graph` print the same text; the glia CLI answers the same question with `--json` rows (`file`, `line`, tier). Run any of them at the repo root (`.` below).

| Want | MCP tool call | glia CLI | uvx mcp-repo-graph |
|---|---|---|---|
| Build or rebuild (incremental) | `refresh` | `glia build .` | `uvx mcp-repo-graph refresh` |
| Clean reparse | `refresh full=true` | `glia build . --no-incremental` | `uvx mcp-repo-graph refresh --full` |
| History for co-change and calibrated rankings | | `glia history sync .`, then `glia history calibrate . --json` | |
| Keep it fresh | the server's file watcher | `glia install-hooks .` or `glia watch .` | |

## Build or rebuild

1. The graph builds itself when it is needed: every `glia` answer builds in memory from the parse cache, and the MCP server builds on its first call. `glia build .` writes the layout to `.glia/graph/` (the directory the MCP server and `load_from_gmap` read); after a big refactor or a branch switch, run it again. Only changed files re-parse; `--no-incremental` forces a clean reparse.
2. Give the rankings history: `glia history sync .` writes `.glia/history-snapshot/` (commits, co-change, redacted messages; `--blame` adds blame for `hotspots`). Then `glia history calibrate . --json` replays past commits to pick each answer's best ranking for this repo and writes `.glia/calibration-snapshot/`. Rerun both after upgrading glia: a calibration is read only by the build that wrote it.
3. Keep it fresh: `glia install-hooks .` adds post-commit, post-merge and post-checkout hooks that rerun `glia build .`, or `glia watch .` keeps one build open and prints an update per change (stop it with Ctrl-C).
4. Confirm it loaded: `glia arch . --json` (or `orient` over MCP).

## Wire it into a project

`uvx mcp-repo-graph install` finds the coding agents installed on this machine (Claude Code, Cursor, VS Code, Codex, Gemini CLI and others), then writes each one's MCP config, a short usage block in its instructions file, and auto-allow for the tools. `--dry-run` previews it, `--agents all` covers every supported agent, and `uvx mcp-repo-graph uninstall` reverses it. Restart the agent session afterwards so it loads the tools.

By hand, it's one `.mcp.json` at the repo root:

```json
{"mcpServers": {"repo-graph": {"command": "uvx", "args": ["mcp-repo-graph", "--repo", "."]}}}
```

No MCP at all? Copy these skills to `~/.claude/skills/` and the agent calls the CLI.

Siblings: `glia-orient`, `glia-find`, `glia-debug`, `glia-impact`, `glia-trace`, `glia-init`; `glia` is the full CLI reference (every command, flag and answer shape).
