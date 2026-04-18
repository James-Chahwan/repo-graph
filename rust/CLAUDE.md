# CLAUDE.md (glia engine)

This file provides guidance to Claude Code when working in the Rust workspace. After v0.4.12 this directory will be split into its own `glia` repo via `git filter-repo`; these docs travel with it.

## What This Is

**glia** is the Rust engine behind repo-graph. It parses source, builds a unified cross-language graph, stores it in a zero-copy `.gmap` file (rkyv + mmap), runs Personalised PageRank activation over it, and projects it to dense text or structured forms.

Designed to be domain-agnostic: code is the first primitive, but other domains (video, molecules, policy, climate) slot in via the same registry model. See `dev-notes/glia-memory/project_050_domain_agnostic.md` for the direction.

## Workspace Layout

```
core/               Node, Edge, QName, shared primitives (no domain assumptions)
code-domain/        Code-specific registries: NodeKind, EdgeCategory, CellType (u32 IDs)
graph/              Per-repo graph builder, universal resolver, cross-graph resolvers
store/              .gmap binary format — rkyv + mmap, sharded layout
projection-text/    Dense sigil text output (scopes, defaults, module dedup)
activation/         Spreading activation — domain-agnostic PPR with configurable direction/weights
parsers/code/
  python/  go/  typescript/  rust/  java/  csharp/  ruby/  php/  swift/
  c_cpp/   scala/  clojure/  dart/  elixir/  solidity/  terraform/
  react/   angular/  vue/    — framework parsers stacked on typescript
  extractors/ — cross-cutting: data_sources, cli, grpc, queues, websocket,
                eventbus, graphql, ts_routes, angular/react/vue route extractors
py/                 pyo3 bindings — the only Rust crate published to PyPI (as repo-graph-py)
```

Parsers live at `parsers/<domain>/<language>/`. When v0.5.0 adds non-code domains, they nest alongside `parsers/code/`.

## Data Flow

```
source files
   → per-language parser (tree-sitter → ExtractedItems)
   → extractors (cross-cutting: HTTP, gRPC, queues, data_sources, CLI)
   → graph builder (resolves intra-repo references)
   → cross-graph resolvers (HttpStack, GraphQL, gRPC, Queue, WebSocket, EventBus, SharedSchema, DB, CLI)
   → merged graph
   → .gmap (rkyv + mmap, sharded)
   → [optional] activation (PPR) / projection-text / pyo3 → Python
```

## Parser-vs-Graph Split (locked at v0.4.3b)

Parsers **extract**; graph crate **resolves**. Parsers emit raw `ExtractedItems` with unresolved references (`UnresolvedRef`). The graph builder walks the tree to turn those into concrete edges uniformly across languages.

- `SelfMethod` walks to the enclosing `CLASS` / `STRUCT` / equivalent.
- A reserved `extra_hook` seam lets a parser contribute language-specific resolution when the generic walker isn't enough.
- Parsers must not short-circuit this: extract what the AST makes available; don't cap at what old regex heuristics happened to capture.

## Format Spec — `.gmap`

Zero-copy rkyv serialisation with memory-mapped read. Sharded by kind to keep hot paths local. Write-once, rebuild-whole-file — no in-place mutation. Owned vs Archived types are the mental model: loaded views are `Archived<T>`, writes go through `Owned<T>` then serialise.

Projections on top of the store:
- **Binary** — the `.gmap` itself, consumed by activation and the pyo3 layer
- **Dense text** — sigil-based projection with prefix/default/module dedup and scope collapse
- **JSON** — legacy enriched nodes/edges for compatibility

See `dev-notes/glia-memory/reference_format_spec.md` and `reference_rkyv_design.md`.

## Code-Domain Registries

Locked `u32` IDs for `NodeKind`, `EdgeCategory`, `CellType`. Qualified names use `::` as the separator. Extraction vs. resolution split is enforced across all code parsers so the graph builder sees a uniform shape.

IDs ref: `dev-notes/glia-memory/reference_kind_category_ids.md` and `reference_code_domain_registries.md`.

## Activation (PPR)

Personalised PageRank with damping = 0.5 (not custom spreading activation). `ActivationConfig` is domain-agnostic: direction, edge weights, and node specificity are all provided by the domain, not hardcoded. Code-graph adaptations: edge weights, direction, node specificity — three dials the domain sets.

## Adding a New Language Parser

1. Create `parsers/code/<language>/` with a `Cargo.toml`
2. Use the `tree-sitter-<lang>` grammar; beware grammar quirks (see `dev-notes/glia-memory/reference_treesitter_quirks.md`)
3. Implement `parse()` → `ExtractedItems` with raw nodes + `UnresolvedRef`s
4. Emit qnames with `::` separator; use the locked `NodeKind` IDs from `code-domain`
5. Add the crate to `Cargo.toml` workspace members
6. Add it to `rust/py/Cargo.toml` and re-export through pyo3 if it should be user-visible

If the language needs routes (HTTP, gRPC, queues, etc.), the extractor belongs in `parsers/code/extractors/` as a cross-cutting module, not inside the language parser.

## Adding a New Cross-Graph Resolver

Implement `CrossGraphResolver`; register it so `MergedGraph` calls it during cross-repo resolution. `HttpStackResolver` is the canonical example. Backlog of planned resolvers: GraphQL, gRPC, Queue, WebSocket, SharedSchema, EventBus, DB, CLI. See `dev-notes/glia-memory/project_040_stack_resolvers_backlog.md`.

## Key Design Decisions

- **Tree-sitter, not regex.** 0.4.x moved to AST extraction; 0.2.0 regex is not a ceiling.
- **Zero-copy store.** rkyv + mmap; writes rebuild the whole file.
- **Domain-agnostic core.** `core` and `activation` know nothing about code. Code lives in `code-domain` and the parsers.
- **Publish gate.** Only `rust/py/` publishes to PyPI (as `repo-graph-py`). Everything else is internal workspace.
- **No Python fallback.** After v0.4.10c, Python is a thin pyo3 wrapper; there is no parallel Python implementation to keep in sync.

## Roadmap

- **0.4.13** — maturin GitHub Actions wheel matrix; candle `forward_input_embed` latent hook; SWE-bench Lite N=20–30 run (Qwen 2.5 Coder 7B, Runpod 4090, ~$20–30)
- **0.5.0** — rename to **glia**; domain registries for non-code (video, chemistry, policy, climate); code stays the reference domain

## Memory

Relevant architecture/spec memories from the repo-graph project memory system are copied under `dev-notes/glia-memory/`. When this directory becomes its own repo, those files seed the new Claude memory directory there.
