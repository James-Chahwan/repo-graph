---
name: 0.4.0 vision — Rust + new data format + multicellular nodes + mempalace bridge + dense text (one big-leap release)
description: 0.4.0 collapses Rust rewrite, dense data format, multicellular nodes, dense text projection, and mempalace bridge into one big-leap release; not split across 0.4/0.5/0.6
type: project
originSessionId: f5091c3e-4ad2-47ca-be6b-233c911fb6a7
---
**Confirmed 2026-04-16.** User collapsed the previously separate releases into one:

> "these should all be 0.4.0 the data format layer in rust and the big leap"

Items collapsed into 0.4.0:
- Rust rewrite (was tentatively 0.5.0+)
- New dense data format (was 0.4.0)
- Multicellular nodes — typed cells: code, intent, doc, test, fail, constraint, decision, env, conv, attn (was "later")
- Dense text projection — topology-first notation, legend sigils (was "later")
- mempalace bridge (was "later")

**Why bundle:** if Rust is the producer of the new format from day one, separating Rust from format is artificial. The format only matters if it's fast enough to use as the canonical runtime form, which means Rust. Multicellular nodes and dense text projection are the format. mempalace bridge is what proves the format crosses the structure↔memory boundary.

**Invariant for 0.3.0 design decisions:**
- Python never produces the new data format. Python's terminal output is enriched JSON in the existing schema.
- Rust impl is greenfield against the 0.3.0 fixture suite as its contract.
- Three projections from one Rust canonical: binary on-disk, dense text for LLMs, latent vectors.

**Acceptance criterion for 0.4.0 (revised 2026-04-16):**

Earlier "byte-for-byte on the unchanged output format" framing was rejected on user re-examination — it would force Rust to maintain a legacy serializer for a format about to be deprecated, lock Rust into Python's exact ID encoding/whitespace/key-ordering, and turn trivial serialization diffs into noise.

**Correct gate: structural equivalence on the fixture suite.**
- Rust 0.4.0 produces the new dense format only (no dual output).
- Test harness reads Python's 0.3.x JSON output AND Rust's new-format output for each fixture.
- Both get normalized to comparable shape: node id set, edge tuple set (from, to, type).
- Assert: Rust's graph is a structural superset of Python's — every relationship Python captures is present in Rust's output, plus whatever the new format adds.

This keeps the fixtures as a pass/fail gate without coupling Rust to Python's serialization choices. The fixtures have a job on both sides: regression lock for Python 0.3.x, structural-equivalence gate for Rust 0.4.0.

Implication for 0.3.x: fixture quality matters. A sloppy fixture locks in a sloppy spec. A tight fixture forces the Rust impl to capture everything Python did. The fixture's *graph content* is what matters, not the JSON bytes.

**In 0.4.0 (confirmed 2026-04-16, after I'd initially scoped these as optional/deferred):**
- **Latent-vector hooks are required, not optional.** Verbatim user: *"latent vector hooks need to be done not optional, this means we can hook our own local llm for testing which is awesome shit bro."* Rationale: enables a local LLM (candle/ort/llama.cpp) hooked directly against subgraph vectors for testing the latent projection inside the same release that defines it. Forces the projection-agnostic core to actually be projection-agnostic — three real consumers (binary, text, vectors) prove the abstraction. Also unlocks fast format-iteration loops without API billing.
- **Cross-repo graph merging.** Verbatim user: *"shouldn't cross-repo graph merging just be like cross-repo stack merging etc like it should be possible in 0.4.0"*. Reframed as cross-repo *stack* merging: frontend + backend + infra repos compose into one graph; flows cross repo boundaries (HTTP call from frontend resolves to route in backend). Schema implication: `NodeId` enum needs a `RepoId` component or a parallel `RepoId` table — must be decided before locking the binary format. Resolver implication: the existing cross-stack linking post-pass (string-match between `endpoint_*` and `route_*`) becomes a first-class resolver step over the merged symbol table. Sequencing implication: a multi-repo merge step lands between per-repo graph construction and serialisation.
- **Sharded file layout — one rkyv file per stack/repo + a cross-stack shard.** Confirmed 2026-04-17, verbatim user: *"absolutely include sharding in 0.4.0 for the seperate stacks in the repo thats too good of an idea and really awesome."* Layout: `.ai/repo-graph/{frontend,backend,infra}.rkyv` + `cross_stack.rkyv` (cross-repo edges only) + `manifest.json`. Editing code in one stack only rebuilds that stack's shard; other stacks' mmap'd views stay live. The cross-stack shard rebuilds when any per-repo shard changes but is small (cross-repo edges only). A reader mmaps all shards and walks them as a unified graph via the trait abstraction. **Why this fell out naturally:** rkyv files are write-once / read-mmap; updates always rebuild the whole file. Sharding is the only sane way to get incremental rebuild semantics without abandoning rkyv. Pairs perfectly with cross-repo stack merging — same architectural decision viewed two ways. Implementation lands as part of step 4 (multi-repo merge) and step 5 (rkyv serialisation).
  - **Single-repo default = one shard, no ceremony.** Verbatim user: *"yeah single repo makes sense just one then easy."* Sharding is opt-in for multi-stack repos.
  - **Shard discovery: LLM-assisted, post-first-generate.** Verbatim user: *"shard discovery would be optimal but config is a default for now. like a user could just ask you to do it after the graphs have been made once and you could infer it then write config, and it's super quick to regen?"* Pattern mirrors `repo-graph-init`: first run is single-shard; user asks Claude (or runs `repo-graph stacks --infer`) → Claude reads the existing graph, spots stack boundaries (package.json vs pyproject.toml vs go.mod clusters), proposes config, writes it. Regen with sharding is cheap.
  - **Schema version is manifest-level, not per-shard.** Corrected 2026-04-17 after I'd added per-shard versions to the design. Verbatim user: *"why is the schema version per shard so important, wouldn't it always be able to be fully regenerated if old?"* — caught the over-engineering. All shards in a project are produced by the same binary in the same generate run; per-shard versions are always identical by construction. One `schema_version` in `manifest.json`; mismatch wipes and regenerates everything (seconds). Per-shard `mtime` + `content_hash` + `depends_on` are still tracked, but for staleness/dependency, not compatibility. Per-shard versioning would only matter for shared-graph-artifact futures (CI publishes a shard, dev downloads it) — not 0.4.0 scope.
  - **Schema version = repo-graph binary version.** Confirmed 2026-04-17, verbatim user: *"schemas will be whatever version of repo-graph your on i guess"*. Manifest stores the binary's semver (e.g. `"schema_version": "0.4.0"`). Binary bump → manifest mismatch on read → auto-regen. No separate schema numbering to maintain.
  - **Pre-commit hook regen pattern, same as 0.2.0 dev.** Verbatim user: *"if regen is so quick just slap it in a pre-commit hook again lmao"*. Per-shard regen is fast enough (ms per shard in Rust) that a hook on changed files → rebuild affected shards → stage updated `.ai/repo-graph/` is viable and zero-context-cost. Mirrors the `feedback_precommit_hook_usage.md` pattern already in use.

**Deliberately deferred past 0.4.0 — TBD:**
- Graph-based IDE consumer (separate product)
- LSP integration

**Test corpus:** quokka-stack (not KinaSwap — corrected 2026-04-16). Multi-repo by nature, so it doubles as the cross-repo merging fixture.

**Format name: `gmap` (confirmed 2026-04-17).** Verbatim user: *"yeah the data format name is absolutely gmap as the json parellel the only reason not for .rgraph is this is an llm interface where in we provide all the map for context and the query and work write to directly interface with the llm reasoning hopefully?"*

Positioning: gmap is the **JSON-parallel for graph-as-LLM-context.** Not "a file format repo-graph emits" — an interface that LLMs reason against. The name does framing work the docs can't: file formats are things you read, interfaces are things you reason with. Standalone name (no "repo-graph gmap" — just "gmap"), the way nobody says "JavaScript JSON".

**Three projections, all called gmap:**
- **gmap binary** (`.gmap` file, rkyv-backed) — canonical, mmap'd, zero-copy. Engine + IDE + MCP server consume.
- **gmap text** (dense sigil notation: `>`, `x>`, `

, `^`) — LLM-readable. Returned from MCP tool calls, not stored on disk.
- **gmap vectors** (latent embeddings) — model-native. Hooked to local LLM via the latent projection.

Why this naming is load-bearing for the bigger product: positions latent-vector projection as first-class ("gmap vectors" reads naturally; ".rgraph vectors" doesn't); survives IDE rendering ("a view of the gmap"); survives mempalace bridge ("send the gmap into the palace"); works for the future write-path ("the LLM writes to the gmap"). File-format naming would have shut all of that down.

**Step 0 (rkyv hello world, exploratory probe — not yet a commitment to 0.4.0 Rust path):**
- Location: `repo-graph/rust/scratch/` (workspace root at `repo-graph/rust/Cargo.toml`)
- Edition: 2024
- rkyv version: **0.8** (not 0.7 — flipped after user pointed out "if you're writing it, more blog posts doesn't matter; pick the newer stabler API")
- Claude writes the code, user reads it (verbatim user: *"once i see it working my understanding will switch like i can read the code it's more the rustisms and see it's possible quickly"*)
- Framing: verbatim user *"it's really lets see what we can get and how it goes first step to learn a bunch and see if we should?"* — if rkyv's Owned/Archived split feels too painful in practice, walk away from the Rust path. Cheap probe.

**STEP 0 COMPLETED 2026-04-17 — green light to step 1.** Hello world compiles, runs, tests pass. User verbatim on the learning value: *"whelp this is why we doing step 0 aint it"*. Lessons actually surfaced (see `reference_rkyv_design.md` for full detail): (1) recursive `Box<NodeId>` failed at compile time, toolchain-confirmed flat-ID + side table is the right shape, (2) `Archived*` types don't auto-derive trait impls, need `#[rkyv(derive(Trait))]`, (3) rkyv 0.8 concrete API idioms captured. File size on 3-node toy case: JSON 252 bytes vs gmap 144 bytes (43% smaller, gap widens with scale). Workspace + scratch crate uncommitted on disk at `/home/ivy/Code/repo-graph/rust/`.

This memory is a vision pointer, not a plan. Detailed 0.4.0 scope is opened after 0.3.0 ships and the AST fixtures exist as a stable contract.

---

## 2026-04-17 design session — 0.4.0 expanded + sequence locked

User pasted a "context transfer from extended design conversation" reframing repo-graph as **a knowledge format primitive, not a code analysis tool**. Code is the first domain. Format is domain-agnostic. The AST layer is an input transformer for the code primitive type, not the product itself.

**Major shifts from earlier 0.4.0 framing:**

1. **Strict Node shape locked.** Earlier "pragmatic" Node `{id, repo, name, kind, parent, ...}` rejected — assumed code-domain hierarchy is universal (it's not: video frames have indices not names, molecules have elements not names). Final shape:
   ```rust
   struct Node { id: NodeId, repo: RepoId, confidence: Confidence, cells: Vec<Cell> }
   ```
   Navigation lives in **domain-owned indices stored alongside nodes in the container**, mmap'd zero-copy. Code domain ships `name_by_id`/`parent_of`/`children_of`. Other domains ship `by_timestamp`/`position_kdtree`/etc. Core knows nothing about any of them.

2. **CrossGraphResolver trait** (renamed from cross-stack). "Stack" was code-specific. User insight: *"axis of decomposition"* — stack is one axis, repo is another, security zone, team, runtime, human ownership all axes. Each domain registers resolvers for the relationships it knows about.

3. **HippoRAG spreading activation pulled INTO 0.4.0** (was post-0.4.0). Without it, repo-graph is "AST + nice format" — the commoditising space. With it = the synthesis nobody else has. Ships as v0.4.8.

4. **v0.4.9 multicellular cell population + v0.4.10 mempalace bridge are REQUIRED, not optional.** User verbatim: *"these aren't optional. i believe"*. Without them, "multicellular nodes" is empty cell slots and "mempalace bridge" is vapourware.

5. **Mempalace as direct dep, not MCP-routed.** Vendored from GitHub. In-process function calls, no IPC, no MCP server dance.

6. **quokka-stack is Go backend + Angular/TS frontend** (not TS+Python as earlier assumed). Step 3b parsers = Go + TypeScript with Angular layer.

7. **Path A / Path B split at v0.4.12:**
   - **Path A (v0.4.12a, the ship)** — text loop with Claude/etc. Skill-based interceptor. PyPI public 0.4.0 ships here.
   - **Path B (v0.4.12b, the proof)** — direct latent loop with local open LLM via candle (soft-prompt-prefix injection + constrained decoding for native structural-op output). SWE-bench Verified benchmark. The artifact is the number, not the release.

8. **Cell payload: `enum CellPayload { Text(String), Json(String), Bytes(Vec<u8>) }`** — user: *"c i mean rust loves that shit right ?"*

9. **Extensibility encoding:** GraphType is self-describing `String` (one per file, saving meaningless). CellTypeId/EdgeCategoryId/NodeKindId are `u32` registry-backed (high-volume, registry pays off). Registry lives in container header, not core.

10. **NodeId recipe locked:** `NodeId(u64) = xxhash(graph_type, repo, kind, qualified_name)` — graph_type now in the recipe so cross-domain graphs in one mempalace don't collide.

**v0.4.x sequence re-locked 2026-04-17 (candle slid into 0.4.13 — see below):**

The ship (0.4.0, text + binary projections only, no candle in wheel):
- v0.4.1 — repo-graph-core (domain types) — **COMPLETED + TAGGED 2026-04-17** at hash `93aa4d9`. 6 tests green. Strict Node shape works; NodeLike/EdgeLike traits uniform across Owned and Archived forms.
- v0.4.2 — Python parser (tree-sitter) — **COMPLETED + TAGGED 2026-04-17** at hash `02daa89`. 10 tests green (6 unit + 4 py_smoke fixture). `FileParse` carries nodes/edges/imports/calls/nav; intra-file resolution only. `CallQualifier::Attribute` kept untyped at parse time — v0.4.3's resolver disambiguates via import table.
- v0.4.3 — per-repo graph construction (Python) — **COMPLETED + TAGGED 2026-04-17** at hash `c64c6ec`. 4 graph tests green (2 unit + 2 py_smoke_graph integration), 21 workspace tests green, clippy clean. `build_python(repo, parses)` runs a 4-stage pipeline: merge → symbol table → `resolve_imports` → `resolve_calls`. Reproduces the 5 cross-file edges the Python 0.3.0 analyzer produced on py_smoke and drops `do_login→User.login` (unknown receiver type) into `unresolved_calls`. `SymbolTable` has four HashMaps keyed by node id so consumers never re-parse qnames. Traversal primitives (`neighbours`, `bfs`, `parent_chain`, `count_of_kind`) implemented on `RepoGraph`.
- v0.4.3b — Go + TypeScript parsers — **COMPLETED + TAGGED 2026-04-17** at hash `97101f4` (tag `v0.4.3b` local only, not pushed yet). Angular moved to 0.4.10 batch per user 2026-04-17: *"oh angular is now in the language parses 0.4.10 section like html and scss and vue and react"*:
    - **v0.4.3b.1 code-domain extract** — DONE. `rust/code-domain/` crate now owns `GRAPH_TYPE`, registry modules (`node_kind`/`edge_category`/`cell_type`), `ParseError`, `ImportStmt`/`ImportTarget`, `CallSite`/`CallQualifier`, `FileParse`, `CodeNav`. parser-python re-exports; no duplication across language parsers.
    - **v0.4.3b.2 parser-go** — DONE. `rust/parsers/code/go/` standalone crate. Tree-sitter-go 0.25. 4 unit tests green. `parse_file(source, file_rel, package_qname, module_import_prefix, repo)` emits Module/Struct/Interface/Function/Method with receiver-based method attachment (two-pass: `collect_types` builds `HashMap<String, NodeId>`, then funcs/methods). `module_import_prefix` (e.g. `"github.com/foo/bar"`) strips go.mod prefix from import targets to yield repo-local `::` qnames. `collect_calls_in` recurses but skips `func_literal` bodies. `classify_call` produces Bare/SelfMethod/Attribute/ComplexReceiver. Cells: Module gets whole-file Code+Position; entities get their own slice. Clippy clean (two `too_many_arguments` allows on helpers).
    - **v0.4.3b.3 parser-typescript** — DONE. `rust/parsers/code/typescript/` standalone crate. Tree-sitter-typescript 0.23 (`LANGUAGE_TYPESCRIPT`). 5 unit tests green. `parse_file(source, file_rel, module_qname, repo)` emits Module/Class/Interface/Function/Method. `visit_top` dispatcher handles import_statement, export_statement (unwrap + re-dispatch), class_declaration, interface_declaration, function_declaration, and `lexical_declaration/variable_declaration` hoisting of `const foo = () => {...}` / `const foo = function(){...}` to Function nodes. Imports parsed into ImportTarget::Module (side-effect, namespace `* as`) or ImportTarget::Symbol (default → `name="default"`, named). Raw source strings (`./user`, `@angular/core`) preserved — resolver closure in graph crate does path resolution. `extract_call_qualifier`: identifier → Bare, `this.foo` → SelfMethod, identifier.member → Attribute, else → ComplexReceiver. `collect_calls_in` stops at nested fn/class bodies.
    - **v0.4.3b graph integration** — DONE. `rust/graph/src/lib.rs` now exposes three entry points: `build_python`, `build_go`, `build_typescript<R: Fn(&str, &str) -> Option<String>>` (resolver closure for raw TS source strings). Shared `merge_parses` dedups nodes by `NodeId` — same-qname Modules from multi-file Go packages collapse onto one node with stacked cells. `build_symbol_table` handles STRUCT parent kind identically to CLASS (for Go methods). `resolve_calls` now resolves `CallQualifier::SelfMethod` by walking `parent_of` to the enclosing CLASS/STRUCT and looking up in `class_methods` — works uniformly for Python `self.x`, TS `this.x`, Go `u.x`. `resolve_imports_go` (path matches module_by_qname directly) and `resolve_imports_ts` (closure-based) added. `resolve_calls<H>` has an `extra_hook` seam for future language-specific resolution (unused today).
    - **v0.4.3b smoke fixtures + integration tests** — DONE. `tests/fixtures/go_smoke/` (go.mod + helpers/{helpers,extra}.go + users/users.go + auth/auth.go) exercises multi-file package dedup, intra-package cross-file bare calls, self-method via receiver var, cross-package attribute calls, go.mod prefix stripping. `tests/fixtures/ts_smoke/` (src/{helpers,user,auth}.ts + tsconfig.json) exercises named imports, namespace imports (`* as`), self-method via `this.`, intra-file bare calls, resolver-closure path resolution. `rust/graph/tests/go_smoke_graph.rs` and `rust/graph/tests/ts_smoke_graph.rs` each pass. **Workspace gate: 32 tests green across 16 targets, clippy --workspace --all-targets -D warnings clean.** Ready to tag v0.4.3b.
    - **v0.4.3b.4 Angular enricher** — MOVED TO 0.4.10 batch (rationale: Angular's UX is inseparable from HTML templates + SCSS — parsing TS decorators alone would leave dangling template/style refs, same argument that grouped HTML+CSS+Vue+React templates together). Angular enricher (Injects via EdgeCategory=8; roles via Intent cell) now lands with the templates/styles batch.
- v0.4.4 — multi-repo merge + CrossGraphResolver + HttpStackResolver
- v0.4.5 — rkyv store (.rg) + dense text projection
- v0.4.6 — pyo3 bindings (was 4.7 — slid earlier; Path A testable against 4.5 fixtures)
- v0.4.7 — HippoRAG spreading activation
- v0.4.8 — multicellular cell population (auto-derive + MCP write tools; register `:task` cell type here)
- v0.4.9 — mempalace bridge (vendored direct; concurrent-writers test)
- v0.4.10 — finish remaining language parsers + repo-testing sweep + **frontend framework batch** (Angular full stack — decorators/Routes/DI + HTML templates + SCSS, React + JSX, Vue SFCs, plain HTML/CSS). One batch because frameworks are inseparable from their templates+styles. Scope decision confirmed 2026-04-17 during v0.4.3b design, user verbatim: *"i guess if we html then we need also scss or css too then right ?"* — parsing templates without styles leaves dangling class-selector references. Angular moved into this batch 2026-04-17 (was 0.4.3b.4) — user: *"oh angular is now in the language parses 0.4.10 section like html and scss and vue and react"*.
- v0.4.11 — text loop + interceptor skill (Python/MCP glue; no candle)
- v0.4.12 — **PyPI publish → 0.4.0 tag** (wheel + Registry + GitHub release + GitLab mirror)

The proof (0.4.13, latent + multi-agent — separate release, another time):
- candle/latent integration (was 4.6 — moved here since Path A doesn't need it)
- SWE-bench Lite 20–30 problem subset on 4090 Runpod (~$20–30 total). Same model, different context.
- two agents sharing one .rg container (architectural proof of shared-state loop)

**Why this split:** 0.4.0 wheel has zero candle dep → lean install, fast Path-A iteration. 0.4.13 is the honest proof story — latent loop lit up, benchmark number, multi-agent demo. "0.4.0 ships the map; 0.4.13 ships the feedback loop."

**Output shape framing (confirmed 2026-04-17):** 0.4.0 only touches *local* outputs — `.rg` files on disk, mempalace writes, dense text into the LLM's context window, MCP write-tools (text-mediated, trivial shape). No model-generated structural ops that write back. 0.4.13 is where output stops being derivative: constrained decoding + soft-prompt-prefix means the model emits `ADD_EDGE(a,b,calls)` as its native output, not parsed text.

**Workspace crate naming locked (hyphenated, prefixed):** `repo-graph-core`, `repo-graph-parser-python`, `repo-graph-graph`, `repo-graph-merge`, `repo-graph-store`, `repo-graph-projection`, `repo-graph-py`. (Was `core-types`/`parser-py`/etc. — renamed.)

**File extension question to resolve:** earlier session locked `.gmap`. The 2026-04-17 context transfer used `.rg`. Ambiguity: are these two names for one thing, or did the user flip? Current working assumption: `.rg` is the file extension, `gmap` is the LLM-interface name (gmap binary / gmap text / gmap vectors). Confirm with user when v0.4.5 starts.

**Test corpus stays quokka-stack.** Now correctly understood as Go backend + Angular/TS frontend.

**See also:**
- `reference_format_spec.md` — dense sigil notation, multicellular cells, three projections, container header
- `reference_swe_bench_plan.md` — Path B benchmark plan (N=50/200, 4090, Runpod)
- `project_competitive_landscape.md` — positioning vs commoditising MCP code-graph space
- `project_050_domain_agnostic.md` — 0.5.0+ vision (chemistry/climate/policy/video as primitives)
- `feedback_research_timing.md` — don't hedge research timing with "weeks/months"
- `feedback_domain_assumptions.md` — don't smuggle code-domain into "universal" claims
