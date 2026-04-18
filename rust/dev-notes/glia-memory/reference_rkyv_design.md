---
name: rkyv + mmap design model for 0.4.0 Rust impl
description: Architectural mental model for 0.4.0's storage layer — zero-copy via rkyv, mmap-as-default, write-once-rebuild-whole-file, sharding for incremental updates
type: reference
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
Captures the rkyv design discussion (2026-04-17) so the Rust 0.4.0 implementer doesn't re-derive it. Pair with `dev-notes/0.3.0-decisions.md` (what + why for the AST layer) — this file is what + why for the storage layer.

## The core invariant

**Write once, mmap forever, read in place, deserialise only at boundaries.**

This is the whole reason for picking rkyv over JSON. If you ever find yourself routinely deserialising the whole graph into owned types, you've defeated the design — at that point JSON would be simpler.

## Why zero-copy matters for repo-graph

- **Startup latency.** MCP server starts → graph loads → first tool call returns. With JSON, every startup pays parse cost. With rkyv + mmap, startup is constant-time regardless of graph size.
- **Memory footprint.** OS pages parts of the file in/out as touched. A 1GB graph queried by a process using only RAM for the parts actually read.
- **Multi-process sharing.** Two processes mmap'ing the same file share physical pages. Future IDE + MCP server reading the same graph = no duplication.
- **Latent vectors especially.** Big arrays of floats; mmap means "load 10GB of vectors" is free until touched.
- **Cross-repo merging.** Multiple stack shards stay mmap'd, not duplicated.

## The Owned vs Archived type split

- rkyv generates a **parallel type** for every type containing pointers: `String` → `ArchivedString`, `Vec<T>` → `ArchivedVec<Archived<T>>`, `Box<T>` → `ArchivedBox<Archived<T>>`, etc.
- They're **not the same struct**. Owned has absolute pointers (only valid in the allocating process); archived has relative offsets (valid wherever the bytes are mmap'd).
- `&NodeId` and `&ArchivedNodeId` cannot be passed interchangeably. Different layout, different methods.

## How to handle both — trait-based generics

```rust
trait NodeIdLike {
    fn name(&self) -> &str;
    fn kind(&self) -> NodeKind;
}
impl NodeIdLike for NodeId         { ... }
impl NodeIdLike for ArchivedNodeId { ... }

fn process<N: NodeIdLike>(node: &N) { ... }
```

- One function source, two specialised compiled versions (monomorphisation), zero runtime overhead.
- Most of the codebase = generic functions over `NodeIdLike` (and similar traits per type).
- Generic structs (`Graph<N>`) when a struct *holds* one of those types.
- Trait objects (`Box<dyn NodeIdLike>`) almost never needed.
- Enum dispatch (`enum AnyNode { Owned, Archived }`) only if you ever need to mix both in one collection (you probably won't).

## What "having both" means in practice

- **Files on disk:** can have `nodes.json` and `nodes.rkyv` simultaneously (debug mode). Trivial.
- **Both representations in RAM:** call `archived.deserialize(&mut rkyv::Infallible)` to get an owned copy. Allocates. Use at boundaries (pyo3 FFI, JSON export, mutation).
- **One struct that's both at once:** physically impossible. Pointer field and offset field can't share bits.
- **Code that works against both:** trait + generics. This is "having both" in the only sense that matters.

## The lifecycle (correcting the "shift state back and forth" misconception)

Zero-copy is **not** a ferry between RAM and disk. It's "we stopped taking the ferry."

**Step 1 — Generate (once per scan):**
```
scan repo → build owned Graph in RAM
         → rkyv::to_bytes(&graph) → Vec<u8>
         → write to graph.rkyv.tmp → atomic rename
         → drop owned graph
```
Cost: pay parse + alloc + serialise once.

**Step 2 — Use (every read, forever):**
```
Mmap::map("graph.rkyv") → &[u8]
rkyv::check_archived_root::<Graph>(&bytes) → &ArchivedGraph
... traverse, query, BFS, render ...
```
Cost: zero. No parse, no allocate, no copy.

**Step 3 — Boundary deserialise (rare):**
- pyo3 returning a node to Python → deserialise that one node, hand across, drop.
- JSON export → deserialise on the way out.
- Mutation → deserialise the slice, mutate, re-serialise the file.

## Mutation model — no in-place edits

- mmap is read-only in this design. rkyv format is offsets-pointing-at-offsets; can't insert without shifting every following offset.
- **All updates rebuild the whole file.** Build owned graph, serialise, atomic rename. Done.
- File sizes are small (single-digit MB even for huge graphs), so rebuild + write is milliseconds.
- Atomic rename via `tmp` + `rename()` means no torn-write window. Existing readers hold the old inode and keep their mmap valid until they re-mmap.

## Incremental updates = sharding (not byte-level edits)

- **Within a file:** never edit. Always rebuild the whole shard.
- **Across files:** shard intelligently so rebuild scope stays narrow.
- Layout: `.ai/repo-graph/{frontend,backend,infra}.rkyv` + `cross_stack.rkyv` + `manifest.json`.
- Edit code in one stack → only that shard rebuilds. Others' mmap'd views stay live.
- See `project_040_vision.md` sharding bullet for full design.

## Recursive enum vs flat ID + table — the resolved choice

Two ways to encode hierarchy in `NodeId`:

**Recursive:** `Method { class: Box<NodeId>, name }` — self-describing, but every edge stores full ancestor chain twice (once each side); no cheap eq/hash; rkyv gets `ArchivedBox` indirection at every level.

**Flat ID + table:** `NodeId(u64)` opaque, hierarchy lives as `parent: Option<NodeId>` field on a side `NodeMeta` table — tiny edges (24 bytes), trivial eq/hash, rkyv loves it.

**Decision: flat ID + table for the canonical format.** Edge storage dominates everything else; that's where recursive bleeds. Indirection cost is zero in code that already has a `&Graph` in scope (most code).

**Open sub-decision (settle in step 1 of sequencing):**
- (a) `NodeId(u64) = xxhash(language, repo, kind, qualified_name)` — deterministic, regenerable, survives merge.
- (b) Session-local u64 + separate `StableId(String)` for external references — simpler core, two ID concepts.
- Lean (a) — survives mempalace bridge, survives shard regen.

## Step 0 — rkyv hello world (do this before step 1 proper)

50 lines, one file. Forces toolchain install, dev loop setup, and rkyv constraints into your fingers before committing to the full type hierarchy. **Framed as an exploratory probe**, not a commitment — if rkyv's Owned/Archived split feels too painful in practice, walking away from the Rust path is the right call.

**Location & layout (confirmed 2026-04-17):**
- Workspace at `repo-graph/rust/Cargo.toml` (inside the existing repo, no separate repo)
- First crate: `repo-graph/rust/scratch/` (throwaway; deleted or kept as regression test once step 1 begins)
- Future crates added as workspace members: `core-types`, `parser-py`, `graph`, `merge`, `serde-json`, `rkyv-store`, `latent`, `py-bindings`

**Toolchain:**
- `rustup default stable` (need 1.85+ for edition 2024), add `clippy rustfmt`
- `cargo install cargo-watch` (optional)
- Edition: **2024** (no reason to start a fresh 2026 project on 2021)

**Cargo deps:**
- `serde = { version = "1", features = ["derive"] }`
- `serde_json = "1"`
- `rkyv = { version = "0.8", features = ["bytecheck"] }` — **0.8 not 0.7.** API restructured but for a fresh project, the newer/stabler API wins over "more blog posts exist for 0.7".
- `memmap2 = "0.9"`

**Authorship:** Claude writes the code, user reads it. User's framing: *"once i see it working my understanding will switch like i can read the code it's more the rustisms and see it's possible quickly"*.

## Step 0 outcomes (executed 2026-04-17)

**Status: PASSED.** Workspace + scratch crate live at `/home/ivy/Code/repo-graph/rust/` (uncommitted). `cargo build` green, `cargo run` prints zero-copy reads from mmap, `cargo test` green. User verbatim on the experience: *"whelp this is why we doing step 0 aint it"*.

**Local environment quirk:** Rust 1.95.0 stable is installed at `~/.cargo/bin/` but **not** on the default shell PATH. Every Bash invocation needs `export PATH="$HOME/.cargo/bin:$PATH" &&` prefix. Toolchain installed via rustup; `rustup show` confirms `stable-x86_64-unknown-linux-gnu` active.

**Concrete lessons surfaced (saved hours of step-1 churn):**

1. **Recursive `Box<NodeId>` failed at compile time** — exactly as the design doc predicted: `error[E0275]: overflow evaluating the requirement Box<NodeId>: Archive`. rkyv 0.8's trait resolution can't handle self-recursive enums via Box without `#[rkyv(omit_bounds)]` ceremony. **The toolchain mechanically confirmed the flat ID + side table decision** — no longer just a paper argument.

2. **`Archived*` types don't auto-inherit trait impls.** Adding `#[derive(Debug)]` to `NodeKind` does NOT give `ArchivedNodeKind` a `Debug` impl. You opt the archived type in explicitly: `#[rkyv(derive(Debug))]` on the original. This pattern applies for any trait you want on the archived side.

3. **rkyv 0.8 API forms (different from 0.7):**
   - Serialise: `rkyv::to_bytes::<rkyv::rancor::Error>(&value)` returns `AlignedVec`
   - Zero-copy access: `rkyv::access::<rkyv::Archived<T>, rkyv::rancor::Error>(&bytes)` returns `Result<&Archived<T>, _>`
   - Deserialise (allocates): `rkyv::deserialize::<T, rkyv::rancor::Error>(archived)`
   - Standard error type: `rkyv::rancor::Error`
   - Feature flag: `bytecheck` (not `validation` like 0.7)
   - Derives: `#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]`

4. **Reading from archived form:**
   - `ArchivedString::as_str() -> &str`
   - `Archived<u64>::to_native() -> u64` (endian conversion if needed)
   - `ArchivedVec::iter()` walks `&ArchivedT` directly from mmap'd bytes — no allocation

5. **Workspace + edition 2024 needs `resolver = "3"`** in workspace `Cargo.toml`.

**Size evidence (3-node toy case):**
- `nodes.json` = 252 bytes
- `nodes.gmap` = 144 bytes (43% smaller)
- Gap widens with scale because rkyv overhead is fixed while JSON's per-field cost scales linearly.

**Decision check passed:** toolchain feels good, dev loop is fast (~0.4s incremental builds), Owned/Archived split is real but manageable with the trait pattern, format choice is now toolchain-confirmed. Green light to step 1.

**The exercise:**
- Define a 3-variant `NodeId` enum (include one `Box<NodeId>` recursive variant — forces you to feel `ArchivedBox` indirection).
- Derive `Serialize`/`Deserialize` (serde), `Archive`/`Serialize`/`Deserialize` (rkyv), `#[archive(check_bytes)]`.
- Build a `Vec<NodeId>` with one of each variant.
- JSON roundtrip: `serde_json::to_writer_pretty` → file → `from_reader` → `assert_eq!`.
- rkyv roundtrip: `rkyv::to_bytes` → file → `Mmap::map` → `check_archived_root` → `deserialize(&mut Infallible)` → `assert_eq!`.

**What this teaches in 50 lines:**
- `Archived<T>` is genuinely a different type — you'll fight it on `assert_eq!`.
- Recursive variants force `ArchivedBox` indirection at every level — confirms flat ID + table is the right call.
- `#[archive(check_bytes)]` adds bytecheck dep; better to hit that compile error now.
- mmap + lifetime story — felt cheaply.
- `cargo check`/`test`/`run` dev loop is established.

**Acceptance for step 0:** both roundtrips green; binary file meaningfully smaller than JSON; you can answer "recursive vs flat" without speculation. Then step 1 proper begins.

## Step 1 outcomes (executed 2026-04-17, hash 93aa4d9)

**Status: PASSED.** `repo-graph-core` crate compiles, 6 tests green. The Owned/Archived trait-unification approach works cleanly.

**Concrete patterns that worked (save future self the trial-and-error):**

1. **Unified trait surface across Owned + Archived via From-bridge for unit enums.** For registry-backed newtypes (`NodeId(u64)`, `EdgeCategoryId(u32)`), the Archived form is accessed via `archived.0.to_native()` and rewrapped. For unit-variant enums (`Confidence`), write a single `impl From<&ArchivedConfidence> for Confidence` that pattern-matches variants — pattern matching on the archived enum works because variant names are preserved by default in rkyv 0.8. Then the trait method becomes `(&self.confidence).into()`.

2. **`#[rkyv(derive(PartialEq, Eq, Hash))]` on unit-variant enums and newtype-u32s works out of the box.** No manual impls needed.

3. **`ArchivedVec<T>` supports `.iter()`, indexing with `&archived[i]`, and `.len()`.** BFS and neighbour walks are ergonomic on the archived form.

4. **`xxhash` via `twox-hash 2.x` with explicit byte writes** (write, write_u8, write_u32, write_u64, finish) produces deterministic IDs. Interleave `0xFF` separator bytes between variable-length fields to prevent `(co,de) == (c,ode)` collisions. Test confirmed: 1000 synthetic IDs, zero collisions.

5. **Single-file lib.rs (~300 lines) is fine for a scaffold** — resist the urge to split into modules until the crate actually grows. One module = one compile target = fastest iteration.

6. **Deps that matter:** `serde` (features = ["derive"]), `rkyv` (features = ["bytecheck"]), `thiserror = "2"`, `twox-hash = "2"` (default-features = false, features = ["xxhash64"]).

**The load-bearing claim from step 0 cashed in:** *"Owned/Archived split feels manageable with the trait pattern"* — step 1 confirmed this at real scale. Trait method surface stays small (id/repo/confidence/cell_count for NodeLike), conversion cost at call sites is a single `.to_native()` per primitive. No GATs needed yet; may need them for returning collections of archived cells in v0.4.5 when traversal touches cells.

## Parallelism shape — sequential first, profile, then rayon

**Principle (confirmed 2026-04-17):** *"oh i see some very useful areas but not for everything and we need to build first to see where we can use it"*. Add rayon only where the profile points after a working end-to-end build, not speculatively.

**Where parallelism does and doesn't fit:**

| Phase | Shape | Parallel? |
|---|---|---|
| File parse | many → many independent | ✅ within shard, rayon-friendly |
| Per-shard symbol table | many files → one table per shard | ✅ within shard |
| Per-shard graph build | one shard's data → one shard graph | per-shard, sequential within |
| Cross-stack merge | N shards → 1 merged table | ❌ join, serial |
| Per-shard rkyv write | one graph → one file | trivially parallel across shards |

**Underlying rule (verbatim user model):** *"symbol table is obviously after the shards and shared state so one core and one hit, it's joining things right i mean you could parrellise joins but thats stupid for now."* and *"cross stack and anything shared is just bad af."* — **parallel where data is independent, serial where data converges.** Joins stay serial; locking the merged table costs more than the join saves at any sane graph scale.

**Practical sequence:** zero rayon through step 5. After end-to-end working on real repos, `hyperfine` against quokka-stack + a bigger test repo. Add rayon to the parse loop (the obvious win, ~80% of total time). Re-measure. Stop.

## Workspace crates (split early to keep compile times sane)

- `core-types` — `NodeId`, `RepoId`, `ShardId`, `Node`, `Edge`, `EdgeCategory`, traits, error types
- `parser-py` — tree-sitter Python visitor
- `parser-<lang>` per language as added
- `graph` — construction, resolution, traversal
- `merge` — multi-repo / cross-stack resolver
- `serde-json` — JSON projection (debug)
- `rkyv-store` — binary serialisation, mmap loader, sharding, manifest
- `latent` — vector projection, local LLM hook (candle or ort, decide early)
- `py-bindings` — pyo3 + maturin

## What this file does NOT cover

- Tree-sitter grammar choice and visitor patterns → step 2 work, separate notes
- Latent projection model choice (candle vs ort) → decide in step 6, separate notes
- pyo3 binding shape → step 7, separate notes
- Dense text projection format and sigil semantics → see `project_larger_vision.md`
- Multicellular node cell schema → see `project_040_vision.md`
