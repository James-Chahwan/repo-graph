---
name: Larger product vision — graph-based IDE + shared human/AI memory
description: repo-graph is the structural foundation of a bigger product; design decisions must account for multicellular nodes, projection-agnostic core, and future latent-vector consumers
type: project
originSessionId: e18af0c7-26eb-409e-8c0d-89cbaf6550d0
---
Surfaced 2026-04-16. repo-graph is not the end product — it is the structural foundation of a graph-based IDE that serves as shared working memory between human developers and AI agents.

**Product stack:**
1. **repo-graph** generates the code graph (exists, evolving)
2. **mempalace** (github.com/mempalace/mempalace, MIT, 41k stars) — memory palace architecture: wings, rooms, halls, tunnels, closets, drawers
3. **Bridge layer** maps repo-graph output into mempalace's palace structure
4. **Native C++ IDE** (not Electron) provides spatial navigation: left panel graph explorer, centre code DAG with slices across files, right panel state transitions + LLM context metrics, bottom Claude Code
5. **MCP integration** — Claude Code talks to repo-graph + mempalace simultaneously

**Architectural insights that must shape repo-graph's evolution:**

**Nodes are multicellular, not just code.** Each node should eventually contain: code, intent, documentation, conversation history, test cases, failure history, constraints, decision records, environment context, ownership/attention metrics, and typed/semantic edges (not just "imports" but "trusts validated output", "crosses auth boundary", "touches money").

**Output format is the critical bottleneck.** Current text output is too verbose for LLM consumption. Need dense symbolic format optimised for transformer attention:
- Topology-first notation (A>B>C style)
- Legend-based operator sigils (`>` depends, `x>` failure propagates, `$` touches money, `^` security boundary)
- Lazy-loaded node content
- Compressed neighbourhood info baked into node encoding

**Token efficiency is the core metric.** Current ~150-200 tokens/entity. Target 40-70 tokens/entity with equivalent or better accuracy on traversal, intent divergence, comprehension.

**Three projections from one source:**
- Binary on-disk container for the IDE
- Dense text projection for current LLMs
- mempalace-compatible format for palace integration
- Future: direct latent vector output for models that support native graph ingestion

**Human-AI architecture mismatch.** Humans experience graphs through parallel activation. LLMs process sequentially through attention layers. Format must give LLMs topology first as scaffolding, then lazy-load content on demand, to approximate humans' native parallel comprehension.

**Future: latent-space communication.** Verbatim user: *"As latent space communication between models matures, the graph engine should eventually pass subgraph representations directly into model internal state as dense vectors rather than serialising to text at all. This means the format architecture should separate the graph data layer from the projection layer cleanly. Future projections will include direct latent vector output for models that support native graph ingestion. Design repo-graph's internal graph representation as projection-agnostic so new output modes can be added without restructuring the core."*

**Sequencing philosophy (user-stated):**
- Phase 1: Format iteration on repo-graph itself using real codebases (quokka-stack as test corpus). CLI only.
- Phase 2: Build the bridge to mempalace.
- Phase 3: Validate value through CLI usage with Claude Code + mempalace + repo-graph MCPs.
- Phase 4: Build the C++ IDE once format and workflow are proven.

**User's strategic framing (2026-04-16):** *"trying to make a data format so that when your interface expands i can just pass you directly efficient context and understanding"* — confirms the canonical graph data is the durable asset. Projectors/analyzers/MCP tools are replaceable; the graph schema + semantics survive across consumers. Pre-computing rich structured data now means any new interface (latent ingestion, new models, competing tools) slots in as a projection rather than a rebuild.

**How to apply to roadmap decisions:**
- Every schema choice must accommodate cells envelope + typed/kinded edges + future latent slot
- Projection layer must be cleanly separable from canonical data — no conflating on-disk JSON with MCP response bodies
- quokka-stack is the canonical test corpus for format validation and token-efficiency benchmarks
- Don't build the IDE yet. Prove the CLI workflow first.
- Don't build mempalace bridge yet. Get format + schema stable first (0.3.0 → 0.5.0).
