---
name: v0.4.5 complete — rkyv store + dense text projection
description: 5a (repo-graph-store crate, .gmap container, atomic write + mmap) + 5b (repo-graph-projection-text crate, sigil notation) — both implemented and tested 2026-04-17. 5c sharding deferred to v0.4.10.
type: project
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**Status 2026-04-17**: 5a + 5b done, awaiting commit + bundled `v0.4.5` tag. 5c (sharding) deferred per the plan's "only if it falls out naturally" rule.

## What landed

### v0.4.5a — `rust/store/`
- New crate `repo-graph-store` (Cargo dep: `rkyv 0.8 + bytecheck`, `memmap2 = "0.9"`, `thiserror`).
- `Container { header, repo, nodes, edges, code_nav: CodeNavStore, symbols: SymbolTableStore, unresolved_calls, unresolved_refs }` — single rkyv-archived top-level struct per `.gmap` file.
- `Header { magic: b"GMAP", version: u32 = 1, graph_type: "code", cell/edge/node_kind registries (empty at 0.4.5a, diagnostic-only) }`.
- HashMap → sorted `Vec<(K, V)>` flattening at the serialise boundary (`CodeNavStore::from_owned`, `SymbolTableStore::from_owned`). Keeps bytes deterministic + binary-search-able on the archived form.
- `write_repo_graph(g, path)` — atomic via `<path>.tmp` + `rename`.
- `MmapContainer { bytes: Mmap }` — opens read-only, validates magic + version on construction, exposes `archived()` returning `&ArchivedContainer` with lifetime tied to `&self`.
- `ArchivedContainer::edges_iter()`, `qname(id)`, `kind(id)` — binary-search lookups on the sorted Vec mirrors.
- Code-domain crate gained rkyv derives on `ImportStmt`, `ImportTarget`, `CallSite`, `UnresolvedRef`, `CallQualifier` (these flow through the Container).
- Tests: 3 unit + 2 integration (full backend roundtrip via tempdir) — all green.

### v0.4.5b — `rust/projection-text/`
- New crate `repo-graph-projection-text` (deps: `repo-graph-core`, `repo-graph-code-domain`, `repo-graph-graph`).
- Public API: `render_repo_graph(&RepoGraph) -> String`, `render_merged(&MergedGraph) -> String`.
- Output shape: `[LEGEND]` + `[TOPOLOGY]` + per-node `[<qname>]` blocks with `:kind`, `:confidence`, and one line per cell.
- Sigils shipped: `>` (CALLS / HANDLED_BY / HTTP_CALLS), `*` (Route / Endpoint), `@` (target id not in any nav → `@unresolved#<hex>`). Other sigils (`$`, `^`, `!`, `?`, `#`, `~`) stay in the LEGEND as a stable contract — populated when v0.4.8 cells land.
- Reads from owned `RepoGraph` only; archived-side renderer waits for a caller (the trait surface exists via `NodeLike`/`EdgeLike` but nav is map-shaped only on the owned side; `MmapContainer` exposes nav as point-lookups, not a full iter).
- Tests: 5 unit (mini-graph, entry sigil, external sigil, merged cross-edge, preview truncation) + 1 integration (full backend render, asserts LEGEND/TOPOLOGY/route blocks/handler blocks/`route * > handler` line) — all green.

## v0.4.5c — DONE (2026-04-17)
User said *"yeah do it now"*; batched into the v0.4.5 tag.

**What landed in `rust/store/src/lib.rs`:**
- `Manifest { schema_version, shards: Vec<ShardEntry>, cross: Option<ShardEntry> }` — JSON, serde-derived.
- `ShardEntry { name, path, content_hash }` — content hash is xxhash64 hex (16 chars), produced by a small `hex_xxhash64` helper using `twox-hash` (already on the workspace).
- `Container::for_cross_edges(edges)` — builds a Container with empty nodes/nav/symbols and a synthetic `repo = RepoId::from_canonical("cross_stack")`. Reuses the existing rkyv shape so the loader doesn't need a new variant. Cross-edges only live here (Option A from the design fork).
- `write_sharded(shards: &[(&str, &RepoGraph)], cross_edges: &[Edge], dir: &Path) -> Result<Manifest, _>` — writes one `<name>.gmap` per shard, optionally `cross_stack.gmap`, plus `manifest.json`. Each file uses the same `write_atomic` helper that `write_repo_graph` was refactored onto.
- `ShardedMmap { manifest, shards: Vec<(String, MmapContainer)>, cross: Option<MmapContainer> }` — `open(dir)` validates the manifest schema version, then per-shard rehashes the file bytes against the manifest entry before mmap'ing it. Hash mismatches surface as `StoreError::ContentHashMismatch { shard, expected, got }`.
- `ShardedMmap::edges_iter()` — flattens edges across every shard + the cross shard, useful for whole-graph walks.
- New error variants: `ManifestJson`, `ManifestSchemaVersion { got, supported }`, `ContentHashMismatch { shard, expected, got }`, `ShardMissing(name)`.
- New deps on `repo-graph-store`: `serde`, `serde_json`, `twox-hash`.

**Tests in `rust/store/tests/sharded.rs`:**
1. `sharded_layout_roundtrips_with_cross_edges` — writes the http_stack_smoke backend graph + a synthetic 1-Endpoint frontend graph + 1 HTTP_CALLS cross-edge to a tempdir, re-opens via `ShardedMmap::open`, asserts manifest shape, files exist, per-shard archived contents survive (node/edge counts), cross shard has zero nodes and exactly the cross edges, `edges_iter()` sums the lot.
2. `no_cross_edges_writes_no_cross_stack_file` — confirms the `Option<ShardEntry>` cross wiring is honoured both ways.
3. `corrupted_shard_is_caught_by_hash_check` — flips a byte mid-file post-write, asserts `ContentHashMismatch` on reopen with the shard name in the message.

All 8 store tests green (3 unit + 2 single-file roundtrip + 3 sharded). Clippy clean across workspace.

## Design choices made under fire
- Cross shard reuses `Container` (Option A) — kept the on-disk format uniform; one decoder handles every `.gmap`.
- Synthetic `repo = "cross_stack"` for the cross shard — avoided adding a `ShardKind` field to Header.
- Caller-provided shard names (`&[(&str, &RepoGraph)]`) — explicit, no auto-naming surprises.
- `write_atomic` extracted from `write_repo_graph` so manifest + every shard go through the same tmp+rename path.
- Hash check happens *before* mmap'ing — corrupt files don't get held open by an Mmap that survives the error.

## Workspace shape after 0.4.5
```
rust/
  core/                     domain-agnostic primitives
  code-domain/              code-domain registries + types
  graph/                    per-repo build + cross-resolvers + MergedGraph
  store/                    .gmap container (rkyv + mmap)
  projection-text/          dense text renderer
  parsers/code/{python,go,typescript}/
  scratch/                  ignore — leftover from rkyv hello-world
```

## Sample dense-text output (backend fixture)
```
[LEGEND]
> depends    * entry point    @ external

[TOPOLOGY]
route:/api/users * > users::Create
route:/api/users * > users::List
route:/api/users/:id * > users::Get

[route:/api/users] *
:kind       Route
:confidence strong
:method     {"method":"GET","handler":"users.List",...}
:method     {"method":"POST","handler":"users.Create",...}

[users::List]
:kind       Function
:confidence strong
:code       func List(_ any)   {}
:position   {"file":"users/users.go","start_line":8,"end_line":8}
```

## Commit + tag plan
Per user instruction: sub-commits per phase, single bundled `v0.4.5` tag.
- Commit 1 (5a): `repo-graph-store` crate + rkyv derives on code-domain types + workspace member.
- Commit 2 (5b): `repo-graph-projection-text` crate + workspace member.
- Tag: `v0.4.5` on the second commit.
