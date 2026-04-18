---
name: v0.4.10b pyo3 bindings complete
description: repo-graph-py crate built with pyo3 0.28 + maturin; full Python API surface verified on quokka-stack (1,788 nodes, 32 cross-edges)
type: project
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**COMPLETED 2026-04-17.** `rust/py/` crate — pyo3/maturin Python bindings for the entire Rust pipeline.

### Crate setup
- `rust/py/Cargo.toml`: pyo3 0.28.3 (supports Python 3.14), cdylib, all 19 parser crates + core + code-domain + graph + extractors + projection-text + activation + serde_json
- `rust/py/src/lib.rs`: ~450 lines, manual JSON building (no serde derives needed)
- Added to workspace members in `rust/Cargo.toml`
- `.venv` created at `/home/ivy/Code/repo-graph/.venv` for maturin builds

### Python API surface
- `generate(repo_path) -> PyGraph` — full pipeline: walk → parse → build graphs → run 8 resolvers
- `parse_file_to_json(source, path, lang) -> str` — single-file parsing
- `version() -> str` — "0.4.10"
- `PyGraph.node_count()`, `.edge_count()`, `.cross_edge_count()`
- `PyGraph.dense_text()` — sigil notation
- `PyGraph.nodes_json()`, `.edges_json()` — JSON serialization
- `PyGraph.find_node(name)`, `.find_nodes_by_qname(pattern)`
- `PyGraph.neighbours(node_id)`, `.activate(seed_ids, top_k)`

### Quokka-stack results (with stack resolvers)
- 1,788 nodes, 2,539 edges, 32 cross-stack edges
- Up from 1,350 nodes / 2,535 edges / 7 cross (pre-stack-resolvers)
- Stack resolvers found 25 additional cross-edges (gRPC, queue, GraphQL, WS, event, CLI, shared schema)

### Fixes during build
- pyo3 0.24→0.28 for Python 3.14 compat
- c_cpp parser needs 5th arg `is_cpp: bool` — detected from file extension
- `NodeId.0` not `.as_u64()` (tuple struct)
- `ActivationResult.scores` not `.ranked`
- Manual JSON building instead of serde derives (avoids dep issues)
- 3 clippy fixes: collapsible ifs, field_reassign_with_default

**Why:** This is the bridge that lets Python MCP server use the Rust parsing/graph/activation engine.

**How to apply:** Next step is v0.4.10c (text loop + interceptor skill) which wires `repo_graph_py` into the MCP server's Python layer.
