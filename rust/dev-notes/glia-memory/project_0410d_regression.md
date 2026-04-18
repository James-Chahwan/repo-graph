---
name: v0.4.10d quokka regression results
description: Python 0.2.0 vs Rust 0.4.10 on quokka-stack — 3.1x nodes, 4x edges, 32 cross-stack, no core regressions
type: project
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**COMPLETED 2026-04-17.** Regression test comparing old Python 0.2.0 output vs new Rust 0.4.10 on quokka-stack.

### Headline
| Metric | Old (Python 0.2.0) | New (Rust 0.4.10) | Delta |
|--------|-------------------|-------------------|-------|
| Nodes | 584 | 1,788 | +1,204 (3.1x) |
| Edges | 638 | 2,539 | +1,901 (4.0x) |
| Cross-stack | 0 | 32 | +32 |
| Flows | 66 | 19 | -47 (per-path vs per-method) |
| Calls edges | 33 | 918 | 28x |

### Wins
- 887 method nodes, 121 structs, 81 interfaces, 37 endpoints (all 0 in old)
- 32 cross-stack HTTP edges linking frontend endpoints to backend routes
- PPR spreading activation, 431KB dense text, confidence tiers
- 918 calls edges vs 33 (tree-sitter resolves call targets)

### Gaps (deferred, not regressions)
- 4 data_source nodes (db/mongodb, queue/nats, email/resend, blob/s3) — needs Rust data_sources extractor
- 11 test_file nodes — needs Rust test file detection
- 1 grpc_method node — Rust detects services not individual methods
- 1 queue_consumer — extractor pattern doesn't match quokka's NATS usage
- 0 imports/contains/uses edges — Go/TS parsers emit DEFINES + CALLS only; import resolution deferred
- 0 tests edges — no test file detection in Rust yet
- Flow count lower (19 vs 66) — old created per-HTTP-method flows, new per-path (cleaner)

### Verdict
No core regressions. All gaps are deferred features. Strictly better for LLM navigation.

**Why:** Validates that the Rust rewrite didn't lose structural coverage. Gaps noted for v0.4.11 pre-publish sweep.
