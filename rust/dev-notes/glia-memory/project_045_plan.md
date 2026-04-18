---
name: v0.4.5 plan — rkyv store + dense text projection
description: Sub-scope split (a/b/c) and locked design decisions for the v0.4.5 storage + projection layer. Tag bundled at v0.4.5; sub-commits per phase.
type: project
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**Status 2026-04-17**: planned, not started. Tasks #33 (5a) and #34 (5b) created.

## Sub-scope (mirrors v0.4.4a/b pattern)

- **v0.4.5a** — `repo-graph-store` crate: Container struct (header + nodes + edges + code-domain indices), atomic write via `.gmap.tmp` + rename, mmap reader returning Archived view, smoke test for disk roundtrip parity. Task #33.
- **v0.4.5b** — dense text projection: LEGEND + TOPOLOGY + per-node typed-cell blocks per `reference_format_spec.md` sigil legend. Reads from Owned or Archived via `NodeLike`/`EdgeLike` traits. Task #34.
- **v0.4.5c** — sharding + manifest (per-shard `.gmap` + `manifest.json` with mtime/content_hash/depends_on). **Deferred decision**: only do this in 0.4.5 if it falls out naturally from 5a/5b; otherwise defer to v0.4.10. `MergedGraph.cross_edges` already gestures at the per-shard model so sharding is a natural fit, but not required for the v0.4.5 release.

## Locked design decisions (user-confirmed 2026-04-17)

- **File extension: `.gmap`** (user verbatim: *"1 is .gmap"*). Matches the scratch-crate hello-world that already wrote `nodes.gmap`. Format-name-as-LLM-interface framing: `gmap binary / gmap text / gmap vectors`.
- **HashMap handling: convert to sorted `Vec<(K,V)>` at the serialise boundary.** Reasons: rkyv 0.8 supports `HashMap` but the cost is real; sorted Vec aligns with the spec's "domain-owned indices as named byte ranges" model; binary-search lookup on the archived form is fast enough for the access patterns we have. Affects `CodeNav` (5 maps), `SymbolTable` (4 maps), and any future domain index.
- **Commit cadence: sub-commits per phase, single tag at v0.4.5** (user verbatim: *"look do them as 0.4.5a,b,c and commit as 0.4.5  yeah bundle the tag thouugh"*). Same pattern as 0.4.4a/0.4.4b commits but without the intermediate `v0.4.4a` tag.

## v0.4.5a concrete plan

**New crate**: `rust/store/` (workspace member name `repo-graph-store`).

**Deps**: `repo-graph-core`, `repo-graph-code-domain`, `repo-graph-graph`, `rkyv` (with `bytecheck`), `memmap2 = "0.9"`, `thiserror = "2"`.

**Container shape** (single rkyv-archived top-level struct for v0.4.5a; sectioned-byte-ranges deferred to v0.4.5c if needed):

```rust
struct Container {
    header: Header,
    nodes: Vec<Node>,
    edges: Vec<Edge>,
    code_nav: CodeNavSerialised,    // CodeNav with HashMap → sorted Vec
    symbols: SymbolTableSerialised, // same
    unresolved_calls: Vec<CallSite>,
    unresolved_refs: Vec<UnresolvedRef>,
    repo: RepoId,
}

struct Header {
    magic: [u8; 4],     // b"GMAP"
    version: u32,       // 1
    graph_type: String, // "code"
    cell_registry: Vec<(u32, String)>,        // for diagnostics, never load-bearing
    edge_category_registry: Vec<(u32, String)>,
    node_kind_registry: Vec<(u32, String)>,
}
```

**Lifecycle (per `reference_rkyv_design.md` step-1 patterns)**:
- `write_container(repo_graph: &RepoGraph, path: &Path) -> Result<(), Error>` — convert nav/symbols to sorted-Vec form, build Container, `rkyv::to_bytes`, write `path.gmap.tmp`, atomic `rename`.
- `open_container(path: &Path) -> Result<MmapContainer, Error>` — `Mmap::map`, `rkyv::access::<ArchivedContainer, _>`, return a wrapper struct holding both the Mmap and the &ArchivedContainer (lifetime-tied via self-referential pattern or `owning_ref`-style).

**Smoke test**: build the http_stack_smoke backend graph, write to a `tempfile::NamedTempFile`, mmap-load, assert: same node count, same edge count, sample lookups via the Archived nav match the Owned nav.

**Sharp edges to expect** (from step-0/1 lessons in `reference_rkyv_design.md`):
- `Archived*` types don't auto-inherit traits — every type that needs `Debug`/`PartialEq` on the archived side needs `#[rkyv(derive(...))]`.
- Self-referential mmap holder is the trickiest part — likely use the `ouroboros` crate or hand-roll a `(Mmap, &'static ArchivedContainer)` with a strict private constructor that bounds the borrow.

## v0.4.5b concrete plan

Renderer module producing the dense-text projection per `reference_format_spec.md`:

```
[LEGEND]
> depends   >> trusts validated   x> failure propagates
~ shares    $ touches money        ^ security boundary
! constraint ? known issue         # has failure history
* entry point @ external dependency

[TOPOLOGY]
esc.settle $^ > fee.calc > usr.store
auth.login ^ > token.issue > session.create

[NODE blocks]
[esc.settle]
:code   func Settle(...) {...}
:intent reject duplicate settlements, commit atomic
...
```

**Open at v0.4.5b start** (not yet decided):
- Where the renderer lives: probably new `repo-graph-projection-text` crate (so future `projection-vector` etc. mirror it) or a module under `graph/`. Lean toward separate crate per the workspace-split-early principle.
- Sigil derivation rules for v0.4.5b: most sigils (`$`, `^`, `!`, `?`, `#`) need cell data that v0.4.8 will populate. v0.4.5b probably ships only `>` (depends/CALLS), `*` (entrypoint/Route+Endpoint), `@` (external/unresolved). Rest are placeholders waiting for v0.4.8.
- Whether topology block needs flow-aware layout (group by Route/CLI/Queue entrypoint and walk CALLS) — flows already exist in the Python codebase but Rust side hasn't done flow construction yet. Probably defer flow-aware layout, render topology as raw entrypoint→reachable edges for now.

## v0.4.5c (deferred-decision sharding)

Skip unless 5a/5b naturally point at it. The `MergedGraph.cross_edges`-on-container model already implies a per-shard `.gmap` layout, but for a single-repo build there's no shard pressure. Likely punted to v0.4.10 when multi-repo workflows are real.
