---
name: v0.4.6 activation engine — domain-agnostic PPR design
description: Spreading activation must be domain-agnostic; direction, edge weights, node specificity are all domain-provided config, not hardcoded code-domain assumptions
type: project
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**Decided 2026-04-17.** User flagged that all three HippoRAG adaptations are code-domain-specific and other domains would differ.

### Design: domain-agnostic ActivationConfig

```rust
struct ActivationConfig {
    damping: f64,                              // 0.5 default
    direction: Direction,                      // Forward / Backward / Undirected
    edge_weights: HashMap<EdgeCategoryId, f64>, // domain provides
    node_specificity: Specificity,             // None / Idf / InverseIdf / Custom
    top_k: usize,
}
```

- **Direction:** code = directed (A calls B ≠ B calls A). Molecules = undirected (symmetric bonds). Policy = bidirectional. Core supports all three.
- **Edge weights:** code domain: `calls > contains`. Other domains provide their own table. Not baked into algorithm.
- **Node specificity:** IDF wrong for code (popular utils matter), right for NL knowledge graphs. Domain-configurable scoring function.

### Crate location
New `repo-graph-activation` crate or module in `repo-graph-core`. Engine is domain-agnostic. Code domain provides default `ActivationConfig`.

### User verbatim
*"some of these might be diff based on domain something to really note. and try to deal with here"*

**How to apply:** PPR engine takes graph + ActivationConfig. Code domain ships defaults. Aligns with v0.5.0 domain-agnostic principle — engine doesn't know what "calls" or "bonds" mean.
