# repo-graph handoff - glia 0.5.5 -> 0.5.6

For: repo-graph (the MCP server wrapping glia-py). **Pin: `glia-py==0.5.6`.** Apply after the 0.5.4 and 0.5.5
handoffs (`dev-notes/repo-graph-handoff-0.5.4.md`, `dev-notes/repo-graph-handoff-0.5.5.md`).

**Status: written at glia HEAD `d3a264bf` (after wave W12 of 0.5.6), before the bump.** The version bump, the
`v0.5.6` tag and the `glia-py` / `glia-cli` publish are James's release steps after these docs; the pin above is
the one to take **once James tags `v0.5.6`**. Until then the workspace reads 0.5.5 and a wheel built from `main`
reports `0.5.5+p<stamp>` from `glia_py.build_stamp()`.

**Where repo-graph stands.** Read read-only at HEAD `0f8ecfa`: `pyproject.toml:31` still pins `glia-py==0.5.2`
and the uncommitted 0.5.2 port is in the working tree, so the 0.5.4 and 0.5.5 handoffs are not applied yet.
Apply them first, in order, then this one. Act on repo-graph only.

0.5.6 finishes started work (plan `dev-notes/next-leap-0.5.6.md`, packets `dev-notes/leap-056-packets.json`,
waves W0-W13): GA watch (the body-only fast path, multi-repo watch, one memory budget), GB concept search over
flows (placement measured FAIL and not shipped), GD per-language precision and recall, GH the host graph (plugin
hosts and environment hosts: who registers, who starts what), GP build speed and hygiene. No registry id
(next free stays node 51 / edge 39 / cell 28), no `FORMAT_VERSION` (3) or `MANIFEST_VERSION` (2) change, no
Cargo.lock move.

Sources, in order of authority: the code at `d3a264bf`; `git diff v0.5.5..HEAD -- py/api_surface/ cli/surface/`;
each packet's landed result (its `breaking` text) and commit body; the `HANDOFF FROM ..` paragraphs routed to
GZ.2 in `dev-notes/leap-056-corrections.json`. Packet ids are glossed in words; the hash after an id is the glia
commit that landed it.

---

## 0. TL;DR

1. **No wrapper code change is required.** Every pyo3 call repo-graph makes (`blast_radius`,
   `cross_stack_trace`, `find`, `node_cells`, `bfs`, `predecessors`, `WatchSession(repo)`, `poll`,
   `snapshot`, `persist`) keeps its signature; every surface change is an appended keyword, a new method or a
   new dict key (section 2).
2. **One cosmetic fix is worth making.** `_cell_text` (`repo_graph/server.py:771-775`) renders any ENTRYPOINT
   cell with `source == "main_guard"` as `(__main__ guard)` and `server.py:855` labels it `entry point`. Since
   GH.11 (`914510fb`, TS / JS script entries) a TypeScript module guarded by `if (require.main === module)` /
   `if (import.meta.main)` writes the same `source: "main_guard"`, so a TS module reads `(__main__ guard)`.
   Say `(main guard)`, or branch on the file extension in `decl`.
3. **New ENTRYPOINT sources and keys** (section 3.4): `host:<h>`, `shebang`, `script_arg`, plus `host` /
   `trigger` keys on host starts. The generic branch of `_cell_text` prints `decl pattern source` and stays
   correct; it just does not show `host` / `trigger`.
4. **Trace can now resolve by concept** (GB.1 `4598c291`, GB.3 `9bb8ca3d`): `resolved_by` reads `concept` or
   `concept_semantic`. `server.py:642-644` prints the value as-is, so `[resolved by concept]` appears; nothing
   breaks.
5. **Stored edge order is canonical** (GA.2 `af92cd26`): `bfs` / `predecessors` (`repo_graph/graph.py:114,126`),
   `neighbours`, `edges_json` and trace hops at one depth come back in (from qname, from kind, to qname, to
   kind), then category, confidence, cells order. A test that pins the old emission order moves.
6. **Graph content moves a lot** (section 4): routes gain their mount prefixes (Django, Flask / FastAPI,
   Express / Koa / Hono / NestJS, gin groups), new host nodes (`host_cmd:` / `host_event:` / `config:<host>:`),
   infra start edges, TS interface METHODs, Rust trait METHODs, `.mjs` / `.cjs` / `.mts` / `.cts` modules. Any
   test that pins a node count or a route name on a fixture repo re-records.
7. **Opt-ins worth adopting** (section 5): `WatchSession(.., memory_budget_mb=)`, `glia watch --embed`,
   `PyGraph.find_flows`, `PyGraph.concept_flows`, `query(.., max_mb=)`.

## 1. The pin

| file:line (repo-graph working tree, read-only) | now | change to |
|---|---|---|
| `pyproject.toml:31` | `"glia-py==0.5.2",` | `"glia-py==0.5.6",` (after the 0.5.4 / 0.5.5 handoffs) |
| `CLAUDE.md:28` | runtime deps `glia-py==0.5.2` | `glia-py==0.5.6` |
| `CLAUDE.md:131` | the 0.5.2 boundary notes | add the 0.5.4, 0.5.5 and 0.5.6 notes (sections 2-4 here) |

**Stamps and caches.** PARSER_STAMP / BUILD_STAMP moved at almost every packet (graph, engine, code-domain,
parsers and store edits). The first build after the upgrade reparses everything and rewrites `.glia/graph/`
(every shard's bytes change at least once, GA.2), and a calibration record (`glia history calibrate`) is read
only by the build that wrote it: recalibrate. Vectors (`.glia/vectors.jsonl`) are keyed by text hash and stay
valid; `glia embed` re-embeds only nodes whose text moved.

## 2. API and surface changes (all additive for a Python caller)

From `git diff v0.5.5..HEAD -- py/api_surface/ cli/surface/`:

| packet | pyo3 | CLI |
|---|---|---|
| GA.12 one memory budget, watch half (`2c204a31`) | `WatchSession(repo, overlay=True, memory_budget_mb=None, ..)`; `WatchSession.memory()` -> dict (`rss_kb`, `budget_mb`, `cached_groups`, `groups`, `cache_entries`, `memo_paths`, `evictions`, `memo_clears`, `rank`) | `glia watch --memory-budget-mb <MB>` (0 = none; overrides `GLIA_MEMORY_BUDGET_MB`) |
| GA.11 multi-repo watch (`a0e52d65`) | `WatchSession(.., with_repos=None, out=None)` (appended after `memory_budget_mb`, positional order kept); read-only `roots` property; `with_repos` without `out` is a `ValueError`; `persist()` writes to `out` when given | `glia watch --with <REPO>.. --out <DIR>` (`--with` without `--out` exits 2); `--max-latency-ms <N>`, default 2000 |
| GA.15 watch embeds (`067b3b5c`) | - | `glia watch --embed [--embed-model bge-small\|test-hash]`; `glia install-hooks --embed` |
| GA.14 one memory budget, rules half (`60fca954`) | `PyGraph.query(.., max_rows=None, max_mb=None)`, `PyGraph.query_gql(.., max_rows=None, max_mb=None)` | `glia query --max-mb <MB>` (0 lifts it; exit 2 when it trips) |
| GB.1 concept search over flows (`4598c291`) | `PyGraph.concept_flows(word, depth=6, limit=20, collapse=True, ..)` -> `{results, absence}` | `glia flows --concept <word>` (exit 0 rows, 1 the `no_match` absence, 2 error) |
| GB.3 the fused semantic concept tier (`9bb8ca3d`, `aec37667`) | `PyGraph.concept_flows(.., semantic=None)` | `glia flows --no-semantic` (with `--concept`), `glia trace --no-semantic` |
| GB.2 entry flows through a find hit (`6eea7286`) | `PyGraph.find_flows(query, top_k=20, depth=6, collapse=True)` -> `{results, absence, flows}` | `glia find --flows [--depth <n>]` (conflicts with `--files` / `--no-semantic`) |

GB.6's concept gate passed (`dev-notes/concept-gate-0.5.6.md`, `VERDICT: PASS`, C1 4/5, C2 4/5), so the
semantic tier of GB.3 ships. Nothing else on `py/api_surface/` or `cli/surface/` moved.

### Keys that changed meaning or gained values

- **Watch update dicts** (`WatchSession.apply` / `poll`, `glia watch` NDJSON): a `body_only` key after
  `groups_rebuilt` (GA.4 `6a52dff4`): the groups re-stitched by the body-only fast path, `python`, `typescript`
  (GA.6 `f82594d1`) or `go` (GA.7 `617f47b0`); Rust has no fast path in 0.5.6 (FA.1's verdict, `Rust: FAIL`,
  `dev-notes/surface-replay-0.5.6.md`). `GLIA_WATCH_FAST_PATH=0`, read at open, turns the path off. In a
  multi-repo session `groups_rebuilt` entries read `<label>:<key>` and file paths `<label>:<rel>` (GA.9
  `cbc88def`). An overlay edit now lists only the groups it moved (GA.17 `ba212f8e`); `full_rebuild` still
  reads `overlay`.
- **Delta and watch edge rows** (GA.18 `fbeb57f8`, `graph_delta`, `glia delta --json`, watch rows): a new
  change kind `restamped` (an edge whose EVIDENCE emitter / rule changed at the same confidence, e.g. a SCIP
  confirm of a Strong edge), and every row gains `rule`, `was_emitter`, `was_rule`; counts gain
  `edges_restamped`. A wrapper that switches on `change` must accept `restamped`.
- **Trace** (GB.1, GB.3): `resolved_by` may read `concept` or `concept_semantic`. An unknown word, or a dead
  end found by name / find, can now resolve through the flows that touch it; an exact-qname dead end still ends
  in its `no_edges` absence. Concept rows carry a `tier` (`entry`, `hop_name`, `hop_qname`, `kind`,
  `mechanism`, `data_entity`, `external_host`, `doc`, and GB.3's `semantic`, last) and, for `semantic`, a
  `similarity` key (absent otherwise).
- **Rules** (GA.13 `f2c8c3f5`, GA.14, GA.16 `1fb0ec17`): the row budget now charges intermediate bindings, so a
  query near its budget may stop earlier (pyo3 `ValueError`, CLI exit 2) and the Budget text says `bindings`.
  A set `GLIA_MEMORY_BUDGET_MB` (the watch budget) also bounds `query`, check's rule invariants, review and the
  overlay trial: a trip raises `ValueError` starting `<query>:<l>:<c>: error: memory budget:` and the rule
  error kind is `memory_budget`. `--explain` witnesses are BFS-shortest at their tier, so some get shorter; a
  fact-tier prefix inside a derived row's witness may show derived support. Rows, tiers and caveats are
  unchanged.
- **Health** (GH.10 `db342162`): `.mjs` / `.cjs` / `.mts` / `.cts` are parsed now, so they leave `unparsed`
  (`glia_engine::health::CODE_LIKE_EXTS` 36 -> 32 entries).

## 3. Cells and keys the wrapper renders

### 3.1 CODE cells with a Json payload (new)

- INFRA_RESOURCE image / service / workload / process nodes carry start cells (GH.15 `04e5af09`, GH.16
  `cf8c2a5c`, GH.17 `a3c9ed5d`): `{"start":{"host":..,..}}` (Dockerfile stages, compose services, k8s
  containers, Procfile types, systemd units, supervisord programs), `{"build":{"host":"compose"|"skaffold",..}}`
  on declared images, and `{"script":<repo path>,"exec":<line>,"row":<1-based>}` when a start names an entry
  script the build read (GH.19b `47f00873`).
- A package.json MODULE with scripts carries `{"pkg_scripts":{"file","scripts":[{name,cmd,line}]}}` (GH.19
  `9679d051`); a package.json with scripts but no dependency and no bin is a new synthetic MODULE.
- A manifest-declared CLI_COMMAND (`cli:<bin>`) carries `{"manifest":"cargo|pyproject|setup|npm|gemspec|composer",
  "file","line","target"}` (GH.20 `b91169a6`) and a HANDLED_BY to its implementation.

`_cell_text` falls through to `json.dumps` for these; a renderer that prints CODE as source text should skip a
dict payload.

### 3.2 ORIGIN keys

- Maven / Gradle PROJECTs gain `coordinate` (`package:maven:<g>:<a>`, GD.32 `c7a9b3ef`).
- A PROJECT whose tsconfig declares `outDir` gains `ts_out` `{"tsconfig","dir","out_dir","root_dir"}` (GH.19b).
- An npm PROJECT's `subpaths` may hold a `*` pattern key (GD.33 `25775504`): a reader of `subpaths` as literal
  subpath -> file must skip keys containing `*`.

### 3.3 ROLE

- Dart CLASSes whose in-repo heritage reaches a COMPONENT gain ROLE COMPONENT (GD.10 `e427dea5`).
- A TS `memo(..)` / `forwardRef(..)` const is a FUNCTION with ROLE COMPONENT (GD.11 `ec4946df`), and a
  capitalised top-level function or arrow rendering JSX gets ROLE COMPONENT from the AST (GD.39 `f32a3248`);
  react.rs's line-scanned standalone COMPONENT markers are gone in TS-family files.

### 3.4 ENTRYPOINT

New sources, each `{"decl":"<file>:<1-based row>","source":..}`:

| source | on | packet |
|---|---|---|
| `host:love`, `host:neovim`, `host:wezterm` | LOVE `love.<cb>` FUNCTIONs, plugin-unit MODULEs | GH.4 `390cb981` |
| `shebang`, `script_arg` | Lua script MODULEs | GH.4 |
| `host:nginx` | an nginx conf MODULE with an init / init_worker / exit_worker Lua phase | GH.6 `dfc62ecd` |
| `host:pytest` | pytest hooks and fixtures | GH.8 `64bca53a` |
| `host:vscode` | an extension's exported `activate` / `deactivate` | GH.9 `85314804` |
| `host:obsidian`, `host:webpack` | plugin METHODs | GH.10 |
| `main_guard`, `shebang` | TS / JS script MODULEs (`require.main === module`, `import.meta.main`, a `#!` naming node / deno / bun / tsx / ts-node) | GH.11 |
| `host:docker`, `host:compose`, `host:k8s`, `host:procfile`, `host:systemd`, `host:supervisor` | the code a container / process start runs; extra keys `host` (the infra qname) and `trigger` (`container_start`, `schedule`, `process_type`, `boot`, `supervised`) | GH.18 `f1017cdc`, GH.19, GH.19b |

A Dockerfile stage is a launch only when a compose / k8s file targets it or it is the final stage (James
2026-11-01): a stage with its own ENTRYPOINT / CMD that no file in the repo targets gets no start edge.

## 4. Graph content (no code change; answers change)

**Resolve passes: 19** (`[passes] domain=code resolve=19 post=9 finalize=2`): GH.6 adds `resolver:host`
after `config`. Its edges carry emitter `resolver:host`, rules `<directive>` (nginx), `script_file` /
`script_call` / `script_eval` / `include_str` / `include_bytes` (GH.7 `e8b517f8`), `<host>:<form>` starts
(`docker:script`, `compose:module_attr`, `procfile:celery_app`, `compose:pkg_script` ..), `<host>:via_script`
(GH.19b) and `manifest_bin` (GH.20).

### 4.1 Re-keyed nodes (a qname or kind moved)

| packet | old -> new |
|---|---|
| GD.40 Django include mounts (`6b19e684`) | `ANY workspaces/<str:slug>/views/` -> `ANY /api/workspaces/<str:slug>/views/`; regex anchors dropped (`ANY ^admin/` -> `ANY /admin/`); `ANY <include prefix>` ROUTEs and `PATCH <mock target>` ROUTEs (`@mock.patch`) gone; Django ROUTEs gain POSITION |
| GD.41 Flask / FastAPI mounts (`fb5a02d9`) | `POST /filter` -> `POST /artifacts/filter`; a blueprint under url_prefix `/svc`: `GET /items` -> `GET /svc/items` |
| GD.42 Express / Koa / Hono / NestJS mounts (`beb6fc62`) | `GET /health` under `app.use('/api', routes)` -> `GET /api/health`; NestJS global prefix and RouterModule paths (`GET /albums @server` -> `GET /api/albums @server`) |
| GD.28 gin groups chained through `.Use(..)` (`4242b652`) | `POST /createAuthority` -> `POST /authority/createAuthority` |
| GD.14 Go route residuals (`f5898fcc`) | field-mount routes re-keyed under clause-named owners; new gorilla `.Methods(..)` and chi / echo `Method(..)` ROUTEs |
| GD.16 OpenAPI `servers:` at indent 0 or in flow style (`681d9b4a`) | `contract::<doc>::GET:/x` -> `contract::<doc>::GET:<base>/x` (prefect-databricks: 32 ops gain `/api`); DOCUMENTS pairs `exact` instead of `prefix` |
| GD.19 GraphQL client residuals (`57893857`) | `graphql_op:client.query` / `graphql_op:request` / `graphql_op:useQuery` .. are gone where the call holds its own document; a Dart anonymous or by-value document is `graphql_op:<op name \| first root field>` |
| GD.11 TS value positions (`ec4946df`) | `memo` / `forwardRef` consts: STATE_VAR / standalone COMPONENT -> FUNCTION (same qname, new kind) |
| GD.38 TSX grammar for .tsx / .jsx / .js / .mjs / .cjs (`0c14aec4`) | locals the old grammar's recovery hoisted to module-level FUNCTIONs are gone; standalone COMPONENT / HOOK markers fold into their FUNCTION (twenty: standalone 1202 -> 250) |
| GD.39 JSX (`f32a3248`) | a standalone COMPONENT with no same-qname FUNCTION is gone (twenty 105272 -> 105059 nodes) |
| GD.17 Elixir (`b0d29de6`) | a behaviour module that also defines functions: PACKAGE -> INTERFACE (qname kept) |
| GD.18 Ruby Bunny (`6115d1f3`) | `queue_producer:unresolved:rabbitmq` -> `queue_producer:<exchange>`, `queue_consumer:unresolved:rabbitmq` -> `queue_consumer:<exchange>`, paired by QUEUE_FLOWS |
| GD.23 Solidity (`c03557db`) | an undocumented literal-constant state variable has no STATE_VAR; its public getter `evm:<C>.<name>` is CONTAINed by the file MODULE, with no HANDLED_BY |
| GH.13 Dockerfile image identity (`1bf73a3e`) | `infra:image:--platform=$BUILDPLATFORM` gone; a Dockerfile under a generic dir takes the nearest non-generic ancestor (`infra:image:src` -> `infra:image:cartservice`; a root `app/Dockerfile`, every directory generic, is named `image`); no image for a FROM naming a stage, `scratch` or an unfilled `$VAR` |
| GD.25 nested `build/` / `out/` source dirs (`190d347d`) | a REGION `build_output` for a nested `build/` or `out/` that is not at a repo or project root is replaced by that directory's nodes |
| a11ec18d `.yarn` | `.yarn/` is a vendored REGION like node_modules: no nodes under it |

### 4.2 New nodes

- **Host graph** (GH.2 `c29f5bd7`, GH.3 `d9a4b89e`, GH.5 `97f7a265`, GH.8, GH.9, GH.10): CLI_COMMAND
  `host_cmd:<host>:<name>` (Neovim, Maki, VS Code, Obsidian; never a `cli:` command, CliResolver does not pair
  them with shell invocations), EVENT_HANDLER `host_event:<host>:<event>` (Neovim autocmds, WoW, AwesomeWM,
  Flask hooks, VS Code `onDid*`, Obsidian, webpack hooks), CONFIG_KEY `config:<host>:<key>` (WezTerm, Neovim
  options, VS Code `getConfiguration(..).get(..)`; never paired as SHARES_CONFIG), FUNCTIONs `command <name>` /
  `on <event>` for anonymous handlers (a call inside one moves from the enclosing scope to it).
- **Environment hosts** (GH.6, GH.15-GH.17): nginx conf MODULEs (`deploy::nginx.conf`) with ROUTE `ANY <path>`
  HANDLED_BY the Lua module a `content_by_lua_file` names; CLI_INVOCATION `cli_invoke:<bin>` from Dockerfiles;
  synthetic MODULEs for Procfile / systemd / supervisord and INFRA_RESOURCE `infra:process:<type>@<dir>`,
  `infra:unit:<stem>`, `infra:program:<name>`; skaffold artifacts mint their `infra:image:<name>`.
- **Languages:** TS interface member METHODs `<module>::<Interface>::<member>` (GD.2 `e79a4d6e`); Rust trait
  METHODs `<trait>::<fn>` (GD.5 `39c7f9e0`); Swift protocol requirement METHODs (GD.15 `75893093`); Elixir
  protocol-head and StreamData `property <name>` FUNCTIONs, elixir-grpc servers / clients, Absinthe resolvers
  (GD.17); CommonJS `exports.k = function` FUNCTIONs (GD.11); `.mjs` / `.cjs` / `.mts` / `.cts` MODULEs
  (GH.10; zora-protocol 0 -> 5 modules); PACKAGE_DEP from Cargo dotted / target tables, pyproject optional
  deps and dependency groups, every Poetry group (GD.37 `3ea90c58`); CONFIG_KEY `config:env:<X>` (Dart) and
  `config:setting:<app>:<key>` (Elixir), PHP CLI_INVOCATIONs, `package:args` / pubspec / gemspec CLI_COMMANDs
  (GD.21 `326242e2`).
- **Mechanisms:** EVM clients in TS (GD.20 `30af8154`, GD.30 `1bcdcac5`, GD.31 `3bd4d914`); GraphQL
  concatenated / by-value documents and aliased / namespace / CommonJS / apollo-angular transports, graphql-ruby
  roots (GD.19); TS inferred-wrapper ENDPOINTs through class heritage (GD.26 `72605887`; plane loses 62 phantom
  ROUTEs read from `this.post('/x', data)`), class-resource and ESLint `/* global X */` clients (GD.29
  `3ce330f5`).

### 4.3 New and removed edges

- **Added** (no node removed): Go single-type-argument instantiation CALLS (GD.1 `a251c999`); TS receivers
  through default imports, subclass statics, inherited members, module consts, TestBed / awaited / subscribed
  results, interface-typed receivers (GD.2, GD.3 `b7bf8f3d`, GD.4 `65d1a467`); TS imported type names USES
  (GD.27 `34c7812f`; plane's IWorkspaceView went from a `no_edges` absence to 3317 impact rows); JSX
  `jsx_element` / `jsx_attribute` USES (GD.39); C++ base clauses INHERITS_FROM and base-member CALLS (GD.6
  `90222425`); Python decorator-registered handlers HANDLED_BY their def and fact-tier star re-exports (GD.9
  `d986ed23`); Dart barrels (GD.8 `d67f2698`), generated riverpod providers and BuildContext reads (GD.22
  `666aaa65`); Angular template member reads (GD.24 `7d9707cf`); Go wire cells and handler USES (GD.13
  `47788a1d`); TS wire shapes (GD.12 `fd63ffb3`); Ruby dry-auto_inject / mixin CALLS (GD.18); JVM org routing
  (GD.32: org_import / org_call / org_ref for Java / Kotlin), more npm / cargo org edges (GD.33); infra
  INFRA_REFERENCES image -> base and compose service -> image (GH.13, GH.16); HANDLED_BY from infra starts to
  code (GH.18, GH.19, GH.19b), from manifest CLI_COMMANDs (GH.20), Python / Rust USES into script MODULEs
  (GH.7).
- **Removed:** false Rust MODULE -IMPLEMENTS-> trait edges for foreign / reference / blanket impls (GD.5);
  heritage from a qualified framework base to a same-named app type, heritage self-loops, PHP IMPORTS of an
  unowned namespace (GD.7 `4b077825`); `tail_unique` IMPORTS to mechanism nodes, self, Go stdlib / foreign
  modules, JDK / .NET platform roots (GD.34 `3b025619`); cross-directory TESTS name_match when the test has an
  own-directory candidate, Go cross-directory TESTS, flutter drive hosts (GD.36 `4844ddfe`); WoW
  `RegisterEvent` / `SetScript` as CALLS sites (GH.3).
- **Moved:** a Rust `use` inside an inline `mod` starts at the inline PACKAGE, not the file MODULE (GD.35
  `aa4dde8d`).

### 4.4 Answers that move with it

- **dead_symbol** shrinks: interface members in every language are withheld (GD.2, `[dead-interface]`), Go
  `init` is live only when its package is in use (GD.10), more framework / host entries (GH.4, GH.8-GH.11,
  GH.18), JSX and type-position USES (GD.27, GD.39; twenty dead_symbol 6143 -> 4189).
- **impact / blast-radius** gain `infra:*` rows and `live` flips to true on host-started modules (GH.18).
- **tests-for / review's tests** change on repos with cross-directory name matches (GD.36).
- **HTTP pairing** grows with mounted routes (plane 0 -> 404 HTTP_CALLS pairs, prefect 22 -> 303).
- **Coverage / absence caveats**: new rows (python HANDLED_BY for GH.8, typescript HANDLED_BY and
  DEFINES_CONFIG for GH.9, `host` HANDLED_BY for GH.18, a c_cpp INHERITS_FROM row for GD.6; the Dart CALLS
  caveat no longer lists export barrels, GD.8).
- **Rankings may reorder** (blast-radius, diff-impact, review, pack) on repos whose graph moved; the close-out's
  rank and cohort gates read them.

## 5. New primitives worth adopting (all optional)

- **Bound the held session.** `glia_py.WatchSession(repo, memory_budget_mb=<MB>)` evicts cached group builds
  and memos past the budget (GA.12). The budget counts the whole process RSS, so the MCP host's own memory is
  included; on glia the unbudgeted plateau was 940 MB, every cache evicted 779 MB. `session.memory()` reports
  it.
- **Embed as you watch.** `glia watch --embed` embeds changed / un-embedded nodes after each update (GA.15),
  and `glia install-hooks --embed` adds `glia embed . --limit 2000` to the rebuild hooks.
- **Flows by concept.** `PyGraph.concept_flows(word)` and `PyGraph.find_flows(query)` give the trace tool a
  "which flows touch X" answer; `cross_stack_trace` already falls back to it (`resolved_by: concept`).
- **Rules memory.** `query(.., max_mb=)` / `query_gql(.., max_mb=)`.
- **Multi-repo watch.** `WatchSession(repo, with_repos=[..], out=<dir>)` keeps a joint build of several repos;
  its layout goes to `out`, never a repo's own `.glia/graph/`.

## 6. Not in 0.5.6

- **No `glia place` / `PyGraph.place`.** Placement measured FAIL (`dev-notes/place-eval-2026-11.md`:
  `Placement: FAIL (directory: no ranker beats the best control ..)`); GB.5 was not built.
- **No Rust body-only watch path** and no `rebuild_rust_bodies` (FA.1: `Rust: FAIL`, body-only 0.316 < 0.40).
- **No docs-as-a-second-graph rows** (`via_doc`): GP.9 measured FAIL, GP.10 / GP.11 were not built; the
  section-level doc ties are parked for 0.5.7.

## 7. Re-test

1. `pip install glia-py==0.5.6` into repo-graph's venv; `make test` (or `pytest tests/`).
2. Expect re-records where a test pins: an edge order out of `bfs` / `predecessors`, a dead-code row of an
   interface member, a route name under a mount, a node count.
3. In a live MCP session: `impact` on a Dockerfile-started module now lists `infra:*` rows; `trace` of an
   unknown word may answer `[resolved by concept]`; `read` of a TS script MODULE shows its `main_guard` entry.
4. Watch: edit a Python / TS / Go function body, the update's `body_only` names the group; edit
   `.glia/overlay.toml`, `groups_rebuilt` lists only the groups it moved.

## 8. stderr markers (only for a stderr parser)

New lines: `[watch] fast_path ..`, `[watch] rss ..`, `[rules] mem ..`, `[dead-interface] ..`, `[route-mounts]
..`, `[py-django] ..`, `[evm-instances] ..`, `[dart-bloc] ..`, `[nginx] ..`, `[host-resolve] ..`,
`[host-start] ..`, `[ts-out] ..`, `[timing] grafts ..`, `[calibrate] ppr prefetch ..`, `[recv] ts inherited:
..`. Lines that gained fields: `[watch] update` (`body_only=`, `restamped=`), `[watch] listening`
(`max_latency_ms=`, ` repos=`), `[watch] persisted` (` out=`), `[delta] base=` (` restamped=`), `[rules] eval`
(` shortest_fixed=`), `[trace]` (` concept_tier=`), `[timing] persist` (` spans_ms= encode_ms= write_ms=`),
`[resolve-pool]` (` hook_pooled= hook_serial=`; TS ` imports_ms= merge_ms=`; Go `serial_hooks=-`),
`[graft-memo]` (` imports hit= index=`, ` wrappers hit= scan hit=`), `[live]` (` init_gated=`), `[invoked]`
(` aliased= intermediate=`), `[org-packages]` (` maven=`), `[graphql-transport]` (` aliased= namespace= cjs=
apollo_angular=`), `[model-schemas]` (`aliases=`), `[dart-riverpod]` (`generated=`), `[rust-types]`
(`trait_methods= cross_file_self= method_implements=`), `[walk] collapsed` (` build_source=`), `[tests] module
TESTS edges:` (` own_dir= drive_hosts=`), `[http-wrappers]` (` heritage= ..`), `[angular-template]`
(` member_reads=`), `[host]` (`loads=`), `[sol-abi]` (`literal_constants=`). GA.11, GA.4 and GA.18's watch lines
are the ones a watcher log reader sees.

## 9. Packet index

Every 0.5.6 packet whose landed result declares a consumer-visible change, and where it is listed:
GA.2 (s0, s4), GA.4 / GA.6 / GA.7 / GA.9 / GA.17 (s2 watch keys), GA.11 / GA.12 / GA.15 (s2), GA.13 / GA.14 /
GA.16 (s2 rules), GA.18 (s2 delta), GA.19 / GA.20 / GA.21 / GP.2 / GP.3 / GP.4 / GP.5 (s8 markers), GB.1 / GB.2
/ GB.3 (s2), GD.1-GD.42 (s4; GD.10 also s3.3, GD.32 / GD.33 s3.2), GH.2-GH.11 and GH.13 / GH.15-GH.20 (s3, s4),
GH.10 (s2 health). Not shipped, so nothing to adopt: GA.5, GB.5, GP.10, GP.11. Additive engine-only or
bench-only, nothing for repo-graph: GA.1, GA.3, GA.8, GA.10, GB.4, GB.6, GH.1, GH.12, GH.14, GP.1, GP.6-GP.9,
GP.12-GP.16.
