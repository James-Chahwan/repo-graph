# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A thin **Python MCP server** that wraps the **glia** Rust engine (crate `repo-graph-py`, PyPI `repo-graph-py`). It exposes 13 MCP tools for structural navigation, context budgeting, health analysis, and visual graph maps over any codebase.

The Python side is ~900 lines across 4 files. All parsing, graph building, storage (`.gmap`), and activation happen in Rust. The Python package only hosts the MCP server, the CLI entrypoints, and a thin wrapper over the pyo3 bindings.

## Commands

```bash
# Install (editable, for development)
pip install -e .

# Run the MCP server (points at a target repo)
repo-graph --repo /path/to/target-repo

# Initialise a new target repo (writes .mcp.json + CLAUDE.md instructions + first graph)
repo-graph-init --repo /path/to/target-repo
```

Python 3.11+ required. Runtime deps: `mcp[cli]>=1.0.0`, `repo-graph-py>=0.4.12`.

## Architecture

```
repo_graph/
  server.py   MCP server — 13 tools across 4 tiers, wraps repo-graph-py
  graph.py    Graph loader — reads .gmap via pyo3, BFS traversal helpers
  init.py     repo-graph-init CLI — bootstraps a target repo
  __init__.py empty
```

The Rust engine is a separate workspace under `rust/` and will split into its own repo (`glia`) post-0.4.12. See `rust/CLAUDE.md` for the engine architecture, parser model, `.gmap` format, and activation design.

### MCP tool tiers

- **Generation**: `generate` — scan codebase and (re)build graph
- **Navigation**: `status`, `flow`, `trace`, `impact`, `neighbours`
- **Budgeting**: `cost`, `hotspots`, `minimal_read`
- **Health**: `bloat_report`, `split_plan`, `graph_view`, `reload`

### Python/Rust boundary

Python calls into `repo_graph_py` (the pyo3 extension module shipped as PyPI package `repo-graph-py`). That module re-exports a small surface: generate, load graph, list nodes/edges, run activation, write `.gmap`. Everything else — parsers, resolvers, store layout, text projection — stays in Rust.

Do not port Rust logic back to Python. The Python side is intentionally minimal and should stay that way.

## Publishing & Releases

Two packages ship from this repo:

- `repo-graph-py` — pyo3 wheel built by maturin (from `rust/py/`)
- `mcp-repo-graph` — pure-Python MCP server (from root)

Also registered on the MCP Registry as `io.github.James-Chahwan/repo-graph`.

### Release process (version bump)

```bash
# 1. Bump versions
#    - rust/py/Cargo.toml: version = "X.Y.Z"
#    - pyproject.toml:     version = "X.Y.Z"; "repo-graph-py>=X.Y.Z"
#    - server.json:        "version" (top-level + packages[].version)

# 2. Build + publish repo-graph-py (linux x86_64 wheel for Glama Docker)
cd rust/py
maturin build --release
twine upload target/wheels/repo_graph_py-*.whl -u __token__ -p <PYPI_TOKEN>
cd ../..

# 3. Build + publish mcp-repo-graph
rm -rf dist/ && python -m build
twine upload dist/* -u __token__ -p <PYPI_TOKEN>

# 4. Publish to MCP Registry (token expires each session)
/tmp/mcp-publisher login github
/tmp/mcp-publisher publish

# 5. Commit, tag, push both remotes
git add -A
git commit -m "chore: bump to X.Y.Z"
git tag vX.Y.Z
git push github main && git push gitlab main
git push github --tags && git push gitlab --tags

# 6. Cut GitHub release
gh release create vX.Y.Z --title "vX.Y.Z" --notes "release notes here"
```

If `/tmp/mcp-publisher` is missing, re-download:
```bash
curl -sL "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_linux_amd64.tar.gz" | tar xz -C /tmp/
```

### Check stats

```bash
pypistats overall mcp-repo-graph
gh api repos/James-Chahwan/repo-graph/traffic/clones
gh api repos/James-Chahwan/repo-graph/traffic/views
gh api repos/James-Chahwan/repo-graph --jq '.stargazers_count'
```

### Remotes

- `github` — git@github.com:James-Chahwan/repo-graph.git (public, primary)
- `gitlab` — git@gitlab.com:jameschahwan/repo-graph.git (private, backup)

Always push to both: `git push github main && git push gitlab main`

## Roadmap

- **0.4.13** — PyPI wheel matrix via maturin GitHub Actions (linux x86_64/aarch64, macos x86_64/arm64, windows x86_64 × Python 3.11–3.14). Latent-vector hook in candle; SWE-bench Lite N=20–30 run on Runpod 4090 with Qwen 2.5 Coder 7B.
- **Post-0.4.13** — split `rust/` into its own `glia` repo via `git filter-repo`. This repo stays as the Python MCP wrapper.
- **0.5.0** — rename this package in lockstep with the glia split maturing into a multi-domain engine (code is first primitive; video/molecules/policy slot in via registries).
