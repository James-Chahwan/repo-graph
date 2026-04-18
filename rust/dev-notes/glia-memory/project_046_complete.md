---
name: v0.4.6 complete — activation crate (PPR)
description: repo-graph-activation crate implemented 2026-04-17; domain-agnostic PPR, 13 unit tests, quokka integration validated (3 seeds → 33 nodes, 17 iters)
type: project
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**Completed 2026-04-17.**

### What shipped
- New crate `rust/activation/` — `repo-graph-activation` v0.4.6
- Domain-agnostic Personalized PageRank via power iteration
- Dangling node redistribution (standard PPR — keeps scores summing to 1.0)
- `ActivationConfig`: damping, Direction (Forward/Backward/Undirected), edge_weights HashMap, Specificity (None/Idf/InverseIdf), top_k, max_iterations, epsilon
- `ActivationResult`: sorted (NodeId, f64) scores + iteration count, with `top_ids()` and `score_of()` helpers

### Graph crate additions
- `RepoGraph::activate(&seeds, &config)` convenience method
- `MergedGraph::activate(&seeds, &config)` — collects all nodes + all_edges + cross_edges
- `code_activation_defaults()` — code-domain weight table:
  - calls=5, http_calls=5, handled_by=4, imports=3, uses=3, tests=2, injects=2, defines=1, contains=1, documents=0.5

### Tests
- 13 unit tests in activation crate (all algorithmic properties)
- Integration test in quokka_dump: 3 route seeds → 33 activated nodes, 17 iterations
- Quokka results: routes (0.184) → handlers (0.092) → services (0.058) → utilities (0.015)
- Full workspace: 90+ tests green, clippy clean

### Key implementation detail
- Fixed 3 test failures by adding dangling node handling — nodes with no outgoing edges redistribute their PPR mass back to seeds via personalization vector
- Edition 2024 pattern binding: `filter(|(_, s)| **s > 0.0)` not `filter(|(_, &s)| s > 0.0)`

### Files
- `rust/activation/Cargo.toml` — depends only on repo-graph-core
- `rust/activation/src/lib.rs` — ~260 lines algorithm + 180 lines tests
- `rust/graph/Cargo.toml` — added activation dep
- `rust/graph/src/lib.rs` — added activate() methods + code_activation_defaults()
- `rust/Cargo.toml` — added "activation" to workspace members
