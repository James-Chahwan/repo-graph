---
name: 0.5.0+ vision — domain-agnostic knowledge format primitive (chemistry, climate, policy, video, etc.)
description: 0.5.0 expands the format beyond code; design constraints carried into 0.4.0 to keep the door open
type: project
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**Confirmed 2026-04-17 in extended design session.**

repo-graph is **a knowledge format primitive, not a code analysis tool**. Code is the first domain. The format is a domain-agnostic container that stores multicellular graph nodes with typed cells, multiple output projections, and accumulated human and AI understanding. The AST parsing layer is an input transformer for the code primitive type, not the product itself.

## Per-primitive input transformers (each is a separate crate)

- **Code primitive** — tree-sitter AST extraction (v0.4.x scope)
- **Chemistry primitive** — SDF/PDB structure ingestion
- **Climate primitive** — time series with metadata
- **Policy primitive** — regulatory/legislative structure
- **Video primitive** — frames, shots, scenes, objects (no native names — uses indices)
- **Audio primitive** — samples, phonemes, words, speakers
- **Social primitive** — persons + relationships (flat, not hierarchical)

The container, projections, retrieval, and memory palace bridge work identically regardless of domain.

## 0.5.0 design constraints (carried into 0.4.0)

These constraints exist to keep the door open. Violating them in 0.4.0 means re-architecting at 0.5.0.

- **GraphType must be extensible** — code is first variant, others follow. Implemented as `GraphType(String)` self-describing, not a closed Rust enum.
- **CellType registry must be per-GraphType** — not hardcoded to code cells. Implemented as `CellTypeId(u32)` registry-backed in container header.
- **Input transformer trait must be generic** — for non-AST data sources.
- **Edge semantics must support domain-specific relationship types** — `EdgeCategoryId(u32)` registry-backed; chemistry knows Bonds/Reacts, video knows TemporalContinuity.
- **Container format must not assume code-specific node types in binary layout** — strict Node shape `{id, repo, confidence, cells: Vec<Cell>}` carries no domain assumptions.
- **Projections must work regardless of domain** — dense text projection renders any graph type, not just code.
- **mempalace bridge must map any primitive type into wing/room structure** — not just code.
- **HippoRAG/spreading activation wrapper must work on any graph** — Personalized PageRank is domain-agnostic.
- **Spatial position cell must be domain-agnostic** — `position` cell with coordinates, ignored by LLMs, used by IDE + human spatial memory.
- **CrossGraphResolver trait must be domain-agnostic** — code domain ships HttpStackResolver/GrpcStackResolver/etc; chemistry would ship CrossReactionResolver; video would ship ObjectReidentificationResolver.

The format header's cell + edge + node-kind registries are the extension point. New domains add types through the registries. **No core changes required.**

## "Universal navigation fields" was wrong (the lesson)

Earlier 0.4.0 design had `Node { id, repo, name, kind, parent, ... cells }` — assumed every domain has name/kind/parent. User pushed back: video frames have indices not names, molecules have elements not names, social graphs have no hierarchy. Strict shape adopted: `Node { id, repo, confidence, cells }`. Navigation lives in **domain-owned indices stored in the container**, not in Node fields.

See `feedback_domain_assumptions.md` for the behavioral guidance this surfaced.

## 0.5.0 candidates

- **General knowledge primitive** — Wikipedia-shape entities + relationships
- **Chemistry primitive** — molecule structures, reactions
- **PolycrisisMonitor** — real-world non-code test case for the format (user has interest here per BMC `polycrisis`)

PolycrisisMonitor is interesting because it's a domain the user already cares about and would dogfood — best non-code primitive candidate to start with.

## What survives across domains

- Strict Node shape
- Container layout (header + nodes + edges + domain indices + embeddings)
- Three projections (binary / dense text / latent vectors)
- Spreading activation retrieval (HippoRAG)
- Mempalace bridge (cell↔hall mapping, shared ID space)
- Confidence tiers
- ID encoding (`xxhash(graph_type, repo, kind, qualified_name)`)

## What's domain-specific

- Cell type registry (what cells exist + their semantics)
- Edge category registry
- Node kind registry
- Input transformer (parser equivalent)
- Domain-owned navigation indices
- Cross-graph resolvers
- Spatial position semantics (3D for chemistry, 2D for IDE, temporal for video, etc.)
