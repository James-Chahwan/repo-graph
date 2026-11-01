---
name: glia-find
description: Find where a feature, symbol or concept lives in a codebase, as ranked nodes with path:line, then read their source. Use for "where is X", "find the code that handles Y", "which files is this task about", or to work out which files matter before reading any.
---

# Find where something lives

Get the relevant set, ranked and located, instead of grepping for one lucky file.

## Transports

Use whichever is available, in this order: the repo-graph MCP tools when loaded (`mcp__repo-graph__<tool>`, or `mcp__plugin_repo-graph_repo-graph__<tool>` from the Claude Code plugin; they may be deferred, so search your tool list first); the `glia` CLI when on PATH; else `uvx --from glia-cli glia <command> ..` (no install; the first run downloads the wheel); else `uvx mcp-repo-graph <verb>`. The MCP tools and `uvx mcp-repo-graph` print the same text; the glia CLI answers the same question with `--json` rows (`file`, `line`, tier). Run any of them at the repo root (`.` below).

| Want | MCP tool call | glia CLI | uvx mcp-repo-graph |
|---|---|---|---|
| Nodes matching a name or keyword | `find query=<text>` | `glia find . <text> --json` | `uvx mcp-repo-graph find "<text>"` |
| The files a task, ticket or PR title is about | `find query=<text>` | `glia find . "<text>" --files --json` | `uvx mcp-repo-graph find "<text>"` |
| The cluster around a concept, within a budget | `find query=<text> expand=true` | `glia pack . "<task>" --budget 4000 --json` | `uvx mcp-repo-graph find "<text>" --expand` |
| Their source, several at once | `read node=<a>,<b>,<c>` | open the `file:line` each row gives | `uvx mcp-repo-graph read "<a>,<b>,<c>"` |

## Steps

1. `find` a name or a word from the feature: `checkout`, `UserService`, `/api/orders` (`glia find . UserService --json`). Rows come back ranked, each with its kind, qname, `file` and `line`. `live: false` (`⊘` in tables) marks a node no entry point reaches, which is likely dead code. `--top-k <n>` changes how many rows you get (default 20).
2. For a task rather than a name, ask for its files: `glia find . "add a discount to checkout" --files --json` ranks the files the ids and words in the text route to (an id defined in a task list, past commit messages). It needs `glia history sync .` for the message part; with no input it says which one was missing.
3. For a concept, get its neighbourhood packed to a token budget: `glia pack . "<task>" --budget 4000 --json` ranks the code around the matches, so related code that doesn't share the word still shows up, each node at the detail the budget buys. Over MCP, `expand=true` does the same ranking.
4. Read the top hits, not whole files. MCP `read` slices each to its line span with a `context:` footer (cross-stack callers, covering tests); with the CLI, open the `file:line` a row gives. glia has no `read` verb. Use the qname from the row when a short name is ambiguous.

An empty answer is an `absence` with a reason and caveats, not "nothing exists": check `glia coverage . --json` before trusting it.

Need the whole flow, or what a change would break? Use `glia-trace` or `glia-impact`. Starting from an error or a failing test? Use `glia-debug`. Siblings: `glia-orient`, `glia-find`, `glia-debug`, `glia-impact`, `glia-trace`, `glia-init`; `glia` is the full CLI reference (every command, flag and answer shape).
