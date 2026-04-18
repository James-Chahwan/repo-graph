---
name: 0.4.0 competitive landscape — code-graph MCP space is commoditising; the moat is everything above the graph
description: Named competitors, the commoditising-space framing, and the synthesis that nobody else has
type: project
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**Surfaced 2026-04-17 (extended design session).**

## The commoditising space

Multiple code-graph MCP servers now exist with broad language coverage. Competing on AST extraction is a losing game.

- **code-graph-mcp** — Rust, 16 languages
- **codebase-memory-mcp** — Go, 12 languages, has an arXiv preprint
- **CodexGraph** — Neo4j-backed, NAACL 2025 paper
- **CGM** — NeurIPS 2025, graph structure injected into LLM attention

These all do "extract AST → expose as MCP tools". Same shape, different stack choices. Convergent.

## The repo-graph moat

Everything above the graph that none of the competitors have:

- **Multicellular nodes** — typed cells (code/intent/doc/test/fail/constraint/decision/env/conv/attn/position) per node
- **Dense symbolic projection** — sigil notation, topology-first, ~40-70 tokens/entity vs 150-200
- **Latent vector projection** — per-node embeddings, today for semantic search, tomorrow for direct LLM injection
- **Memory palace bridge** — shared ID space with mempalace, cell↔hall mapping, conversation persistence
- **Spreading activation retrieval** — HippoRAG-wrapped Personalized PageRank over graph + GNN preprocessing
- **Bidirectional model-graph loop** — LLM emits structural ops not text diffs; graph stays current without re-parse
- **Domain-agnostic format** — code is the first primitive type; chemistry/video/policy/climate slot in via cell registries

The synthesis doesn't exist anywhere. That's the whole moat.

## Anthropic itself named the direction

> "repository intelligence: AI that grasps not just lines of code but the relationships and intent behind them"

Nobody has shipped it. repo-graph 0.4.0 (with v0.4.8 HippoRAG + v0.4.9 multicellular + v0.4.10 mempalace + v0.4.12 loop) is the first attempt to ship the whole thing.

## Positioning consequences

- **Don't lead with "code analysis MCP server"** — that's the commoditised category. Lead with "the format that demonstrated 100x context efficiency" (after v0.4.12b lands the SWE-bench numbers).
- **Don't compete on language count** — v0.4.11 brings parity, but parity isn't the wedge.
- **Path A (v0.4.12a) alone = "another MCP server with nicer formatting"** — commodity space.
- **Path B (v0.4.12b) alone = research demo nobody can use** — irrelevant.
- **Both together = the synthesis.** "Here's the product working with Claude today. Here's the same product on a local model showing the interface commercial APIs don't expose yet. When they open in 2027-2028, repo-graph is already there." That's the frame.

## Context-assembly bottleneck (the equaliser argument)

Current AI coding benchmarks (SWE-bench etc.) have models spending ~30-40% of capacity on context assembly (finding files, understanding deps, building architectural context). With pre-assembled graph context bundles, that capacity returns to reasoning.

- Frontier models improve moderately
- Open source models improve dramatically (context assembly was a larger proportion of their workload)
- The graph layer is an **equaliser between frontier and open source** — that framing matters for the OSS-leaning audience

## Latent-transfer future-proofing

Active research (Interlat Nov 2025, Direct Semantic Communication via Vector Translation Nov 2025, Vision Wormhole Feb 2026). Commercial latent APIs don't exist yet but agentic-workload market pressure forces providers to open non-text interfaces, likely 2027-2028.

The latent vector projection is useful **today** for semantic search. When latent APIs open, the same projection feeds directly into model hidden state. **Design for both uses from day one** = repo-graph is already there when the API opens.
