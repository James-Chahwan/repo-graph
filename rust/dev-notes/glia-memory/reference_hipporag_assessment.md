---
name: HippoRAG paper assessment for v0.4.6
description: Technical analysis of HippoRAG (arXiv 2405.14831, NeurIPS 2024) — what to take, what to discard, three adaptation concerns for code graphs
type: reference
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**Assessed 2026-04-17.** Paper by Bernal Jiménez Gutiérrez et al. (Ohio State).

### Core mechanism
HippoRAG's "spreading activation" is actually **Personalized PageRank (PPR)** via igraph's PRPACK solver:
```python
graph.personalized_pagerank(damping=0.5, directed=False, weights='weight', reset=reset_prob)
```
- Damping=0.5 (aggressive vs vanilla PageRank's 0.85) — 50% restart probability keeps activation tightly local around seed nodes
- PRPACK uses direct LU decomposition, not iterative convergence
- Node specificity pre-multiplier: `s_i = |P_i|^{-1}` (IDF-style, rare nodes boosted)

### What we take
- Directed weighted PPR on our existing graph, seeded from exact node IDs
- Top-K activated subgraph as query result ("relevance halo")
- Multi-path convergence property: nodes reachable from multiple seed paths score higher naturally — this is the thing BFS can't do

### What we discard (most of the paper)
- OpenIE extraction pipeline (we already have the graph)
- NER-based seed selection (we have exact node IDs)
- Synonymy edges via embedding cosine similarity
- Undirected graph assumption

### Three adaptation concerns for code graphs

1. **Edge types matter but PPR ignores them.** HippoRAG treats all edges identically. We need edge-type weights as a parameter — `calls` should propagate more than `contains`, `tests` edges different again. PPR supports weighted edges natively.

2. **Direction matters.** HippoRAG runs undirected. Impact analysis needs forward propagation; trace needs backward. Need directed PPR or separate forward/backward passes.

3. **Node specificity is inverted.** IDF-based weighting (rare nodes boosted) is wrong for code — a utility called by 50 modules is important *because* it's widely used. Flip or drop this weighting.

### Non-concerns
- **Scale:** 1,350 nodes / 2,500 edges → PPR runs in microseconds. Paper tested up to ~92K nodes / ~213K edges.
- **Algorithm soundness:** PPR is well-understood, decades of research. No novel risk.

### Paper performance
- Online: ~180ms/query (dominated by LLM NER call, not PPR)
- Error breakdown (100 MuSiQue errors): 48% NER, 28% OpenIE, 24% PPR (diffuse activation when concept appears in many unrelated contexts)
- PPR failure mode: damping=0.5 mitigates but doesn't eliminate diffuse spread

### User's read
User confirmed it *"sounds pretty logical and is the next step for the leap"* — no concerns raised. The algorithm is the moat differentiator vs commoditising code-graph MCP space.
