# repo-graph handoff - glia 0.5.2 (the four bets 2026-10-16, the tweaks 2026-10-17)

**Status: active. glia 0.5.2 is released 2026-10-18 (tag `v0.5.2`, `glia-py` 0.5.2 on PyPI), and
repo-graph upgrades to it now, pinned `glia-py==0.5.2`.** James, 2026-10-18: *"maybe we just do the 0.5.2
and slowly work on 0.5.3 over the next week"*, then "repo-graph upgrades to 0.5.2 now". That lifts the
hold (2026-10-16: *"Hold repo graph for post 0.5.3 better to do all changes at once"*) and reverses the
2026-10-17 plan of no 0.5.2 release (*"can't we just go 0.5.1-> 0.5.3 release"*), under which this file
was written as the 0.5.2 half of a combined 0.5.1 -> 0.5.3 handoff. It is now the whole 0.5.2 handoff;
0.5.3, paced over the week, is a normal 0.5.2 -> 0.5.3 release with its own handoff. Section 9 lists the
tweaks (DT.1a-DT.13, waves W15-W26) on top of the W0-W14 content below, and section 10 the close-out
(DT.5h-DT.5l, the dead_symbol false positives, waves W27-W30, and DT.14). Every row names the glia
packet and commit, the change (old -> new) and the wrapper site.

The fifth glia -> repo-graph handoff, after `repo-graph-handoff-0.5.1.md`. 0.5.2 is "the four bets":
153 packets in `dev-notes/leap-052-packets.json` (plan: `dev-notes/next-leap-0.5.2.md`), 151 landed in
waves W0-W13 on glia's local `main` since v0.5.1 (`84e2e71`); W14 is the two docs packets (DZ.1 the
release docs, DZ.2 these handoffs). Groups: DA the `glia-rules` Datalog crate, DB rules in the engine
(check, `glia query`, GQL), DC `glia watch` and `WatchSession`, DD cross-repo identity (SAME_AS), DE
Engram anchors and engine hygiene, DF the 0.5.1 language deferrals, DG / DH the rest of the coverage
matrix. Breaks were allowed when a packet declared them, and **consumers pin the release exactly**.

Sources, in order of authority:
- the landed code at glia HEAD `12f58844` (the W13 close-out `f468af11` plus two plan commits) and the
  pyo3 / CLI surface snapshots, diffed `v0.5.1..HEAD -- py/api_surface/ cli/surface/` (section 5 lists
  the diff);
- each packet's landed `breaking` report and commit body. Where a report differs from its spec, the
  report wins, and where a report is wrong about the wrapper this doc says so;
- the specs' `breaking` blocks in `dev-notes/leap-052-packets.json`, and the routed handoff paragraphs
  in `dev-notes/leap-052-corrections.json`.

Every wrapper `file:line` was read at repo-graph HEAD `0f8ecfa` (mcp-repo-graph 0.5.2 on
`glia-py==0.5.1`), read-only. The working tree also holds 12 modified and 4 untracked paths (a one-shot
CLI, `repo_graph/cli.py`); its `server.py` change sits inside `main()` after line 1122, so every
`server.py` line number below line 1122 is the same in the working tree. Short names: `server.py`,
`graph.py`, `watcher.py`, `init.py` live in `repo_graph/`. Packet ids are glossed in words; the hash
after an id is the glia commit that landed it.

---

## 0. TL;DR

**The wrapper runs on 0.5.2 without a code change.** Every pyo3 call it makes still binds: `generate`,
`save_to_default`, `default_gmap_dir`, `version`, `load_from_gmap`, `activate`, `dense_text`,
`dense_text_subset`, `resolve`, `node_cells`, `governing_docs`, `coverage`, `node_count`, `edge_count`,
`cross_edge_count`, `nodes_json`, `bfs`, `predecessors`, `shortest_path`, `kind_names`,
`category_names`, `cell_type_names`, `entry_kinds` are unchanged in `py/api_surface/`; `find`,
`blast_radius`, `cross_stack_trace` and `entry_flows` gained `collapse=True` as their LAST keyword, so
the wrapper's positional calls (`graph.py:155`, `server.py:437`, `:520`, `:608`, `graph.py:69`) bind as
before. One registry id was allocated: edge category 37, SAME_AS (D0.1, `9d180f01`). No node kind or
cell type was added.

What repo-graph has to do:
1. **Pin exactly** (section 1): `glia-py==0.5.2`.
2. **Adopt `WatchSession`** (Q14, section 3): one session per repo instead of a full
   `generate(incremental=True)` per change in `_watch_rebuild` (`server.py:165-172`). Seven steps,
   with the measured memory cost.
3. **Optional renders** (section 2): the `identity` of a collapsed row and a hop's `to_identity`;
   `external` on a dialled client in `read`.

What changes under the wrapper with no code change: answers fold FACT / DERIVED identity classes into
one row (in a single-repo MCP graph: contract-op, contract-route and workspace-package classes, and since
the tweaks client <-> server model classes, section 9); SHARES_DEPENDENCY is no longer emitted; generated gRPC stubs stop "calling" every service; many
more edges in Python, TS, Go, Dart, Swift, C/C++, Rust, Scala, Ruby, PHP, Elixir and Clojure repos; the
coverage footer's text; new stderr lines, among them one `[memory] malloc_trim` line per dropped
PyGraph, which makes `_release_freed_memory` (`server.py:120-134`) redundant (keeping it is harmless).

New primitives worth an MCP mode (section 5): `PyGraph.query` / `query_gql` (a candidate single
`query` tool for P4), `PyGraph.identity_classes`, `glia_py.WatchSession`.

Bump order:
1. **glia (James):** `[workspace.package].version` (`Cargo.toml:74`), `py/pyproject.toml:7` and the
   excluded `engram-export/Cargo.toml:3` are bumped 0.5.1 -> 0.5.2 together in the release commit;
   James pushes it, tags `v0.5.2` and lets `wheels-py.yml` publish `glia-py` 0.5.2 (2026-10-18).
2. **repo-graph:** pin `glia-py==0.5.2` (section 1), run section 7 against a local wheel, port
   `WatchSession` (section 3), then release after glia-py 0.5.2 is on PyPI.

Tell builds apart with `glia_py.build_stamp()`: the W13 close-out wheel reads `0.5.1+p0c104fe6f8df1704`,
a wheel built at `196728e3` (0.5.2's last code commit, before the bump) reads
`0.5.1+p395be331c3dfb5b8`, and the released wheel reads `0.5.2+p90f604c450633cf4`. The release commit changes no
source file after `196728e3`; the stamp's hex half moves only because PARSER_STAMP hashes
every `Cargo.toml` and `Cargo.lock`, which the bump edits.

## 1. The pin

| file:line (HEAD `0f8ecfa`) | now | change to |
|---|---|---|
| `pyproject.toml:31` | `"glia-py==0.5.1",  # glia pins consumers exactly per release (0.5.1 breaks the graph contents)` | `"glia-py==0.5.2",` |
| `CLAUDE.md:24` | runtime deps `glia-py==0.5.1` | the same pin |
| `CLAUDE.md:105-109` | "glia 0.5.1 boundary notes", "Exact pin `glia-py==0.5.1`" | a 0.5.2 boundary note from sections 2-3, 9 and 10 |
| `README.md:26-30` | "engine (glia 0.5.1, pinned exactly) ... Reinstall the CLI from the `v0.5.1` tag" | `glia 0.5.2`, the `v0.5.2` tag |

`tests/test_packaging.py` already counts `==` as capped (`CLAUDE.md:109`), so the pin needs no test
change. The exact pin also means the published wrapper does not pick up glia-py 0.5.3 on its own.

**Mixed versions until both sides move.** FORMAT_VERSION stays 3, so a 0.5.1 layout is not an old
format, but its build stamp differs: whichever of the MCP server (glia-py 0.5.1) and a 0.5.2 `glia`
CLI (`glia build`, the `install-hooks` hooks, `glia watch`) loads the other's `.glia/graph/` rebuilds it
first (`[gmap] rebuilt <dir> (written by another glia build (...))`), on every alternation. And a 0.5.1
engine ignores a version-2 `.glia/overlay.toml` whole (DB.1, row 9), so the MCP graph then lacks that
file's entrypoints, wrappers and edges. Move the MCP server and the `glia` CLI (reinstall it from the
`v0.5.2` tag) to 0.5.2 together, one glia version per repo.

## 2. Breaks that reach the wrapper

Every row names the glia packet and commit, what changed (old -> new), and the wrapper site. None asks
for a code edit; rows 2-4 and 15 offer an optional render.

| # | packet (commit) | old -> new | wrapper site and action |
|---|---|---|---|
| 1 | D0.1 SAME_AS allocated as edge category 37 (`9d180f01`); DD.5 the identity resolver emits it (`1b631092`) | `category_names()` 36 -> 37 rows. SAME_AS cross edges (EVIDENCE emitter `resolver:identity`, rule `package_name` / `manifest_name` / `message_fqname` / `contract_op` / `contract_route` / `scip_symbol`, optionally `/diverged`; FACT rules Strong, DERIVED Medium; DD.6's HEURISTIC `body_hash` / `path_suffix/diverged` Weak) join each member to the class centre, the least (qname, kind, first graph index). A single repo gains them only for contract-op classes (with `contract_route`) and workspace-package classes (`manifest_name`). A merge of quokka-stack + quokka_web prints `[identity] classes=94 edges=134 diverged=0 package_name=17 manifest_name=0 message_fqname=0 contract_op=39 contract_route=38` (DD.5), and `glia identity` counts 17 FACT + 39 DERIVED classes once overlapping op and route classes join (DD.15). `why` / `check` tier them by rule, note `identity class (<rule>[, diverged])`. | `graph.py:22` builds `CATEGORY_NAMES` by name: `same_as`. `_MECH_ICON` (`server.py:498`) has no entry, so a SAME_AS hop renders with the default arrow. No change. |
| 2 | DD.9 find collapses identity classes (`acd819ef`) | a FACT / DERIVED class is one row (the best-ranked member) plus `identity` {`tier`, `rules`, `diverged`, `also_in`: [{`repo`, `qname`, `file`, `line`}]}; before, one row per member. Rows outside a class are byte-identical (the key is absent). `PyGraph.find(query, top_k=20, kinds=None, scope=None, collapse=True)`; `glia find --no-collapse`. | `graph.py:155` `find(query, top_k)` binds. `find_nodes` maps `r["id"]`, which is the shown member. **Optional:** `_render_located` (`server.py:326`) can print `also in: <repo> <file>:<line>` from `identity.also_in`. |
| 3 | DD.10 blast radius walks the identity quotient (`1604b425`) | a walk class (manifest_name, message_fqname, contract_op, contract_route, scip_symbol) is one node in the BFS and the PPR, so **scores move** on a graph with walk classes; a FACT / DERIVED class is one row with `identity`; two seeds in one walk class are one seed. `blast_radius(..., scope=None, collapse=True)`; `glia blast-radius --no-collapse`. | `server.py:437` `blast_radius(names, dir_engine, depth, None, live_only)` binds. Rows may gain `identity` (render as in row 2). |
| 4 | DD.11 trace and flows walk the quotient (`6938c604`) | a class is crossed at zero hops; paths, ranks and flow rows change when walk classes exist; two entries in one walk class are one flow; a hop into a FACT / DERIVED class gains `to_identity`. `cross_stack_trace(feature, depth=6, to=None, max_paths=10, collapse=True)`, `entry_flows(depth=6, collapse=True)`; `glia trace` / `glia flows` `--no-collapse` (on `flows` it conflicts with `--features` / `--out`); the trace table's location cell ends `(also in: ...; diverged)`. | `server.py:520`, `:608` and `graph.py:69` bind. `graph.py:74-77` `flows` keys by `key` and already collapsed duplicates. **Optional:** `_render_hop` (`server.py:538`) can show `to_identity.also_in`. |
| 5 | DD.12 tests-for (`5e293e54`), DD.13 serves (`da4e9857`), DD.14 arch (`1934981b`), DD.15 diff-impact labels (`9262a597`) | `tests_for` / `tests_for_diff` / `tests_for_rev`, `serves`, `service_map` gain `collapse=True` (last); test rows gain `identity`, serves rows `identity` / `handler_identity`; `service_map` counts a SAME_AS class once per service pair (from <= to, even with `collapse=False`) and class-mapped endpoint pairs once (two OpenAPI copies of one route: DOCUMENTS count 2 -> 1); under per-repo keying an unlocated SAME_AS member (a PACKAGE_DEP) is placed in its repo's service for links only (Kina + lapse: 5 -> 55 SAME_AS links, unplaced 72 -> 22). `diff_impact` / `diff_impact_vs_rev` rows' `identity.also_in[].repo`: `repo#<id % 1000>` -> the build's repo label. `timeline_history`'s unknown-symbol suggestions stay raw (two members of one class are two suggestions). | the wrapper calls none of these (grep of `repo_graph/`: 0 hits). |
| 6 | DD.16 SAME_AS stars replace SHARES_DEPENDENCY and the message half of SHARES_SCHEMA (`14c6ae40`) | SHARES_DEPENDENCY (31) is never emitted (a `package_name` SAME_AS star per shared package); SHARES_SCHEMA (16) is never emitted between MESSAGE_TYPEs (a `message_fqname` star per shared message; CLASS / INTERFACE / STRUCT SHARES_SCHEMA stay). The `[schema-link]` stderr line is gone; `[passes] domain=code resolve=14` (0.5.1: 15; DD.5's identity added one, DD.16 removed `package` and `message_schema`). | the single-repo MCP graph never had either category; a merge shows SAME_AS in their place, rendered by name. No change. |
| 7 | DE.11 the 0.5.0 pattern aliases removed (`a7f2c70a`) | `PyGraph.patterns_experimental` and `glia_py.patterns_vs_rev_experimental` raise AttributeError (were DeprecationWarning aliases); `glia patterns --experimental` exits 2 | the wrapper calls neither (grep: 0 hits) |
| 8 | DE.10 freed heap released when a PyGraph drops (`4f1d2dea`) | each dropped PyGraph runs glibc `malloc_trim(0)` and prints `[memory] malloc_trim site=pygraph_drop rss_mb=<before>-><after>` (Linux glibc only; `GLIA_MALLOC_TRIM=0` opts out). The rebuild-and-swap pattern stops creeping: glia, VmRSS rebuild 15 minus rebuild 1, `+607 / +635 / +591 / +629 MB` on the W0 HEAD wheel -> `-139 / -127 / -160 / -155 MB` with DE.10 (grpc-go `+297 / +258 / +340` -> `-49 / -52 / -46`). | `_release_freed_memory` (`server.py:120-134`, called at `:161`) is redundant on glia >= 0.5.2; it runs after the engine's trim and finds little. Keep or drop it. The server relays one more stderr line per swap. |
| 9 | DB.1 overlay `version = 2` (`00177a71`) | `[[constraint]]` gains `rule` (an invariant's Datalog text), `transitive` + `via` (forbid_edge) and `min_tier` (`fact` / `derived`). **A 0.5.1 glia ignores a version-2 overlay whole.** The cell API refuses any CONSTRAINT entry carrying `rule`: `glia cell set` exits 2 and writes nothing, a `.glia/cells.jsonl` row is rejected, pyo3 `set_cell` / `write_cell` refuse it. Overlay error text: "this glia reads version 1" -> "this glia reads versions 1 and 2". | the wrapper writes no cell (grep: 0 hits for `set_cell` / `write_cell`). Mixed versions: section 1. |
| 10 | DB.3a rule invariants and the min_tier gate (`333ec252`), DB.3b transitive forbid (`bda10135`), DB.3d check's rendering and exit (`afcea62d`) | `check()` violations gain `blocking` (after `tier`) and, on the new rule kinds `rule` / `forbid_path`, `subject` / `file` / `line` / `caveats`. An invariant with `rule` is evaluated (was unchecked); a `transitive = true` forbid_edge reports one `forbid_path` violation per hit. A violation weaker than its rule's `min_tier` (default derived) is advisory, never blocking. **`glia check` exits 1 only on a blocking violation** (was: any violation); the summary reads `- violations: V (blocking B, advisory A)`; new stderr `[check] gate blocking=<B> advisory=<A>` and `[rules] check ...`. | the wrapper calls neither `check` nor `glia check` (grep). A CI job that gates on `glia check --json` should read `blocking`. |
| 11 | DB.3c review reads min_tier (`dd71fc94`) | `review_vs_rev()["blocking"]` and `glia review`'s exit 1 need a new violation at or above its rule's min_tier (a heuristic-only new violation no longer fails); rule / forbid_path violations are classed new / resolved by `subject`; the markdown headline gains ` (<A> advisory)` when A > 0, `### New violations (blocking)` lists only blocking ones and a new `### New violations (advisory: below the rule's min_tier)` section lists the rest; the impact `also_in` repo is a label. | the wrapper does not call review |
| 12 | DB.4 gaps `rotted_rule` (`50d22541`) | `gaps::CATEGORIES` 12 -> 13 (`rotted_rule`, after `redundant_rule`: a `[[constraint]]` whose `rule` this glia can no longer read, a FACT row); `skipped` with no roots lists it; the `[gaps] rows=` marker gains `rotted_rule=<n>`; `glia gaps --category` / `glia overlay propose --category` accept it; `overlay_accept(remove=)` / `glia overlay accept --remove` take its ids. Row shape unchanged. | the wrapper calls neither `gaps` nor `overlay_*` (grep: 0 hits) |
| 13 | DB.9a rules through the overlay loop (`fb22da3d`), DB.9b try judges rules by the check delta (`48a94843`), DB.9c try shows the rule part (`521a1b90`) | a candidate may hold `[[constraint]]` rules (handles `constraint#<n>`); `[overlay] candidate` / `[overlay] accept` markers gain ` constraint=<n>`; new `[overlay] try-rules` line; `overlay_try`'s dict gains optional `rules` and per-stanza `rule` / `rules`; a graph stanza that adds or hides a declared rule's violation is `review` (was `keep`); the verdict line becomes `verdict: <v> - graph part <g> (<why>), rule part <rv>` when a rule part exists; a rule that does not validate is refused (`ValueError` in py, exit 1). accept raises a file to `version = 2` only when a written rule needs it, and a 0.5.1 glia ignores a file so raised. | the wrapper calls no `overlay_*` (grep: 0 hits). A future overlay mode reads `verdict` and the rule part. |
| 14 | DF.21 DF close-out caveats (`9e57112a`), DF.22c concrete overrides (`8a4b6557`), DH.14 PHP heritage (`a08fc669`) | `coverage()` note text changes for swift / dart / c_cpp CALLS, c_cpp IMPORTS, go HANDLED_BY, `*` QUEUE_FLOWS (Pub/Sub), `*` GRAPHQL_CALLS / WS_CONNECTS / GRPC_CALLS and `*` HANDLED_BY (queue callbacks): row count, order and keys unchanged (DF.21). A TS repo gains a typescript CALLS row (DF.22c). The php IMPLEMENTS row is gone and the php INHERITS_FROM note becomes the residual (traits and enum methods are not nodes, last-segment binding) (DH.14). | `_coverage_note` (`server.py:1008-1028`) prints `recs[:8]` capped at 200 characters: the orient blind-spots footer shows the new text, and on TS repos the new row may enter the eight. No change. |
| 15 | DF.8 external WS / gRPC / GraphQL client sites marked (`f1de14d9`), DF.10 they say so (`1f150479`) | the `ENDPOINT_HIT` of a WS_CLIENT / GRPC_CLIENT / GRAPHQL_OPERATION site gains a trailing `"external":true` when every host is public and unconfigured (`{"via":"ws","host":"stream.binance.com","external":true}`); a gRPC host carries its port (`geocoder.googleapis.com:443`). Such a client gains ORIGIN `{"provenance":"external"}`, `effects` / `serves` rows name it in `external_hosts`, and `glia gaps` no longer lists it as a `suspected_edge` orphan. | **Correction to DF.8's note** ("`_cell_text` and the read footer render `external`"): `_dial_text` (`server.py:724-739`) handles every payload with `via` and renders only `host (via)`, so `read` shows `dials: stream.binance.com (ws)` with no external mark. **Optional:** append ` external` when `data.get("external")`. |
| 16 | DF.20 TS endpoint bases held in a class member or a config const fold (`7d2f16a2`) | `ENDPOINT_HIT` gains a trailing `"alias":"this.<m>"` beside the substituted `template` / `folded_from` / `host` | `_cell_text` (`server.py:678-721`) prints the first six fields (method, path, file, line, col, confidence), so `read` is unchanged |
| 17 | DF.14 GCP Pub/Sub subscription -> topic binding from Terraform (`3b271bf4`) | `google_pubsub_topic` / `google_pubsub_subscription` INFRA_RESOURCE nodes carry a second CODE cell, Json `{"pubsub":"topic","name":..}` / `{"pubsub":"subscription","name":..,"topic":..}` (or `topic_ref`), after the text CODE cell; new QUEUE_FLOWS (rule `binding`, at most Medium) | `_READ_CELL_TYPES` excludes CODE, so `read` is unchanged |
| 18 | DF.19 OpenAPI server bases in the contract link (`61de0c5b`) | `spec_status` pairing gains `server_base` / `annotated_base` (`implemented (server_base, <conf>)`); an op of a swaggo repo with one `@BasePath` gains ORIGIN `annotated_base` / `annotated_at`; a guessed prefix pair to several routes keeps only the exact route under the base (quokka: 180 -> 178 DOCUMENTS) | the wrapper does not call `spec_status`; `governing_docs` (`server.py:777`) reaches a swagger op through the exact base |
| 19 | DE.1 graph content stops depending on the RepoId (`98650a9c`) | an ambiguous backticked doc mention binds the least (qname, kind, graph index) candidate instead of the lowest NodeId: such a DOCUMENTS edge can move once at the upgrade (one copy, before -> after: Kina 4, glia 159, quokka-stack 127 edges moved) | `_governing_docs_note` (`server.py:773`) may name a different section for such a symbol. No change. |
| 20 | DE.7 generated-code provenance (`db774107`) | nodes of a file whose head carries a generator header, or named `.g.dart` / `.freezed.dart` / `.gr.dart` / `.mocks.dart` / `.g.cs` / `.designer.cs`, gain ORIGIN `generated`; `.pbgrpc.dart` / `_pb.js` / `_grpc_pb.js` / `_pb.d.ts` gain `generated_proto`. `hotspots` and `patterns` drop them. The `[provenance]` line's `generated=<n>` becomes `generated=<n> (name=<a> banner=<b> qname=<c>)` | the server parses no stderr. No change. |
| 21 | DE.9 requirements.txt / Pipfile root a Python project (`e0370f74`), DG.12 sbt sub-projects (`ff881e56`) | new PROJECT nodes, so `project_roots()` / `glia projects` / `glia arch` rows change and `--scope` accepts the new labels; a `[[project]]` stanza at a root labelled by its directory now gives that root its declared label (`[roots] declared=.. relabelled=<r>`) | the wrapper's `refresh` / `orient` print no project list. No change. |
| 22 | D0.2 the `glia-rules` crate, the one Cargo.lock change (`35cfec86`), and every packet that edits a hashed source | PARSER_STAMP / BUILD_STAMP move, so every parse cache reparses and every `.glia/graph/` layout rebuilds once at the upgrade | the first `load_from_gmap` (`server.py:190`) or `refresh` is a full build |

## 3. Adopt `WatchSession` (Q14)

Leap doc section 0.1, Q14: "repo-graph adopts `WatchSession`: yes, a handoff item for its session".
What the wrapper does today: `start_watcher(REPO_PATH, _watch_rebuild)` (`server.py:1143`) debounces
watchdog write events (`watcher.py:54-77`, `DEBOUNCE_SEC = 0.3`) into `_watch_rebuild()`
(`server.py:165-172`), which calls `_build_graph(REPO_PATH, incremental=True)` (`server.py:137-162`): a
whole `generate` (every file walked, unchanged files' parses from the cache, every group rebuilt, every
pass rerun), then `save_to_default` on every event batch, then the swap and `_release_freed_memory()`.

`glia_py.WatchSession` (DC.9, `902c5456`, over `glia_engine::watch`, DC.7a-c `b5b4fcc2` / `d30fc67b` /
`9bbf002c`) holds the walk table, the parse cache, DC.4's graft memos and each language group's last
build in the process. `apply(paths)` re-reads only the named paths and rebuilds only the groups whose
inputs changed (early cutoff on a per-group fingerprint), and its output equals a clean build byte for
byte (`engine/tests/watch_parity.rs`, DC.10a / DC.10b). The surface (`py/api_surface/watch.txt`):

```
glia_py.WatchSession(repo, overlay=True)
WatchSession.apply(paths) -> dict          # {seq, files {added, modified, removed, reparsed, reused},
                                           #  groups_rebuilt, full_rebuild, total_nodes, total_edges,
                                           #  counts, nodes, edges, phase_ms}
WatchSession.poll() -> dict | None         # its own stat scan, then apply; None when nothing changed
WatchSession.snapshot() -> PyGraph         # an independent copy; later updates never change it
WatchSession.persist() -> None             # <repo>/.glia/graph/ (writer `watch`) + parse_cache.bin
```

The seven steps:

1. **Open one session per repo, off the request path.** Where the watcher starts (`main()`,
   `server.py:1141-1144`), open `glia_py.WatchSession(REPO_PATH)` on a background thread, so
   `mcp.run()` is not delayed; the first tool calls keep using `get_graph()`'s `load_from_gmap`
   (`server.py:175-195`). Keep `overlay=True` (the default): `persist()` refuses an `overlay=False`
   session with `ValueError`, the rule `save_to_default` already applies. Opening loads
   `<repo>/.glia/graph/parse_cache.bin` once and builds once (DC.9: glia 2.18 s, grpc-go 1.37 s); it
   raises `ValueError` when the path is not a directory. `[watch] open repo=.. files=.. groups=..
   nodes=.. edges=.. took=..` and `[watch] session repo=<repo> overlay=true surface=py` go to stderr.
2. **Accumulate paths in the Debouncer.** `apply()` re-reads only the paths it is given. `Debouncer`
   (`watcher.py:54-77`) keeps a `set` under its `_lock`: `trigger(path)` adds to it and restarts the
   timer; the timer callback swaps the set out under the lock and calls `on_change(paths)`.
   `_Handler.on_any_event` (`watcher.py:105-113`) passes `event.src_path` and, for a move,
   `event.dest_path` too, each through `is_ignored`: today it keeps only `dest_path or src_path`
   (`watcher.py:110`), which is enough for a full rebuild but leaves a moved file's old path in a
   session. A directory event may be passed as a path; `apply` accepts files and directories, absolute
   under the repo or repo-relative.
3. **Apply, then swap in a snapshot.** `_watch_rebuild(paths)` becomes: `upd = session.apply(sorted(paths))`;
   when `upd["seq"]` moved (an update that changed nothing keeps `seq` and has no rows), install
   `RustGraph(session.snapshot(), REPO_PATH)` as `_graph` and keep `_release_freed_memory()` after the
   swap (step 7). `apply` raises `RuntimeError` when the repo is no longer a directory; the session
   keeps its previous state, so log it and keep serving.
4. **Persist on an interval and at shutdown, never per event.** Drop `save_to_default` from the watch
   path. After an update, call `session.persist()` when the last persist is older than an interval
   (`glia watch` defaults to `--persist-every 60` seconds) and once at exit (`atexit`). `persist()`
   writes the layout and the parse cache under `<repo>/.glia/graph/`, which `is_ignored`'s layout-dir
   prefix rule (`watcher.py:39-51`) already skips, so a persist never triggers an update. A write
   error is `OSError`. `_build_graph` keeps `save_to_default` for `refresh` and the cold path.
5. **One caller at a time.** The session takes one call at a time: a second Python thread calling into
   it during `apply` / `poll` gets pyo3's `RuntimeError` "Already borrowed" instead of waiting.
   `threading.Timer` fires each debounce on a new thread, and a slow `apply` (glia: 1.81 s mean) can
   overlap the next fire, so hold `_rebuild_lock` (`server.py:60`) around every session call. The GIL
   is released while the engine works (`__init__`, `apply`, `poll`, `snapshot`, `persist`), so tool
   calls keep answering on the previous snapshot meanwhile.
6. **Keep the event filter; rename the wrapper's own `[watch]` lines.** Keep `WRITE_EVENTS`
   (`watcher.py:34`, the read-event loop fix) and `is_ignored`. glia now prints `[watch] open`,
   `[watch] update seq=.. files +a ~m -r groups_rebuilt=<k>/<n> full_rebuild=.. nodes +a -r ~m >v
   edges +a -r ~c took=.. repo=..`, `[watch] noop`, `[watch] outside`, `[watch] poll` and
   `[watch] session` on the same stderr, so rename `[watch] rebuilt:` and `[watch] rebuild failed:`
   (`server.py:170`, `:172`) and `[watch] watching` (`:1144`), for example to `[repo-graph] watch ...`.
7. **Memory, `refresh` and fallbacks.** A held session costs about twice a generate loop's steady
   state (parse cache + group cache + current result + one snapshot) and creeps slowly. DC.9's rows
   (`bench/rss/results.jsonl`, source `DC.9 wheel (HEAD+DC.9)`, 12 updates, VmRSS):

   | repo | session open | update 1 -> 12 | peak HWM | mean s / update | control: generate + save loop, same wheel |
   |---|---|---|---|---|---|
   | glia@9c7c6faa (edit in `engine/src/watch.rs`) | 658 MB | 668 -> 748 MB | 1118 MB | 2.69 (apply 1.81, persist 0.73) | 510 -> 391 MB (rebuild 2: 301), 2.45 s |
   | grpc-go@6f50403 (edit in `server.go`) | 278 MB | 290 -> 327 MB | 482 MB | 1.32 (apply 1.02, persist 0.25) | 240 -> 173 MB (rebuild 2: 142), 2.49 s |

   It levels off (DC.8, W9, `dev-notes/next-leap-0.5.3.md` section F.3): 100 watch-only updates on a
   glia copy rose about 75 MB over the first ~12 updates, then stayed flat at 615-685 MB. The snapshot
   costs what a fresh `generate` costs; the engine trims freed heap after each update (site
   `watch_update`) and when the old PyGraph drops (`pygraph_drop`), so `_release_freed_memory()` after
   the swap is harmless and redundant. `refresh(full=False)` (`server.py:845-864`) can call
   `session.poll()` and swap on a dict; `refresh(full=True)`, or a `repo_path` that retargets the
   server, keeps `_build_graph(target, incremental=False)` and then re-opens the session for the new
   target (the old one is dropped). Without watchdog (`start_watcher` returns None), a timer calling
   `session.poll()` gives the same freshness (`glia watch` polls every 500 ms); with
   `REPO_GRAPH_WATCH=0` no session is opened.

`glia watch <repo> [--debounce-ms <N>] [--persist-every <S>] [--poll-ms <N>]` (DC.8, `1f749b76`) is the
same loop as a foreground CLI: NDJSON per update on stdout, a persist on the interval and on exit,
SIGINT / SIGTERM / stdin EOF to stop, `--no-overlay` refused (exit 2). Q14 picks the embedded session;
the CLI is the alternative for a non-Python consumer.

## 4. Graph content: what the answers show differently

No wrapper code parses these qnames, caches them across rebuilds or keys state on them (`graph.py`
rebuilds its index from `nodes_json()` on every load, and `flows` is recomputed). They change golden
outputs, counts and the names `find` / `impact` / `trace` / `read` / `orient` print.

### 4a. Identity changes (qname or NodeId)

| packet (commit) | old -> new | measured |
|---|---|---|
| DE.9 requirements.txt / Pipfile roots (`e0370f74`) | HTTP / channel qnames under a NESTED python root gain the owner suffix: `GET /health` -> `GET /health @svc/email`, `grpc_client:ProductCatalogService` -> `... @src/recommendationservice`; a node two such services shared unowned splits into one per owner; new `project:<dir>` PROJECTs | microservices-demo: 21 qnames gone, 35 new, nodes 3,083 -> 3,097; `(outside projects)` 23 files / 366 nodes -> 11 / 101 |
| DG.12 sbt sub-projects (`ff881e56`) | ROUTE / ENDPOINT / QUEUE_* / WS_* / GRAPHQL_* / GRPC_* / RPC qnames of files under a member gain ` @<dir>`; new `project:<dir>` PROJECTs (ecosystem sbt) | fixture only |
| DF.7 Go route-group prefixes held in a constant (`0fab4960`) | `<METHOD> <local>[ @owner]` -> `<METHOD> <const prefix><local>[ @owner]` (`GET /items` -> `GET /api/v1/items`) | quokka-stack and grpc-go unchanged |
| DF.18 OpenAPI server bases (`78645340`) | an op of a document whose first server url is templated with defaulted variables: `contract::docs::openapi::GET:/users` -> `contract::docs::openapi::GET:/api/v1/users` (name `GET /api/v1/users`); a multi-server document's ops gain ORIGIN `bases` | no bench, matrix or quokka op moved |
| DF.20 TS endpoint bases from config (`7d2f16a2`) | `endpoint:<M>:${…}/<rest>` -> `endpoint:<M>:<base path>/<rest>`: Kina `endpoint:GET:${…}/stats @frontend` -> `endpoint:GET:/admin/stats @frontend`, `${…}/trades` -> `/api/trades` | Kina: 85 call sites, ENDPOINTs 112 -> 103 (9 merge into an existing real-path node); HTTP_CALLS exact 48 -> 85, base 45 -> 1 |
| DG.10 Akka / Pekko HTTP path matchers composed (`774de9b4`) | `ANY /<first literal>` -> `ANY /<pathPrefix segments>/<every matcher segment>` (`ANY /ws` -> `ANY /ws/chat`, `ANY /users` -> `ANY /api/users`; `Segment` -> `:segment`, number / UUID matchers -> `:id`, `Remaining` -> `*`); ROUTEs read from a non-directive `path(` or an unreadable matcher are removed | fixtures and matrix probes |
| DH.20 Swift Vapor routes (`121041d3`) | `GET /users/id` -> `GET /users/:id`; `PATCH /todos/todoID/patched` -> `PATCH /todos/:todoID`; phantom ROUTEs from `.get(` calls with no `use:` and no trailing closure (`GET /id` from `req.parameters.get("id")`) removed | fixtures |
| DH.17b Elixir behaviours (`8f72df22`) | a pure behaviour module (`@callback` only) is INTERFACE instead of PACKAGE: same qname, new NodeId | fixtures |
| DH.8 GraphQL roots for graphql-ruby / Absinthe; Dart operation names (`edfba300`) | Dart package:graphql `graphql_op:client.query` / `client.mutate` / `client.subscribe` -> `graphql_op:<OpName>` when the call's `gql(..)` document is a same-file constant or an inline literal | fixtures |
| DH.1 Ruby (`41f4c589`), DH.2 PHP (`214105be`), DH.3 Dart (`4d96781a`), DH.4 Elixir (`57ae47f1`) broker rows | framework tags replaced by named queues: Ruby `queue_producer:unresolved:sns` -> `queue_producer:<topic>`; php-amqplib `queue_producer:unresolved:rabbitmq` -> `queue_producer:<routing key>`, php-rdkafka `queue_consumer:unresolved:kafka` -> `queue_consumer:<topic>`; kafka_dart `queue_producer:unresolved:kafka` -> `queue_producer:<topic>`; Oban pipe form `queue_producer:unresolved:oban` -> `queue_producer:<Worker>`; plus new `queue_producer:<t>` / `queue_consumer:<t>` nodes (Laravel jobs as `<JobClass>`) | fixtures and matrix probes |

The DH packets declared `node_id` for nodes they ADD with no qname moved: DH.5 `config:env:<NAME>` from
Dart / Elixir / Laravel env reads (`d7230be3`); DH.6 `config:flag:<key>` / `config:secret:aws_sm/<ref>`
(`c4bb7da0`); DH.7 `event_emit:<name>` / `event_handle:<name>` for ActiveSupport::Notifications, Laravel
events, Dart event_bus, Phoenix.PubSub (`6db8612a`); DH.9 Ratchet `ws:<path>`, Dart `ws_client:<path>`
(`df81a9c1`); DH.10 `cli:<name>` CLI_COMMANDs for package:args, Mix tasks, composer `bin`, gemspec
`executables` (a gemspec with an executable is a manifest MODULE) and CLI_INVOCATIONs (`9c895029`);
DH.11 `data_entity:sql:<table>` from sqflite and Ecto migrations (`13902a97`); DH.12 elixir-grpc
`grpc_client:<Service>` (`ab306320`); DH.13 Ruby INHERITS_FROM / INJECTS / constructed-receiver CALLS,
edges only (`e8223e1f`); DH.14 PHP interface METHODs `<Interface>::<method>` (`a08fc669`); DH.15 Dart
injectable INJECTS and shelf_router HANDLED_BY, edges only (`304037c1`); DH.17a Elixir remote CALLS,
edges only (`77e8d9fa`); DH.17b ExUnit FUNCTIONs `<module>::test <name>` (spaces in the qname, as ROUTE
names have); DH.18 Ecto `data_entity:sql:<Model>` (`411c063e`); DH.19 Compojure / reitit HANDLED_BY,
edges only (`db240e69`); DH.21 libcurl `endpoint:<METHOD>:<path>` (`837297c7`).

### 4b. Removed nodes and edges

| packet (commit) | what goes | measured |
|---|---|---|
| DE.8 generated gRPC stubs mint no GRPC_CLIENT (`38b4f41e`) | GRPC_CLIENT nodes minted only by generated stubs (`*_grpc.pb.go`, `*_pb2_grpc.py`, `*.pbgrpc.dart` ...) and their GRPC_CALLS; a client a hand-written site also mints keeps its qname and moves POSITION to that site | microservices-demo: Go services 36 -> 13 GRPC_CALLS, Python 18 -> 3; `glia arch` out column productcatalogservice 9 -> 0, shippingservice 9 -> 0; quokka-stack `grpc_client:QuokkaChatService @quokka_android` now at `lib/core/services/chat_service.dart:58`; grpc-go GRPC_CLIENT 28 -> 21 |
| DD.16 (`14c6ae40`) | SHARES_DEPENDENCY, message SHARES_SCHEMA (section 2, row 6) | 99 / 99 multi-dir fixtures' `contract_fields` unchanged |
| DF.9 external WS / gRPC / GraphQL clients stay out of pairing (`b4b8565f`) | WS_CONNECTS / GRPC_CALLS / GRAPHQL_CALLS from a client whose every hit is `external` and whose hosts name no service | 3 fixture edges |
| DF.2 PHP symbol imports bind through declared namespaces (`7fbc75f2`) | a `.php` import into an undeclared namespace under the repo's own root namespace no longer takes the `tail_unique` guess; a symbol import into a declared namespace that lacks the member, or has two, binds nothing (PHP and C# `using static`) | symfony-demo loses 2 wrong IMPORTS |
| DF.19 (`61de0c5b`) | an OpenAPI op paired to several routes by the API-prefix guess keeps only the exact route under its base | quokka 180 -> 178 DOCUMENTS |
| DF.22a TS parameter and local receivers (`4135c395`) | a constructor-body bare `x.m()` that bound through field `x` loses its edge when a constructor local named `x` of another type shadows it | 0 edges removed on 7 real copies and 115 TS fixtures |
| DF.4b Dart plain imports (`2692e523`) | a Dart name HEAD bound through a repo-unique fallback now binds through the plain import first | 0 edges lost across the 41 Dart fixtures and probes; game_template 480 -> 497 edges, provider_shopper 194 -> 196 |
| DF.6 CMake generator expressions (`72a67c22`) | an angle include HEAD bound through a later root (`include/` or a compile_commands dir) can bind through an earlier genex root holding the same header | the other 12 C/C++ fixture dirs: node and edge sets identical |
| DG.1 Rust brokers (`4dac65bb`), DG.2 Scala brokers (`089e03d8`), DH.1 / DH.2 / DH.4 broker gates | eventbus verb-fallback EVENT_EMITTER / EVENT_HANDLER phantoms (`publisher.publish(..)`, `.subscribe(`, `.on(`) in files that name one of the new broker libraries, in any language (C / C++ files naming `google/cloud/pubsub` included); Alpakka GooglePubSub EVENT twins, `unresolved:redispubsub` tags, `event_emit:ProducerRecord` | fixtures |

### 4c. New edges and evidence

- **Identity (DD.5-DD.7, `1b631092`, `fe20779b`, `16020321`):** SAME_AS stars (section 2, row 1); multi-repo
  merges also get HEURISTIC Weak SAME_AS for vendored copies (`body_hash`, `path_suffix/diverged`,
  never collapsed): quokka-stack + quokka_web 670 Weak edges (`body_hash=537 path_suffix=133
  offsets=1/1`). Repos with SCIP snapshots on both sides get FACT `scip_symbol`. `glia identity` on quokka-stack --with quokka_web:
  726 classes (fact 17, derived 39, heuristic 670, diverged 133); Kina --with lapse: 55.
- **TypeScript (DF.17 `04f17964`, DF.22a-c):** CALLS rule `receiver_state` into another class's STATE_VAR
  (DERIVED, like `receiver_type`, never name-only; Kina `[recv]` typescript= 313 -> 444); CALLS rule `receiver_type` from class-typed parameters and
  locals, top-level test callbacks included (shell 234 -> 400, mem0 0 -> 359 binds; mem0 dead_symbol
  496 -> 426 rows); CALLS rule `inherited_receiver` (DF.22b `5ebb3db5`); method-level IMPLEMENTS rule
  `concrete_override`, Strong (DF.22c: wpf +3, shell +4, mem0 +4), so overrides of a called member are
  live and leave `dead_symbol`. `dead_symbol` rows change three ways: a method that gains its first
  caller leaves, TS overrides of a called member are withheld, overridden concrete members leave; a
  `super.m()` call (rule `super_method`) vouches for no override. `patterns`, `check` and the
  reflexion model read the new edges. **cell_value:** a TS `super.m()` CALLS edge's EVIDENCE rule
  changes from `inherited_method` to `super_method` (`this.m()` keeps `inherited_method`). No qname
  moves.
- **Go:** DF.15 an un-aliased import binds the package clause name (`d2f0be22`); DF.16 method-value
  handlers of a typed parameter or local bind through the type (`511a2c0c`): an existing name-bound
  handler's EVIDENCE goes `graph:refs` / `global_unique_method` -> `graph:go_packages` /
  `package_type_method` or `local_type_method`, so its `why` tier rises heuristic -> fact.
- **PHP / C# (DF.1 `e39dfe8a`, DF.2):** group `use \A\B\{..}` parses (the rest of such a file used to be
  lost); a symbol import bound through a declared namespace has EVIDENCE rule `namespace` and tiers FACT
  in `why` (was HEURISTIC `tail_unique`), the same for C# `using static`.
- **Dart (DF.4a `edf4079b`, DF.4b):** own-package `package:<name>/..` IMPORTS; plain-import CALLS (rule
  `import_binding`); heritage / INJECTS refs into plainly imported libraries keep their target but go
  `global_unique` -> `import_binding` (heuristic -> fact in `why`; game_template 2 INHERITS_FROM + 2
  IMPLEMENTS). That rule change is a cell_value break DF.4b's spec did not declare; it is inherent to the
  declared mechanism (the session routed it here so the handoffs list it).
- **Swift (DF.3 `314956fe`), C/C++ (DF.5 `f8c3956e`, DF.6, DH.21):** local / parameter receivers (rule
  `local_receiver`), lambda calls and `auto` locals (rule `receiver_return`), CMake genex include roots,
  libcurl ENDPOINTs + HTTP_CALLS.
- **Python (DF.12 `5bec20cd`, DF.13 `dc4b37a7`):** blinker / Django signal EVENT nodes and
  cross-file EVENT_FLOWS (owner edges rule `python_signal`).
- **Declared tests (DF.11 `a18f668b`):** `[walk] tests` in `.glia/overlay.toml` now feeds the TESTS pass
  (rule `declared_name`).
- **Rust / Scala (DG.1-DG.13b):** Rust broker / task-queue rows, tokio broadcast and Akka EventStream
  events, async-graphql / Caliban resolvers, axum / Akka WebSocket handlers, aws-sdk-secretsmanager /
  LaunchDarkly / Scala env CONFIG reads (`glia flags` includes Rust LaunchDarkly), tokio-cron-scheduler /
  akka-quartz CRON_JOBs, scopt CLI, Slick DATA_ENTITYs, http4s HANDLED_BY, ScalaTest / MUnit case
  FUNCTIONs `<suite>::<description>` with TESTS (DG.11 `c8357fbb`), Rust `impl Trait for Type`
  IMPLEMENTS across files (DG.13a `2d99ca0e`, rule `trait_impl`: glia's `CrossGraphResolver` gains 17
  implementors) and axum / actix-web / Rocket state INJECTS (DG.13b `4bee7730`, EVIDENCE
  `graph:rust_paths` / `extractor_injects`).
- **Elixir (DH.17a `77e8d9fa`, DH.17b):** remote CALLS by full module name (EVIDENCE
  `graph:elixir_modules`, rules `full_name` / `alias_path` / `nested_alias` / `module_self`),
  `@behaviour` IMPLEMENTS, `Application.compile_env` INJECTS, ExUnit test FUNCTIONs with TESTS.
- **Queues / config (DF.14, DH.5, DH.6):** Pub/Sub topic -> subscription QUEUE_FLOWS (rule `binding`,
  Medium); Dart / Elixir / Laravel env READS_CONFIG; Ruby / Elixir / PHP flags and secrets.

### 4d. Stderr lines (the server relays them and parses none)

- **New:** `[memory] malloc_trim`; `[groups]`, `[const-fold]`, `[evidence-split]`; `[graft-memo]` (on
  incremental and in-process repeat builds: `refresh`, the watcher, a `WatchSession`); `[identity]`;
  `[identity] collapse surface=<find|blast_radius|trace|flows|tests_for|serves|arch>`;
  `[scip] identity`; `[rules] eval`, `[rules] check`, `[rules] reflexion`; `[check] gate`;
  `[query] lang=.. surface=..`; `[watch] ...`; `[ts-locals]`; `[elixir-calls]`, `[elixir-types]`;
  `[c-http-client]`; `[eventbus] typed`; `[config] env-read`; `[event-py-signals]`;
  `[grpc-client] skipped generated file`; `[imports] dart plain-import names bound=<b> ambiguous=<a>`;
  `[overlay] try-rules`.
- **Changed:**
  - `[ts-inherit] calls bound through superclasses: <n> (self=<s> super=<p> receiver=<r> ambiguous=<a>) abstract implements=<m> concrete overrides=<c>`;
  - `[recv]` counts; `[provenance] ... generated=<n> (name=<a> banner=<b> qname=<c>)`;
  - `[c-includes] ... genex=<g>`; `[cpp-scope] ... receiver_return=<n>`; `[swift-scope] ... local_receiver=<n>`;
  - `[go-mounts] ... const_prefixes= const_unresolved=`; `[go-routes] registrations= ... consts=`;
    `[go-routes] receiver-method handlers=<r> local-method=<n> in <file>`;
    `[go-package] root-package ... clause_named=<n>`;
  - `[cron] code .. nestjs=<n> tokio=<n> akka_quartz=<n> ..`;
    `[cli-decl] manifest ... (pyproject= setup= npm= cargo= composer= gemspec=)`;
  - `[queues] resolver ... binding=<b>`; `[contract-link] ops=.. based=<b>`;
    `[roots] declared=.. relabelled=<r>`; `[gaps] rows= .. rotted_rule=<n>`;
  - `[overlay] candidate` / `[overlay] accept` `... constraint=<n>`;
  - `[identity] ... scip_symbol=<n> body_hash=<n> path_suffix=<n> offsets=<c>/<s>` and
    `[evidence-rules] resolver=identity ... scip_symbol=<n> body_hash=<n> path_suffix=<n>`; an
    incomplete SCIP snapshot prints `[scip] snapshot incomplete` twice per build;
    `[passes] domain=code resolve=14`;
  - `[const]` bindings / conflicts counts include config-expression bindings (DF.20); the walk's
    `[parallel] walk .. read <n> files` count includes HOCON `.conf` files (DG.7b).
- **Gone:** `[schema-link]`.

## 5. New primitives worth adopting

From the surface diff (`v0.5.1..HEAD`): new `py/api_surface/{query,identity,watch}.txt`; `collapse=True`
appended to `find`, `blast_radius`, `cross_stack_trace`, `entry_flows`, `tests_for`, `tests_for_diff`,
`tests_for_rev`, `serves`, `service_map`; `patterns_experimental` / `patterns_vs_rev_experimental`
removed. CLI: new `glia query`, `glia identity`, `glia watch`; `--no-collapse` on `find`, `blast-radius`,
`trace`, `flows`, `tests-for`, `serves`, `arch`; `rotted_rule` in `gaps` / `overlay propose`
`--category`; SAME_AS in `hubs --category`; `patterns --experimental` gone.

| primitive (pyo3) | returns | fits | packet (commit) |
|---|---|---|---|
| `PyGraph.query(program, outputs=None, limit=None, explain=False, max_rows=None)`, `PyGraph.query_gql(query, limit=None, explain=False, max_rows=None)` | `{language, outputs, results, absence}`: Datalog over the code graph (the predicate prelude merged in: `calls`, `imports`, `depends`, `handles`, `unhandled_route`, `tested`, `unreached`, `cross_repo`, `module_dep` ...) or a GQL `MATCH .. WHERE .. RETURN` read; every row tiered and located; a parse, analysis, budget or evaluation error raises `ValueError` with the rendered diagnostics; a budget stop names `max_rows=<n>` | a single `query` MCP tool for P4 (collapse the six tools' structural questions into one surface); CLI twin `glia query <repo> [<file>] -e <text> [--gql] --json` (exit 0 rows / 1 none / 2 an error, the error text on stderr only) | DB.2a-DB.2c, DB.7a-DB.7c, DB.5 (`940b6137`), DB.6 (`8420aa44`) |
| `PyGraph.identity_classes(tier=None, rule=None, diverged_only=False, limit=None)` | the identity report: counts, per-rule counts, classes with members located, diverged copies with their variants; ValueError on an unknown tier or rule | an `orient` note in a merged session ("these N packages / messages / contract ops are one thing across repos") | DD.8 (`a7da80dc`), DD.15 (`9262a597`) |
| `glia_py.WatchSession(repo, overlay=True)` | section 3 | replaces `_watch_rebuild`'s full generate | DC.7a-DC.7c, DC.9 (`902c5456`) |
| `collapse=` on the answers above | `identity` / `to_identity` / `handler_identity` keys on folded rows | render `also_in`; pass `collapse=False` to see every member | DD.9-DD.14 |

The engine's `memory::release_freed_memory` runs on its own (DE.10, section 2 row 8): no call needed.

## 6. Needs no change (checked)

- **Registry decoding** (`graph.py:21-28`, `server.py:650`): one new category, decoded by name; no node
  kind or cell type.
- **Every call site in section 0:** signatures unchanged, or a new keyword last.
- **The watcher filter** (`watcher.py:24-51`): 0.5.2 writes only inside `default_gmap_dir()` or into
  `.glia/` inputs that should trigger a rebuild; `glia watch` / `WatchSession.persist()` write the same
  layout dir.
- **`init.py:36-45`**: `generate(incremental=True)` + `save_to_default` + `default_gmap_dir` unchanged.
- **Evidence strings:** the wrapper parses no emitter or rule, so the new rules (`super_method`,
  `receiver_state`, `inherited_receiver`, `concrete_override`, `import_binding`, `namespace`,
  `local_type_method`, `python_signal`, `binding`, `declared_name`, the SAME_AS rules) need nothing.
- **DD.3 `DomainTables.identity_rules`** (`92a960fd`, api_signature): a Rust struct field; the wrapper
  builds no profile. **DD.7 `IdentityResolver`** becomes `IdentityResolver<'a>` with `new()` /
  `with_scip()` (`16020321`): Rust only.
- **DD.4 PROJECT ORIGIN `label_source`** (`efa0ac66`): the wrapper reads no PROJECT ORIGIN.
- **DF.22b's `[ts-inherit]` and DF.22a's `[recv]` / `[ts-locals]` changes**: stderr only.

## 7. Re-test

```
# the released wheel (pip install glia-py==0.5.2) or one built at the v0.5.2 tag, in a throwaway venv (never ~/.venvs/glia-leap or the user site)
python3 -m venv /tmp/rg-052 && /tmp/rg-052/bin/pip install /home/ivy/Code/glia/target/wheels/glia_py-*.whl
/tmp/rg-052/bin/python -c "import glia_py as g; print(g.version(), g.build_stamp(), len(g.category_names()))"
#   expect the stamp of the wheel you built and 37 categories

# the wrapper's suites, then the WatchSession port against a scratch copy of a repo
cd /home/ivy/Code/repo-graph && /tmp/rg-052/bin/pip install -e ".[dev]" && /tmp/rg-052/bin/pytest -m "not perf"
/tmp/rg-052/bin/pytest -m e2e

# a session's update equals a clean build: edit a file in a scratch copy of a repo (generate() writes
# under the repo it builds), then
/tmp/rg-052/bin/python - <scratch-copy> <<'PY'
import sys, glia_py as g
r = sys.argv[1]; s = g.WatchSession(r)
u = s.apply(["<edited file>"]); snap = s.snapshot(); fresh = g.generate(r)
print(u["seq"], snap.node_count() == fresh.node_count(), snap.edge_count() == fresh.edge_count())
PY

# glia side: the wheel matches the pinned surface
cd /home/ivy/Code/glia && ~/.venvs/glia-leap/bin/python py/check_api_surface.py
```

The wrapper suite was not run for this handoff (glia's rule: never call the wheel's `generate()` on a
repo from the glia session).

## 8. Done vs pending

- **Landed:** W0-W13, 151 packets (all green but DH.16, a bench fixture recorded `partial`), and the docs
  packets DZ.1 / DZ.2 in W14. The W13 close-out (`f468af11`) measured 5,552 workspace tests passing,
  378 substrate-gap fixtures with 0 blind spots, the coverage matrix at 345 full / 1 partial / 0 none /
  136 unknown / 28 n/a, `[engram-export] check: ok - build + 95 tests passed`, the wheel
  `glia_py-0.5.1-cp311-abi3-manylinux_2_39_x86_64.whl` (stamp `0.5.1+p0c104fe6f8df1704`, api surface OK,
  every pyo3 surface test green, `test_watch` 35 checks and `test_query` 39 included).
- **Landed after this doc was first written:** the tweaks, W15-W26 (DT.1a-DT.13, section 9). The W25
  close-out (`8293cb00`) measured 6,217 workspace tests passing, 414 substrate-gap fixtures with 0 blind
  spots and the matrix at 346 full / 0 partial / 0 none / 136 unknown / 28 n/a.
- **Released 2026-10-18:** the bump of every version field is the release commit (section 0); James
  pushes it, tags `v0.5.2` and publishes glia-py 0.5.2. This handoff is active: repo-graph upgrades now
  (James, 2026-10-18), no longer held for 0.5.3.
- **Open on glia's side, for the wrapper's benefit (0.5.3):** multi-repo watch (Q13, a `--with` option
  for `glia watch`); watch's body-only fast path (Q15); a memory budget for long-lived sessions (0.5.3
  seed section F.3); org-internal package routing (Q19).
- **Checked, no wrapper change:** D0.3-D0.8 (wave 0: empty module slots); DA.1-DA.20 (the
  `glia-rules` crate: `publish = false`, no out-of-repo consumer; its oracle, determinism, budget and
  toy proof tests); DB.2a-DB.2c, DB.7a-DB.7c (the engine rules slot and GQL, reached through
  `query` / `query_gql`); DB.8a / DB.8b (check's reflexion model now runs through `reflexion.dl`: report,
  stdout and exit codes byte-identical; one more `[rules] reflexion relations=15 rows=<n>` line; a check
  with a model costs the rules evaluation, quokka debug derive 12.8 ms -> 188.5-210 ms, whole check
  39.1 -> 215-231 ms); DC.1-DC.6 (build-stage refactors and speed-ups, byte-identical); DC.10a / DC.10b
  (watch parity gates); DD.1 / DD.2 / DD.8 (classes, keys, the identity view); DE.2-DE.6
  (engram-export only); DF.1 / DF.3 / DF.4a / DF.5 / DF.11-DF.13 / DF.15-DF.17 and DG.1-DG.9 / DG.11 /
  DG.13a / DG.13b (additive content, section 4c); DH.16 (fixture data).

## 9. The 0.5.2 tweaks (DT.1a-DT.13, waves W15-W26, 2026-10-17)

After the W14 docs, James ran 0.5.2 against Kina (an Angular + Go + Solidity app) and quokka-stack (an
Angular / Flutter + Go app) and asked for the gaps they showed to be fixed inside 0.5.2
(`dev-notes/tweaks-0.5.2.md`, T1-T13): 57 packets, `5af245f6`..`40332f16` plus this docs packet. Sources
as in the header: each packet's landed commit body (its `Declared breaks` paragraph) and the routed
handoff paragraphs in `dev-notes/leap-052-corrections.json`. Wrapper sites were read at repo-graph HEAD
`0f8ecfa` again (the same 12 modified and 4 untracked paths; nothing at a cited line moved).

**Still no code change.** No pyo3 method the wrapper calls changed its signature or return shape. The
traversal methods' `categories` parameter type moved (DT.9), but the wrapper passes `None`
(`graph.py:114`, `:126`, `:137`). What the wrapper shows changes: fewer `⊘` marks, folded model rows in
`find` / `impact` / `trace`, new nodes and edges, a longer coverage footer, and two `read` cells that now
render oddly (rows 2 and 3, optional fixes).

### 9.1 Breaks that reach the wrapper

| # | packet (commit) | old -> new | wrapper site and action |
|---|---|---|---|
| 1 | DT.1h http_model identity (`44f20d6b`), DT.1k graphql_model identity (`bbe70ea0`) | a new `models` Resolve pass (`[passes] domain=code resolve=14` -> `resolve=17` with DT.5f's gqlgen and DT.10b's evm) writes SAME_AS client model -> server model (rule `http_model[/diverged]`: a TS interface / class or Dart model -> the Go struct of one HTTP exchange) and result model / gqlgen struct -> `message:graphql:<T>` (`graphql_model`), emitter `resolver:models`, DERIVED, walking. **Inside one repo too**: quokka-stack forms 19 http_model classes (8 with an Android member); examples-glia gains the graphql_model class of `StockItem` (admin) and gqlgen's `models_gen::Product` -> `message:graphql:Product @api`. The identity report's `by_rule` gains `http_model`, `graphql_model` (8 -> 10 entries; Rust `same_as::ALL_RULES` `[&str; 9]` -> `[&str; 10]`, `MODEL_RULES` `[&str; 1]` -> `[&str; 2]` across DT.1h / DT.1k); `glia identity --rule` accepts both. | `find` (`graph.py:155`), `impact` (`server.py:437`) and `trace` (`server.py:520`, `:608`, `graph.py:69`) fold a client model and its server struct into one row with `identity.also_in`, and walks cross the class: a Go struct's blast radius now reaches the TS code reading it. Section 0's "only contract-op, contract-route and workspace-package classes" no longer holds. **Optional:** the row 2-4 renders of section 2. |
| 2 | DT.11b GraphQL transport as an HTTP call (`c8673f13`) | each Apollo / urql / graphql-request client mints `endpoint:POST:<path>` whose ENDPOINT_HIT is an HTTP call-site payload ending `"host":..,"via":"graphql"` (`{"method":"POST","path":"/graphql","file":"src/client.ts","line":5,"col":8,"confidence":"strong","raw":"http://localhost:8080/graphql","host":"localhost:8080","via":"graphql"}`), plus HTTP_CALLS to the server's route | **Rendering bug, optional fix.** `_dial_text` (`server.py:724-739`) treats every payload with `via` as a channel client's dial target, so `read` of such an ENDPOINT shows `dials: localhost:8080 (graphql)` instead of the `called by (cross-stack)` caller. Return None from `_dial_text` when the payload has `method` (an HTTP call site). |
| 3 | DT.10c-DT.10k EVM clients (`f5dad689` and later) | new RPC_CALL `evm_call:<scope>.<fn>` and EVENT_HANDLER `evm_event:<scope>.<E>` nodes carry an ENDPOINT_HIT `{"via":"evm","lib":"ethers","args":[..],"abi":[..]}` (no host; `abi_ref` / `abi_from` since DT.10g) | **Rendering, optional.** `_dial_text` renders it `dials: host not named in source (evm)`. Render `via == "evm"` as the library and ABI (`ethers, abi ESCROW_ABI (evm)`), or skip it. |
| 4 | DT.1c declared model fields (`2009dc35`), DT.1l Dart models (`f247e21e`), DT.1j GraphQL types (`a52201dd`) | every TS interface / field-only class, Go struct, Dart `fromJson` / `@JsonSerializable` model and GraphQL SDL type gains SCHEMA_FIELDS `{"extends"?,"fields":[{"name","type","required",..}],"format":"ts\|go\|dart\|graphql","open"?}` (Kina 128 structs + 130 interfaces, quokka-stack 97 + 75); `message:graphql:<T>` MESSAGE_TYPE nodes are new | `read` lists SCHEMA_FIELDS as `fields` (`_CELL_LABEL_OVERRIDES`, `server.py:658`), and `_cell_text`'s dict branch (`:718-719`) prints `fields=[{...}] format=ts`, cut at 400 chars. **Optional:** render `name: type` pairs, `?` when not required. |
| 5 | DT.1e Go wire cells (`d5e6f011`), DT.1f typed (`4dee0a11`), DT.1j / DT.1k GraphQL cells | Go handlers gain MESSAGE_TYPE cells (form `json_response` / `json_bind`, `model` keys from DT.1f); GraphQL root fields `graphql_returns`, operations `graphql_selection`, TS callables issuing a typed GraphQL call `graphql_result` | orient's dense map (`server.py:296`, `:300`) shows a `:msgtype` line per cell and a model-field line per SCHEMA_FIELDS node, so `DENSE_TEXT_MAX_CHARS` (50,000, `:274-276`) truncates a large repo's full map sooner. No change; raise the cap or scope the map if it bites. |
| 6 | DT.1d TS wire shapes (`0685f7a4`), DT.1l Dart (`f247e21e`), DT.4 query suffix (`3a830b3f`), DT.3b WS host (`d405c8e6`) | ENDPOINT_HIT payloads gain trailing `response` / `request` (TS / Dart), `query` (after `alias`) and, on a folded WS client, `host` | `_cell_text` prints the first six fields (`:719`); `_dial_text` now shows the WS host where it said `host not named in source`. No change. |
| 7 | DT.5a-DT.5g dead-symbol precision (`b0856ea5`, `402ca6e6`, `e22c2d21`, `5dd52313`, `787fe464`, `6a8b49c3`, `9d4494af`), DT.10a Solidity procedures (`fb811da7`), DT.1b / DT.1q imports (`f4dd85de`, `e7dfb31d`) | a used owner's framework- and runtime-invoked members and constructors are live (a walk-local hop; the `[live]` line gains `invoked=`); Angular inline / `templateUrl` / host bindings, template receivers and decorator-bound members, Flutter closures / constructions / method refs and widget classes (ROLE COMPONENT, entries), gqlgen resolver methods, TS values passed by reference and getter reads, Solidity external functions are edges or entries; generated code is no `dead_symbol` row. Kina `dead_symbol` 517 -> 52 and quokka-stack 748 -> 124 across the packets (each step measured on its own base; DT.5a alone, the declared break: Kina 517 -> 208, quokka-stack 748 -> 741; the close-out, section 10, then takes them to 32 and 41). DT.5b's walk reads an `.html` beside a same-stem `.ts` (no node or MODULE; the `[parallel] walk .. read <n> files` count grows) and binds it to the component that names it in `templateUrl` | `⊘` (`server.py:981-985`) and the impact note's dead count (`:485`) flip to live for those symbols; `live_only=True` keeps more rows. No change. |
| 8 | DT.11z channel caveats (`71a13fe2`), DT.10h EVM caveats (`2fc07e62`) | `coverage()` rewrites the `*` QUEUE_FLOWS, WS_CONNECTS and GRAPHQL_CALLS notes, extends the universal RPC_CALLS note and verify with the EVM reading and adds one universal `*` EVENT_FLOWS row (contract-event subscriptions); every absence that reads RPC_CALLS or EVENT_FLOWS carries them | `_coverage_note` (`server.py:1008-1028`) prints `recs[:8]` capped at 200 chars: the footer text changes and the new row may enter the eight. No change. |
| 9 | DT.9 traversal category names (`b1ecad68`) | `neighbours` / `bfs` / `predecessors` / `reachable_by` / `shortest_path` take `categories=["CALLS", "imports", 9]` (ids or registry names, mixed, case-insensitive); an unknown name is a `ValueError` naming it; rows still carry ids; `py/api_surface/traversal.txt` `Option<Vec<u32>>` -> `Option<Vec<CategoryArg>>` | **Correction to DT.9's note** ("the wrapper may drop its category_names() id lookup before traversal calls"): the wrapper looks no id up before a traversal call; it passes `None` (`graph.py:114`, `:126`, `:137`), and `CATEGORY_NAMES` (`graph.py:22`) decodes the ids the rows carry, so it stays. A future filtered call can pass names. |
| 10 | DT.6a test-only routes (`5112e840`), DT.6b (`b3537e71`) | HTTP_CALLS into a ROUTE every registration site of which is test code are gone; a product ROUTE no longer carries ORIGIN `test_fixture`; `gaps` withholds test-only routes and `suffix_of` / `suspected_edge` skip them; the prelude's `unhandled_route` excludes them | a client that calls a test-only route loses that hop in `impact` / `trace` (no test-bed pair moved: Kina 6 and examples-glia 1 such routes have no product caller); the wrapper calls no `gaps` / `query`. No change. Rust (additive): `MountedHttpResolver::without_routes`. |

### 9.2 Answers the wrapper does not call (for P4 or a later mode)

The wrapper calls none of these (grep of `repo_graph/` at `0f8ecfa`: 0 hits). Several packets' notes name
a "repo-graph check tool", a "contracts tool" or "the wrapper's result dict": **correction**, no such
wrapper code exists today; the rows apply when P4 adds those modes.

| packet (commit) | old -> new |
|---|---|
| DT.1i model drift (`d8051a4b`), DT.1n GraphQL selection drift (`12a430d5`) | `PyGraph.contract_fields()` / `glia contracts --fields` return three new pairings where they returned none: `http_model` (each client call site's model against the server model of its HTTP exchange, response and request; rules json_field_missing, json_field_optional_absent, json_field_unread, json_field_may_be_absent, json_field_dropped, json_required_missing, json_field_unset, json_type_mismatch, and DT.1n's json_required_may_be_unset as a `required` change), `client_contract` (a client against the OpenAPI op that DOCUMENTS its route: contract_field_undeclared, contract_field_optional_undeclared, contract_field_unread, contract_request_field_undeclared, contract_required_missing, contract_field_unset, contract_type_mismatch) and `graphql_selection` (graphql_field_undefined). Notes `open` / `union` ride on a verdict; a row that compared nothing is `unknown` with `ambiguous_server`, `client_type_unresolved`, `server_type_unresolved`, `op_type_unresolved` or a GraphQL refusal (`conflicting_selection`, `owner_mismatch`, ...). The `[contract-fields]` marker gains `http_model=<n> client_contract=<n> graphql_selection=<n>`. Measured: examples-glia http_model 7, Kina 142, quokka-stack 71 + 32 client_contract (DT.1i); quokka-stack 103 -> 146 rows with Dart models (DT.1l). |
| DT.1p model breaks in the PR gates (`40332f16`), on DT.1o's judge (`86b76fe5`) | `contract_breaks_vs_rev(.., models_min_tier="fact")`: dict keys `{base, schemas, orphaned_clients, breaking, absence}` -> `{base, schemas, models, orphaned_clients, breaking, advisory, absence}`; `breaking` also counts blocking model rows (none by default: the 0.5.2 pairs are derived). `review_vs_rev(.., models_min_tier="fact")`: gains `model_breaks` (after `resolved_violations`), `counts.model_breaks` and, when non-empty, `unanchored`; `blocking` also on a blocking model row; markdown gains the headline suffix ` \| <M> model break(s)[ (<A> advisory)]`, `### Model breaks (blocking)` / `(advisory: ..)` and `### Rules that check nothing`; a rule's caveats print once per section. CLI `--models-min-tier fact\|derived` on both; an unknown tier is a `ValueError` before any build. stderr `[model-breaks] ..`, `[review] caveats ..`. |
| DT.7b rules that check nothing (`f542b49b`), DT.7c loader-rejected stanzas (`6c301ec0`), DT.7a sub-project anchors (`8dbf40f9`) | `PyGraph.check()` -> `check(strict=False)`; it reads each repo root's overlay; the dict gains `unanchored` when a row exists (section `overlay` and loader `rejected` rows since DT.7c); an empty-scope rule leaves `errors` for `unanchored` unless `strict=True`. CLI `glia check --strict`; `## Rules that check nothing`; `- rules:` gains `, checking nothing <n>`; an empty-scope rule exits 0 / 1 by its violations, not 2. A sub-project `[[constraint]]` now anchors on its enclosing PROJECT or a MODULE, so it is checked (Kina's demo rules 1 -> 2, +1 forbid_edge violation of 8 FACT edges): CI exit codes can move. `overlay_try`'s rule `status` gains `checks_nothing` (with `reason` / `fix`, verdict review) where an empty scope read `error`. |
| DT.8a check caveats once (`f0dd035a`) | `glia check` markdown: a rule's coverage caveats print once, under its heading (Kina 24 `⚠` lines -> 3); --json and `PyGraph.check()` unchanged; new stderr `[check] caveats rules=<r> lines=<l> folded=<f>`. |
| DT.8b located GQL rows (`75bf3def`) | `PyGraph.query_gql` rows that return properties only carry `file` / `line` (the first property's node) where they had none; aggregate rows stay unlocated. Rust: `glia_rules::gql::Compiled` gains `pub anchor: Option<String>`. |
| DT.12b cell hints (`e3699f97`) | `PyGraph.set_cell(.., dims=None, hint=None)` / `glia_py.write_cell(.., dims=None, hint=None)`: a caller's v1 identity hint, validated (`ValueError` on a non-v1, unregistered-kind or kind-contradicting hint); the outcome dict gains `node_hint` and `hint_differs` on every write, and `target` reads `hint_differs` when a fresh layout's binding differs. `glia cell set --hint`. |
| DT.3c WS-served routes (`18af8bb5`), DT.11c implied GraphQL transports (`02f78792`) | `gaps()`: a ROUTE a WebSocket client connects through is no `unpaired_route` (examples-glia 3 -> 2, quokka-stack 10 -> 9); an unpaired `"via":"graphql"` transport whose project's operations pair a resolver on a server with no route at its segment is no `unpaired_endpoint`, and any other unpaired transport's detail starts `graphql transport; ` (with `route_at_server=<qname> (<repo>)` when the server holds such a route); overlay-loop gap ids and counts move with them. Rust: `glia_graph::WebSocketStackResolver::served_routes`. |
| DT.5d liveness (`5dd52313`) | `gaps()` `dead_symbol` loses a used owner's invoked members and constructors and every ORIGIN `generated` / `generated_proto` row (Kina 517 -> 427 and quokka-stack 748 -> 512 on its base); `overlay_propose`'s dead_symbol candidates drop with it. |

### 9.3 Graph content (no wrapper code parses it)

- **Re-keyed (qname, so NodeId):** DT.4 (`3a830b3f`): a trailing query interpolation leaves the client
  path, `endpoint:GET:/api/orders${…}` -> `endpoint:GET:/api/orders` (examples-glia), Kina
  `endpoint:GET:${…}/smr${…}` -> `endpoint:GET:${…}/smr` and `endpoint:GET:/admin/smr${…}` ->
  `endpoint:GET:/admin/smr`, newly paired. DT.3a (`8429d100`) / DT.3b (`d405c8e6`): WS clients leave
  the generic `ws_client:ws`, `ws_client:ws @web` -> `ws_client:/live/orders @web` (examples-glia),
  `ws_client:ws @quokka_web` -> `ws_client:/api/protected/chat/ws @quokka_web` (Weak, builder-read), a
  config base folds (`ws_client:/prices` -> `ws_client:/rt/prices`). DT.2c (`1986a9cc`): NATS producer
  subjects carry `*` tokens (`queue_producer:orders.` -> `queue_producer:orders.*.placed`,
  `queue_producer:shop.orders.%s.placed` -> `queue_producer:shop.orders.*.placed`); a dynamic consumer
  subject is `queue_consumer:unresolved:nats`. Datalog / GQL match a `*` literally. DT.11a
  (`717cfbdd`): an anonymous GraphQL document's op is `graphql_op:<first root field>` (new), and every
  GRAPHQL_OPERATION read from a document gains the document as a CODE text cell (delta / review see an
  edited document as a modified op).
- **Added nodes:** DT.2a (`1a7acd56`) `unresolved:<family>` queue tags in mixed-row files, anchored at
  every unexplained site, in every broker family; DT.2b (`ec7c885c`) nats.go / JetStream queue nodes on
  any receiver (examples-glia `queue_consumer:shop.shipments.* @api`, quokka
  `queue_producer:unresolved:nats @turps`); DT.1d awaited generic axios / HttpClient ENDPOINTs; DT.5e
  ENDPOINTs for Dio calls inside closures (quokka `POST /api/auth/refresh`); DT.11b transport
  ENDPOINTs; DT.1j `message:graphql:<T>` MESSAGE_TYPEs; DT.10a RPC_PROCEDURE `evm:<Contract>.<fn>`
  (Kina +38); DT.10c-DT.10k RPC_CALL / EVENT_HANDLER EVM clients (ethers DT.10c `f5dad689`, call forms
  DT.10i `1d7b02d9`, hardhat / TypeChain / artifacts DT.10d `347d9087`, viem / wagmi / web3.js DT.10j
  `79a4ca79`, go-ethereum DT.10e `53593205`, wrappers DT.10f `6606dce9`, events / abigen DT.10k
  `62533102`), and DT.10g (`e2fe3ca6`): an ABI declared in another file (an exported TS const imported
  by relative path, a Go string const of another file of the package) fills the client's evm cell
  (`abi_ref` / `abi_from`), so the call pairs by `abi` (DERIVED) and a contradicted `name_hint` pair is
  removed.
- **Removed:** DT.10b (`b53fbd67`) EventBusResolver no longer pairs a Solidity event with an in-process
  EVENT_HANDLER by name (0 such edges on every test bed); DT.11b spurious GRAPHQL_RESOLVERs read from a
  root field's multi-line argument list or description; DT.2b the RabbitMQ / SNS reading of a
  `.Publish(` a NATS row read, in a file importing both; DT.3b a WS_CONNECTS that paired a tail-only
  path through another route; DT.11a name-only GraphQL pairs whose document selects other fields
  (`Products -> products`); DT.6a HTTP_CALLS into test-only routes; DT.1q a name-only ref that bound a
  different same-named node than the barrel's (replaced). Between EVM packets (no 0.5.1 consumer saw
  either): **undeclared, DT.10j**, in an ethers file a member that a TS object-literal / parseAbi /
  human-readable ABI does not list is no longer an RPC_CALL (counted `not_in_abi=`), where DT.10c-era
  builds minted it against an unknown ABI; DT.10k re-keys an abigen call site
  `evm_call:recv:contract.<m>` (DT.10e) -> `evm_call:abi:<X>MetaData.<m>`.
- **Added edges and evidence:** IMPORTS rules `dir_index` (DT.1b, Kina +82) and `reexport` (DT.1q,
  quokka +35; 49 INJECTS re-ruled `global_unique` -> `import_binding`, heuristic -> fact in `why`);
  handler -USES-> STRUCT `graph:go_wire` (DT.1f, Kina USES 4 -> 54); TS USES `value_ref` and CALLS
  `accessor_read` / `accessor_write` (DT.5g, Kina +1026 USES, +91 CALLS); Angular CLASS -> METHOD
  CALLS / USES `extractor:angular_template` (DT.5a Kina +342, DT.5b quokka +245) and class-scope
  receiver CALLS (DT.5c, Kina +68); Dart CALLS / USES `method_ref` and ROLE COMPONENT (DT.5e, quokka
  +86 CALLS, +24 USES); gqlgen HANDLED_BY `resolver:gqlgen` (DT.5f: trace from a GraphQL op continues
  into Go, examples-glia dead_symbol 25 -> 21); GRAPHQL_CALLS rule `root_field` (DT.11a: examples-glia
  `StockList -> products` added); QUEUE_FLOWS rule `pattern` (Weak) for `*` producers (DT.2c); a named
  queue argument (`subject="x"`, `subject: x`) now reads its value (**undeclared, DT.2c**: a literal is
  as before; an identifier becomes the LA.4 expression where nothing was read); RPC_CALLS / EVENT_FLOWS
  `resolver:evm` (`contract` / `abi` DERIVED, `abi_hint` / `name_hint` HEURISTIC and Weak, so a check
  violation through one is advisory); SAME_AS `http_model` / `graphql_model` (row 1). PPR, community,
  hub and pack rankings move with the new IMPORTS, USES and CALLS.

### 9.4 Stderr (the server relays and parses none)

New: `[model-schemas]`, `[ts-wire]`, `[go-wire]`, `[dart-wire]`, `[models] client_wires / pairs /
classes / graphql results / graphql pairs`, `[evidence-rules] resolver=models`, `[contract-fields]
.. http_model= client_contract= graphql_selection=`, `[model-breaks]`, `[review] caveats`, `[imports]
dir-index`, `[imports] reexport`, `[queues] tag`, `[queues] go-nats`, `[queues] subject-fold`,
`[queues] resolver placeholder`, `[ws] client urls`, `[ws-base]`, `[gaps] ws-served routes`,
`[ts-endpoints] query suffixes`, `[http] test routes excluded from route index`, `[gaps] unpaired_route
rows withheld`, `[angular-template] inline` (with ` no_class=`) / `external`, `[recv] class-scope
receivers`, `[dead-framework]`, `[dart-flutter]`, `[gqlgen]`, `[ts-value-refs]`, `[check] declared not
checked`, `[check] overlay rejected`, `[check] caveats`, `[gql] anchor`, `[sol-abi]`, `[evm-link]`,
`[eventbus-evm]`, `[evm-client] lang=ts|go`, `[evm-wrappers]`, `[evm-abi-join]`, `[graphql-sdl] code
types`, `[graphql-root-fields]`, `[graphql-transport]`, `[gaps] graphql transports`. Changed:
`[passes] domain=code resolve=17`; `[live] .. invoked=`; `[declared] .. anchor_enclosing=`; `[check]
rules= .. unanchored=`; `[overlay] try-rules (.. checks_nothing=)`; `[graphql-sdl] .. types=`;
`[dart-calls] .. closures= creations= method_refs=`; `[http] routes=`, `[http-qname] routes=`,
`[http-owner] index routes=` drop by the test routes; `[cells] write .. differs=`; `[channel-owner]`
and `[marker-anchor]` counts grow. The CLAUDE.md marker list has every format.

### 9.5 Every DT packet, for the merge

Declared no break (additive, no answer moves): DT.1a wire vocabulary (`5af245f6`), DT.1g client_wires
(`eddf53b4`), DT.1m wire_pairs (`62fa15c4`), DT.1o the model-breaks engine (`86b76fe5`), DT.13 these
docs. Everything else is in 9.1-9.4: DT.1b-DT.1f, DT.1h-DT.1l, DT.1n, DT.1p, DT.1q, DT.2a-DT.2c,
DT.3a-DT.3c, DT.4, DT.5a-DT.5g, DT.6a, DT.6b, DT.7a-DT.7c, DT.8a, DT.8b, DT.9, DT.10a-DT.10k, DT.11a-DT.11c,
DT.11z, DT.12a (engram-export only: `<out>.hints.jsonl`), DT.12b. PARSER_STAMP moved with most of
them, so the first build after the upgrade reparses everything; FORMAT_VERSION stays 3 and no registry
id was allocated.

## 10. The close-out: dead_symbol false positives (DT.5h-DT.5l, waves W27-W30, 2026-10-17)

James, 2026-10-17 (`dev-notes/tweaks-0.5.2.md` ruling 7): *"lets fix the false positives that counts
as closeout i think"*. The re-demo's remaining `dead_symbol` rows were audited by hand: Kina `8ac238c`
52 and quokka-stack `a77d4cb` 124, 176 rows, 103 false and 73 truly dead (the audit's list has 74
entries; Kina's names `OnboardingStore::reset` twice). Each false mechanism became one packet, and each
packet's precision gate kept every truly dead row. Measured by DT.14 at glia HEAD `1212a3be` (debug CLI,
stamp `0.5.1+p395be331c3dfb5b8`, `glia gaps <copy> --json --top-k 5000 --category dead_symbol` on
git-archive copies): **Kina 52 -> 32, quokka-stack 124 -> 41, examples-glia `fbfb6c0` 11 -> 11**, and the
rows left on Kina and quokka-stack are exactly the audit's 32 and 41 truly dead qnames (none missing,
none extra). The released 0.5.2 carries this section.
Sources as in the header: each packet's landed commit body and its routed handoff paragraph in
`dev-notes/leap-052-corrections.json`. Wrapper sites read at repo-graph HEAD `0f8ecfa` again (the same 12
modified and 4 untracked paths; nothing at a cited line moved).

**Still no code change.** No pyo3 method changed its signature or return shape (DT.5l's
`node_record` reads `EntryRule::is_entry_at` inside the engine). What the wrapper shows changes: fewer
`⊘`, more callers in `impact` / `trace`, more entry flows, and a few new role labels.

### 10.1 Breaks that reach the wrapper

| # | packet (commit) | old -> new | wrapper site and action |
|---|---|---|---|
| 1 | DT.5l runtime-invoked entries and members (`b7f4dace`) | entries: a Go `func init()` (the entry table's new `FUNCTION init` row, limited to `.go` files: a TS or Python `init` stays an ordinary name), a Swift `@main` / `@UIApplicationMain` / `@NSApplicationMain` type and a Kotlin FlutterActivity / FlutterFragmentActivity / FlutterFragment / FlutterApplication subclass under an io.flutter import (both new ROLE COMPONENT cells); a Python MODULE with an `if __name__ == "__main__":` guard gains one ENTRYPOINT cell `{"decl":"<file>:<1-based row>","source":"main_guard"}` and is a declared entry. Live members of a live owner: Go methods the runtime calls by signature (`Error` / `String` `()(string)`, `Unwrap` beside an `Error`, the JSON / text / BSON marshalers, `Scan`, `Value`, `ServeHTTP`, `Len` / `Less` / `Swap` together), an `@main` type's app-delegate callbacks and SwiftUI `body`, and members a library base calls (Transloco loaders and handlers, Angular ErrorHandler / Resolve / TitleStrategy / RouteReuseStrategy, dio interceptors). Kina 52 -> 48, quokka-stack 124 -> 116 on its own base | `nodes_json` (`graph.py:58`): `entry` turns true for the Go `init`, `@main` and Flutter-activity nodes (a script MODULE stays `entry: false`, its entry is a declared one) and `live` true for all of them and what they reach, so `_classify_tier` (`server.py:911-924`) tiers them ENTRY (`_effective_kind`, `:898`, now reads `component` for the Swift and Kotlin classes), `_elive` (`:980-985`) drops their `⊘`, and the impact note's dead count (`:474`, `:483-486`) falls. `entry_flows` (`graph.py:64-71`, `flows` `:73-76`) gains flows rooted at Go `init`, `@main` types and Flutter activities (not at a script MODULE), so refresh's entry-point count (`server.py:862`) and trace's "Available entry points" (`:530-534`) grow. **Optional render:** `read` lists a script MODULE's ENTRYPOINT cell under the label "declared entry point" (`_CELL_LABEL_OVERRIDES`, `:663`; `_cell_text`'s ENTRYPOINT branch, `:703`) as `tool.py:12 main_guard`; it is read from the source, not declared, so label it "entry point" when `source == "main_guard"`. |
| 2 | DT.5i Riverpod receivers and the Dio interceptor ROLE (`bf53a65e`) | a class extending dio's Interceptor / QueuedInterceptor / InterceptorsWrapper / QueuedInterceptorsWrapper in a file importing `package:dio/` gains ROLE SERVICE (services extractor rule `dio_interceptor`, HEURISTIC; quokka-stack `AuthInterceptor`) | `nodes_json` `roles` gains `service`: `_record_kind` (`:886`) / `_effective_kind` label it `service` (was `class`); its tier stays HANDLER (`_HANDLER_KINDS`). No change. |
| 3 | DT.5h (`332e66e5`), DT.5i, DT.5j (`784d8553`), DT.5k (`aa30014b`) new edges | Dart, Go and TS graphs gain CALLS / USES / INJECTS / HANDLED_BY / TESTS edges (10.3) and lose no edge; no node is added on the measured repos and no qname moves | `impact` (`server.py:437`) and `trace` (`:520`, `:608`, `graph.py:69`) reach the new callers and dependents; `live_only=True` keeps more rows; the `⊘` marks drop (dead_symbol per packet: quokka-stack 124 -> 86 DT.5h, 78 -> 45 DT.5i, 45 -> 43 DT.5j, 43 -> 41 DT.5k; Kina 48 -> 38 DT.5j, 38 -> 32 DT.5k). No change. |

### 10.2 Answers the wrapper does not call (for P4 or a later mode)

The wrapper calls none of these (grep of `repo_graph/` at `0f8ecfa`: 0 hits).

| packet (commit) | old -> new |
|---|---|
| all five | `gaps()` `dead_symbol` loses the rows above, and `overlay_propose`'s dead_symbol candidates and `overlay_delta`'s counts drop with them; `PyGraph.query` / `query_gql`'s prelude `live` / `unreached` move; `communities` / `splits` gain entry flags on Go `init`, `@main` types and Flutter activities, and `entry_flows` / `duplicate_flows` gain their flows (DT.5l). |
| DT.5j (`784d8553`) | EVIDENCE moves on Go calls through a package-qualified field: emitter / rule `graph:calls` `receiver_type` -> `graph:go_packages` `receiver_field_chain`, same target (Kina 305 pairs, examples-glia 8): `why`, `check` / `review` violation tables and `query`'s edge_cell rows show the new emitter. New USES rule `composite_literal` (a fn / METHOD / package var -> the STRUCT a literal builds; Kina 492 edges, quokka-stack 103, examples-glia 14), so a `forbid_edge` over USES can gain rows: Kina's own handlers -> repository rule goes 30 -> 37 (8 CALLS rows now name graph:go_packages, 7 new USES composite_literal rows for handlers building repository filter / record structs; exit 1 before and after). |
| DT.5k (`aa30014b`) | `glia coverage`'s TypeScript CALLS row and analyze's unresolved counts move (`unresolved_calls` lose the bound sites; `unresolved_refs` gain the inline-inject INJECTS refs whose target is third-party: Kina 15, quokka-stack 3). |

### 10.3 Graph content (no wrapper code parses it)

- **DT.5h Dart names and member reads (`332e66e5`).** A getter / setter named in a body is CALLS
  `accessor_read` / `accessor_write` (parser:dart), a METHOD / FUNCTION named in any value position
  (conditionals, `??`, initialisers, interpolations, collection elements, returns) USES `method_ref`;
  a member read no call follows (`Env.apiBaseUrl`, `.map(Friend.fromJson)`) is CALLS `accessor_read`,
  USES `tear_off` or USES of the CLASS `static_member`, emitter `graph:reads`; `T.new` and a
  constructor tear-off CALLS the class; a class field's initialiser is its CLASS's CALLS / USES (a
  self-loop when a class constructs itself in a static field). quokka-stack +58 unique edges (USES 40,
  CALLS 18), 0 removed; Kina and examples-glia byte-identical. `RepoGraph.properties` now holds Dart
  getters / setters. A Dio / http call in a field initialiser would mint its ENDPOINT (none measured).
- **DT.5i Riverpod (`bf53a65e`).** CALLS `graph:dart` `provider_receiver` for `ref.read(p).m()`,
  `ref.read(p.notifier).m()` and a local holding the read, bound only to a METHOD of the type the
  provider declares; `graph:reads` `accessor_read` on provider reads; `graph:calls` `receiver_type` on a
  StateNotifier / Notifier / ValueNotifier subclass's `state.m()`. quokka-stack +64 unique CALLS, 0
  removed, `[live] reached=` 1709 -> 1867 of 3455; ROLE SERVICE on Dio interceptors (10.1 row 2).
- **DT.5j Go (`784d8553`).** CALLS through range-variable elements, package-qualified fields,
  func-value locals, agreeing alternatives and composite-literal receivers; USES `method_value` /
  `func_value` (a func or method passed, assigned, returned or initialising a package var) and
  `composite_literal`, emitter `graph:go_packages`; HANDLED_BY `package_function` (a `pkg.F` handler in
  another file of the imported package); TESTS follow the new CALLS. Kina +524 pairs (CALLS 29, value
  USES 4, HANDLED_BY 1, TESTS 1, composite_literal 489 pairs / 492 edges), quokka-stack +4 + 103
  composite_literal, examples-glia 8 evidence moves + 14 composite_literal; 0 removed anywhere. Go
  STRUCTs now carry incoming USES from their literals.
- **DT.5k TypeScript (`aa30014b`).** CALLS `receiver_type` through an Angular signal query field or an
  inline `inject(T)`, `receiver_return` through a call-result local, `receiver_accessor_read` /
  `receiver_accessor_write` for a getter / setter on another typed object; INJECTS from each scope that
  runs an inline `inject(T)` (functional guards and interceptors, InjectionToken factories,
  call-initialised fields: `graph:refs` `import_binding`, or parser rule `inject_call` in-file); USES
  `static_member` for `T.X`; USES `value_ref` for an `inject`'s later argument. Kina +51 triples / +127
  edge rows (CALLS 36, INJECTS 14, USES 1), quokka-stack +18 (CALLS 14, INJECTS 4), examples-glia 0;
  nothing removed, no node added, no existing edge's cells changed.
- **DT.5l (`b7f4dace`).** A `__main__` guard's calls are MODULE -> callee CALLS; a bare Python call
  binds the caller's nested def first (CALLS rule `nested_def`), so an edge that bound a shadowed
  module-level function moves to the nested def (edge_removal: none on Kina / quokka-stack, one in the
  new fixture); a guard's HTTP client call can mint an ENDPOINT (none measured); the ROLE and
  ENTRYPOINT cells of 10.1 row 1.

### 10.4 Stderr (the server relays and parses none)

New: `[reads] member reads ..` (DT.5h), `[dart-scope] provider receivers bound=`, `[dart-riverpod]
providers= locals= holders= file=`, `[services] dart classified= rules=dio_interceptor:` (DT.5i),
`[go-receivers] typed elem= qualified_field= func_value= alternatives= conversion=`, `[go-values]
uses= (method= func= composite_literal=) dropped= refs= pkg_handlers=` (DT.5j), `[ts-receivers] ..`,
`[recv] ts receivers bound: ..`, `[resolve] static member uses bound: <n>` (DT.5k), `[invoked] rows=
.. sig_rejected=`, `[py-main] guard module= calls= file=`, `[py-nested] nested-def calls bound=
file=`, `[swift-app] entry types= file=` (DT.5l). Changed: `[dart-calls]` gains `accessor_refs=
tear_offs= field_inits= member_reads= elements=` and fires on more files (DT.5h); `[ts-locals]` gains
`call=` (DT.5k); `[live]` and `[dead-framework]` counts; `[kotlin/retrofit] components=` counts
Flutter activities (DT.5l); `[go-receivers] bound=`, `[recv]`, `[iface]`, `[go-embeds] .. fields=`
counts (DT.5j); `[evidence-graph]` extra_hook counts on Dart graphs (DT.5i). CLAUDE.md's marker list
has every format.

### 10.5 Every close-out packet, for the merge

DT.5h `332e66e5`, DT.5l `b7f4dace` (W27), DT.5i `bf53a65e` (W28), DT.5j `784d8553` (W29), DT.5k
`aa30014b` (W30): each declared a graph-content break (above) and moved PARSER_STAMP, so the first
build after the upgrade reparses everything. DT.14 (W31) is these docs: no break. No registry id, no
FORMAT_VERSION change, no Cargo.lock move.
