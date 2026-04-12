# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

An MCP server that provides structural navigation, context budgeting, health analysis, and visual graph maps for any codebase. It auto-detects project languages/frameworks, builds a graph of entities and relationships, and exposes tools for tracing feature flows, impact analysis, file hotspot detection, split planning, and ASCII visual maps.

Supports Go, Rust, TypeScript, React, Angular, Python, Java/Kotlin, C#/.NET, Ruby, PHP, Swift, C/C++, and SCSS out of the box. New languages are added by creating a single analyzer file.

## Commands

```bash
# Install (editable, for development)
pip install -e .

# Run the MCP server (points at a target repo)
repo-graph --repo /path/to/target-repo

# Generate graph data for a target repo (CLI)
repo-graph-generate --repo /path/to/target-repo

# Test on this repo itself
repo-graph-generate --repo .
```

There are no tests in this project. Python 3.11+ required. Only dependency: `mcp[cli]>=1.0.0`.

## Architecture

### Module structure

```
repo_graph/
  server.py              MCP server — 13 tools in 4 tiers
  graph.py               Graph loader + BFS traversal engine
  generator.py           Orchestrator — discovers analyzers, merges results, writes output
  analyzers/
    __init__.py           Registry — discover_analyzers(), get_file_analyzer()
    base.py               LanguageAnalyzer ABC + Node/Edge/AnalysisResult dataclasses
    go.py                 Go: packages, functions, HTTP routes, imports
    rust.py               Rust: crates, modules, structs, traits, routes (Actix/Rocket/Axum)
    typescript.py         TypeScript: modules, classes, exports, imports
    react.py              React: components, hooks, context, React Router, fetch/axios calls
    angular.py            Angular: components, services, guards, DI, HTTP calls
    python_lang.py        Python: modules, classes, functions, Flask/FastAPI/Django routes
    java.py               Java/Kotlin: packages, classes, Spring/JAX-RS routes
    csharp.py             C#/.NET: namespaces, classes, ASP.NET/Minimal API routes
    ruby.py               Ruby: files, classes, modules, Rails routes
    php.py                PHP: namespaces, classes, interfaces, Laravel/Symfony routes
    swift.py              Swift: files, types (class/struct/enum/protocol/actor), Vapor routes
    c_cpp.py              C/C++: sources, headers, classes, structs, enums, namespaces
    scss.py               SCSS: file-level analysis only (bloat_report, no graph nodes)
```

### Data flow

`generator.py` discovers analyzers → each `analyzer.scan()` returns nodes/edges/flows → generator merges & deduplicates → writes `.ai/repo-graph/` → `graph.py` loads it → `server.py` exposes it via MCP tools.

### MCP tool tiers

- **Generation**: `generate` — scan codebase and (re)build graph
- **Navigation**: `status`, `flow`, `trace`, `impact`, `neighbours`
- **Budgeting**: `cost`, `hotspots`, `minimal_read`
- **Health**: `bloat_report`, `split_plan`, `graph_view`, `reload`

### Adding a new language analyzer

1. Create `repo_graph/analyzers/<language>.py`
2. Subclass `LanguageAnalyzer` from `base.py`
3. Implement `detect(repo_root)` — check for marker files (e.g., `Cargo.toml`)
4. Implement `scan()` — return `AnalysisResult` with nodes, edges, flows
5. Optionally implement `supported_extensions()`, `analyze_file()`, `suggest_splits()`, `format_bloat_report()`, `format_split_plan()` for file-level health tools
6. Add the class to `_analyzer_classes()` in `analyzers/__init__.py`

### Key design decisions

- Analyzers use regex heuristics, not AST parsing — keeps dependencies at zero and works across languages with a consistent approach.
- Multiple analyzers can match one repo (e.g., Go + SCSS in a monorepo). Results are merged and deduplicated by the orchestrator.
- `graph.py` is fully generic — it only reads `nodes.json`/`edges.json`/`flows/*.yaml`. No language assumptions.
- Graph singleton in `server.py` is lazy-loaded and reset by `reload`/`generate` tools.
- The `generate` tool allows Claude to trigger graph rebuilds mid-conversation without restarting the server.

## Publishing & Releases

Package is live on PyPI as `mcp-repo-graph` and on the MCP Registry as `io.github.James-Chahwan/repo-graph`.

### Release process (version bump)

```bash
# 1. Update version in BOTH files
#    - pyproject.toml: version = "X.Y.Z"
#    - server.json: "version": "X.Y.Z" (appears twice — top-level and in packages)

# 2. Build
rm -rf dist/ && python -m build

# 3. Upload to PyPI
twine upload dist/* -u __token__ -p <PYPI_TOKEN>

# 4. Publish to MCP Registry (token expires each session)
/tmp/mcp-publisher login github
/tmp/mcp-publisher publish

# 5. Commit and push
git add pyproject.toml server.json
git commit -m "chore: bump to X.Y.Z"
git push github main && git push gitlab main
```

If `/tmp/mcp-publisher` is missing, re-download:
```bash
curl -sL "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_linux_amd64.tar.gz" | tar xz -C /tmp/
```

### Check stats

```bash
# PyPI downloads (takes ~24h for first data)
pypistats overall mcp-repo-graph

# GitHub traffic (last 14 days, owner only)
gh api repos/James-Chahwan/repo-graph/traffic/clones
gh api repos/James-Chahwan/repo-graph/traffic/views
gh api repos/James-Chahwan/repo-graph --jq '.stargazers_count'
```

Web: https://pypistats.org/packages/mcp-repo-graph

### Remotes

- `github` — git@github.com:James-Chahwan/repo-graph.git (public, primary)
- `gitlab` — git@gitlab.com:jameschahwan/repo-graph.git (private, backup)

Always push to both: `git push github main && git push gitlab main`

## Roadmap

Planned features (not yet implemented):

- **Init/bootstrap system** — `repo-graph-init` command where the LLM helps discover project structure on first run, saves config to `.ai/repo-graph/config.yaml` for future generations
- **Promotion** — share on Reddit (r/ChatGPTPro, r/ClaudeAI, r/MachineLearning), Hacker News, X/Twitter, MCP community channels, Claude Code Discord. Lead with the pitch: "stop wasting LLM context on orientation — give it a map instead"
- **More analyzers** — Elixir, Dart/Flutter, Scala, Zig as community requests come in
- **Smarter flows** — use call graph analysis to build more precise flows instead of BFS from routes
- **Config file** — let users define custom entry points, skip patterns, and feature groupings
