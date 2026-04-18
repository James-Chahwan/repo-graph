---
name: v0.4.10c Python clean break complete
description: MCP server rewired from Python analyzers to Rust engine; 27 Python files deleted, 4 remain as thin wrapper; 11 MCP tools verified on quokka-stack
type: project
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**COMPLETED 2026-04-17.** Clean break from Python analysis layer — MCP server now powered entirely by Rust via pyo3.

### What was deleted
- `repo_graph/analyzers/` — 27 files (20 language analyzers + base + registry + 4 cross-cutting)
- `repo_graph/generator.py` — Python orchestrator
- `repo_graph/discovery.py` — file discovery
- `repo_graph/test_edges.py` — test edge detection
- `repo_graph/config.py` — config.yaml loader
- `repo-graph-generate` CLI entry point removed from pyproject.toml

### What was rewritten
- `graph.py` — `RustGraph` class wrapping `PyGraph`: parses nodes_json/edges_json, builds adjacency lists, BFS traversal, auto-generates flows from entry point nodes (ROUTE, GRPC_SERVICE, QUEUE_CONSUMER etc.)
- `server.py` — 11 MCP tools backed by Rust engine
- `init.py` — uses `repo_graph_py.generate()` instead of Python generator
- `pyproject.toml` — version 0.4.10, added `repo-graph-py` dep

### MCP tool surface (11 tools)
**Kept adapted:** generate, status, flow, trace, impact, neighbours, graph_view, reload
**New:** dense_text (full sigil output), activate (PPR spreading activation), find (node lookup)
**Removed:** bloat_report, split_plan (relied on Python per-file analyzers), cost, hotspots, minimal_read

### Key fix during build
- Kind/category registry IDs were wrong in Python mapping — ROUTE is 5 not 6, CLASS is 2 not 4, etc. Fixed by reading actual values from `rust/code-domain/src/lib.rs`

### Result
`repo_graph/` is 4 files (~450 lines) down from ~30 files (~5,000+ lines). All 11 tools verified on quokka-stack (1,788 nodes, 2,539 edges, 32 cross-stack, 19 auto-detected flows).

User quote: *"yeah this is the break for old python world right now we moving onto rust time"*

**Why:** Rust engine (tree-sitter AST) produces 3.2× more nodes and 4.1× more edges than Python (regex). No reason to maintain both.

**How to apply:** Python layer is now a thin MCP wrapper. All parsing/graph/activation logic lives in Rust. Future features go in Rust crates, not Python.
