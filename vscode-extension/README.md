# repo-graph for VS Code

**Zero-config structural codebase map for AI coding assistants.**

This extension registers [repo-graph](https://github.com/James-Chahwan/repo-graph)
as an MCP server in VS Code's agent mode. Install it and your open workspace is
mapped automatically — no JSON config, no path to type.

repo-graph gives the AI a graph of your codebase — entities, relationships, and
feature flows — so it navigates straight to the files that matter instead of
grepping and reading everything first. Works across 20+ languages/frameworks
(Go, Rust, TypeScript/React/Angular/Vue, Python, Java, C#, …) with cross-stack
linking between frontend calls and backend routes.

Six tools show up in agent mode: **`orient`** (the lay of the land, and where the
graph is blind), **`find`** (turn a symbol, a stacktrace, a failing test or a diff
into the ranked nodes that matter), **`impact`** (blast radius, dead code flagged
⊘), **`trace`** (a feature end-to-end, or the path between two nodes), **`read`**
(exact source plus who calls it and what tests it) and **`refresh`**.

When the graph can't answer, it says why: the reason, whether that reason is a
fact or a heuristic, and which extractions are partial. Better than an empty
result the model reads as "nothing uses this".

## Requirements

- [`uv`](https://docs.astral.sh/uv/) on your `PATH`. The extension runs
  `uvx mcp-repo-graph`, which fetches the package and its prebuilt Rust engine
  wheel on first use — no Python or Rust toolchain setup required.

## How it works

On activation the extension provisions an MCP stdio server:

```
uvx mcp-repo-graph --repo <your-workspace-folder>
```

VS Code's agent then gets repo-graph's 6 tools: `orient` (repo shape + where the
graph is blind), `find` (a symbol, keyword, stacktrace, failing test, or diff →
the ranked nodes that matter), `impact` (blast radius, dead code flagged `⊘`),
`trace` (a feature end-to-end, or the path between two nodes), `read` (a node's
exact source), and `refresh` (rebuild). The `--repo` argument follows your active
workspace folder automatically.

## Usage

1. Install the extension.
2. Open a project folder.
3. In agent mode, repo-graph's tools are available — ask things like
   *"what does this codebase do?"* or *"trace the checkout flow"*.

## Links

- [GitHub](https://github.com/James-Chahwan/repo-graph)
- [PyPI](https://pypi.org/project/mcp-repo-graph/)
- [MCP Registry](https://registry.modelcontextprotocol.io/)

MIT licensed.
