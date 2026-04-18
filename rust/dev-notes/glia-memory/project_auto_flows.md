---
name: Auto-flow generation
description: Generator auto-builds flows from route nodes when analyzers don't provide their own. Fixed BFS to avoid sibling route contamination.
type: project
originSessionId: 6408138d-8c57-417e-b3fa-73a15b35a7bf
---
`generator.py` has `_auto_flows()` that builds flows from any route node by following handled_by edges. Only React and Angular analyzers generate their own flows; all other languages get auto-flows from the generator.

Key design: BFS must NOT follow `handles` edges back to sibling routes. Only follow: handled_by, defines, contains, imports, calls, uses. Skip any node with type "route" during traversal (prevents cross-contamination).

**Why:** FastAPI flows were including unrelated routes because BFS walked route→module→(handles)→other_route. Fixed by restricting edge types during traversal.

**How to apply:** When modifying flow generation, always verify flows don't include unrelated routes. Test with a project that has multiple routes pointing to the same handler module (FastAPI is a good test case).
