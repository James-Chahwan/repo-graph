---
name: Quokka-stack Rust pipeline dumps
description: Rust pipeline runs on quokka-stack — tracking node/edge/cross-edge counts across versions
type: project
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
### v0.4.5 (2026-04-17) — first dump
- Go backend (turps): 60 files, 648 nodes, 1,299 edges
- TS frontend (quokka_web): 61 files, 702 nodes, 1,229 edges
- HTTP cross-edges: 7 (HttpStackResolver only)
- Total: 1,350 nodes, 2,535 edges (2,528 intra + 7 cross)
- Time: 0.49s
- Dense text: 451 KB

### v0.4.10b (2026-04-17) — with stack resolvers + pyo3
- Total: 1,788 nodes, 2,539 edges, 32 cross-stack edges
- 438 new nodes from stack resolver extractors (gRPC services/clients, queue producers/consumers, GraphQL ops/resolvers, WS handlers/clients, event emitters/handlers, CLI commands/invocations)
- 25 new cross-edges beyond the original 7 HTTP

### Comparison to Python 0.2.0
Python 0.2.0: 566 nodes / 620 edges. Rust 0.4.10: 1,788 nodes / 2,539 edges — 3.2× nodes, 4.1× edges.

**Why:** Quokka-stack is the primary validation corpus. These numbers track progress across versions.
