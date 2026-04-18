---
name: gmap / .rg format spec — multicellular nodes, sigil notation, three projections, domain-agnostic container
description: Reference for the canonical format design — strict Node shape, domain-owned indices, dense text sigils, latent vectors, container layout
type: reference
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
The canonical format design as of 2026-04-17. Pair with `reference_rkyv_design.md` (storage layer mechanics) and `project_040_vision.md` (sequence + scope).

## Strict Node shape (domain-agnostic)

```rust
struct Node {
    id: NodeId,
    repo: RepoId,
    confidence: Confidence,
    cells: Vec<Cell>,
}

struct Cell {
    kind: CellTypeId,        // u32, registry-backed, registry in container header
    payload: CellPayload,
}

enum CellPayload {
    Text(String),     // most cells: code, intent, doc, conv
    Json(String),     // structured: position, attn, decisions
    Bytes(Vec<u8>),   // binary: cached embeddings
}
```

**Why strict:** Earlier "pragmatic" shape with name/kind/parent on Node smuggled code-domain assumptions. Video frames have indices not names. Molecules have elements not names. Social graphs have no hierarchy. Universal navigation fields don't exist; per-domain indices do.

## Domain-owned navigation indices

Stored in the container alongside nodes, mmap'd zero-copy. Each domain crate writes its own indices at serialise time, reads them by named section at load time.

- **Code domain** ships: `name_by_id`, `parent_of`, `children_of`, `by_qualified_name`
- **Video domain** would ship: `by_timestamp`, `by_shot_id`, `objects_in_frame`
- **Molecules domain** would ship: `position_kdtree`, `bonds_of_atom`

Core knows nothing about any specific index. Container header lists "domain index sections" as byte ranges; each domain crate knows how to read its own.

**Cost trade:** slight container complexity (index sections in binary layout), but zero per-visit cell-decode cost on navigation hot path. Pays off the moment you do a single BFS.

## Cell types per domain

Code primitive's cell registry (target set):
- `code` — source bytes
- `intent` — what this entity is for (human or LLM-authored)
- `doc` — docstring / comment block
- `test` — tests covering this entity
- `fail` — failure history (auto-derived from test results, CI logs)
- `constraint` — invariants, perf budgets ("idempotent, <200ms")
- `decision` — design decisions ("chose pg advisory locks over distributed lock")
- `env` — runtime/environment context
- `conv` — conversation history (LLM reasoning traces from extended thinking, persisted per node)
- `attn` — attention/ownership metrics (git blame, edit frequency)
- `position` — spatial coordinates for IDE consistent layout (ignored by LLMs)
- `vector` — cached embedding (CellPayload::Bytes)

Cell types are registered via `CellTypeId(u32)` in the per-domain registry. Adding a cell type = adding a registry entry + populator + (optional) consumer. No core changes.

## Three projections from one canonical

1. **Binary on-disk** — `.rg` file, rkyv-backed, mmap zero-copy. IDE + MCP server + tooling consume.
2. **Dense text** — sigil notation, returned from MCP tool calls, not stored on disk.
3. **Latent vectors** — embeddings per node. Today: semantic search via ChromaDB-like. Tomorrow: direct injection into model hidden state when latent APIs open (~2027-2028).

The format must be **projection-agnostic internally**. Adding a new projection = writing a new serialiser. Never restructuring the core.

## Dense text projection — sigil legend

Loaded once per context window (~30 tokens), then every entity ~40-70 tokens (vs 150-200 in current formats).

```
LEGEND
> depends           >> trusts validated output    x> failure propagates
~ shares data       $ touches money               ^ security boundary
! constraint        ? known issue                 # has failure history
* entry point       @ external dependency
```

## Output structure

```
[LEGEND block — sigils defined once]

[TOPOLOGY block — graph shape first, no detail]
esc.settle $^ > fee.calc > usr.store
auth.login ^ > token.issue > session.create

[NODE blocks — typed cells, addressable]
[esc.settle]
:code   func Settle(ctx, tx) error { ... }
:intent reject duplicate settlements, commit atomic
:fail   tz-bug x3, reentrancy once
:constraint idempotent, <200ms
:decision   chose pg advisory locks over distributed lock
```

**Why topology first:** transformer attention is sequential. Topology block builds the graph skeleton in attention before detail loads. Compensates for LLM sequential limit; humans get parallel activation natively, LLMs don't.

## Container layout

- **Header** — magic bytes, format version, `graph_type` (extensible string), `cell_registry`, `edge_category_registry`, `node_kind_registry`, `domain_index_sections` (named byte ranges)
- **Nodes section** — rkyv-archived `Vec<Node>`
- **Edges section** — rkyv-archived `Vec<Edge>`
- **Domain index sections** — per-domain, named, opaque to core
- **Embeddings section** (optional) — per-node vectors as raw bytes

Sharded layout per project: `frontend.rg`, `backend.rg`, `cross_stack.rg` + `manifest.json` carrying `schema_version` (= repo-graph binary version), per-shard mtime + content_hash + depends_on.

## ID encoding

- `NodeId(u64) = xxhash(graph_type, repo, kind, qualified_name)` — deterministic, regenerable, survives shard regen + cross-repo merge + cross-domain mempalace use
- `RepoId(u64) = xxhash(canonical_url_or_path)`
- `ShardId(u64) = xxhash(repo_id, shard_name)`

Shared ID space between repo-graph and mempalace (v0.4.10).

## Extensibility encoding

- `GraphType(String)` — self-describing, one per file, saving from u32 indirection meaningless
- `CellTypeId(u32)`, `EdgeCategoryId(u32)`, `NodeKindId(u32)` — registry-backed, high volume justifies indirection
- Registries live in container header, not core. Per-domain crates register their own types.

## Naming pending

Earlier session locked `gmap` as the format name (with the "JSON-parallel for graph-as-LLM-context" framing). 2026-04-17 context transfer used `.rg` as the file extension. Working assumption: `.rg` extension, `gmap` is the LLM-interface name (gmap binary / gmap text / gmap vectors). Confirm with user when v0.4.5 starts.
