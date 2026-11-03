# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A thin **Python MCP server** that wraps the **glia** Rust engine (crate `glia-py`, PyPI `glia-py`). It exposes **6 MCP tools** — `orient`, `find`, `impact`, `trace`, `read`, `refresh` — over any codebase. Each is a natural verb backed by an engine primitive (v0.5.0: `find`, `blast_radius`, `cross_stack_trace`, `resolve`, `entry_flows`, `coverage`, `governing_docs`), so the wrapper stays thin — the engine owns lookup, traversal, ranking, `file`/`line` locating, and the `live` (dead-code) flag.

The Python side is a handful of small modules (server, CLI, graph loader, watcher, installer). All parsing, graph building, storage (`.gmap`), activation, ranking, locating, and liveness happen in Rust. The Python package only hosts the MCP server, the CLI entrypoints, and a thin wrapper over the pyo3 bindings.

## Commands

```bash
# Install (editable, for development)
pip install -e .

# Run the MCP server (points at a target repo)
repo-graph --repo /path/to/target-repo

# Or ask one question and exit, no server: each tool is a subcommand
repo-graph find checkout --repo /path/to/target-repo
git diff | repo-graph find - --kind diff      # `-` reads a positional from stdin

# Initialise a new target repo (writes .mcp.json + CLAUDE.md instructions + first graph)
repo-graph-init --repo /path/to/target-repo
```

Python 3.11+ required. Runtime deps: `mcp[cli]>=2,<3` (2.x renamed FastMCP → MCPServer; ported in 0.5.1), `glia-py==0.5.7` (glia pins consumers exactly per release), `watchdog>=3.0,<7`.

### Cache reuse on cold start

The wrapper caches the graph at `<repo>/.glia/graph/` (sharded `.gmap` files). Since glia 0.5.0 (LC.8) `load_from_gmap(dir, repo_path)` **self-heals** — it rebuilds a stale, old-format or missing layout itself and writes it back — so `get_graph()` has no `is_stale` pre-check any more:

- `load_from_gmap(default_gmap_dir(repo), repo)` — serves the layout, rebuilding it in place if it can't.
- `ValueError` → fall back to `_build_graph()` (a full `generate` + `save_to_default`).

`generate` is a **pure build** in 0.5.0: it writes no layout, so the explicit `save_to_default` in `_build_graph` is the only thing keeping the next cold start fast. Cache writes are best-effort: a read-only filesystem or perms error doesn't break the live graph.

The layout dir ignores itself (`.glia/graph/.gitignore` = `*`), so it never shows in `git status`; `gitexclude.py` is now only a safety net for a layout written elsewhere. Note `.glia/` also holds committed **inputs** (`overlay.toml`, `cells.jsonl`, `vectors.jsonl`) — never blanket-skip `.glia`, only the `default_gmap_dir` prefix.

#### Incremental parse cache

`refresh` takes `full: bool = False` and passes `incremental=not full`. When incremental, the engine reuses a per-file parse cache at `<repo>/.glia/graph/parse_cache.bin` (content-hashed; mtime fast-path deferred to a v2) so unchanged files skip tree-sitter re-parsing — only edited files re-parse. `incremental=False` forces a full reparse — and it is the engine's **default** since 0.5.0, so every call site passes `incremental=` explicitly. The internal `_build_graph(target, incremental)` helper is the single path through which `get_graph` (cold regen) and `refresh` build + cache the graph; the watcher uses it only until its session is open (see the glia 0.5.2 notes). Incremental output is equivalent to a full reparse (same nodes/edges/cross-edges and same dense-text line set; raw dense-text *order* is nondeterministic across independent generates — only a `.gmap` round-trip is order-stable). The engine logs `[incremental] reused N, reparsed M` to **stderr** (safe for the MCP stdio channel).

### Testing

```bash
pip install -e ".[dev]"          # installs pytest + pytest-asyncio
pytest                           # full suite (234 tests in ~17s, incl. e2e subprocess)
pytest -m "not e2e"              # fast loop — skip MCP subprocess spin-up
pytest -m perf                   # opt-in performance gates
pytest -m e2e                    # only MCP-over-stdio end-to-end tests
```

Test layers:
- `test_mcp_tools.py` — in-process @mcp.tool function calls, the 6-tool surface (56 tests)
- `test_mcp_e2e.py` — spawn `repo-graph` subprocess, talk MCP/JSON-RPC over stdio, incl. a live edit served through the watch session (13 tests)
- `test_installer.py` — `repo-graph install` config writers across agents (45 tests)
- `test_cache.py` — `.gmap` cache reuse roundtrip + incremental parse cache + the engine's heap trim when a rebuild drops a graph (10 tests)
- `test_gitexclude.py` — cache kept out of `git status` via `info/exclude` (10 tests)
- `test_watcher.py` — in-server file watcher, incl. the rebuild-loop guard, and the held `WatchSession` update / persist / retarget path (19 tests)
- `test_grade.py` — bench recall/precision grader (7 tests)
- `test_packaging.py` — install surface: `uvx`-runnable console script + annotations + every dependency major-capped or exactly pinned (12 tests)
- `test_perf.py` — generate/dense_text/activate budgets (6 tests)
- `test_init.py` — `repo-graph-init` bootstrap CLI (5 tests)
- `test_cli.py`: `repo-graph <tool>` one-shot commands, with output identical to the MCP tool, flags read off the signature, stdin, quiet engine log (25 tests)
- `test_skills.py`: `skills/` held to the live surface, checking MCP args vs tool signatures, shell commands vs the CLI parser, plugin copy in sync (26 tests)

## Architecture

```
repo_graph/
  server.py   MCP server — 6 tools, thin presentation over engine primitives
  cli.py      `repo-graph <tool> ...`: the same 6 tools as one-shot commands, flags built from their signatures
  graph.py    Graph loader — reads .gmap via pyo3, BFS traversal helpers
  watcher.py  in-server file watcher — write-events only, skips the layout dir by prefix and skip dirs only below the repo root; triggers the held WatchSession
  gitexclude.py  adds the layout dir to .git/info/exclude on cache write (safety net; the dir self-ignores)
  init.py     repo-graph-init CLI — bootstraps a target repo
  __init__.py empty
```

The Rust engine lives in a separate repo (`glia` at `/home/ivy/Code/glia`) as of 2026-05-09. This repo no longer carries a `rust/` subtree — it was removed on 2026-06-10 once the glia CI wheel matrix was green. This repo is purely the Python MCP wrapper; it consumes the published `glia-py` wheel (`==0.5.7`).

### The 6 MCP tools

Collapsed from 13 in the v0.4.18 cycle. Ported to the glia 0.5.0 primitives in the 0.5.0 cycle — handoff `dev-notes/repo-graph-handoff-0.5.0.md` (copied from `../glia/dev-notes/`). Each verb folds several old tools into one engine primitive:

- **`orient`** (← `status` + `dense_text` + `graph_view` + `coverage`) — overview + entry points + a `blind spots` note (from engine `coverage()`) flagging which languages/edges are under-linked so the agent falls back to grep deliberately. `seed=<node>` → scoped map; `full=true` → whole-repo dense map.
- **`find`** (← `find` + `locate` + `activate`) — any text → ranked located nodes. A symbol/keyword returns matches; a pasted stacktrace/failing-test/diff is resolved via engine `resolve`. `expand=true` fans out to the PPR-ranked neighbourhood. Every row carries `path:line`.
- **`impact`** (← `impact` + `neighbours`) — blast radius via engine `blast_radius`: deduped, ranked (co-change first where a history snapshot exists, then PPR), located, live-filtered closure with a per-node `via <reason>` and `⊘` dead-code marker. Structural import/containment fan-out is excluded (no noise). `direction` forward/backward/both (downstream/upstream aliases); `live_only` drops likely-dead; depth-1 both = neighbours. Comma-separate nodes for a whole-diff radius. Since glia 0.5.4 the default answer is an overview: 25 rows, then a footer with the next page, the `areas` (each with the `scope` that selects it), the likely `files`, the ranking `selection` and any `blind` mechanism. `top_k` / `scope` / `offset` / `full` pass straight through (`full` drops `top_k` / `offset`, which the engine refuses with it).
- **`trace`** (← `flow` + `trace`) — one arg: feature end-to-end via engine `cross_stack_trace` (mechanism-labelled hops, cross-service marked), falling back to entry-point flow layering. Two args: shortest path A→B.
- **`read`** — a node's exact source sliced from its span, plus a `context:` footer from `node_cells` (method / cross-stack callers, or `dials` on a WS / gRPC / GraphQL / tRPC client / covering tests / intent-decision-constraint). Comma-separate to batch-read a ranked set.
- **`refresh`** (← `generate` + `reload`) — rebuild the graph; `repo_path` retargets (path or git URL), `full=true` forces a clean reparse. Incremental by default; routine edits are auto-picked-up by the file watcher.

Most read tools take a `budget` char cap. Liveness (`live`/`⊘`) and `file`/`line` come from the engine now — the wrapper no longer re-derives them.

Lock: the public tool surface is asserted by `tests/test_mcp_tools.py::test_six_tools_decorated` (checked against the live MCP registry, catches added *and* removed tools) and `tests/test_installer.py::test_tool_names_match_server_registry`. Adding or removing a tool must update `server.py`, `installer/constants.py` `TOOL_NAMES`, `cli.py` `POSITIONAL`, the skills, and this list in lockstep.

### Skills and the CLI

Every tool is also a shell command (`repo-graph find checkout`, or `uvx mcp-repo-graph find checkout` with nothing installed). `cli.py` calls the same registered function, so the text is byte for byte the MCP answer, and builds each subcommand's flags from the function's `Annotated[..., Field(...)]` signature (types, defaults, `ge`/`le` bounds, help), so a new parameter shows up as a flag with no CLI edit. The engine's progress log goes straight to fd 2 from Rust; the CLI points fd 2 at devnull around the call (`--verbose` keeps it). There's no watcher: `load_from_gmap` rebuilds a stale layout before answering, so each call is fresh.

**The skills live in glia** (`../glia/skills/`, since glia 0.5.4 FE.7). `skills/` here is a copy, and `claude-plugin/skills/` is a copy of that, because a marketplace install copies only the plugin dir and `../skills` doesn't load. Never edit them here: change them in glia, then `make skills` (`GLIA=<path>` if glia isn't at `../glia`; copy from the glia tag this repo pins). There are eight: six task skills (`glia-orient`, `-find`, `-debug`, `-impact`, `-trace`, `-init`) and two glia CLI references (`glia`, `glia-overlay`). Each task skill shows three routes: the MCP call (`impact nodes=<n> direction=backward`), the glia CLI command, and `uvx mcp-repo-graph impact "<n>" --direction backward`. `tests/test_skills.py` checks the two repo-graph routes of the task skills: MCP arguments against the tool signatures, every shell command through the real parser (argparse abbreviations are off, so `--dir` can't pass for `--direction`). It fails while the plugin copy differs. Rename a parameter and the skills go red here, which means glia's skills need the same change.

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

### glia 0.5.1 boundary notes

No pyo3 call the wrapper makes changed signature or shape, and no registry id was added (full detail in `dev-notes/repo-graph-handoff-0.5.1.md`, copied from `../glia/dev-notes/`). What the wrapper absorbed:

- **Exact pin** `glia-py==0.5.1`. glia pins consumers per release because each one changes the graph contents. `test_every_dependency_caps_its_major` counts `==` as capped.
- **`.gmap` format 2 → 3.** `load_from_gmap` rebuilds a 0.5.0 layout once, alone. Two writers on different glia versions (glia's own `install-hooks` CLI vs this wrapper's `githook.py`) rebuild each other's layout on every commit, so users reinstall the glia CLI from the tag alongside the wheel.
- **`ENDPOINT_HIT` has three payloads.** The HTTP call site as before, plus `{via: ws|grpc, host?}` and `{via: graphql|rpc, hosts}` on client nodes, which name the host dialled, not a caller. `_dial_text()` renders those as `dials: <host> (<via>)`.
- **Longer `coverage()` notes** (some ~1,000 chars). `_coverage_note` caps each at `_COVERAGE_NOTE_CAP`.

### glia 0.5.2 boundary notes

No pyo3 call the wrapper makes changed signature or shape; `find`, `blast_radius`, `cross_stack_trace` and `entry_flows` gained a last `collapse=True` keyword, so the positional calls bind as before. One registry id: edge category 37 `SAME_AS`, decoded by name. Full detail in `dev-notes/repo-graph-handoff-0.5.2.md`, copied from `../glia/dev-notes/`. What the wrapper absorbed:

- **Exact pin** `glia-py==0.5.2`. The published wheel's `build_stamp()` is `0.5.2+p90f604c450633cf4`; the stamp keys the parse cache, so the first build after the upgrade reparses everything.
- **The watcher holds a `WatchSession`** (handoff §3). `main()` opens one per repo on a background thread; a debounced change calls `session.poll()` (the engine's own stat scan, so a moved directory or a dropped watchdog event is still caught) and swaps in `session.snapshot()` when `seq` moved. One caller at a time, under `_rebuild_lock`. `persist()` runs at most every `PERSIST_EVERY_SEC` (60 s, as `glia watch`) and at exit, never per change. Before the session opens, or if it can't, a change falls back to `_build_graph`. A retarget drops the session; `refresh(full=true)` re-opens it. Measured 2026-10-18, six edits each, VmRSS steady state: quokka-stack (3.5k nodes) ~164 MB session vs ~138 MB rebuild loop, 0.12 vs 0.17 s per update; glia (37k nodes) ~940 vs ~500 MB, 1.93 vs 2.33 s. So the memory cost is up to ~2x on a large repo, for a modest speed-up; the gain grows with the repo.
- **The wrapper no longer trims the heap.** A dropped PyGraph runs `malloc_trim` itself (`[memory] malloc_trim site=pygraph_drop`), so `_release_freed_memory` is gone. `test_engine_trims_heap_when_a_rebuild_drops_the_old_graph` fails if an engine stops doing it.
- **Identity classes fold into one row.** A FACT / DERIVED class (a client model and the server struct it mirrors, `http_model`; two copies of one contract op) is the best-ranked member's row plus `identity.also_in` (`to_identity` on a trace hop). `_identity_note()` renders `≡ also in: <file:line>; ...  (<rules>[, diverged])` under find / impact rows and trace hops. Walks cross a class, so a Go struct's blast radius now reaches the TS code reading it.
- **`ENDPOINT_HIT` grew.** A GraphQL transport's POST is an HTTP call site that also carries `via`, so `_dial_text()` returns None for any payload with a `method`. A client glia found public and unconfigured gains `external` (`dials: host (ws, external)`). An EVM client names no host: `dials: contract via ethers, ABI X from src/abi.ts (evm)`.
- **New cells rendered in `read`:** `SCHEMA_FIELDS` as `name: type`, `?` when optional; an `ENTRYPOINT` read off a Python `__main__` guard is labelled `entry point`, not `declared entry point`.
- **Graph contents move** with no wrapper change: far fewer `⊘` (dead_symbol false positives cut, e.g. Kina 517 → 32), Go `init` / Swift `@main` / Flutter activities are entries, SHARES_DEPENDENCY is gone, longer coverage notes. PARSER_STAMP moved, so the first build after the upgrade reparses everything.
- **Our log lines are `[repo-graph] watch ...`**, since glia prints its own `[watch] open / update / noop / poll / session`.

### glia 0.5.3 → 0.5.6 boundary notes

Four glia releases in one port (mcp-repo-graph 0.5.3). Full detail in `dev-notes/repo-graph-handoff-0.5.{3,4,5,6}.md`, copied from `../glia/dev-notes/`. 0.5.3 was never applied on its own; the 0.5.4 handoff carries it forward.

- **Exact pin** `glia-py==0.5.6`. PARSER_STAMP / BUILD_STAMP moved, so the first build after the upgrade reparses everything. Mixed glia versions on one repo still rebuild each other's layout.
- **0.5.3 ranking.** `blast_radius` gained trailing `ranking=None, cochange=True, top_files=10`; `ranking=None` means the repo's calibration record picks, falling back to H10 (co-change first, then PPR). With no `.glia/history-snapshot/` rows equal 0.5.2's. The dict gains `files` and `selection`, rendered in the impact footer. The wrapper calls no `history_sync` / `history_calibrate` (minutes on a big history; never on a request path). A PyGraph reads the calibration record once, so a record written mid-session only shows on the next graph.
- **0.5.4 compact answers (the two required code changes).** `top_k=None` means 25 rows, not all; a cut row leaves `name` out when it repeats the qname tail (`_row_name()` falls back to the tail); `seed` → `seed_index`; `truncated` / `areas` added; `full=True` / `offset=` are the last keywords. And `absence.tier` is lowercase (`fact` / `heuristic`). A capped `identity.also_in` stops at 3 plus `also_in_count`, which `_identity_note()` reads.
- **0.5.4 `blind`.** `blast_radius`, `cross_stack_trace` and `entry_flows` carry `blind: [{mechanism, verdict, reason, measure}]` when a mechanism is BLIND / DEGRADED. `_blind_lines()` renders it under impact and trace.
- **0.5.4 vectors are query-time.** `node_cells` no longer returns VECTOR, so the wrapper's skip set is gone. New cell `IMPORT_BINDINGS` (27) is not shown in `read`. Registries grew (`GOAL_UNIT` 50, `TRACES` 38, `UNIT` 26), all decoded by name.
- **0.5.4 skills move to glia** (see Skills and the CLI).
- **0.5.5** is Lua only: `.lua` parses; no API change.
- **0.5.6 entries.** A TS / JS `require.main === module` / `import.meta.main` guard writes `source: main_guard` too, and there are new sources `shebang`, `script_arg`, `host:<h>` (with `host` / `trigger` keys on infra starts). `_entry_read_from()` labels all of them `entry point`: `(__main__ guard)` for `.py`, `(main guard)` otherwise, `(started by compose on container start via infra:service:api)` for a host start. Trace may say `[resolved by concept]`. Edge order out of `bfs` / `predecessors` is canonical. Routes gain mount prefixes, host / infra nodes appear. Every addition is a trailing keyword or a new method, so nothing binds differently.
- **Not adopted yet** (all optional, listed in the handoffs): `find_files` (text → files), `find_flows` / `concept_flows`, `health()` in `orient`, `vocab_sync` (`named_in` on a `no_match`), `embed`, `WatchSession(memory_budget_mb=)`, `review_vs_rev(title=)`, history sync + calibrate on `refresh`.

### glia 0.5.6 → 0.5.7 boundary notes

No code change: every pyo3 call the wrapper makes keeps its signature, and 0.5.7's additions are trailing keywords, new methods or new dict keys. No new id in the code block. Full detail in `dev-notes/repo-graph-handoff-0.5.7.md`, copied from `../glia/dev-notes/`.

- **Exact pin** `glia-py==0.5.7`. PARSER_STAMP / BUILD_STAMP moved, so the first build after the upgrade reparses everything. A calibration record is read only by the build that wrote it.
- **More entries.** Every node with an ENTRYPOINT cell (host starts, scripts, `__main__` guards, overlay `[entrypoints]`) is now a flow entry, so `entry_flows` gains keys and `nodes_json`'s `entry` reads true for them. `_entry_read_from()` already labels these.
- **MCP servers are hosts.** Python `@mcp.tool()` / `.prompt()` / `.resource()` and TypeScript `McpServer` registrations mint `host_cmd:mcp:tool:<name>` / `host_event:mcp:resource:<uri>` nodes, HANDLED_BY the function. On this repo the six tools in `server.py` are entries and their functions read live, no longer `⊘`.
- **Coverage notes moved**: new `ruby` HANDLED_BY and `solidity` EVENT_FLOWS rows, rewritten Python / TypeScript host notes. `_coverage_note` shows the first 8 rows, so a new row can push an older one past the cut.
- **Overlay origin.** An unmarked or `origin = "llm"` `[[wrapper]]` / `[constants]` / `[[route_prefix]]` stanza now tiers its pairings heuristic (rule `<rule>/overlay_llm`); people should write `origin = "human"` on stanzas they wrote by hand.
- **Graph content moves**, with no wrapper change: Rails nested resources, C# verb-constrained routes and every `using` in IMPORT_BINDINGS, Angular lazy / computed nav paths (page qnames may hold a `~<name>` segment, rendered as is), Solidity events, heritage never ending at a namespace, nearer same-stem TESTS, fewer Python ATTRIBUTEs, fewer DOCUMENTS.
- **The skills moved too**: glia's `glia` CLI reference gained `targets`, MCP hosts and `precision`. Synced from the `v0.5.7` tag.
- **Not adopted yet** (optional): `precision` beside each tier on `why` / `check` / `query` / `implementors` / `review_vs_rev` (`precision=False` gives the 0.5.6 bytes; the wrapper calls none of these yet), and the Bazel build-target answers `targets_sync` / `PyGraph.targets_*`.

### Python/Rust boundary

Python calls into `glia_py` (the pyo3 extension module shipped as PyPI package `glia-py`). That module re-exports a small surface: generate, load graph, list nodes/edges, run activation, write `.gmap`. Everything else — parsers, resolvers, store layout, text projection — stays in Rust.

Do not port Rust logic back to Python. The Python side is intentionally minimal and should stay that way.

## Publishing & Releases

Two packages ship from this repo:

- `glia-py` — pyo3 wheel built by maturin (from `py/` in the glia repo)
- `mcp-repo-graph` — pure-Python MCP server (from root)

Also registered on the MCP Registry as `io.github.James-Chahwan/repo-graph`.

### Release process (version bump)

**Release gate: `pytest` must be green before any publish step.** Every test across the twelve layers is the contract. No PyPI upload, no MCP Registry publish, no tag, no GitHub release without this. If a test is broken, fix the test or fix the code — never skip past it.

```bash
# 0. Release gate — non-negotiable
pytest                             # full suite, must be all green
pytest -m perf                     # perf gates must pass

# 1. Bump versions. mcp-repo-graph has its OWN version line: it never matches glia's
#    (glia releases far more often). Bump the patch after the last mcp-repo-graph on PyPI,
#    and move the glia pin separately.
#    - pyproject.toml:        version = "X.Y.Z"; "glia-py==<glia version>" (exact pin)
#    - server.json:           "version" (top-level + packages[].version)
#    - mcpb/manifest.json, .plugin/plugin.json, claude-plugin/.claude-plugin/plugin.json,
#      vscode-extension/package.json (+ its CHANGELOG.md): "version"
#    - uv.lock:               `uv lock`
#    The glia side (glia's own Cargo / py/pyproject versions, its tag and its glia-py
#    publish) is done in the glia repo, before this one.

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
- **0.5.1 (glia)** — ✅ ported in mcp-repo-graph 0.5.2 (see the 0.5.1 boundary notes). The handoff's §4 lists new primitives worth a mode on the six tools (`pack`, `review_vs_rev`, `hotspots`, `cochange`, `communities`, `hubs`, `duplicate_flows`, the overlay loop); none adopted yet.
- **0.5.2 (glia)** — ✅ ported (see the 0.5.2 boundary notes): the watcher holds a `WatchSession`, folded identity rows render `also in`, the new cells render in `read`. The handoff's §5 adds `query` / `query_gql` (Datalog / GQL, a candidate single `query` tool) and `identity_classes` to the unadopted list.
- **0.5.3 → 0.5.6 (glia)** — ✅ ported together, pinned `==0.5.6`, released as mcp-repo-graph 0.5.3 (see the 0.5.3 → 0.5.6 boundary notes). The unadopted list there is the next candidate work: `find_files` and `health()` look like the cheapest wins.
- **0.5.7 (glia)** — ✅ ported, pinned `==0.5.7`, released as mcp-repo-graph 0.5.4 (see the 0.5.6 → 0.5.7 boundary notes). A pin bump plus the skills sync; the MCP tools now read as live entries on this repo.
- **After 0.5.0**: the non-MCP way in (handoff §7b) is ✅ built, unreleased. `repo-graph <tool>` one-shot commands plus six skills that show the MCP call and the shell command side by side, bundled into the Claude Code plugin. Lifting the `mcp[cli]<2` cap (handoff §6): ✅ done in 0.5.1.
