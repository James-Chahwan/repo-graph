# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A thin **Python MCP server** that wraps the **glia** Rust engine (crate `glia-py`, PyPI `glia-py`). It exposes **6 MCP tools** — `orient`, `find`, `impact`, `trace`, `read`, `refresh` — over any codebase. Each is a natural verb backed by an engine primitive (v0.5.0: `find`, `blast_radius`, `cross_stack_trace`, `resolve`, `entry_flows`, `coverage`, `governing_docs`), so the wrapper stays thin — the engine owns lookup, traversal, ranking, `file`/`line` locating, and the `live` (dead-code) flag.

The Python side is ~900 lines across 4 files. All parsing, graph building, storage (`.gmap`), activation, ranking, locating, and liveness happen in Rust. The Python package only hosts the MCP server, the CLI entrypoints, and a thin wrapper over the pyo3 bindings.

## Commands

```bash
# Install (editable, for development)
pip install -e .

# Run the MCP server (points at a target repo)
repo-graph --repo /path/to/target-repo

# Initialise a new target repo (writes .mcp.json + CLAUDE.md instructions + first graph)
repo-graph-init --repo /path/to/target-repo
```

Python 3.11+ required. Runtime deps: `mcp[cli]>=1.0.0,<2` (2.x renamed FastMCP — port before lifting), `glia-py>=0.5.0`.

### Cache reuse on cold start

The wrapper caches the graph at `<repo>/.glia/graph/` (sharded `.gmap` files). Since glia 0.5.0 (LC.8) `load_from_gmap(dir, repo_path)` **self-heals** — it rebuilds a stale, old-format or missing layout itself and writes it back — so `get_graph()` has no `is_stale` pre-check any more:

- `load_from_gmap(default_gmap_dir(repo), repo)` — serves the layout, rebuilding it in place if it can't.
- `ValueError` → fall back to `_build_graph()` (a full `generate` + `save_to_default`).

`generate` is a **pure build** in 0.5.0: it writes no layout, so the explicit `save_to_default` in `_build_graph` is the only thing keeping the next cold start fast. Cache writes are best-effort: a read-only filesystem or perms error doesn't break the live graph.

The layout dir ignores itself (`.glia/graph/.gitignore` = `*`), so it never shows in `git status`; `gitexclude.py` is now only a safety net for a layout written elsewhere. Note `.glia/` also holds committed **inputs** (`overlay.toml`, `cells.jsonl`, `vectors.jsonl`) — never blanket-skip `.glia`, only the `default_gmap_dir` prefix.

#### Incremental parse cache

`refresh` takes `full: bool = False` and passes `incremental=not full`. When incremental, the engine reuses a per-file parse cache at `<repo>/.glia/graph/parse_cache.bin` (content-hashed; mtime fast-path deferred to a v2) so unchanged files skip tree-sitter re-parsing — only edited files re-parse. `incremental=False` forces a full reparse — and it is the engine's **default** since 0.5.0, so every call site passes `incremental=` explicitly. The internal `_build_graph(target, incremental)` helper is the single path through which `get_graph` (cold regen), the watcher, and `refresh` all build + cache the graph. Incremental output is equivalent to a full reparse (same nodes/edges/cross-edges and same dense-text line set; raw dense-text *order* is nondeterministic across independent generates — only a `.gmap` round-trip is order-stable). The engine logs `[incremental] reused N, reparsed M` to **stderr** (safe for the MCP stdio channel).

### Testing

```bash
pip install -e ".[dev]"          # installs pytest + pytest-asyncio
pytest                           # full suite (150 tests in ~10s, incl. e2e subprocess)
pytest -m "not e2e"              # fast loop — skip MCP subprocess spin-up
pytest -m perf                   # opt-in performance gates
pytest -m e2e                    # only MCP-over-stdio end-to-end tests
```

Test layers:
- `test_mcp_tools.py` — in-process @mcp.tool function calls, the 6-tool surface (38 tests)
- `test_mcp_e2e.py` — spawn `repo-graph` subprocess, talk MCP/JSON-RPC over stdio (12 tests)
- `test_installer.py` — `repo-graph install` config writers across agents (45 tests)
- `test_cache.py` — `.gmap` cache reuse roundtrip + incremental parse cache (9 tests)
- `test_gitexclude.py` — cache kept out of `git status` via `info/exclude` (10 tests)
- `test_watcher.py` — in-server file watcher, incl. the rebuild-loop guard (10 tests)
- `test_grade.py` — bench recall/precision grader (7 tests)
- `test_packaging.py` — install surface: `uvx`-runnable console script + annotations + mcp<2 cap (8 tests)
- `test_perf.py` — generate/dense_text/activate budgets (6 tests)
- `test_init.py` — `repo-graph-init` bootstrap CLI (5 tests)

## Architecture

```
repo_graph/
  server.py   MCP server — 6 tools, thin presentation over engine primitives
  graph.py    Graph loader — reads .gmap via pyo3, BFS traversal helpers
  watcher.py  in-server file watcher — write-events only, skips the layout dir by prefix
  gitexclude.py  adds the layout dir to .git/info/exclude on cache write (safety net; the dir self-ignores)
  init.py     repo-graph-init CLI — bootstraps a target repo
  __init__.py empty
```

The Rust engine lives in a separate repo (`glia` at `/home/ivy/Code/glia`) as of 2026-05-09. This repo no longer carries a `rust/` subtree — it was removed on 2026-06-10 once the glia CI wheel matrix was green. This repo is purely the Python MCP wrapper; it consumes the published `glia-py` wheel (`>=0.5.0`).

### The 6 MCP tools

Collapsed from 13 in the v0.4.18 cycle. Ported to the glia 0.5.0 primitives in the 0.5.0 cycle — handoff `dev-notes/repo-graph-handoff-0.5.0.md` (copied from `../glia/dev-notes/`). Each verb folds several old tools into one engine primitive:

- **`orient`** (← `status` + `dense_text` + `graph_view` + `coverage`) — overview + entry points + a `blind spots` note (from engine `coverage()`) flagging which languages/edges are under-linked so the agent falls back to grep deliberately. `seed=<node>` → scoped map; `full=true` → whole-repo dense map.
- **`find`** (← `find` + `locate` + `activate`) — any text → ranked located nodes. A symbol/keyword returns matches; a pasted stacktrace/failing-test/diff is resolved via engine `resolve`. `expand=true` fans out to the PPR-ranked neighbourhood. Every row carries `path:line`.
- **`impact`** (← `impact` + `neighbours`) — blast radius via engine `blast_radius`: complete, deduped, PPR-ranked, located, live-filtered closure with a per-node `via <reason>` and `⊘` dead-code marker. Structural import/containment fan-out is excluded (no noise). `direction` forward/backward/both (downstream/upstream aliases); `live_only` drops likely-dead; depth-1 both = neighbours. Comma-separate nodes for a whole-diff radius.
- **`trace`** (← `flow` + `trace`) — one arg: feature end-to-end via engine `cross_stack_trace` (mechanism-labelled hops, cross-service marked), falling back to entry-point flow layering. Two args: shortest path A→B.
- **`read`** — a node's exact source sliced from its span, plus a `context:` footer from `node_cells` (method / cross-stack callers / covering tests / intent-decision-constraint). Comma-separate to batch-read a ranked set.
- **`refresh`** (← `generate` + `reload`) — rebuild the graph; `repo_path` retargets (path or git URL), `full=true` forces a clean reparse. Incremental by default; routine edits are auto-picked-up by the file watcher.

Most read tools take a `budget` char cap. Liveness (`live`/`⊘`) and `file`/`line` come from the engine now — the wrapper no longer re-derives them.

Lock: the public tool surface is asserted by `tests/test_mcp_tools.py::test_six_tools_decorated` (checked against the live MCP registry, catches added *and* removed tools) and `tests/test_installer.py::test_tool_names_match_server_registry`. Adding or removing a tool must update `server.py`, `installer/constants.py` `TOOL_NAMES`, and this list in lockstep.

### glia 0.5.0 boundary notes

The breaking changes the wrapper absorbed (full detail in `dev-notes/repo-graph-handoff-0.5.0.md`):

- **Module renamed** `repo_graph_py` → `glia_py`; PyPI `repo-graph-py` → `glia-py`. The wrapper's own names (`mcp-repo-graph`, the `repo-graph` scripts, the registry slug) are unchanged.
- **Native returns.** Primitives return dicts/lists, not JSON strings. `resolve`, `find`, `blast_radius`, `cross_stack_trace` and `governing_docs` return a `{results, absence}` envelope — `_rows()` unwraps it, `_render_absence()` renders the engine's own account of an empty answer instead of a wrapper guess.
- **`find_node` / `find_nodes_by_qname` are gone** — one `find(query, top_k, kinds, scope)` replaces them.
- **Traversal moved into the engine** (`bfs` / `predecessors` / `shortest_path` / `entry_flows`), so `graph.py` keeps **no adjacency copy** — it is a node index plus forwarders.
- **1-based lines** everywhere (LD.1), so `_eloc` tests `line is not None`, never truthiness.
- **Tier by role, not kind.** A component/service/hook is a CLASS/FUNCTION carrying a ROLE cell; `nodes_json` rows gain `roles`, `entry`, `live`. `_effective_kind()` prefers the role; `_classify_tier()` trusts the engine's `entry` flag.
- **No hand-kept id tables.** Entry kinds come from `entry_kinds()`, cell labels from `cell_type_names()`. Adding an id to a literal set in this repo is a bug.
- **Layout moved** `.ai/repo-graph/` → `.glia/graph/` and self-ignores.

### Python/Rust boundary

Python calls into `glia_py` (the pyo3 extension module shipped as PyPI package `glia-py`). That module re-exports a small surface: generate, load graph, list nodes/edges, run activation, write `.gmap`. Everything else — parsers, resolvers, store layout, text projection — stays in Rust.

Do not port Rust logic back to Python. The Python side is intentionally minimal and should stay that way.

## Publishing & Releases

Two packages ship from this repo:

- `glia-py` — pyo3 wheel built by maturin (from `py/` in the glia repo)
- `mcp-repo-graph` — pure-Python MCP server (from root)

Also registered on the MCP Registry as `io.github.James-Chahwan/repo-graph`.

### Release process (version bump)

**Release gate: `pytest` must be green before any publish step.** All 150 tests across the ten layers are the contract. No PyPI upload, no MCP Registry publish, no tag, no GitHub release without this. If a test is broken, fix the test or fix the code — never skip past it.

```bash
# 0. Release gate — non-negotiable
pytest                             # full suite, must be all green
pytest -m perf                     # perf gates must pass

# 1. Bump versions
#    - glia/py/Cargo.toml:    version = "X.Y.Z"   (engine — source of truth is the glia repo)
#    - glia/py/pyproject.toml: version = "X.Y.Z"
#    - pyproject.toml:        version = "X.Y.Z"; "glia-py>=X.Y.Z"
#    - server.json:           "version" (top-level + packages[].version)

# 2. Build + publish glia-py — ALL platforms via CI, not a local single-platform build.
#    A local `maturin build` only produces the host wheel (linux x86_64); publishing just
#    that breaks `pip install` on macOS / Windows / aarch64. Drive the full matrix from glia:
#      git -C ../glia tag vX.Y.Z && git -C ../glia push origin vX.Y.Z   # → wheels-py.yml publishes 5 wheels + sdist
#    Or, to backfill missing-platform wheels for the CURRENT version without a new tag:
#      gh workflow run wheels-py.yml -R James-Chahwan/glia                # skip-existing leaves uploaded files alone
#    Publishing uses PyPI OIDC trusted publishing (no token). One-time setup: add GitHub
#    Actions (owner James-Chahwan, repo glia, workflow wheels-py.yml) as a trusted publisher
#    at https://pypi.org/manage/project/glia-py/settings/publishing/
#    Verify the matrix landed before continuing:
#      curl -s https://pypi.org/pypi/glia-py/json | python -c "import sys,json;[print(f['filename']) for f in json.load(sys.stdin)['urls']]"

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
- **Post-0.4.13** — ✅ done. Split `rust/` into its own `glia` repo (2026-05-09) and removed the stale subtree from this repo (2026-06-10). This repo stays as the Python MCP wrapper.
- **0.5.0** — ✅ ported. The engine package renamed `repo-graph-py` → `glia-py` and the wrapper moved onto the 0.5.0 primitives (see the boundary notes above). This package is still `mcp-repo-graph`: renaming it in lockstep with the multi-domain engine (code is first primitive; video/molecules/policy slot in via registries) is still **open** — the 0.5.0 handoff left it to this repo.
- **Open after 0.5.0** — a non-MCP way in: a Claude Code skill plus a `repo-graph` CLI entry point sharing `server.py`'s renderers, for CI and low-memory machines (handoff §7b). Lifting the `mcp[cli]<2` cap (handoff §6). Both are independent of the glia release.
