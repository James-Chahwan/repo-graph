# repo-graph handoff - glia 0.5.1 (the catch-up leap, 2026-10-01)

The fourth glia -> repo-graph handoff, after `repo-graph-handoff-0.5.0.md`. Read it in the repo-graph
session and act on repo-graph only. 0.5.1 is the "catch-up leap": 198 packets in
`dev-notes/leap-051-packets.json` (plan: `dev-notes/next-leap-0.5.1.md`), landed on glia's local `main`
since v0.5.0 (`2170ff8`): 155 in waves W0-W11, then the 43-packet finishing batch (groups CH-CL, the
leap doc's section 7.4, James 2026-10-01) in W12-W19. Breaks were allowed when a packet declared them.
The release keeps the name 0.5.1, so **consumers pin it exactly**.

Sources, in order of authority:
- the landed code at glia HEAD `dbd8d2a` (the W18 close-out; W19 is the docs packet CZ.3, which wrote
  this revision and touches docs only) and the pyo3 / CLI surface snapshots, diffed
  `2170ff8..HEAD -- py/api_surface/ cli/surface/` (section 4 is that diff; the finishing batch adds
  `py/api_surface/overlay_loop.txt` and changes no `cli/surface/` file);
- each packet's own `breaking` report and commit body (W0-W18, plus the CB.23 re-run whose result is
  the one that landed). Where an agent's report differs from the spec, the report wins;
- the specs' `breaking` blocks in `dev-notes/leap-051-packets.json`.

Every wrapper `file:line` below was read at repo-graph HEAD `640d8c9` (read-only). Short names:
`server.py`, `graph.py`, `init.py` and `watcher.py` live in `repo_graph/`, `githook.py` in
`repo_graph/installer/`. Other paths are relative to the repo root. Packet ids are glossed in words; the
commit after each id is the glia commit that landed it.

The wrapper already did the whole 0.5.0 port (`glia_py`, `find`, the `_rows` envelope, the watcher's
write-event filter and layout-prefix skip, `entry_kinds()`, registry cell labels, `roles`, 1-based
`_eloc`, MCP SDK 2.x). This handoff assumes that state.

---

## 0. TL;DR

**The wrapper runs on 0.5.1 without an API change.** No pyo3 function it calls changed its signature
or its return shape (the finishing batch included): the surface diff touches none of `generate`, `load_from_gmap`, `save_to_default`,
`default_gmap_dir`, `nodes_json`, `node_cells`, `find`, `resolve`, `blast_radius`,
`cross_stack_trace`, `entry_flows`, `governing_docs`, `coverage`, `activate`, `dense_text*`, `bfs`,
`predecessors`, `shortest_path`, `kind_names`, `category_names`, `cell_type_names` or `entry_kinds`. No
registry id was allocated (node kinds stay 1-49, edge categories 1-36, cell types 1-25).

What repo-graph has to do:
1. **Pin exactly: `glia-py==0.5.1`** (`pyproject.toml:31`). The wrapper's own packaging test rejects an
   exact pin as "uncapped" (`tests/test_packaging.py:117`), so that predicate changes in the same edit
   (section 1).
2. **Relabel `ENDPOINT_HIT` in `read`** (`server.py:627`). On WS / gRPC / GraphQL / tRPC client nodes
   that cell now records the host the client dials, and `read` prints it under
   "called by (cross-stack)", which is wrong for those kinds (section 2, row 3).
3. **Keep every writer of `.glia/graph` on one glia version.** The `.gmap` format moved 2 -> 3. The
   wrapper's `load_from_gmap` rebuilds a 0.5.0 layout once, on its own, but two writers on different
   versions rewrite each other's layout on every commit: glia's own `install-hooks` (`glia build .`, the
   CLI on PATH) and the wrapper's pre-commit hook (`githook.py:25-26`, which runs
   `uvx --from mcp-repo-graph repo-graph-init --graph-only` and so gets whatever glia-py the published
   wrapper resolves). The exact pin fixes the second; tell users to reinstall the CLI from the tag for the
   first (section 2, row 1).

**Note on timing.** The wrapper on PyPI today pins `glia-py>=0.5.0,<0.6`, so fresh installs pick up
glia-py 0.5.1 the moment it is published, before repo-graph releases. That is safe: nothing the wrapper
calls changed shape. Only the `read` label in item 2 is off until the repo-graph release.

Everything else is graph content: mounted Go routes gain their prefix, quokka's client endpoints gain
`/api`, `<unresolved>` endpoints get real paths, Go implementors change, many more Go / Swift / C++ /
Dart / TS calls resolve, and so on. The wrapper parses none of those qnames, so no code changes
(section 3). Two footers that `read` / `orient` print change content (section 2, rows 12-13). Section 4
lists the new primitives worth an MCP mode, the overlay loop now among them (`overlay_propose` /
`overlay_try` / `overlay_accept`).

Bump order. Nothing is pushed before James says go.
1. **glia (James):** bump `[workspace.package].version` in `Cargo.toml` and `version` in
   `py/pyproject.toml` to 0.5.1 **together** (both read 0.5.0 at HEAD), tag `v0.5.1`, and let
   `wheels-py.yml` publish `glia-py` 0.5.1.
2. **repo-graph:** pin `glia-py==0.5.1`, run section 6 against a local wheel, then release after
   glia-py 0.5.1 is on PyPI.

A wheel built before the bump reports `version() == "0.5.0"`. Tell builds apart with
`glia_py.build_stamp()`: the W18 close-out wheel reports `0.5.0+pa0fc26c918dfcc7c`, and the released
wheel will read `0.5.1+p<hash>`.

## 1. The pin

| file:line | now | change to |
|---|---|---|
| `pyproject.toml:31` | `"glia-py>=0.5.0,<0.6",  # engine API is versioned with the graph format` | `"glia-py==0.5.1",  # glia pins consumers exactly per release (0.5.1 breaks the graph contents)` |
| `tests/test_packaging.py:111-120` `test_every_dependency_caps_its_major` | `uncapped = [d for d in deps if "<" not in d]` | `uncapped = [d for d in deps if "<" not in d and "==" not in d]` (an exact pin is capped), and say so in the docstring |
| `CLAUDE.md:24` | `mcp[cli]>=1.0.0,<2` ... `glia-py>=0.5.0` | the current deps: `mcp[cli]>=2,<3`, `glia-py==0.5.1` |
| `CLAUDE.md:75` | "consumes the published `glia-py` wheel (`>=0.5.0`)" | `==0.5.1` |
| `README.md:59` | "The 0.5.0 engine extracts ... 2,939 nodes and 5,129 edges" | re-measure, or date the figure |
| `.github/workflows/install-matrix.yml:46` | advisory `unpinned-upstream` job drags glia-py to its newest release | no change: it is the early warning for the next glia release, which is the point |

`test_mcp_sdk_floor_is_2` (`tests/test_packaging.py:99-108`) is unaffected: it reads only the `mcp`
entry.

## 2. Breaks that reach the wrapper

Every row names the glia packet and commit, what changed (old -> new), and the wrapper site. Row 3 asks
for a code edit and row 1 for a user-facing upgrade note; the others are listed so the reviewer knows
they were checked.

| # | packet (commit) | old -> new | wrapper site and action |
|---|---|---|---|
| 1 | CD.7b EVIDENCE strings interned in a per-file table (`4fdf434`), CD.7c CODE cells stored as spans into the source (`5611813`), CD.7a parse cache lz4-framed (`7838b32`) | `.gmap` `FORMAT_VERSION` 2 -> 3 (`MANIFEST_VERSION` stays 2). A 0.5.0 layout reports "old format v2 (this build reads v3)"; at the default dir the build-stamp check names it first, so the first load prints `[gmap] rebuilt <dir> (written by another glia build (<0.5.0 stamp>))` and writes a v3 layout. A 0.5.0 reader reports FutureFormat on a v3 layout. `parse_cache.bin` becomes a `GLIAPCZ1` lz4 frame; a 0.5.0 sidecar is discarded once with the unchanged `[incremental] cache stamp mismatch (disk=... build=...)` line. On glia's own v0.5.0 tree the layout shrinks 37.6 MB -> 16.6 MB and `parse_cache.bin` 38.1 MB -> 10.9 MB. | `server.py:159` needs nothing: `load_from_gmap(dir, REPO_PATH)` rebuilds once (one slow first load per repo). `githook.py:27` (`git add -f .glia/graph`) recommits the v3 layout once. **Mixed versions:** a layout written by one glia build and loaded by another is rebuilt ("written by another glia build"), so a repo whose hooks run a 0.5.0 `glia build` (or a `uvx` env that still resolves glia-py 0.5.0) while the MCP server runs 0.5.1 rebuilds on every load. Tell users to reinstall the CLI from the tag (`cargo install --path cli --locked` in a glia checkout at `v0.5.1`) together with the wheel. |
| 2 | every packet that edits a hashed source, first C0.7 the single 0.5.1 dependency commit (`457eba5`) | PARSER_STAMP / BUILD_STAMP move, so every parse cache and layout rebuilds once after the upgrade | none; the first `refresh` or load is a full reparse |
| 3 | CB.21 WS / gRPC clients record their dial host (`016775d`), CB.24 GraphQL / tRPC client base URLs (`99502f9`), CG.4a external call sites marked (`b9a5066`) | `ENDPOINT_HIT` (cell 6) had one payload, the HTTP call site `{method,path,file,line,col,confidence[,raw][,host]}` on ENDPOINT nodes. It now has three: that one (plus a trailing `"external":true` on a call site whose literal host is public and unconfigured), `{"via":"ws"\|"grpc"[,"host":"h[:port]"]}` on every WS_CLIENT / GRPC_CLIENT site, and `{"via":"graphql"\|"rpc","hosts":[..]}` on GRAPHQL_OPERATION / RPC_CALL nodes whose project builds a client with a literal URL. The last two carry no `file` / `path`. | `server.py:627` labels every `ENDPOINT_HIT` "called by (cross-stack)", and `_cell_text` (`server.py:687-688`) prints the first six `k=v` pairs. On a client node that renders `called by (cross-stack): via=ws host=chat:8080`, which names the dial target, not a caller. **Change:** in `_cell_text` (or `_node_context`), render a payload that has `via` as `dials: <host or hosts>` (for example `dials: chat:8080 (ws)`), and keep the old label for HTTP sites. `external` sits after the first six fields, so the HTTP render is unchanged. The finishing batch's keys sit there too: `wrapper` (CH.3a), `wrapper_of` (CH.3b), `folded_from` / `prefix` / `prefix_from` (CH.5b, CH.5c), all after `confidence`; a prefixed site's `path` is rewritten in place (`path=/api/protected/friends`), which is the path the endpoint pairs on. |
| 4 | CC.12b patterns out of experimental (`a2b834a`), CA.5b patterns judge sighted handlers only (`c6f5d9b`) | `PyGraph.patterns_experimental` / `patterns_vs_rev_experimental` -> `PyGraph.patterns(min_support=5, min_share=75, scope=None, group_by="service")` / `patterns_vs_rev(...)`. The old names stay as aliases that raise a `DeprecationWarning` and are **removed in 0.5.2**. The report drops its `experimental` key and gains `blind` / `sighted` / `package`. | the wrapper calls neither (grep: 0 hits); a future caller uses the new names |
| 5 | CC.9a tests-for ranked by failure and co-change (`160ca1e`), CC.9b a rolling window of test runs (`f11f7d7`) | `tests_for` / `tests_for_diff` / `tests_for_rev` gain `limit=None, signals=True`, rows gain `signals`, `cochange_permille`, `fails`, `window`, the answer gains `omitted`. `tests_ingest` gains `window=10, reset=False`, and a re-ingest now accumulates runs (`window=1` is 0.5.0's replace). FAIL cell (9) entries: one per test over the window, id `<classname>::<name>` (was `<run>:<classname>::<name>`), new keys `fails`, `window`, `latest_seq`, `last_failed_seq`. `.glia/test-snapshot/` goes to v2; a 0.5.0 reader writes no FAIL cells from it. | `_cell_text` renders FAIL from `message` / `role` (`server.py:674-683`); both keys are still there, so `read` is unchanged. The wrapper calls neither function. |
| 6 | CC.3 check tiers each edge the way `why` does (`4927e25`), CA.3b Go implicit IMPLEMENTS checked by signature (`c8f2257`), CE.1e SCIP-confirmed edges (`b02725a`) | `why` / `check` report `derived` (not `fact`) for a graph-stage edge below Strong confidence, with note `inferred binding (<rule>, <confidence> confidence)`; Go method-level IMPLEMENTS are now Medium, so they read `derived`; Go type-level IMPLEMENTS carry EVIDENCE rule `method_signature` (was `method_set`) when every signature was compared; a SCIP-confirmed edge reads `fact` with note `confirmed by a SCIP index (<tool>) at <file>:<line>; first emitted by ...`. The `glia check` table gains a `tier` column. | the wrapper calls neither `why` nor `check` (grep: 0 hits) |
| 7 | CD.3b gaps category `suspected_edge` (`dfadd51`), CE.3a stable gap ids and an overlay verdict (`1b93952`) | `gaps()` rows gain `id` (`gap:<16 hex>`, first key) and, on `suspected_edge` rows, `draft` (a paste-ready `[[edge]]` stanza); counts gain `suspected_edge`. `overlay_delta` gains `without`, `with`, `nodes_added_by_kind` and `verdict` (`keep` / `review` / `drop`). | the wrapper calls neither; a future overlay tool reads `verdict`, not `orphans_with < orphans_without` |
| 8 | CC.5a reflexion-model declarations (`08265cc`), CC.5b / CC.5c check v2 evaluates and renders them (`3f1694e`, `b0882a8`) | `.glia/overlay.toml` gains `[[component]]`, `[[layer]]` and `[[constraint]] kind = "allow"`. **A 0.5.0 engine ignores the whole overlay file** (`unknown field component`) once one of them is present, so entrypoints, wrappers and edges from that file vanish for a 0.5.0 reader. `check()` gains a `reflexion` key. CONSTRAINT payloads can hold kinds `component` / `layer` / `allow`. | `_cell_text` renders CONSTRAINT entries generically (`server.py:674-683`), so new kinds show as compact JSON; nothing breaks. The exact pin keeps the wrapper and the file's author on one version. |
| 9 | CA.9 per-phase build timers (`b0a91d9`), plus the markers of the Go-mount, event, tRPC, channel-host, provenance and format packets listed elsewhere in this table | new stderr lines on every build: `[timing] repo=...`, `[timing] build ...`, `[timing] persist ...`, `[provenance] ...`, `[gmap] code spans: ...`, `[go-mounts] ...`, `[http-external] ...`; changed ones such as `[incremental] saved <n> entries (btree, lz4 <raw> -> <framed> bytes)` and `[eventbus-owner] ... same-process=<n> ...` | the server relays glia's stderr and parses none of it; `[watch] rebuilt` (`server.py:139`) is the wrapper's own line |
| 10 | CD.5b timeline sidecar and a recorded rev (`815ef80`) | `manifest.json` `repos[].rev` (for a root inside a git work tree with a commit); `glia timeline build` writes `<layout>/timeline.gmap` | the wrapper reads the manifest only through glia_py; `watcher.py:39-50` skips everything under `default_gmap_dir()` by prefix, so the sidecar never triggers a rebuild |
| 11 | CE.1a-CE.1d SCIP ingest (`5ab07aa`, `174c770`, `47b2f36`, `28dfcf5`) | `glia scip import` writes `.glia/scip-snapshot/` (an input; the new `.glia/.gitignore` lists it). A repo with a snapshot gains Strong CALLS / USES / IMPLEMENTS edges with EVIDENCE emitter `scip:<tool>`, and evidence stage `scip` tiers FACT. | the watcher rebuilds when the snapshot changes, which is correct (it is under `.glia/`, not the layout dir); nothing to change |
| 12 | CJ.2 PROJECT-root and SDD feature docs ingested (`6681070`) | `coverage()` gains a second `(*, DOCUMENTS)` row after the contract-JSON one: the markdown scope (well-known files and `docs/` trees at the repo root and every PROJECT root, `.ai/`, ADR dirs, `features/<f>/*.md`, spec-kit `specs/<NNN-slug>/`, synced docs) and the single-backtick rule, about 900 characters. `governing_docs` finds sections in the newly read docs (quokka-stack: 20 -> 61 docs, 133 -> 401 sections). | `_coverage_note` (`server.py:942-960`) prints `recs[:8]` with each note whole. The `*` rows come first in `coverage()` (CALLS, HTTP_CALLS, three QUEUE_FLOWS, the two DOCUMENTS, GRAPHQL_CALLS, WS_CONNECTS, ...: quokka-stack's first ten, checked 2026-10-02), so on every repo this row is the footer's 7th line (859 characters on quokka-stack) and pushes WS_CONNECTS out of the eight. **Optional:** cap each note (say 200 characters) or skip `DOCUMENTS` rows there. `_governing_docs_note` (`server.py:713-723`) lists up to 5 sections and needs nothing; it now names a sub-project's `docs/` and feature docs. |
| 13 | CL.5b function-level TESTS (`eb302a2`) | TESTS edges `test fn -> unit fn` (`pass:tests` / `calls_into_tested_module`, Medium, DERIVED) for every language, beside the module pairs; LE.3a's TEST cell now sits on the called FUNCTION / METHOD nodes too (Kina: TESTS 57 -> 196, `[test-cells]` nodes 57 -> 147). | `read`'s "covering tests" footer (TEST cells, `server.py:616`) appears on far more functions. Nothing to change. |

## 3. Graph content: what the answers show differently

No wrapper code parses these qnames, caches them across rebuilds or keys state on them (`graph.py`
rebuilds its index from `nodes_json()` on every load, and `flows` is recomputed). They change golden
outputs, counts and the names in find / impact / trace / read / orient.

### 3a. Identity changes (qname or NodeId)

| packet (commit) | old -> new | measured |
|---|---|---|
| CB.23 Go parser emits router mounts (`e072dce`, the W8 re-run), with CB.20 the build-time mount pass (`af2f094`) and CB.11 routes on a struct field (`8b3d8fd`) | A Go ROUTE registered on a group that reaches its function through a router-typed parameter or a struct field, and whose mount the build resolves, gains the prefix: `<METHOD> <local>[ @owner]` -> `<METHOD> <prefix><local>[ @owner]`. A function mounted N times yields N ROUTEs, so routes that shared a local qname split. Unmounted registrations keep their qname byte for byte, and no provisional `<mount:...>` qname ever reaches an answer. | quokka-stack `POST /activity @turps` -> `POST /api/protected/activity @turps` (58 routes renamed); `GET /user/2fa @turps` -> `GET /api/user/2fa` + `GET /api/protected/user/2fa`; Kina `GET /stats @backend` -> `GET /admin/stats @backend`, every `/api` route likewise (87 renamed). Kina loses 1 false HTTP_CALLS (`endpoint:GET:${…}/public/stats @frontend` -> `GET /stats @backend`) and gains 33 by the new mount-segment fold; quokka HTTP_CALLS 47 -> 48. |
| CB.1 `.graphqls` and `.hh/.hxx/.inl/.ipp/.tpp` routed (`84448eb`) | new MODULEs for those files; an out-of-line C++ member whose class is declared only in such a header goes FUNCTION `<file>::Q::m` -> METHOD `<header scope>::Q::m` (`src::widget.cc::Widget::run` -> `include::Widget::run`) | fixtures only |
| CB.19 C/C++ templates, unions, nested types, extern "C" and anonymous namespaces (`70286f0`) | an out-of-line member of a nested type goes FUNCTION `<file>::<ns>::Cart::Line::total` -> METHOD `<outer>::Line::total` | ~/Code/samples runner C++ (322 files): +150 nodes, +203 edges, 0 removed |
| CB.3a verb-named events removed (`444848b`), CB.3b constant-keyed events fold to their literal (`5a968a7`) | `event_emit:emit` / `Subject.next` / `publish` / `dispatchEvent` / `eventBridge.putEvents` ... and `event_handle:on` / `subscribe` / `@OnEvent` / `handle_event` ... vanish with their edges; a constant-keyed site is `event_emit:<literal>` when the const table resolves it, else `event_emit:<Const.Path>`; a putEvents is named by its DetailType | no constant-keyed site on quokka, lapse, repo-graph, Kina or neuropil; fewer phantom `event_handler` entry points |
| CE.4a doc-source seams and fence-aware chunking (`111bd1b`) | a `#` / `##` line inside a ``` / ~~~ fence is no longer a DOC_SECTION; the 2nd+ section with a repeated slug gets `<...>::<slug>-N` (it used to emit one NodeId twice) | Kina's README loses 14 sections (`docs::README::terminal-1` ...), quokka's `.ai/WORKFLOW.md` loses 4, glia's README 10 and `docs/onboarding.md` 13 |
| CB.2 contract YAML sniffing (`2ff7f49`) | a yaml whose indent-0 `openapi:` / `swagger:` / `asyncapi:` key has no version value is no longer a contract (its `contract::...` ops and DOCUMENTS go); an OpenAPI yaml whose marker sits past line 64 (swaggo's alphabetical `swagger.yaml`) now is | the twins share one NodeId (see the note below) |
| CH.3a client URLs read through a URL builder, a URL method, a `const` local or a `readonly` field (`4c05d47`) | `endpoint:<M>:<unresolved>[ @owner]` -> `endpoint:<M>:<path>[ @owner]` for each such site; its ENDPOINT_HIT gains `"wrapper":"<builder>"` | quokka_web: 25 sites move, `endpoint:POST:<unresolved>` and `endpoint:PATCH:<unresolved>` go, HTTP_CALLS +22; Kina: `NotificationsApi::list` -> `endpoint:GET:/api/notifications @frontend`, which pairs `GET /api/notifications @backend` |
| CH.3c `this.<field>.<verb>(..)` on a typed non-HTTP receiver mints no endpoint (`58fb26c`) | CALLS into `endpoint:<M>:<unresolved>` from a `Map` / `Set` / store field go, and an `<unresolved>` ENDPOINT no other site keeps disappears | Kina: 15 CALLS, `endpoint:DELETE:<unresolved>` and `endpoint:PATCH:<unresolved>` go; quokka-stack: 6 CALLS, `GET` / `DELETE` `<unresolved>` go. `glia gaps` unresolved_endpoint rows drop with them |
| CH.5b builder-read TS endpoints folded under the configured API prefix (`17c7bef`) | `endpoint:<M>:<path> @quokka_web` -> `endpoint:<M>:/api<path> @quokka_web`; the node goes Weak -> Medium; its HTTP_CALLS go `route_prefix` -> `exact` | quokka-stack: 50 endpoint qnames from 53 call sites, `[endpoint-prefix] prefixed 53 endpoint paths (wrapper=53 base=0) prefixes=/api`; Kina unchanged |
| CH.5c Dart endpoints folded under agreeing Dio base URLs; a call on a Dio is never a server ROUTE (`4eb3909`) | `endpoint:<M>:/protected/x @quokka_android` -> `endpoint:<M>:/api/protected/x @quokka_android` (Strong -> Medium); the phantom ROUTE `POST /auth/refresh @quokka_android` goes | quokka-stack: 42 entries; `[http] exact=52 rprefix=40` -> `exact=91 rprefix=1`, routes 65 -> 64 |
| CI.5 Go mounts through another package's struct field and a parameter-rooted field group (`ecb0c81`) | `<METHOD> <local>` -> `<METHOD> <prefix><local>` for those two route shapes | fixtures only: no ROUTE moves on quokka-stack, Kina or lapse |
| CL.1 a queue framework tag only for an unexplained call; a RabbitMQ declare is no consume (`6da6473`) | a `queue_consumer:<q>` minted by a declaration alone goes, with its false self QUEUE_FLOWS; an explained `queue_*:unresolved:<family>` tag goes; amqplib `channel.publish(ex, key, ..)` is `queue_producer:<key>` (was `<ex>`); BullMQ `queue.add(name, ..)` mints nothing | matrix probes only |
| CL.2 Go broker rows (`b896904`), CL.3 JVM / .NET broker rows (`7456d6e`) | new `queue_producer:<t>` / `queue_consumer:<t>`; the `queue_producer:unresolved:kafka` tag beside a kafka-go `Writer` literal, `queue_*:unresolved:nats` beside a NATS.Net `*Async` call and `queue_consumer:unresolved:sqs` beside a named SQS request builder go | matrix probes only |
| CL.7b .NET application settings (`2e0ef8a`) | a new CONFIG_KEY track `config:setting:<Section:Key>`: defined by `appsettings*.json` (now a synthetic MODULE) and by every env define `A__B[__C..]` (Dockerfile, .env, k8s, compose; DEFINES_CONFIG with EVIDENCE rule `dotnet_env_override`), read by C# `IConfiguration` (`config["A:B"]`, `GetValue<T>`, `GetSection`, `GetConnectionString`) | fixtures only; no tracked repo under ~/Code defines a `__` env name |
| CJ.1a-CJ.1c the `.rs` / `.py` literal and comment guard (`96f9280`, `aae59c6`, `472de38`) | in a Rust or Python file a needle starting inside a string literal or comment mints nothing: queue / event, WS / gRPC / GraphQL-operation, cron, data-source and env / secret / flag nodes go with their edges | glia's own graph: queue / event phantoms 175 -> 0, WS / gRPC / GraphQL phantoms 36 -> 1, module-owned CRON_JOBs 22 -> 1, non-fixture (module, data source) pairs 87 -> 7. Other languages byte-identical |

**Shared NodeIds across per-language graphs (by design, no action).** swaggo writes `docs/swagger.json` and `docs/swagger.yaml` side by side; CB.2 now reads the yaml too, and by the LB.12 identity rule both name their ops `contract::<dirs>::swagger::<op>`, so the twins are ONE node. `MergedGraph` keeps one instance per per-language graph that holds it ("one id can sit in several per-language graphs", `graph/src/merged.rs`), which is how shared synthetic nodes (`config:env:*`, `data_entity:*`, `data_source:*`) have always been stored, 0.5.0 included. Answers dedupe by id (`glia find` on quokka returns one `contract::turps::docs::swagger::GET:/healthz` row, checked 2026-10-01), and the wrapper's `RustGraph.nodes` dict keeps one. Only code that walks `merged.graphs[].nodes` directly sees an instance per graph; key by id there.

### 3b. New nodes (additive)

| packet (commit) | what appears |
|---|---|
| CB.9 Dart constructors / factories / operators (`ec5c6ea`), CB.17 Dart extensions and top-level initialisers (`205861c`) | METHOD `<T>::<T>`, `<T>::name`, `<T>::_`, `<T>::operator+`, abstract members; ATTRIBUTE `<Enum>::<c>`; CLASS `<module>::extension<T>`; STATE_VARs. quokka-stack gains ~135 Dart METHODs, mostly constructors and `fromJson` / `fromBuffer` factories. Blast radius from a Dart class reaches its constructors' callees one DEFINES hop later. |
| CB.10 Swift init / deinit / subscript / computed properties (`90d1076`) | METHOD `<Type>::init`, `::deinit`, `::subscript`, `::<property>` |
| CG.1 TS / JS arrow-function class fields (`8bff4f9`) | METHOD `<module>::<Class>::<field>`; markers and data access in a field body hang on it (Kina gains 19, quokka 5: `handleMotionPreferenceChange` ...) |
| CB.14 Python strawberry / graphene field resolvers (`a2a619e`) | GRAPHQL_RESOLVER `graphql_resolver:<schema name>` (camelCase unless `name=` or `auto_camel_case=False`), which are entry points |
| CA.6b Ktor-client calls (`d739141`) | client ENDPOINTs and HTTP_CALLS for Kotlin; new `[kotlin-ktor-client]` line |
| CB.13 tRPC server-side callers (`636cc57`) | RPC_CALL `rpc_call:a.b` from `createCaller` / `createCallerFactory` roots |
| CA.4 inferred Go collection wrappers (`a1e05a5`) | DATA_ENTITY `data_entity:nosql:<name>` with ORIGIN `inferred:wrapper` and function-level ACCESSES_DATA (quokka: 12, the `NewCollection[T]` wrapper, with no overlay stanza) |
| CH.1 TS abstract classes (`d12e804`) | CLASS `<module>::<Class>` for every `abstract class`, METHOD members (an abstract one has no body), DEFINES, heritage, INJECTS and its Angular role; `[ts-abstract]` |
| CH.2 call-initialised TS class fields (`faa563b`) | STATE_VAR `<module>::<Class>::<field>` for `signal(..)`, `computed(..)`, `input.required<T>()`, `toSignal(..)`, `effect(..)`, `x$ = this.subject.asObservable()` (any call but `inject(..)`), with DEFINES and their initialiser's CALLS: Kina +1,455, quokka-stack +29; `[ts-state]` |
| CH.5a Dart generic Dio calls (`c44a41e`) | client ENDPOINTs for `dio.get<T>('/x')`: quokka_android 18 -> 41 |
| CJ.2 PROJECT-root and SDD feature docs (`6681070`) | DOC_SECTIONs of the newly read docs: quokka-stack 20 -> 61 docs, 133 -> 401 sections (`[docs] scope: project_root=5 project_docs=0 feature=36 ...`) |
| CL.4 JobRunr / Hangfire / asynq (`d1fd77c`), CL.6a Go / C# GraphQL requests (`c052a5b`), CL.6b HotChocolate (`7941f3a`), CL.7a C# env reads (`3241195`), CL.8 Go EventBus (`ceb7953`), CL.9 NestJS cron (`05f01ed`), CL.10 JVM process launches (`a8ef0f4`) | queue nodes named by the job's method or task type, GRAPHQL_OPERATION / GRAPHQL_RESOLVER, `config:env:<X>` read from C#, EVENT_EMITTER / EVENT_HANDLER, CRON_JOB `cron:<schedule>:<method>`, CLI_INVOCATION `cli_invoke:<bin>`: all in existing qname shapes |

### 3c. Edges

| packet (commit) | change |
|---|---|
| CA.1 Go calls inside func literals (`efdf872`), CA.2a / CA.2b Go typed receivers (`43260b9`, `7788f90`) | many more Go CALLS (closures, call-chain / local / param / field receivers); none removed |
| CA.3b Go implicit IMPLEMENTS checked (`c8f2257`) | Go type -> interface IMPLEMENTS drop when signatures differ or, for one-method / test-file interfaces, no import links the packages: grpc-go 1314 -> 682 type-level, 2550 -> 1519 method-level; Kina 132 -> 84. Impact / trace / implementors over Go interfaces return fewer, correct rows. |
| CA.5a Go handlers as receiver method values (`22c3d82`) | Kina ROUTEs with HANDLED_BY 36 -> 89 of 90 |
| CB.18 Swift implicit self (`008f2b8`), CB.25 C++ call scope (`b78c622`), CB.22 C/C++ include search paths (`24b3cfa`), CB.15 namespace home module (`0742baf`) | a bare call inside a member binds the member, not a same-named free function (the old edge goes); many more Swift / C++ CALLS; C/C++ IMPORTS through `-I` roots and `compile_commands.json`; C# / PHP calls resolve through the member's own file's `use` / `using` (wrong-file binds go) |
| CB.21 (`016775d`), CB.24 (`99502f9`) host narrowing | a WS / gRPC / GraphQL / tRPC hop no longer fans out to every same-key service when the client names a host |
| CG.4b external endpoints (`0a23e66`) | an ENDPOINT whose every site is external and whose hosts name no service gets no HTTP_CALLS (quokka's nominatim `endpoint:GET:/search @quokka_web` no longer hops into `GET /search`) and carries ORIGIN `external` |
| CC.7a feature-flag reads re-homed (`74f9402`) | READS_CONFIG into `config:flag:<key>` starts at the reading function, not the module |
| CB.4 TS decorators (`84a3581`) | a marker on a decorator line (`@OnEvent`, `@MessagePattern` ...) loses `CONTAINS module -> marker` and gains `HANDLED_BY marker -> method`, so those handler methods turn live |
| CB.5 in-process events across nested projects (`25dcc4f`), CB.7 PHP `use` (`0aca1b9`), CB.16 Ruby `require` (`7e6bbeb`), CA.6a Kotlin receivers (`bae111b`), CB.9 Dart constructor bodies | more EVENT_FLOWS / IMPORTS / CALLS; Dart CALLS move from the CLASS to the constructor METHOD |
| CG.3 the doc linker sees the whole section (`dd191fa`) | DOCUMENTS from `pass:doclink` grow: quokka 28 -> 179, glia 41 -> 263, Kina 1 -> 4. `read`'s "governed by (docs)" footer (`server.py:713-723`) lists more sections. |
| CH.1b TS inherited calls and abstract overrides (`d8e5c4c`) | CALLS for an unbound `this.m()` / `super.m()` to the nearest superclass defining `m` (EVIDENCE `graph:calls` / `inherited_method`), and a method-level IMPLEMENTS from an override to the abstract member (`graph:iface` / `abstract_override`, Strong); `[ts-inherit] calls bound through superclasses: <n> (self=<s> super=<p> ambiguous=<a>) abstract implements=<m>`. Additive only |
| CH.1c dead_symbol dispatch (`f130663`) | no edge; `glia gaps` / `PyGraph.gaps` `dead_symbol` withholds a METHOD that IMPLEMENTS a METHOD with an incoming CALLS / USES from a third node: grpc-go 2,672 -> 2,589, lapse 325 -> 290, quokka-stack and Kina unchanged; `[dead-dispatch] dead_symbol rows withheld: <n> (implementations of a called method)`. Liveness, blast and trace are unchanged |
| CH.2 (`faa563b`), CH.4 TS methods passed by value (`3e6e9f3`) | CALLS out of the new STATE_VARs and `this.<signal>()` reads into them; USES from a member to a same-class METHOD it passes by value (`parser:<tag>` / `method_ref`). dead_symbol: Kina 560 -> 521 (CH.2), quokka-stack 774 -> 770 (CH.4) |
| CI.1 Go package-var initialisers (`26d2bd9`) | CALLS out of a Go STATE_VAR: grpc-go 0 -> 235, quokka-stack 43, Kina 5, lapse 4 |
| CI.2a Go struct embeds (`643de54`) | STRUCT INHERITS_FROM to each in-repo embedded STRUCT / INTERFACE (`graph:go_packages` / `embed_package` or `embed_import`), CALLS bound through promotion (`promoted_self`): grpc-go 353 of 359 embeds bound, Kina 7, quokka-stack 3 |
| CI.2b promoted methods in implicit IMPLEMENTS (`5fc42bb`), CI.6 Go type aliases (`4942139`) | new type -> interface IMPLEMENTS (Medium) and method-level pairs (`promoted_method`): grpc-go type-level 675 -> 1,098 (CI.2b) -> 1,137 (CI.6), quokka-stack 7 -> 8 -> 9 (`turps::Services::chat::server::Server` -> `QuokkaChatServiceServer`), none removed; `[iface] go implicit promoted:` and `[go-alias]` lines |
| CI.3 root-package imports; the test side narrowed (`99e2d10`) | IMPORTS / CALLS into a repository-root Go package (grpc-go: 255 root imports bound, CALLS into root-dir nodes 73 -> 2,484). Go IMPLEMENTS with a `_test.go` side whose own file does not import the other side's package directly are dropped: grpc-go 9 type-level + 10 method-level, `implementors` of `Closable` 8 -> 1, two of them true (`checkBufferPool` -> `mem.BufferPool`, `fakeALTSAuthInfo` -> `credentials.AuthInfo`, a declared trade-off). `[iface] go implicit filtered:` loses its ` root_assumed=<n>` field |
| CI.4 split-file and promoted Go handlers (`961c832`) | HANDLED_BY for a receiver-method handler whose type sits in another file of the package or whose method is promoted; an edge HEAD bound by the repo-unique name moves EVIDENCE `graph:refs` / `global_unique_method` -> `graph:go_packages` / `package_type_method` (`why` tier heuristic -> fact). Real repos unchanged |
| CL.5a constructed receivers (`052d0c5`), CL.5b function-level TESTS (`eb302a2`) | CALLS `new Calc().add(..)` -> `Calc::add` (Java / C# / TS / PHP); TESTS test fn -> unit fn (section 2, row 13) |
| CH.3a, CH.5b, CH.5c (section 3a) | HTTP_CALLS of the re-keyed endpoints: quokka-stack `[http] exact=3 rprefix=90` before CH.5b, `exact=91 rprefix=1` after CH.5c |

### 3d. Cells, spans and coverage text

- **CB.4 (`84a3581`):** a decorated TS / Angular / Vue / React method's POSITION and CODE start at its
  first decorator. `read` (`server.py:726-760`) slices from `nodes_json` spans, so it now shows the
  decorators; `_loc` / `_eloc` lines move up by the decorator count.
- **CG.3 (`dd191fa`):** a markdown DOC_SECTION's CODE cell holds the whole section (up to 64 KiB), not
  its first 500 bytes. `_READ_CELL_TYPES` excludes CODE, so `read` is unchanged; `dense_text_full`
  prints whole sections.
- **CD.7c (`5611813`):** a graph loaded from a layout gets CODE as text while the recorded root holds the
  unchanged file. `load_from_gmap` rebuilds when a span no longer resolves, so the wrapper never sees
  the `{"code_span":{...}}` JSON. `read` slices files itself either way.
- **CG.2a test / fixture provenance by path (`5004a5a`):** nodes under `e2e/`, `cypress/`, `fixtures/`,
  `testdata/`, `__mocks__/`, first-segment `test(s)/`, or in `*.spec.tsx` / `*.cy.ts` / `test_*.py`
  files carry ORIGIN `test_fixture` (Kina +50, glia +2,545, quokka 0). `tests_for`, `gaps`
  (`dead_symbol`), `hubs`, `hotspots`, `duplicate_flows` and `patterns` treat them as tests.
- **Coverage caveats** (`coverage()`, rendered by `_coverage_note`, `server.py:942-960`): new rows for
  c_cpp CALLS + IMPORTS, swift CALLS, dart CALLS, go HANDLED_BY and a `*` GRPC_CALLS row in every repo
  (CB.26, `cc508eb`); rewritten text for Go IMPLEMENTS (CA.3b), Kotlin CALLS (CA.6a) and Kotlin
  HTTP_CALLS (CA.6b). The footer shows `recs[:8]`, so which rows make the cut shifts.
- **CB.10 (`90d1076`):** a Swift MODULE's IMPORTS cell holds `X` for `@testable import X` (it held the
  whole statement). **CB.22 (`24b3cfa`):** C/C++ IMPORTS cells list angle includes (`stdio.h`, `curl`).
  Both show in `read`'s `imports:` footer.
- **The finishing batch's cells and caveats.**
  - `ENDPOINT_HIT` gains `wrapper` (CH.3a), `wrapper_of` (CH.3b), `folded_from` / `prefix` /
    `prefix_from` (CH.5b, CH.5c), all after `confidence` (section 2, row 3).
  - TEST cells sit on functions (CL.5b).
  - ORIGIN `test_fixture` also comes from a repo's own `.glia/overlay.toml` `[walk] tests = [..]`
    (CJ.4, `[provenance] declared tests repo=<label> patterns=<n> tagged=<d>`).
  - `coverage()` gains the second `(*, DOCUMENTS)` row (CJ.2, section 2 row 12).
  - The Go IMPLEMENTS caveat is rewritten: promoted methods count (CI.2b); the root-package clause
    goes, and a `_test.go` side pairs "only when that test file imports the other side's package
    directly (or both share a package)" (CI.3); a type alias declared in the repo is resolved
    through the method's package and imports (CI.6).
  - The Go HANDLED_BY caveat says a group held in a struct field "of its own package or an imported
    one" (CI.5). The `(*, HANDLED_BY)` queue-callback caveat names asynq HandleFunc / Handle (CL.4).
  - The `read` footer "governed by (docs)" can list a sub-project's `docs/` sections (CJ.2).
- **New stderr markers** (the server relays them and parses none): `[code-guard]` (CJ.1a-CJ.1c),
  `[ts-abstract]`, `[ts-inherit]`, `[dead-dispatch]`, `[ts-state]`, `[ts-endpoint-args]`,
  `[ts-url-prefix]`, `[ts-endpoint-gate]`, `[ts-method-refs]`, `[endpoint-prefix]`, `[endpoint-base]`,
  `[dart-dio-base]`, `[dart-dio-receivers]`, `[go-calls] package-var initialisers`, `[go-embeds]`,
  `[iface] go implicit promoted:`, `[go-package] root-package imports`, `[go-handlers]`,
  `[go-routes] mount owners`, `[go-alias]`, `[docs] scope:`, `[effects-external]`,
  `[provenance] declared tests`, `[recv] constructed receivers`, `[tests] fn TESTS edges`,
  `[config] settings`, `[config] env overrides`; `[cron] code ..` gains `nestjs=<n>`.

## 4. New primitives worth adopting

From the surface diff. Every answer is a native dict; lines are 1-based; each list answer that can come
back empty carries an `absence`. None of these replaces a call the wrapper makes today; they are
candidates for new modes of the six tools (the 0.5.0 handoff's section 7 rule: keep the tool count, add
modes).

| primitive (pyo3) | returns | fits | packet (commit) |
|---|---|---|---|
| `PyGraph.pack(query, budget=8000, bytes_per_token=3.7, seeds=5, candidates=200, preset=None, scope=None)`, `pack_ids(node_ids, ...)` | `{query, text, budget_tokens, used_tokens, bytes, bytes_per_token, candidates, nodes, dropped, rerenders, absence}`; `nodes` rows `{id, qname, kind, file, line, fidelity, tokens, rank, tier, reason, matched}` with upper-case kind names | `orient(seed)` (`server.py:257-266`): replace `activate` + `dense_text_subset` + character `_truncate` with a context pack sized to the budget; each node is rendered at full / preview / outline / qname fidelity | CC.4a-CC.4c (`7a34e5c`, `62f1a4c`, `25b719b`) |
| `review_vs_rev(repo_path, base="HEAD", format="dict", markdown_rows=20, depth=4, max_tests=50, max_impact=50)` | `{base, counts, changed, impact, tests, edges, new_violations, resolved_violations, check_errors, blocking}`, or the PR markdown with `format="markdown"` | a PR-review mode of `impact`: `blocking` is the CI gate. Builds both sides and writes only `.glia/graph/parse_cache.bin`. | CC.6a / CC.6b (`b492e71`, `d46d5ad`) |
| `PyGraph.hotspots(level="both", top=20, min_churn=2, include_tests=False, scope=None)` | `{modules, symbols, history_head, absence}`; rows `{level, qname, kind, file, line, churn, lines_changed, last_change, churn_rank, centrality_rank, ranked, tier}` | an `orient` note ("where change concentrates"). Needs `history_sync(repo)` first; symbol rows need `blame=True`. | CC.10a / CC.10b (`9456731`, `d00310f`) |
| `PyGraph.cochange(files, min_confidence=0.3, min_support=3, top=20, unlinked_only=False)`, `cochange_vs_rev(repo_path, base="HEAD", ...)` | `{query_files, unmapped, rows, absence}`; rows carry `confidence_permille`, `link` (`direct` / `bridged` / `none`), tier `heuristic` | an `impact` footer: "files that usually change with these" | CC.11a-CC.11c (`7b93c52`, `10d89e2`, `9f150bf`) |
| `PyGraph.communities(scope=None, seed=42, resolution=1.0, top=30, members=10, method=None)` | `{method, seed, resolution, modularity, total, nodes, ...}`; each community `{id, size, label, tier, cohesion, files, kinds, top_members, entries, services, sinks, links}` | an `orient` map by structure rather than by directory | CD.1a-CD.1e (`86cbe89` .. `5f8f785`) |
| `PyGraph.splits(scope=None, parts=2, quotient="module", source=None, sink=None, min_share=0.1, seed=42)` | `{mode, quotient, units, parts, cut_weight, ..., shared_writes, cycles, tier, absence}` | "where would this service split" | CD.2a-CD.2d (`c9f5a03` .. `75bc2ac`) |
| `PyGraph.hubs(scope=None, top=20, category=None, min_degree=5, include_tests=False)` | `{fan_in, fan_out, cross_service, nodes, edges, p99_in, p99_out, absence}` | an `orient` note on utilities / orchestrators / connectors | CD.4a-CD.4c (`1055286`, `16f75ba`, `45dd22c`) |
| `PyGraph.duplicate_flows(scope=None, depth=6, threshold=0.8, min_size=3, include_tests=False, keep_hubs=False)` | `{entries, flows, hubs_ignored, candidates, oversized_buckets, groups, absence}`; exact groups DERIVED, near ones HEURISTIC | a `trace` note ("this flow duplicates ...") | CD.4d-CD.4f (`ba109ed`, `12114b8`, `bc74fce`) |
| `PyGraph.flags(quiet_days=90, scope=None)` | `{flags, definitions_in_graph, quiet_evaluated, history_now, quiet_days, counts, absence}` | stale feature flags (report only) | CC.7a-CC.7c (`74f9402`, `43e07bf`, `983e204`) |
| `contract_breaks_vs_rev(repo_path, base="HEAD", avro="backward", breaking_only=False, with_repos=None)` | `{base, schemas, orphaned_clients, breaking, absence}` | contract / schema breaks vs a rev; `with_repos` adds client repos | CC.8a-CC.8c (`c3b503e`, `37adc46`, `c2dd188`) |
| `timeline_build(repo_path, revs=20, head="HEAD")`, `timeline_history(repo_path, qname, category=None)`, `timeline_as_of(repo_path, rev)` | build: `{revs, skipped, nodes, edges, edge_spans, closed, moves, written}`; history: `{results, absence}` with `since` / `until` revs; as-of: `{rev, nodes, edges, by_category}` | "when did this edge appear" | CD.5a-CD.5d (`e569192` .. `152ea8b`) |
| `PyGraph.patterns(...)`, `patterns_vs_rev(...)` | as `patterns_experimental`, minus `experimental`, plus `blind` / `sighted` / `package` | handler conventions per service or package | CC.12b (`a2b834a`) |
| `PyGraph.activate(seed_ids, top_k=None, profile="centrality")` | the new `centrality` preset (a global PageRank lens) | none required | CC.10a (`9456731`) |
| `overlay_propose(repo_paths, categories=None, top_k=20, snippet_lines=3)`, `overlay_try(repo_paths, candidate, leave_one_out=True)`, `overlay_accept(repo_path, candidate=None, only=None, remove=None, dry_run=False)` | the `glia overlay propose / try / accept --json` objects as dicts: `{rows, counts, snippets, ambiguous_root, guide}`, `{stanzas, base, with, delta, verdict, closed, builds}`, `{added, removed, duplicates, file, dry_run, written, diff}`. `candidate` is TOML text, not a path; a refusal raises `ValueError` with the loader's reasons; markers end `surface=py`; `repo_paths[0]` is the repo whose `.glia/overlay.toml` is read, the rest merge in | an overlay mode: `gaps` -> `overlay_propose` -> a model writes stanzas -> `overlay_try` -> `overlay_accept` of the `keep` stanzas only. `overlay_try` writes only the primary repo's parse cache; `overlay_accept` is the only writer of `.glia/overlay.toml`, which the watcher then rebuilds on. glia's `skills/glia-overlay/SKILL.md` is the model step's playbook | CK.1 (`1d0ec79`), over CE.3b-CE.3d |
| `PyGraph.effects(...)` / `PyGraph.serves(...)`: every row gains `external_hosts` | `effects` rows and `serves` results carry the sorted third-party hosts of a sink marked external (`[]` otherwise); `serves` for an HTTP channel lists each such ENDPOINT after the routes, `"match": "external"`, so a third-party-only channel is answered, not absent | a `trace` / `impact` note "calls <host> (external)" if the wrapper adopts either answer; it calls neither today | CJ.3 (`d06af61`) |

CLI-only, with no pyo3 surface (a skill or a subprocess can use them; an MCP mode cannot):
`glia scip import` (CE.1c), `glia cache push|pull|gc [--layout]` (a shared parse cache and a
whole-layout cache for CI cold starts, CE.2c-CE.2e), and `glia docs sync --source dir|mediawiki|notion`
(CE.4b-CE.4f). The overlay loop (`glia overlay propose|try|accept`, CE.3a-CE.3f) has its pyo3 form
since CK.1, the row above, so an MCP overlay mode is now possible. The 0.5.0 handoff's section 7b (a skill
plus a CLI entry point beside the MCP server) is still open on repo-graph's side (`CLAUDE.md:192`); glia
now has two skills to point at (`skills/glia/SKILL.md`, `skills/glia-overlay/SKILL.md`) and README
`## CLI` lists every 0.5.1 command and flag, held to `cli/surface/` by a test (CZ.1, `2794ec5`).

## 5. Needs no change (checked)

- **Registry decoding** (`graph.py:21-28`, `server.py:618-643`): no new kinds, categories or cell types,
  the finishing batch included (it reuses STATE_VAR, INHERITS_FROM, CONFIG_KEY and the rest by name).
- **Every call site in section 0's list**: signatures and shapes are unchanged in `py/api_surface/`.
- **The watcher** (`watcher.py:24-50`, `:98`): 0.5.1 writes only inside `default_gmap_dir()`
  (`parse_cache.bin`, shards, `timeline.gmap`) or into inputs under `.glia/` that should trigger a
  rebuild (`overlay.toml`, `scip-snapshot/`, `test-snapshot/`, the docs snapshots). `review_vs_rev`,
  `contract_breaks_vs_rev`, `tests_for_rev` and `timeline_build` materialise revs in a temp dir, not in
  the repo.
- **`init.py:36-45`**: `generate(incremental=True)` + `save_to_default` + `default_gmap_dir` are
  unchanged.
- **The wrapper's tests.** They pin no counts on the fixtures, only relative equalities
  (`tests/test_cache.py:119-131`, `:158-182`), and `_PARSE_CACHE` (`:144`) only checks that the file
  exists. The fixture `http_stack_smoke` (byte-identical to glia's copy) gains 4 CALLS: 1 under CA.2a
  and 3 under CA.2b (`api.GET` binds the `Router` interface's `GET`). glia's `cli/tests/merge_cli.rs`
  moved 26 -> 30 intra edges for it (`6d5a6f8`, `c6726b5`). No wrapper assertion reads that number.
- **Trace mechanism icons** (`server.py:467-468`) and tier sets (`server.py:815-823`): no new kind or
  category.
- **Evidence strings:** the wrapper parses no emitter or rule (`method_set`, `receiver_type`,
  `scip:<tool>` ...).

## 6. Re-test

```
# a local 0.5.1 wheel (before PyPI), in a throwaway venv (never ~/.venvs/glia-leap or the user site)
python3 -m venv /tmp/rg-051 && /tmp/rg-051/bin/pip install /home/ivy/Code/glia/target/wheels/glia_py-*.whl
/tmp/rg-051/bin/python -c "import glia_py as g; print(g.version(), g.build_stamp(), len(g.entry_kinds()))"
#   expect the stamp of the wheel you built; len(entry_kinds()) is unchanged from 0.5.0

# the wrapper's suites (the packaging test fails until section 1's predicate change lands)
cd /home/ivy/Code/repo-graph && /tmp/rg-051/bin/pip install -e ".[dev]" && /tmp/rg-051/bin/pytest -m "not perf"
/tmp/rg-051/bin/pytest -m e2e

# first load of a 0.5.0 layout rebuilds once, then loads
/tmp/rg-051/bin/python -c "import glia_py as g, sys; r=sys.argv[1]; g.load_from_gmap(g.default_gmap_dir(r), r); g.load_from_gmap(g.default_gmap_dir(r), r)" <repo> 2>&1 | grep '^\[gmap\] rebuilt'
#   expect exactly one line: [gmap] rebuilt <repo>/.glia/graph (written by another glia build (...))

# glia side: the wheel matches the pinned surface
cd /home/ivy/Code/glia && ~/.venvs/glia-leap/bin/python py/check_api_surface.py
```

The wrapper suite was not run for this handoff (glia's rule: never call the wheel's `generate()` on a
repo from the glia session).

## 7. Done vs pending

- **Landed:** W0-W18 (197 packets, all green) and the docs packet CZ.3 in W19. The W18 close-out
  (`dbd8d2a`) measured 4,460 workspace tests passing, 346 substrate-gap fixtures with 0 blind spots,
  the coverage matrix at 243 full / 34 partial / 69 none / 136 unknown / 28 n/a, `[engram-export] check:
  ok`, and every pyo3 surface test green, `test_overlay_loop` included, on the wheel
  `glia_py-0.5.0-cp311-abi3-manylinux_2_39_x86_64.whl` (stamp `0.5.0+pa0fc26c918dfcc7c`).
- **Release steps (not packets):** the 0.5.1 bump of every version field (every glia crate moves to the
  workspace version, leap doc section 7.4), the tag, the PyPI publish.
- **Open on glia's side, for the wrapper's benefit:**
  - no pyo3 entry takes one precomputed rev delta for impact + tests together (the follow-up of CC.1,
    the rev-delta entry points); `review_vs_rev` already answers both from one delta;
  - deferred to 0.5.2 (README `## Roadmap`): WS / gRPC / GraphQL external-endpoint marking (CJ.3 labels
    HTTP only), `[walk] tests` feeding the TESTS pass, typed-receiver inherited calls in TS.
- **Checked, no wrapper change:** C0.1-C0.7 (wave 0: empty module slots and the one dependency
  commit), C0.9 (the pyo3 `overlay_loop` slot CK.1 filled), CA.7 (the TS family's graph build on the
  engine pool; byte-identical output), CA.8 (grade.py exact matching, bench only), CB.6 (the build-time
  `CodeNav.nav_facts` table; CH.1b, CH.3b, CH.5a and CI.6 add build-time variants, never stored), CB.12
  (host narrowing moved into a shared private resolver module), CB.20 (the private Go mount pass; its
  identity effect is CB.23's), CC.1 (rev-delta entry points for diff-impact and tests-for), CC.2 (a
  crate-private ATTN / FAIL cell reader), CC.4a (projection-text's fidelity ladder; `prose` output
  unchanged), CD.1c (the domain profile's community weights; the wrapper builds no profile), CD.6a
  (graph's unused parser crates moved to dev-dependencies), CE.2a / CE.2b (shared parse cache keys and
  import, engine only), CE.3b-CE.3d (overlay candidate builds, `try`, `propose` / `accept`, engine only),
  CE.4c (a wikitext converter for doc sources), CK.2 / CK.3 (engram-export only), CL.11 (fixture data),
  and every CF matrix probe (bench test data only; CF.13a / CF.13b, the n/a list and the Kotlin matrix
  row, change artefacts the wrapper does not read).
