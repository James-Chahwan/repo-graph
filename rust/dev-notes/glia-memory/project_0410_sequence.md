---
name: v0.4.10 sequence — ALL COMPLETE
description: v0.4.10 all 4 sub-steps done: stack resolvers, pyo3, clean break, quokka regression
type: project
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**ALL COMPLETED 2026-04-17.**

1. **v0.4.10a** — Stack resolvers — **DONE.** 7 resolvers, 12 node kinds, 7 edge categories, 178 tests.
2. **v0.4.10b** — pyo3/maturin bindings — **DONE.** pyo3 0.28, full Python API. Quokka: 1,788/2,539/32.
3. **v0.4.10c** — Python clean break — **DONE.** 27 Python files deleted. 11 MCP tools rewired to Rust. New: dense_text, activate, find.
4. **v0.4.10d** — Quokka regression — **DONE.** 3.1x nodes, 4x edges, 32 cross-stack, no core regressions.

Tier 3 deferred to pre-0.5.0: DatabaseStackResolver, TeamOwnershipResolver, SecurityZoneResolver, RuntimeZoneResolver.

### Deferred gaps noted for v0.4.11
- data_sources extractor (Rust)
- test file detection (Rust)
- import/contains/uses edge categories in Go/TS parsers
- per-method gRPC granularity
