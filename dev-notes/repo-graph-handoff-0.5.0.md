# repo-graph handoff - glia 0.5.0 (LG.5a, 2026-09-20)

The third glia -> repo-graph handoff, after `repo-graph-handoff-v0.4.18.md` and
`repo-graph-handoff-programme-2026-09.md`. Read it in the repo-graph session and act on repo-graph only.
Unlike the programme, **0.5.0 breaks the contract on purpose.** Every break ships in one release, and
glia, repo-graph and Engram move together.

Sources, in order of authority:
- the landed code at glia HEAD (wave W33, `5c925e6`) and the pyo3 / CLI surface snapshots. Their
  diff from the pre-leap set `f030c8f` is section 2a;
- each packet's own landed `breaking` declaration, read from the leap workflow journals;
- the specs (`dev-notes/leap-packets.json`, Batch C in `dev-notes/wave-packets.json`) and
  `dev-notes/leap-corrections.json`.

Every wrapper `file:line` below was read at repo-graph HEAD `2a13ed0` (read-only). Short names:
`server.py`, `graph.py`, `init.py`, `watcher.py` and `gitexclude.py` live in `repo_graph/`, and
`githook.py` and `constants.py` in `repo_graph/installer/`. Every other path is relative to the repo
root.

The inventory behind sections 2b, 4 and 10 is generated. Re-run it to refresh:

```
python3 dev-notes/leap-handoff/breaking_rows.py dev-notes/leap-packets.json dev-notes/wave-packets.json \
  --corrections dev-notes/leap-corrections.json \
  --consumer /home/ivy/Code/repo-graph --alias 'repo-graph wrapper' --alias "repo-graph's wrapper" \
  --alias 'repo-graph MCP' \
  --results '~/.claude/projects/-home-ivy-Code-glia/*/subagents/workflows/*/journal.jsonl' --handoff-to LG.5a
```

At this commit it prints `api=31 content=53 additive=55 unnamed_identity=5 not_landed=1
checked_no_change=17 in_scope=165`. Each row of sections 2b and 4a is one row of that output, with the
same packets and in the same order. Section 4b is its `unnamed_identity` table and section 10 its
`not_landed` table. The journals live outside the repo. Without `--results` the script falls back to
the specs alone and reports different counts.

---

## 0. TL;DR and bump order

**The wrapper does not run unchanged on 0.5.0.** It breaks in this order:
1. `import repo_graph_py` fails. The module is now `glia_py` (graph.py:12, server.py:35, init.py:16).
2. With the import fixed, `graph.py` calls `pygraph.find_node` / `find_nodes_by_qname` (:122, :125,
   :135). Both are removed, so every tool that seeds from a name (orient, find, impact, trace,
   read) raises `AttributeError`.
3. With that fixed, `_jload` (server.py:181-190) turns every dict answer into `[]` **without an
   error**. `resolve`, `blast_radius`, `cross_stack_trace` and `governing_docs` now return dicts, so
   find, impact, trace and the governed-by footer silently answer nothing.
4. The watcher loops. It rebuilds on read-only inotify events, and it does not skip the new layout
   dir `.glia/graph` (section 1, items 1-2).
5. New ask (section 7b): ship a non-MCP way in, a skill plus a CLI entry point, beside the server.

Bump order. Nothing is pushed before James says go.
1. **glia:** James walks the local commits. Bump `py/pyproject.toml` and `[workspace.package].version`
   to 0.5.0 **together**, or the publish silently does nothing (the 0.4.17 lesson). Then push and tag
   `v0.5.0`; `wheels-py.yml` publishes `glia-py`. Before the tag, James must add a **pending trusted
   publisher** on pypi.org for project `glia-py` (owner James-Chahwan, repo `glia`, workflow
   `wheels-py.yml`), or the publish job fails. `repo-graph-py` stays at 0.4.18. Whether a last
   `repo-graph-py` release should point at `glia-py` is James's open question.
2. **repo-graph:** work through sections 1-6 against a local leap wheel (section 9), pin
   `glia-py>=0.5.0` and release the wrapper after glia is on PyPI.

A leap wheel reports `version() == "0.4.18"` until the bump. Tell builds apart with `build_stamp()`
(the W33 leap wheel reports `0.4.18+pc3773758c5544fe0`).

## 1. Before you bump - correctness items, in this order

1. **Watcher rebuild loop (list first).** `watcher.py:82-89` `_Handler.on_any_event` calls
   `debouncer.trigger()` for every event. watchdog 6.0 on Linux also emits read-only events:
   `opened` and `closed_no_write` (`watchdog.events.EVENT_TYPE_OPENED` / `EVENT_TYPE_CLOSED_NO_WRITE`,
   checked on the installed 6.0.0). A rebuild opens every source file, so each rebuild schedules the
   next. Measured on James's machine: in 6 s on glia, 9161 opened, 9160 closed_no_write and 2
   modified events. The loop wrote about 1.2 TB in a day (`parse_cache.bin` rewritten every ~1.4 s)
   with nobody editing. **Fix:** trigger only when `event.event_type in {"created", "modified",
   "moved", "deleted", "closed"}`.
   glia's half landed in LC.11: a no-change rebuild no longer rewrites `parse_cache.bin`, and it logs
   `[incremental] unchanged <n> entries - parse_cache.bin not rewritten` on stderr. Verify with
   `grep '^\[incremental\] unchanged'`. The walk, cache load and resolve still run on every event
   until the wrapper filters them, so both fixes are needed.
2. **Watcher skip set (LC.9 + LF.1d).** `SKIP_DIRS` (watcher.py:23-27) skips `.ai`. The engine now
   writes `<repo>/.glia/graph/`, so the watcher reacts to its own writes. Skip the
   `glia_py.default_gmap_dir(repo)` **prefix**, not the name `.glia`. `.glia/overlay.toml`,
   `.glia/cells.jsonl`, `.glia/vectors.jsonl` and the snapshots under `.glia/` are inputs, and editing
   them must rebuild. `is_ignored` (watcher.py:32-35) matches by path-part set, so it needs a prefix
   test. Tests to move: `tests/test_watcher.py:19`, `:28-29`, `:81-84`.
3. **Package and module rename (LD.11b).** Change `pyproject.toml:26` `repo-graph-py>=0.4.18` to
   `glia-py>=0.5.0`, and `import repo_graph_py` to `import glia_py`. The module API is otherwise the
   same as section 2. Replay the mechanical part from glia's table. It never touches `repo-graph`
   alone or `mcp-repo-graph`, and it skips `dev-notes/`:
   `python3 /home/ivy/Code/glia/dev-notes/rename-0.5.0.py --python --check --root /home/ivy/Code/repo-graph`
   Today that reports **76 tokens in 15 files**: `.github/workflows/tests.yml` 1, `CLAUDE.md` 11,
   `README.md` 3, `docs/guides/install.html` 1, `guides/install.md` 1, `pyproject.toml` 1, `graph.py` 5,
   `init.py` 4, `server.py` 16, `scripts/demo/README.md` 1, `tests/conftest.py` 3,
   `tests/test_cache.py` 25, `tests/test_mcp_e2e.py` 1, `tests/test_mcp_tools.py` 1,
   `tests/test_perf.py` 2. `--apply` rewrites them. Two of those tokens are test assertions on the
   `Engine: repo-graph-py` banner (server.py:635, :767, init.py:46): `tests/test_mcp_tools.py:50` and
   the `repo-graph-py (\S+)` regex at `tests/test_mcp_e2e.py:180`. They move with the banner.
4. **The wrapper's own name is NOT renamed by glia.** `mcp-repo-graph`, the registry slug
   `io.github.James-Chahwan/repo-graph` (`server.json:3`, identifier `mcp-repo-graph` at
   `server.json:13`), `smithery.yaml` (`uvx mcp-repo-graph`), `glama.json`, `mcpb/manifest.json`
   (name `repo-graph`, its six-tool list at :39-61), `mcpb/server/main.py` and the `[project.scripts]`
   `mcp-repo-graph` / `repo-graph` / `repo-graph-init` (`pyproject.toml:46-48`) all stay as they are
   unless repo-graph decides otherwise. LD.11b left the product rename as an open question for the
   repo-graph session. The version fields (`pyproject.toml:3`, `server.json:9,14`,
   `mcpb/manifest.json:5`) move with the wrapper's own release, and `mcpb/repo-graph-0.4.19.mcpb` is
   a built artefact. Other files tied to glia: `.github/workflows/tests.yml:5` (a comment naming the
   wheel) and `docker/install_matrix.py:203-204` (asserts `.ai/repo-graph` exists, so it must become
   `.glia/graph`).
5. **Decode every id through the engine, never a table.** `graph.py:19-20` already builds
   `KIND_NAMES` / `CATEGORY_NAMES` from `kind_names()` / `category_names()`. New in 0.5.0 (L0.1):
   edge_category 35 NAVIGATES_TO and 36 CO_CHANGES; cell_type 19 DOC_TAGS, 20 ROLE, 21 EVIDENCE,
   22 SCHEMA_FIELDS, 23 COVERAGE, 24 ENTRYPOINT and 25 ACCESS_MODE. The node kinds are unchanged
   (49). CO_CHANGES is HEURISTIC history: decode it, but do not follow it in trace or impact
   rendering (LF.5b).
6. **Stop hard-coding the entry kinds.** Sites: `graph.py:22-26` (`ENTRY_KINDS = {5, 11, 13, 15, 17,
   19, 21, 37}`) and `server.py:643-644` (`_ENTRY_KINDS`). They drift from the engine: they lack
   GRPC_SERVER 47, RPC_PROCEDURE 48 and COMPONENT 28. Use `{i for i, _ in glia_py.entry_kinds()}` for
   ids, the lower-cased names for tiers, or the per-node `entry` field of `nodes_json` (LD.6). For
   dead-code marking read the records' `live` (`to_live` on trace hops). `entry` does not yet include
   entrypoints declared in `.glia/overlay.toml` `[entrypoints]` (the ENTRYPOINT cell 24); `live`
   does. The 0.4.18 handoff's advice to "extend `is_entrypoint`" is obsolete: the engine rule is
   `CODE_PROFILE.tables.entry` (`EntryRule { kinds, roles, named }`), and there is no
   `is_entrypoint` any more (LD.14b).
7. **Stop hard-coding the `read` cell ids.** `server.py:519-522` `_READ_CELL_LABELS = {5, 6, 7, 4,
   11, 10, 9, 8, 16}`. Label from `cell_type_names()` (already loaded at server.py:515) with an
   override map for friendly names. Add **13, 14, 23 and 24**:
   - 13 CONV: agent notes ("notes").
   - 14 VECTOR: `node_cells` returns `""` for its Bytes payload. Skip it, or read `node_cell_bytes`.
   - 23 COVERAGE: `{"source":"lcov","lines":N,"hit":N}`.
   - 24 ENTRYPOINT: `{"source":"config","pattern":..,"decl":..}`.

   Payloads that changed shape, where the 400-char truncation (server.py:538-539) now cuts JSON:
   - 7 TEST: an object with `tests[]` (LE.3a).
   - 8 ATTN: churn / blame JSON (LF.5b).
   - 9 FAIL: an entry array. Render `message` and `role`; `via=name` is HEURISTIC, while
     `file_line` / `qname` / `implicated` are FACT (LF.6b).
   - 10 CONSTRAINT and 11 DECISION: entry arrays. Render `title` / `text` (LF.1a, LF.4a/b).

   Optional: 19 DOC_TAGS "natspec" and 22 SCHEMA_FIELDS "fields". `tests/test_mcp_tools.py:295`
   reads `_READ_CELL_LABELS`.
8. **Tier by role, not kind (LB.3a / LB.3b).** A component, service, hook, directive, pipe, guard or
   composable with a declaration twin is now its CLASS / FUNCTION, carrying a ROLE cell.
   `nodes_json` rows gain `"roles": [..]` (always present), plus `"entry"` and `"live"`.
   `graph.py:44-56` copies a fixed key set, so add `roles`, `entry` and `live`. Then switch
   `server.py:646-648` (`_HANDLER_KINDS`), `:655-662` (`_classify_tier`) and `:665-685` (`_kind_icon`)
   to read `roles`.
9. **The wrapper's tests that pin the old engine.**
   - `tests/conftest.py:4,14,29`, `tests/test_perf.py:16,37` and `tests/test_cache.py` (25 tokens):
     the rename.
   - `tests/test_cache.py:142` (used at :148): `_PARSE_CACHE` becomes
     `Path(".glia") / "graph" / "parse_cache.bin"`.
   - `tests/test_gitexclude.py:1,38,58,62,71,78,90,113,121-122,128,133,151`: `.ai/repo-graph` paths.
   - `tests/test_watcher.py:19,28-29,81-84`: see item 2.
   - `tests/test_mcp_tools.py:38-40` (`_real_flow_key` reads `_graph.flows`): see section 3.
   - `tests/test_mcp_tools.py:321` and `tests/test_packaging.py:99-105`: see section 6.

   `tests/test_cache.py:117-131` already calls `save_to_default` before `load_from_gmap`, so LD.2's
   "generate no longer persists" does not break it.

## 2. API changes, old -> new

### 2a. The pyo3 and CLI surface (snapshot diff `f030c8f..HEAD -- py/api_surface/ cli/surface/`)

Mechanical and complete: every removed, changed or added snapshot line is in these two tables. The
snapshots pin names and signatures. Value changes (line base, record fields) are in 2b.

pyo3 (module `glia_py`; methods are `PyGraph`):

| surface | old (0.4.18) | new (0.5.0) | packet | wrapper site |
|---|---|---|---|---|
| module | `repo_graph_py` | `glia_py` | LD.11b | graph.py:12, server.py:35, init.py:16 |
| `generate` | `(repo_path, incremental=True)` | `(repo_path, incremental=False, overlay=True)`; a pure build that writes nothing | LD.2, LF.2b | server.py:118 passes `incremental`; init.py:34 relies on the old default, so pass `incremental=True` |
| `generate_many` | `(repo_paths, incremental=False)` | `+ overlay=True`; raises on no nodes plus parse errors | LF.2b, LD.2 | not called |
| `purge_parse_cache` | - | `(repo_path)` | LD.2 | optional: `refresh(full=true)` |
| `load_from_gmap` | `(dir)` | `(dir, repo_path=None, rebuild=True)`; self-heals | LC.8 | server.py:153-162, `tests/test_cache.py:123` |
| `entry_kinds` | - | `() -> [(id, name)]` | LD.6 | graph.py:26, server.py:643 |
| `blast_radius` | `(qname: str, direction, depth, top_k, live_only, scope) -> str` | `(qnames: str or list[str], ...) -> dict` | LD.5, LD.2 | server.py:367-382 |
| `cross_stack_trace` | `(feature, depth=6) -> str` | `(feature, depth=6, to=None, max_paths=10) -> dict` | LD.4a, LD.2 | server.py:451, :476-503 |
| `entry_flows` | - | `(depth=6) -> list[dict]` | LD.4b | graph.py:62-70, server.py:633, :780-791 |
| `resolve` | `-> str` | `-> dict {results, absence}` | LD.8a, LD.2 | server.py:291 |
| `resolve_signal` | `(text, kind) -> list[int]` | **removed**; use `resolve` | LD.2 | not called |
| `find_node` | `(name) -> int or None` | **removed**; use `find` | LA.14, LD.2 | graph.py:122 |
| `find_nodes_by_qname` | `(pattern, scope) -> list[int]` | **removed**; use `find` | LD.2 | graph.py:125, :135 |
| `find` | - | `(query, top_k=20, kinds=None, scope=None) -> {results, absence}` | LD.3b, LD.2 | replaces graph.py:121-136 |
| `governing_docs` | `-> str` | `-> dict {results, absence}` | LD.8a, LD.2 | server.py:548 |
| `coverage` | `-> str` | `-> list[dict]` | LD.2 | server.py:741 (`_jload` passes a list: works) |
| `project_roots`, `service_map`, `contracts` | `-> str` | `-> list` / `dict` / `list` | LD.2 | not called |
| `contract_fields` | - | `() -> list[dict]` | LE.10d | - |
| `neighbours` | `(node_id) -> [(id, cat)]` (out only) | `(node_id, direction="out", categories=None) -> [(id, cat, "out" or "in")]` | LD.3c | not called |
| `bfs`, `predecessors`, `reachable_by`, `shortest_path` | - | new traversals (section 3) | LD.3c | replace graph.py:74-117 |
| `save_to` | `(dir)` | `(dir, repo_path=None)` | LF.1b | not called |
| `overlay_applied` (getter) | - | `bool` | LF.2b | - |
| `node_cell_bytes`, `set_cell`, `remove_cell`; fns `write_cell`, `remove_cell` | - | cell read / write | LF.1b | - |
| `page_flow` | - | `() -> dict` | LA.6e, LD.2 | - |
| `check`, `cycles`, `spec_status`, `why` | - | section 3 | LE.8, LE.6b, LE.9b, LE.5 | - |
| `diff_impact`; fn `diff_impact_vs_rev`; fn `graph_delta` | - | section 3 | LE.2, LE.1c | - |
| `effects`, `implementors`, `serves` | - | section 3 | LE.4d, LD.7c, LD.8b | - |
| `feature_flows`, `write_feature_flows` | - | section 3 | LG.3c | - |
| `gaps`; fn `overlay_delta` | - | section 3 | LF.2c | - |
| `tests_for`, `tests_for_diff`; fn `tests_for_rev` | - | section 3 | LE.3b | - |
| fns `history_sync`, `tests_ingest`, `merge_gmaps` | - | section 3 | LF.5d, LF.6d, LC.10c | - |
| `patterns_experimental`; fn `patterns_vs_rev_experimental` | - | EXPERIMENTAL: do not expose | LE.7b | - |

Unchanged: `activate`, `dense_text`, `dense_text_full`, `dense_text_subset`, `prose`, `nodes_json` and
`edges_json` (still JSON strings), `node_cells`, `node_count`, `edge_count`, `cross_edge_count`,
`parse_errors`, `save_to_default`, `default_gmap_dir` and `is_stale` (their signatures are unchanged;
`default_gmap_dir`'s value moved, see 2b row 14), `parse_file_to_json`, `kind_names`,
`category_names`, `cell_type_names`, `version` and `build_stamp`.

CLI (`glia`; the wrapper runs no glia command, so no row has a wrapper site):

| surface | change | packet |
|---|---|---|
| global `--no-overlay` | new, on every command | LF.2b |
| `glia blast-radius` | positional `<QNAME>` -> `<QNAME>...` (many seeds) | LD.5 |
| `glia trace` | `--to`, `--max-paths` (default 10) | LD.4a |
| `glia contracts` | `--fields`, `--breaking-only` | LE.10d |
| `glia merge` | `--gmap DIR` (repeatable), `--workspace FILE`, `--layout DIR` | LC.10c |
| `glia install-hooks` | `--pair` | LG.2 |
| new commands | `glia cell ls/rm/set` (LF.1c), `glia check` (LE.8), `glia cycles` (LE.6b), `glia delta` (LE.1c), `glia diff-impact` (LE.2), `glia effects` (LE.4d), `glia find` (LD.3b), `glia flows` (LD.4b, LG.3c), `glia gaps` (LF.2c), `glia history sync` (LF.5d), hidden `glia hook pre-commit/commit-msg` (LG.2), `glia implementors` (LD.7c), `glia inspect` (LC.4), `glia pages` (LA.6e), `glia patterns` (LE.7b), `glia serves` (LD.8b), `glia spec-status` (LE.9b), `glia tests-for` (LE.3b), `glia tests ingest` (LF.6d), `glia why` (LE.5) | per command |

### 2b. Declared API and on-disk breaks (generated rows, api=31)

| # | packets | old -> new | wrapper site and action |
|---|---|---|---|
| 1 | A6.6 | Rust `graph::SymbolTable` gains `pub interface_methods` (struct literals break). The graph gains METHOD->METHOD IMPLEMENTS edges and CALLS into interface methods. | None in code; impact and trace show more CALLS / IMPLEMENTS rows. |
| 2 | LA.13 | Go imports under a nested go.mod become repo-local (`example.com::svc::internal::store` -> `svc::internal::store`). Go IMPORTS cells (16) drop intra-repo paths. Rust: `parse_one_with_go_modules`. | server.py:521 `imports` footer: fewer Go entries; no code. |
| 3 | LA.14 | An exact 2+ segment qname passed to `resolve` returns that node. `blast_radius(scope=)` seeds an ambiguous bare name in scope. `find_node` gained `scope=`, then LD.2 removed it. | graph.py:121-132: use `find(query, scope=..)` (row 18). |
| 4 | LA.20a | New CLI_COMMAND nodes (clap, picocli, System.CommandLine, Spectre) with HANDLED_BY to their implementation. Phantom `cli:<x>` from other languages are gone. Rust `extract_cli_command_nodes` gains `lang`. | None; read / impact on a cli_command now reach its handler. |
| 5 | LA.27 | GRAPHQL_RESOLVER from SDL-shaped text outside `.graphql` or a marked literal are removed. Rust: `extract_graphql_sdl_file_nodes`. | server.py:643 / graph.py:26: fewer phantom entry points; no code. |
| 6 | LA.38 | Decorator-minted GRAPHQL_RESOLVER outside a TS / Python file that imports a GraphQL library are removed; `graphql_resolver:Resolver` / `ResolveField` are never minted. Rust: `extract_graphql_resolver_nodes(.., lang, ..)`. | Same as row 5. |
| 7 | LB.3b | `nodes_json` rows gain `roles` (always present). A COMPONENT role counts as an entry, so `live` flips false -> true below components. | graph.py:44-56: keep `roles`; server.py:643-685 tiers and icons from `roles` (section 1, item 8). |
| 8 | LB.10a, LB.10c | C/C++ MODULE `<dir>::<stem>` -> `<dir>::<file name>` (`src::Widget` -> `src::Widget.h` + `src::Widget.cpp`); symbols follow. Out-of-line members re-parent to the header class (`src::Widget::run` -> `include::Widget::run`). Rust: `parse_file(is_cpp)` -> `(dialect)`, new `build_c_cpp`. | Rendering only. `find` still matches the type or member name. |
| 9 | LB.11b | TS ROUTE `route:<path>` -> `<METHOD> <path>`, one node per method (`ALL` -> `ANY`). ROUTE_METHOD `line` goes from 0 to 1-based. Rust `endpoint::route_path_qname` is removed. | Renders `GET /users`; nothing in the wrapper parses `route:`. |
| 10 | LC.1 | `.gmap` FORMAT_VERSION 1 -> 2 and manifest schema 1 -> 2. Every 0.4.x layout is stale and is rebuilt. | server.py:153-162: the bare except falls back to generate (works); after row 13 it self-heals. githook.py:26: committed layouts regenerate and recommit once. |
| 11 | LC.3b | Rust `CallSite` / `UnresolvedRef` / `ImportStmt` gain `line`, and EVIDENCE cells now point at the call site. | None until the wrapper calls `why` (section 3). |
| 12 | LC.7 | `manifest.json` stores repo labels, roots and parse errors. `load_from_gmap` restores them (`service_map` names repos, `parse_errors` survives a load). | server.py:153-162: a warm graph now equals a fresh one; `tests/test_cache.py:117-131` passes as is. |
| 13 | LC.8 | `load_from_gmap(dir)` -> `(dir, repo_path=None, rebuild=True)`. It rebuilds a stale / old / missing layout and writes it back unless `GLIA_NO_PERSIST=1`, printing `[gmap] rebuilt <dir> (<reason>)`. The error text "... - rebuild the graph" becomes "load_from_gmap: <dir>: needs rebuild (<reason>); ...". | server.py:153-162 -> `glia_py.load_from_gmap(glia_py.default_gmap_dir(REPO_PATH), REPO_PATH)`. Drop the `hasattr` guards, the `is_stale` pre-check and the bare except; keep a `ValueError` fallback to `_build_graph`. `tests/test_cache.py:123-125` (one argument) stays valid. |
| 14 | LC.9 | Default layout dir `<repo>/.ai/repo-graph` -> `<repo>/.glia/graph` (`default_gmap_dir`, `parse_cache.bin`, `glia build`). The dir ignores itself (`.gitignore` = `*`). `.ai/repo-graph` is never read or written again. | watcher.py:23-35 (section 1, item 2); githook.py:26 -> `git add -f .glia/graph`; init.py:36, :43 -> `default_gmap_dir()` or drop (the dir ignores itself); server.py:100-104 (the `.ai` fallback literal), :111-112 (docstring); gitexclude.py:1; constants.py:76 (user text); tests in section 1, item 9; `docker/install_matrix.py:203-204`. |
| 15 | LC.10b | Engine merge of pre-built layouts (`merge::merge_layouts`, `glia.workspace.json`). Store `Manifest` / `ShardEntry` gain fields. | None; enables row 16. |
| 16 | LC.10c | New `glia_py.merge_gmaps(dirs, out=None) -> PyGraph` and `glia merge --gmap/--workspace/--layout`. | Optional multi-repo MCP mode over layouts (server.py `_build_graph`). |
| 17 | LD.1 | Every answer record's `line` goes from 0-based to 1-based: blast_radius, resolve, governing_docs, find, trace `to_line`, contracts. `nodes_json` start / end lines were already 1-based. | server.py:705-712 `_eloc`: section 5. server.py:463 needs no change. `_node_record` (:723-733) now agrees with engine rows. |
| 18 | LD.2 | Answers return native dicts and lists, not JSON strings. `resolve_signal`, `find_node` and `find_nodes_by_qname` are removed and `find` is new. `generate` defaults to `incremental=False` and writes no layout. pyo3 ignores `GLIA_NO_PERSIST`. | server.py:181-190 `_jload` must pass dicts and lists through; call sites :291, :371, :451, :548, :741. graph.py:121-136 -> `pygraph.find(q, top_k)["results"]`. init.py:34 -> `incremental=True`. server.py:119-125 `save_to_default` is now the only layout writer: keep it. |
| 19 | LD.3a | Rust `RepoGraph::neighbours(id)` -> `neighbours(id, reach)` returning 3-tuples; `MergedGraph` gains bfs / predecessors / reachable_by / shortest_path. | None (pyo3 only, row 20). |
| 20 | LD.3c | pyo3 `neighbours(node_id)` -> `(node_id, direction, categories)` returning 3-tuples; new `bfs` / `predecessors` / `reachable_by` / `shortest_path`. | Delete graph.py:36-37, :57-60 (adjacency), :74-97 (`downstream` / `upstream` / `_traverse`) and :99-117 (`shortest_path`); call the engine (`categories=None` keeps the all-edge walk). |
| 21 | LD.4a | `cross_stack_trace` returns `{seed, target, resolved_by, hops, paths, truncated, absence}`, adds a `to=` two-node mode and `max_paths`. An unknown feature is an absence, not a ValueError. Hops gain `cross_repo`; `cross_service` also counts manifest-project boundaries. | server.py:446-465: read `["hops"]` or render the ranked `["paths"]`, and drop the except at :452. server.py:443-444, :476-503 `_trace_path` and graph.py:99-117 -> `cross_stack_trace(frm, to=to_node)`. |
| 22 | LD.5 | `blast_radius(qname)` -> `blast_radius(qnames)` returning `{seeds, unresolved, results, absence}`. Rows gain `seed`; an unknown qname is an absence. | server.py:354-395: one call with the raw names (the engine resolves them; misses come back in `unresolved`). Render `seeds[].linked_seeds`; the module-seed hint (:387-394) becomes the absence note. |
| 23 | LD.6 | Liveness seeds from `CODE_TABLES.entry` (adds 47, 48, 13, 15, 37). New `entry_kinds()`. Rows gain `live` (resolve, governing_docs, find) and `to_live` (trace hops); `nodes_json` gains `entry` and `live`. | graph.py:22-26 and server.py:643-644 (section 1, item 6); server.py:715-720 `_elive` now also fires on find and resolve rows; read `to_live` for trace hops. |
| 24 | LD.8a | resolve, governing_docs and find return the `{results, absence}` envelope. `absence` = `{tier, reason, query, note, mechanisms, caveats, suggestions, nodes_searched, unparsed_files}`; reasons include `unknown_symbol`, `no_edges`, `no_match` and `no_signal_match`. | server.py:291 read `["results"]`, and render `["absence"]` in place of the string at :307-309; server.py:548 read `["results"]`. |
| 25 | LD.8b | Rust `RouteMatch` gains `tier`. New `serves(channel, mechanism="auto")` and `glia serves`. | None; P4 candidate (section 7). |
| 26 | LD.11b | PyPI `repo-graph-py` -> `glia-py`; import `repo_graph_py` -> `glia_py`. | Section 1, item 3 (76 tokens in 15 files). |
| 27 | LE.4d | Rust `DomainTables.effect_sinks` `&[EdgeCategoryId]` -> `&[EffectSink]`. New `effects(...)` and `glia effects`. | None; P4 candidate. |
| 28 | LF.3a | The `[walk] collapsed ...` stderr line gains ` config=N`. New ORIGIN provenance `excluded`, PROJECT ecosystem `declared`. Rust `Collapse` / `Gate` / `gate_dir` change. | None: the wrapper parses no stderr and does not call `project_roots`. |
| 29 | LC.3a | Every edge carries one EVIDENCE cell (21); `.gmap` bytes grow about x1.18. | `edges_json` is unchanged (graph.py:57); `node_cells` never returns edge cells. Visible through `why` only. |
| 30 | LC.4 | `.gmap` headers carry the id registries; new `glia inspect`. | Optional: names could come from a file header rather than `cell_type_names()` (server.py:515). |
| 31 | LF.1d | The walk skips everything under `.glia/`. The manifest records an `external_inputs` fingerprint, and `is_stale` turns true when a `.glia` input changes. | gitexclude.py / init.py:43 / server.py:105: exclude only `.glia/graph`, never `.glia/` (overlay.toml and cells.jsonl are committed inputs). Warm path: expect a regenerate after `glia docs sync` / `history sync` / `tests ingest` or an overlay or cell edit. |

## 3. New primitives: call them instead of wrapper Python

| primitive (pyo3) | replaces or enables | packet |
|---|---|---|
| `find(query, top_k=20, kinds=None, scope=None)` -> `{results[{id,qname,name,kind,live,file,line,match}], absence}`, ranked by match tier | graph.py:121-136 `find_node` / `find_nodes` and the substring loop | LD.3b, LD.2 |
| `bfs(node_id, direction="out", categories=None, depth=3)` -> `[(id, depth, via, parent)]`, `predecessors(...)`, `reachable_by(sink_id, source_ids, ...)`, `shortest_path(from_id, to_id, direction="both", categories=None, depth=12)`, `neighbours(node_id, direction, categories)` | graph.py:36-37, :57-60 adjacency, :74-117 `_traverse` / `downstream` / `upstream` / `shortest_path` | LD.3c |
| `cross_stack_trace(feature, depth=6, to=None, max_paths=10)`: ranked distinct paths, `resolved_by` in `qname / name / find / entry_flow / none` | server.py:446-503 trace and `_trace_path` | LD.4a |
| `entry_flows(depth=6)` -> `[{key, entry, reach, cross_service, mechanisms, services, hops}]` | graph.py:38-40, :62-70 `_build_flows` / `flows`, :142-152 `nodes_for_feature`; server.py:633, :780-791; `tests/test_mcp_tools.py:38-40` | LD.4b |
| `feature_flows(group_by="feature", depth=6, feature=None, scope=None)` -> `[{feature, services, entries, data_sources}]`; `write_feature_flows(out_dir=None, group_by="feature", depth=6)` -> `{written, unchanged, removed, dir}` | the feature grouping the wrapper approximates with flow keys (graph.py:142-152, server.py:467-473) | LG.3a, LG.3c |
| `blast_radius(qnames)`: one walk and one PPR for many seeds | server.py:354-382 per-seed union loop | LD.5 |
| `diff_impact(diff_text, ...)`, `diff_impact_vs_rev(repo_path, base="HEAD", ...)`, `graph_delta(repo_path, base="HEAD")` | the diff branch of `find` (server.py:286-299) plus impact | LE.2, LE.1c |
| `tests_for(qnames, ...)`, `tests_for_diff(diff_text, ...)`, `tests_for_rev(repo_path, ...)` | "which tests cover this change" | LE.3b |
| `implementors(qname, direction="down", transitive=True)` -> `{results, absence}` | interface -> implementation views | LD.7c |
| `serves(channel, mechanism="auto")` -> `{results, absence}` | "what serves X" with no keyword guessing | LD.8b |
| `effects(qnames, depth=8, classes=None, writes_only=False, cross_service=False, scope=None)` -> `{seeds, effects, counts, writes, unresolved, ...}` | side-effect sinks (db / queue / http / email ...) below a symbol | LE.4d |
| `why(from_qname, to_qname, category=None)` -> `{found, edges, path, from_nodes, to_nodes, note, ...}` | edge evidence: the emitter, the rule and the call-site line behind an edge | LE.5 (reads LC.3) |
| `cycles(kind="all", scope=None)`, `check()` -> `{rules, checked, unchecked, errors, violations}`, `spec_status(feature=None)`, `contract_fields()` | architecture and SDD notes | LE.6b, LE.8, LE.9b, LE.10d |
| `page_flow()`, `service_map()`, `project_roots()` | frontend page flow, service map, scope vocabulary | LA.6e, A9.2, A8.6 |
| `gaps(top_k=None, category=None)`, `overlay_delta(repo_paths, incremental=False)` | the overlay agent loop: gaps -> prompt -> write `.glia/overlay.toml` -> `overlay_delta` -> keep only if orphans fall. repo-graph owns this loop; the schema is glia's `docs/overlay.md` (`[[wrapper]]` gained `kind = "data_entity"`, LG.3d). `gaps(category="cochange_no_edge")` rows are HEURISTIC. | LF.2c, LF.2e, LF.5c |
| `generate(..., overlay=False)`, the `overlay_applied` getter, `--no-overlay` | extraction-only facts; `save_to_default` refuses such a graph, so use `save_to(dir)` | LF.2b |
| `set_cell(qname, cell_type, payload, ...)`, `remove_cell`, `write_cell(repo_path, ...)`, `node_cell_bytes` | agent notes / decisions / constraints (writable cells: CONSTRAINT 10, DECISION 11, CONV 13, VECTOR 14) | LF.1b |
| `history_sync(repo_path, max_commits=2000, since=None, blame=False, blame_max_files=300)` | git churn / blame (cell 8) and CO_CHANGES; call it when HEAD moves, before `generate` | LF.5d |
| `tests_ingest(repo_path, junit=None, logs=None, lcov=None, run=None)` | CI results into FAIL (9) / COVERAGE (23) cells. It prints `[tests] ingest ... surface=pyo3` and `warning: skipped <report>: <reason>`; the build never ingests on its own. | LF.6d |
| `merge_gmaps(dirs, out=None)` | multi-repo over pre-built layouts | LC.10c |
| `purge_parse_cache(repo_path)` | a cold `incremental=True` build | LD.2 |
| env `GLIA_THREADS` | parse pool size: the default is every core and `1` is the old single-threaded path. The server's `generate` and every watcher rebuild use it. | LG.1a |

Do not expose `patterns_experimental` / `patterns_vs_rev_experimental` until James promotes the engine;
promotion renames both (LE.7a, LE.7b).

## 4. Graph content changes: what the wrapper's renderers show differently

No wrapper code change is needed unless the row says so. These change golden outputs, counts and
qnames in find, impact, trace, read and orient.

### 4a. Rows that name the wrapper (generated rows, content=53)

| # | packets | old -> new | where it shows |
|---|---|---|---|
| 1 | A13.4 | `cli_invoke:terraform apply` -> `cli_invoke:terraform`, `cli_invoke:/usr/bin/kubectl` -> `cli_invoke:kubectl`; a new Json CODE cell `{bin, argv}` | cli_invocation rows; re-key anything cached by those qnames (the wrapper caches none) |
| 2 | LA.4 | Const-resolved topics: `queue_producer:unresolved:<fw>` -> `queue_producer:<topic>`; the QUEUE_FLOWS coverage caveat text is rewritten | queue rows; server.py:736-754 `_coverage_note` |
| 3 | LA.6b | Nested nav routes `page:/users` -> `page:/admin/users`; nav ROUTEs from non-router objects removed; HANDLED_BY nav ROUTE -> component | impact on a component reaches its routes |
| 4 | LA.18a | New WS_HANDLER / WS_CLIENT for Python, Java and C#; client qnames read the path (`ws_client:ws://` -> `ws_client:/ws/chat`); gorilla `ws:ws` anchors at `.Upgrade(` with HANDLED_BY | ws rows (server.py:673 has the icons) |
| 5 | LB.2 | Java `<dir>::<Stem>::<Type>[::m]` -> `<dir>::<Type>[::m]` (`server::UserController::UserController::getUser` -> `server::UserController::getUser`); Kotlin the same | find / impact / read |
| 6 | LB.4a | Nested-project repos: ROUTE / ENDPOINT / page qnames gain ` @<root>` (`GET /health` -> `GET /health @services/users`); display names unchanged | find / impact / trace; substring search still matches |
| 7 | LB.4c | Client-router routes `GET /users` -> `page:/users` (name `/users`) | trace / impact |
| 8 | LB.7a, LB.7b, LB.7c, LB.7d, LB.9b, LB.10b, LB.13, LB.14 | Type qnames lose the file stem: `<dir>::<Stem>::<Type>` -> `<dir>::<Type>` (Scala, PHP, Swift; C# -> `<Ns>::<Type>`). Same-stem siblings `<dir>::<stem>` -> `<dir>::<file name>` (LB.9b, LB.13). C/C++ header types `src::Widget.h::Widget` -> `src::Widget` (LB.10b). C# `file` types -> `<file module>::<Type>` (LB.14) | find / impact / read; substring on the type or member name still matches |
| 9 | LB.8 | Nested-project repos: queue / ws / graphql / grpc client and server qnames gain ` @<root>` | find / impact / trace (the kind tables at server.py:643-652 key by kind) |
| 10 | LB.8b | The same for `rpc:`, `rpc_call:`, `event_emit:` and `event_handle:`; EVENT_FLOWS between different owners dropped | find / impact / trace |
| 11 | LB.9a | Non-code MODULE `<dir>::<stem>` -> `<dir>::<file name>` (`api::user` -> `api::user.proto`, `Cargo` -> `Cargo.toml`) | find by file name |
| 12 | LB.11a | Go `route:/users` -> `GET /users` + `POST /users` (`http.HandleFunc` -> `ANY /health`); display name = qname | route rows |
| 13 | LB.12 | Contract ops `contract::<stem>::<op>` -> `contract::<dirs>::<stem>::<op>` | server.py:544-554 governed-by footer |
| 14 | LE.9a | Spec-kit contract ops `contract::<stem>::...` -> `contract::feature:<NNN-slug>:<stem>::...`; new `feature.yaml` ops | governed-by footer |
| 15 | LG.3b | Junk DATA_ENTITY nodes removed (quokka 41 -> 2, lapse 95 -> 41, webplatform 128 -> 43, neuropil 180 -> 114); new `data_entity:nosql:<name>` from Go / Java / C# collection calls | data_entity rows (server.py:652) |
| 16 | LA.22b | Feign / HttpExchange / RestClient / Retrofit interfaces: ROUTE -> client ENDPOINT (`GET /feign/users/{id}` -> `endpoint:GET:/feign/users/{id}`) | orient moves them from ENTRY to DATA |
| 17 | LB.1 | RepoId = hash of the repo identity (git remote / gitdir / dir name), not the path: every NodeId changes once, and so do shard names | in-memory ids only (graph.py:43); committed layouts (githook.py:26) see renamed shards once |
| 18 | LB.3a | Role twins (SERVICE / COMPONENT / HOOK / ...) fold into their declaration: kind CLASS / FUNCTION plus a ROLE cell (20); duplicate overlay edges removed; lookups prefer declarations | server.py:646-648, :679-680 role kinds arrive as class / function (section 1, item 8) |
| 19 | A14.2 | `.kt` has its own parser, no longer the Java grammar; Kotlin coverage caveats go 5 -> 6 | orient blind-spot footer |
| 20 | LA.1b | Rust IMPORTS retarget to MODULE / PACKAGE; the Rust IMPORTS cell lists external crates; new Rust CALLS caveat | read `imports` footer (server.py:521); coverage footer |
| 21 | LA.13b | Wrong Go IMPORTS via the repo-wide tail fallback removed; CALLS across a package's files | more Go callers |
| 22 | LA.18b | Generic WS_CONNECTS pairs removed; param / upgrade pairs added; new WS_CONNECTS coverage row | coverage footer |
| 23 | LA.23d | Go methods declared outside their struct's file move under the struct | orient seeded map, read |
| 24 | LA.26 | Phantom GRAPHQL_OPERATION nodes removed; a gql-tag `graphql-request` op anchors at its call line, not its import | graphql_operation rows |
| 25 | LA.28 | `data_entity:graph:<name>` from non-Cypher text removed (glia 209 -> 3, repo-graph 1 -> 0) | data_entity rows |
| 26 | LA.29 | Phantom `event_emit:publish` / `event_handle:subscribe` (non-bus receivers, AWS SDK `.send(new XCommand)`) removed | orient entry list, flows (graph.py:26 holds 19) |
| 27 | LA.37b | Dart CALLS re-credited to their owner; no CALLS starts at an ENDPOINT | impact / trace |
| 28 | LA.39 | EVENT_* from non-bus `.on(` / `.emit(` / DOM listeners removed (quokka 9 -> 2) | fewer entry points |
| 29 | LA.41 | Malformed event names removed | fewer garbage rows |
| 30 | LA.42 | Malformed DATA_ENTITY names removed | fewer garbage rows |
| 31 | LB.4b | HTTP_CALLS narrowed by project host; duplicate HTTP_CALLS emitted once (quokka 49 -> 47) | fewer cross-service hops |
| 32 | LE.4a | ACCESSES_DATA re-homes MODULE -> FUNCTION / METHOD; ACCESS_MODE edge cell (25) | impact / trace reach tables from functions |
| 33 | LE.4b | READS_CONFIG re-homes MODULE -> FUNCTION / METHOD | config keys hang off the reading function |
| 34 | A6.8 | TS IMPORTS cell (16) drops tsconfig `paths` aliases (`@core/auth.service`); aliased IMPORTS edges added | read `imports` footer |
| 35 | A7.8 | Parents of live methods and implementers of live interfaces flip `live` false -> true | fewer ⊘ (server.py:412-417) |
| 36 | LA.7a | Elixir DOC cells from `@doc` / `@moduledoc` | none (DOC 2 is not in `_READ_CELL_LABELS`) |
| 37 | LA.37a | A top-level Dart function's CODE / POSITION span covers its body | read (server.py:557-591) slices the whole function |
| 38 | LC.3c | EVIDENCE on cross edges gains `rule` (`exact`, `endpoint_prefix`, `any`, ...) | through `why` only |
| 39 | LC.3d | EVIDENCE emitter `graph:build` -> `graph:calls / refs / imports / iface / rust_paths / go_packages / nav`, plus a rule | through `why` only |
| 40 | LF.4b | ADR sections become DOC_SECTION + DOCUMENTS; DECISION (11) is a JSON entry array `{adr, id, section, source, status, title}` | read `decision` footer (server.py:521): render title / status |
| 41 | LG.10a | DOC_SECTION POSITION ends at the section's last non-blank line | read of a doc node (server.py:557, `_loc` :692): a shorter span |
| 42 | LA.5 | `service_map` / `glia arch` stop listing platform shells (android / ios) as services | none today (no `service_map` call) |
| 43 | LA.6a | NAVIGATES_TO (35) edges exist and carry blast and trace | server.py:429-430 `_MECH_ICON`: add an arrow (optional); graph.py:20 decodes it |
| 44 | LA.17 | RPC_PROCEDURE / RPC_CALL (48 / 49) for Connect and Twirp; RPC_CALLS in arch; a new coverage row | graph.py:26 lacks 48 (fixed by `entry_kinds()`); server.py:643-685: add `rpc_procedure` (ENTRY) and `rpc_call` (DATA) tiers and icons |
| 45 | LA.33 | QUEUE_CONSUMER HANDLED_BY its callback; a new HANDLED_BY coverage row | queue flows gain handler steps |
| 46 | LA.35b | More Rust CALLS; the Rust CALLS caveat text changes | coverage footer |
| 47 | LD.4b | A one-node trace falls back to the entry flow whose key matches (`resolved_by: entry_flow`); `entry_flows()` | graph.py:38-40, :62-70, :142-152; server.py:467-473, :633, :780-791 -> `entry_flows()`; server.py:805-833 `_render_nodes_layered` becomes unused; `tests/test_mcp_tools.py:38-40` |
| 48 | LG.1a | Parsing runs on a `GLIA_THREADS` pool (default every core, `1` = the old path); per-file stderr markers come out unordered; a new `[parallel]` line | the server's `generate` (server.py:118) and watcher rebuilds use every core; set `GLIA_THREADS` in the server env to cap it |
| 49 | LG.3d | Overlay `[[wrapper]] kind = "data_entity"`; the `[overlay] wrappers` tally gains `data_entity=` | the overlay agent loop (section 3) may propose data_entity wrappers |
| 50 | LA.3 | Rust inline `mod x {}` -> PACKAGE; enum variants -> ATTRIBUTE (glia self-graph 8,580 -> 11,387 nodes) | orient kind counts |
| 51 | LA.30b | Java enum constants -> ATTRIBUTE; enum-body members appear | orient kind counts |
| 52 | LA.31 | tRPC RPC_PROCEDURE / RPC_CALL gain POSITION and owner edges | read / impact rows carry path:line |
| 53 | LA.32a | Go ROUTEs gain one POSITION per registration; more Go route forms | route rows carry path:line |

### 4b. Identity changes that do not name the wrapper (generated rows, unnamed_identity=5)

The wrapper still renders these qnames:

| packets | old -> new |
|---|---|
| A13.2 | Java DATA_ENTITY `User` -> `data_entity:sql:User` (`@Entity`) or `data_entity:nosql:User` (`@Document`) |
| A14.5 | Nested Ktor routes compose: `route("/admin") { delete("/users/{id}") }` `DELETE /users/{id}` -> `DELETE /admin/users/{id}` |
| LA.18c | Phoenix `ws:default` / `ws:ws` -> `ws:<socket mount>` / `ws:<topic pattern>`; Rails `ws:default` -> `ws:<ChannelClass>` |
| LA.22c | Phantom reitit ROUTEs from non-route Clojure text removed |
| LB.5 | Route and endpoint paths get a leading slash: `GET widgets` -> `GET /widgets`, `route:items` -> `route:/items`, `endpoint:<M>:api/users` -> `endpoint:<M>:/api/users` |

Also from corrections: GRAPHQL_OPERATION phantoms are gone (row 24). No DATA_ENTITY change needs code in
repo-graph (row 15).

## 5. The `_eloc` fix

Since LD.1, every answer record's `line` is 1-based, and so is `nodes_json` `start_line`. The old
wrapper printed 0-based lines (one too low) and dropped line 0 through `if line`. After the bump the
numbers are right with no change, and the explicit test is the correct one:

```python
def _eloc(rec: dict) -> str:                     # server.py:705-712
    f = rec.get("file")
    if not f:
        return ""
    line = rec.get("line")
    return f"  {f}:{line}" if line is not None else f"  {f}"
```

The trace hop call `_eloc({"file": h.get("to_file"), "line": h.get("to_line")})` (server.py:463) needs
nothing: `to_line` is 1-based too. `_loc` (server.py:692-702) reads `nodes_json` spans, which were
already 1-based.

## 6. MCP SDK 2.x port (the port itself is repo-graph's work)

The pin is `pyproject.toml:25` `"mcp[cli]>=1.0.0,<2",  # 2.x renamed FastMCP → MCPServer; port before
lifting`. `tests/test_packaging.py:99-105` `test_mcp_sdk_capped_below_2` enforces the cap and must be
inverted or removed when the cap is lifted. The user site runs mcp 1.27.0.

Checked against the mcp **2.2.0** wheel in the uv cache (`~/.cache/uv/archive-v0/PbgwBkwAhIz4G4gio5ZYL`):
- `mcp/server/fastmcp.py` is a stub that raises `ModuleNotFoundError`: "This is mcp 2.x, where FastMCP
  was renamed to MCPServer (from mcp.server.mcpserver import MCPServer) and other APIs changed; see
  the migration guide at https://py.sdk.modelcontextprotocol.io/v2/migration/#fastmcp-renamed-to-mcpserver".
- `MCPServer(name, title, description, instructions, ...)` still takes `instructions`.
  `MCPServer.tool(name, title, description, annotations, icons, meta, structured_output)` still takes
  `annotations`. `run(transport="stdio")` is still the default.
- `mcp.types` mirrors the new `mcp_types` package, which still exports `ToolAnnotations`.
- `mcp.ClientSession`, `mcp.StdioServerParameters`, `mcp.client.stdio.stdio_client`,
  `MCPServer.list_tools()` and `_tool_manager._tools` all still exist.
- Not checked here: the rest of the migration guide ("other APIs changed"), or whether pydantic
  `Annotated[..., Field(...)]` tool parameters and `str` returns behave the same under 2.x
  structured output. Read the guide before lifting the cap.

Sites:

| file:line | now | 2.x |
|---|---|---|
| server.py:32 | `from mcp.server.fastmcp import FastMCP` | `from mcp.server.mcpserver import MCPServer` |
| server.py:33 | `from mcp.types import ToolAnnotations` | unchanged (still exported) |
| server.py:42 | `mcp = FastMCP("repo-graph", instructions=...)` | `MCPServer("repo-graph", instructions=...)` |
| server.py:208, :269, :341, :433, :594, :615 | `@mcp.tool(annotations=ToolAnnotations(...))` | same decorator signature |
| server.py:868 | `mcp.run()` | same (stdio default) |
| `tests/test_mcp_tools.py:321` | `server.mcp._tool_manager._tools` | still exists in 2.2.0 (private: may drift) |
| `tests/test_installer.py:52`, `tests/test_packaging.py:89` | `await srv.mcp.list_tools()` | exists |
| `tests/test_mcp_e2e.py:30-31` | `from mcp import ClientSession, StdioServerParameters`; `mcp.client.stdio.stdio_client` | exported |
| `pyproject.toml:25`, `tests/test_packaging.py:99-105` | the `<2` cap and its guard | lift together |

## 7. P4 tool collapse (a proposal only; repo-graph decides)

The six tools stay six. Each becomes a thin call into one engine primitive, and most of `graph.py`
disappears.

| tool | engine primitive after 0.5.0 | wrapper code that goes |
|---|---|---|
| `orient` | counts from `node_count` / `edge_count`; entry points from `entry_flows()`; blind spots from `coverage()` (plus optional `gaps()` / `cycles()` notes); seeded map from `activate` + `dense_text_subset` (unchanged) | graph.py:38-40, :62-70 flows; server.py:780-791 |
| `find` | `find(query, top_k, kinds, scope)` for a symbol, `resolve(text, kind, top_k)` for a signal; both return `{results, absence}`, so render the absence instead of "No nodes matched"; `expand` keeps `activate` | graph.py:121-136; server.py:301-314 keyword path |
| `impact` | `blast_radius(names, ...)` once, `diff_impact(diff_text)` for a diff, optional `tests_for` / `effects` sections | server.py:354-395 seed loop, union and module hint |
| `trace` | `cross_stack_trace(feature, depth, to=..., max_paths)` with ranked paths; `feature_flows(feature=...)` for a feature overview; `why(a, b)` as an edge-evidence footer | graph.py:74-117, :142-152; server.py:467-503, :805-833 |
| `read` | `nodes_json` spans + `node_cells` (labels from `cell_type_names()`) + `governing_docs(...)["results"]` | the hard-coded `_READ_CELL_LABELS` ids |
| `refresh` | `generate(repo, incremental=not full)` + `save_to_default`; counts from `entry_flows()` | `len(g.flows)` (server.py:633) |

Candidates for new modes rather than new tools, to keep the fixed per-turn schema tax small: `serves`,
`implementors`, `graph_delta` / `diff_impact_vs_rev`, `check` / `spec_status`, `page_flow`,
`service_map`, the overlay loop (`gaps` -> write `.glia/overlay.toml` -> `overlay_delta`) and the cell
writers for agent notes. Changing the tool set means updating `constants.py:30` `TOOL_NAMES`,
`tests/test_mcp_tools.py:314-322`, `mcpb/manifest.json:39-61` and the CLAUDE.md tool list together.

## 7b. A non-MCP way in: a skill and the CLI (James, 2026-09-20)

James asked for a way to use the graph **without** the resident MCP server. Two reasons, both measured:
the server holds **~1.0 GB** RSS (all anonymous memory, peak 1.41 GB) while one glia build of the glia
repo peaks at **90 MB** (release binary, 2.5 s), and while it runs, the watcher loop (section 1, item 1)
rebuilds about every 1.4 s. A per-call surface has neither cost.

What already exists on the glia side: every answer is a `glia` subcommand with `--json`, and the layout
at `<repo>/.glia/graph` is reused across calls (`load_from_gmap` / `is_stale`), so a call after the first
is a load, not a build. The surfaces are pinned in `cli/surface/*.txt`: `arch`, `find`, `resolve`,
`blast-radius`, `impact`, `trace`, `flows`, `why`, `serves`, `implementors`, `effects`, `tests-for`,
`diff-impact`, `delta`, `cycles`, `check`, `spec-status`, `pages`, `contracts`, `coverage`, `gaps`,
`docs-for`, `patterns --experimental`.

What repo-graph should ship beside the MCP server (repo-graph decides the shape):
1. **A Claude Code skill** (`SKILL.md`) that maps the six MCP tools to CLI calls, so an agent with no MCP
   server runs `glia <cmd> <repo> ... --json`: orient -> `glia arch` + `glia coverage` + `glia flows`;
   find -> `glia find` / `glia resolve`; impact -> `glia blast-radius` (`glia diff-impact` for a diff);
   trace -> `glia trace` / `glia flows --features`; read -> the `file:line` every answer row carries.
   Keep the skill's command list checked against `cli/surface/*.txt`, not hand-maintained (glia's
   own skill, LG.15, does exactly that - reuse it or point at it).
2. **A `repo-graph` CLI entry point** that runs the same tool functions as the server, without the
   MCP SDK, for users who do not run an MCP client. It shares `server.py`'s renderers, so output
   matches the MCP tools byte for byte.
3. Say in the README which to pick: MCP for an always-on agent session, the skill / CLI for occasional
   queries, CI and low-memory machines.

**Memory, to verify after the watcher fix:** the ~1.0 GB is most likely (a) allocator high-water from
rebuilding every ~1.4 s for 30+ hours (freed graphs are not returned to the OS) plus (b) the wrapper's
Python copy of the graph (dicts per node and edge from `nodes_json` / `edges_json`, plus the flows
index). Check: reconnect the server and record RSS at start and after an hour of normal use. If it
starts near 200-300 MB and climbs, it is (a); the watcher fix removes it. The P4 collapse (section 7)
removes most of (b), because the primitives return only the rows asked for.

## 8. Gotchas carried over

- **Stale `.so`.** maturin can repackage an old build. After installing a wheel, check
  `glia_py.build_stamp()`: it changes whenever any graph-shaping source changes, even though
  `version()` reads 0.4.18 until the bump. To rebuild, run `cargo clean -p glia-engine -p glia-py`
  (the cargo package names moved in LD.11a).
- **Two modules in one env.** `glia_py` and the old `repo_graph_py` can be installed side by side.
  After the bump the wrapper must import only `glia_py`: an old import would silently serve the
  0.4.18 engine.
- **`install-hooks` now writes where git reads (LG.2).** In a linked worktree, glia used to write
  `<main>/.git/worktrees/<wt>/hooks`, which git never runs. It now writes
  `git rev-parse --git-path hooks` and honours `core.hooksPath`. The wrapper's own `githook.py:35-47`
  `_hooks_dir` has the same flaw: it follows `.git`'s `gitdir:` line to the per-worktree dir and
  ignores `core.hooksPath`. The same fix applies.
- **The legacy dir.** glia never reads `.ai/repo-graph`. It prints `[gmap] legacy layout ignored: ..`
  and deletes only orphan shards; the old dir stays until someone removes it. Passing `.ai/repo-graph`
  itself to `load_from_gmap` rebuilds it in place as a 0.5.0 layout (LG.6c). Always use
  `default_gmap_dir()`.
- **Nothing writes by default (LD.2).** `generate` is a pure build. `incremental=True` writes only
  `.glia/graph/parse_cache.bin`. `save_to_default` is the one layout writer. A `load_from_gmap`
  rebuild writes into its dir unless `GLIA_NO_PERSIST=1`.
- **The first build after the bump reparses everything.** PARSER_STAMP moved and the format went to
  2, so every cache and layout rebuilds once.
- **stderr order (LG.1c).** At the default thread count, per-language diagnostic lines are unordered
  across languages. `GLIA_THREADS=1` restores the sequential order; the set of marker lines is the
  same either way.
- **The committed-layout flow.** `.glia/graph/` carries its own `.gitignore` (`*`), so `git status` never
  shows it, while `git add -f .glia/graph` (githook.py:26) still stages it. The `info/exclude` step
  (gitexclude.py) is redundant for the default dir.

## 9. Re-test commands

```
# a local leap wheel (before PyPI), in a throwaway venv
python3 -m venv /tmp/rg-050 && /tmp/rg-050/bin/pip install /home/ivy/Code/glia/target/wheels/glia_py-*.whl
/tmp/rg-050/bin/python -c "import glia_py as g; print(g.version(), g.build_stamp(), len(g.entry_kinds()))"

# the rename, until it reports 0 tokens
python3 /home/ivy/Code/glia/dev-notes/rename-0.5.0.py --python --check --root /home/ivy/Code/repo-graph

# the wrapper's suites
cd /home/ivy/Code/repo-graph && /tmp/rg-050/bin/pip install -e ".[dev]" && /tmp/rg-050/bin/pytest -m "not perf"
/tmp/rg-050/bin/pytest -m e2e

# watcher: one edit must give one rebuild, not a loop (a loop shows dozens). The pipe holds stdin
# open so the stdio server stays up; the watcher starts before mcp.run()
( sleep 45 | REPO_GRAPH_WATCH=1 /tmp/rg-050/bin/repo-graph --repo <repo> 2> /tmp/rg-watch.log ) &
sleep 5; touch <repo>/<a source file>; sleep 30
grep -c '^\[watch\] rebuilt' /tmp/rg-watch.log
grep '^\[incremental\] unchanged' /tmp/rg-watch.log   # glia's LC.11 line on a no-change rebuild

# glia side: the wheel matches the pinned surface
cd /home/ivy/Code/glia && ~/.venvs/glia-leap/bin/python py/check_api_surface.py
```

## 10. Done vs pending

- **Landed:** waves W0-W33 (`leap_schedule.py` `LANDED`). Every row in sections 2b and 4 has a
  landed commit, shown in the generated output.
- **Specced but not landed** (generated, not_landed=1):

  | packet | status | what the spec promised the wrapper |
  |---|---|---|
  | LA.43 | not-needed: nothing shipped | its spec'd `replace_queue_nodes` signature change was unnecessary (LE.4c carries the path) and its evidence change was already on HEAD; the const-topic queue hops it described reach impact / trace through LA.4 + LE.4c |

- **Still to land in the leap (W34-W41):** LG.4b (README / CLAUDE refresh), LG.7, LG.8, LG.8a, LG.9,
  LG.10, LG.11, LG.12 and LG.14 (Engram), and LG.5b (neuropil). No spec among them names the
  wrapper.
- **Release steps (not packets):** the 0.5.0 version bump, the PyPI pending publisher for `glia-py`,
  the push and the tag. See section 0.
- **Open, owned by nobody yet:**
  - LF.3b's suggestion to give `EntryRule` a `cells` field, so that `nodes_json` `entry`,
    `trace::entries` and projection-text read declared entrypoints from one rule. Until then only
    `live` honours the ENTRYPOINT cell (section 1, item 6).
  - The "Test-report snapshot" section of glia's `docs/overlay.md` (LF.6d's handoff). The
    `tests_ingest` surface is in section 3.
- **Checked, no wrapper change** (generated, checked_no_change=17): L0.3, L0.4, L0.5, LA.15a, LA.15b,
  LA.16, LA.20b, LA.25a, LC.2, LC.5b, LD.10, LD.11a, LD.12c, LD.13, LD.14b, LD.15b and LG.2. The
  generated output's 55 additive rows declare no break; their wrapper-facing surface is sections 1
  and 3.
