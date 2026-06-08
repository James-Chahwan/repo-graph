# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A thin **Python MCP server** that wraps the **glia** Rust engine (crate `repo-graph-py`, PyPI `repo-graph-py`). It exposes **11 MCP tools** across four tiers — generation, navigation, activation & context, health & admin — over any codebase.

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

Python 3.11+ required. Runtime deps: `mcp[cli]>=1.0.0`, `repo-graph-py>=0.4.16`.

### Cache reuse on cold start

Since engine v0.4.14 the wrapper caches the graph at `<repo>/.ai/repo-graph/` (sharded `.gmap` files). On every server start `get_graph()` checks `is_stale(gmap_dir, repo_path)`:

- **Fresh cache** → `load_from_gmap()` (≈10× faster than re-scanning; a 22k-node repo loads in ~250ms instead of ~2.8s).
- **Stale or missing** → `generate()` + `save_to_default()` so the next cold start is fast.

Cache writes are best-effort: a read-only filesystem or perms error doesn't break the live graph. The `generate` MCP tool always writes the cache after a successful scan; the `reload` tool now forces a real re-generate (not just a `.gmap` reload), so edits between calls always show up. Source-tree change detection for the `.gmap` staleness check is mtime-based and skips `.git`, `target`, `node_modules`, `.venv`, `__pycache__`, `.ai/`.

#### Incremental parse cache (engine v0.4.16)

`generate` and `reload` take `incremental: bool = True`. When on, the engine reuses a per-file parse cache at `<repo>/.ai/repo-graph/parse_cache.bin` (content-hashed; mtime fast-path deferred to a v2) so unchanged files skip tree-sitter re-parsing — only edited files re-parse. `incremental=False` forces a full reparse. The internal `_build_graph(target, incremental)` helper is the single path through which `get_graph` (cold regen), `generate`, and `reload` all build + cache the graph. Incremental output is equivalent to a full reparse (same nodes/edges/cross-edges and same dense-text line set; raw dense-text *order* is nondeterministic across independent generates — only a `.gmap` round-trip is order-stable). The engine logs `[incremental] reused N, reparsed M` to **stderr** (safe for the MCP stdio channel).

### Testing

```bash
pip install -e ".[dev]"          # installs pytest + pytest-asyncio
pytest                           # full suite (65 tests in ~9s, incl. e2e subprocess)
pytest -m "not e2e"              # fast loop — skip MCP subprocess spin-up
pytest -m perf                   # opt-in performance gates
pytest -m e2e                    # only MCP-over-stdio end-to-end tests
```

Six test layers:
- `test_mcp_tools.py` — in-process @mcp.tool function calls (22 tests)
- `test_mcp_e2e.py` — spawn `repo-graph` subprocess, talk MCP/JSON-RPC over stdio (14 tests)
- `test_cache.py` — `.gmap` cache reuse roundtrip + incremental parse cache (9 tests)
- `test_init.py` — `repo-graph-init` bootstrap CLI (5 tests)
- `test_packaging.py` — install surface: `uvx`-runnable console script + server.json sync (3 tests)
- `test_perf.py` — generate/dense_text/activate budgets (6 tests)

## Architecture

```
repo_graph/
  server.py   MCP server — 11 tools across 4 tiers, wraps repo-graph-py
  graph.py    Graph loader — reads .gmap via pyo3, BFS traversal helpers
  init.py     repo-graph-init CLI — bootstraps a target repo
  __init__.py empty
```

The Rust engine lives in a separate repo (`glia` at `/home/ivy/Code/glia`) as of 2026-05-09. The `rust/` subtree in this repo is a stale snapshot — engine source-of-truth is in glia.

### MCP tool tiers

- **Generation**: `generate` — scan codebase and (re)build graph
- **Navigation**: `status`, `flow`, `trace`, `impact`, `neighbours`
- **Activation & Context**: `activate`, `find`, `dense_text`
- **Health & Admin**: `graph_view`, `reload`

Lock: the public tool surface is asserted by `tests/test_mcp_tools.py::test_eleven_tools_decorated`. Adding or removing a tool must update both `server.py` and this list.

### Python/Rust boundary

Python calls into `repo_graph_py` (the pyo3 extension module shipped as PyPI package `repo-graph-py`). That module re-exports a small surface: generate, load graph, list nodes/edges, run activation, write `.gmap`. Everything else — parsers, resolvers, store layout, text projection — stays in Rust.

Do not port Rust logic back to Python. The Python side is intentionally minimal and should stay that way.

## Publishing & Releases

Two packages ship from this repo:

- `repo-graph-py` — pyo3 wheel built by maturin (from `rust/py/`)
- `mcp-repo-graph` — pure-Python MCP server (from root)

Also registered on the MCP Registry as `io.github.James-Chahwan/repo-graph`.

### Release process (version bump)

**Release gate: `pytest` must be green before any publish step.** All 55 tests across the six layers (cache, init, e2e, mcp_tools, packaging, perf) are the contract. No PyPI upload, no MCP Registry publish, no tag, no GitHub release without this. If a test is broken, fix the test or fix the code — never skip past it.

```bash
# 0. Release gate — non-negotiable
pytest                             # full suite, must be all green
pytest -m perf                     # perf gates must pass

# 1. Bump versions
#    - glia/py/Cargo.toml:    version = "X.Y.Z"   (engine — source of truth is the glia repo)
#    - glia/py/pyproject.toml: version = "X.Y.Z"
#    - pyproject.toml:        version = "X.Y.Z"; "repo-graph-py>=X.Y.Z"
#    - server.json:           "version" (top-level + packages[].version)

# 2. Build + publish repo-graph-py — ALL platforms via CI, not a local single-platform build.
#    A local `maturin build` only produces the host wheel (linux x86_64); publishing just
#    that breaks `pip install` on macOS / Windows / aarch64. Drive the full matrix from glia:
#      git -C ../glia tag vX.Y.Z && git -C ../glia push origin vX.Y.Z   # → wheels-py.yml publishes 5 wheels + sdist
#    Or, to backfill missing-platform wheels for the CURRENT version without a new tag:
#      gh workflow run wheels-py.yml -R James-Chahwan/glia                # skip-existing leaves uploaded files alone
#    Publishing uses PyPI OIDC trusted publishing (no token). One-time setup: add GitHub
#    Actions (owner James-Chahwan, repo glia, workflow wheels-py.yml) as a trusted publisher
#    at https://pypi.org/manage/project/repo-graph-py/settings/publishing/
#    Verify the matrix landed before continuing:
#      curl -s https://pypi.org/pypi/repo-graph-py/json | python -c "import sys,json;[print(f['filename']) for f in json.load(sys.stdin)['urls']]"

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
