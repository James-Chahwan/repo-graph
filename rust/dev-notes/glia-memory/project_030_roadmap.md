---
name: 0.3.0 — dev branch (never ships) — IMPLEMENTED 2026-04-16
description: 0.3.0 is a dev-only branch capturing Python AST semantics; fixtures + decisions log are the spec for 0.4.0 Rust rewrite
type: project
originSessionId: f5091c3e-4ad2-47ca-be6b-233c911fb6a7
---
**IMPLEMENTED 2026-04-16.**

**0.3.0 never ships to PyPI.** Verbatim (2026-04-16): "0.3.0 is a development
branch, not a public release. It will never ships to PyPI. Users stay on 0.2.0
until 0.4.0 lands. When 0.4.0 drops, the 0.3.0 branch gets archived."

Reason: Python AST work benefits Python only. Shipping a Python-only feature
release creates two user migrations (0.2.0 → 0.3.x → 0.4.0) and splits
maintainer focus. Cleaner to keep 0.3.0 internal and hand users one upgrade
at 0.4.0 with everything.

**What 0.3.0 actually produces (the durable output):**
Per user: "The fixtures survive, not the Python implementation." The Python
code is scaffolding; the fixtures at `tests/fixtures/py_smoke/` are the
spec for 0.4.0 Rust rewrite. The log at `dev-notes/0.3.0-decisions.md` is
the why-spec alongside the what-spec (fixtures).

**Implementation results on repo_graph itself (2026-04-16):**
- 243 `py_method` nodes (0 in 0.2.0)
- 438 `calls` edges (0 in 0.2.0)
- 31 `imports` edges including absolute imports (0.2.0 silently dropped abs imports)
- Two-pass AST walk in single file `repo_graph/analyzers/python_lang.py`
- 8 pytest tests passing (`tests/test_py_smoke.py`)

**Locked scope (all implemented):**
1. `analyzers/python_lang.py` rewritten on stdlib `ast` — one file, no subpackage
2. `py_method` nodes with ID shape `py_method_{class_id}_{name}`
3. `calls` edges — cross-file, self-call in-class, constructor calls; ambiguous drops
4. Absolute imports produce `imports` edges (`_IMPORT_ABS` regex was unused in 0.2.0)
5. `_auto_flows` tightened: source with outgoing `calls` skips `defines`/`contains`
6. pytest added as dev-dep only; fixtures as Rust spec

**Validation observation — logged in decisions entry #10:** the prefer-calls
rule only bites at function/method sources. Python 0.3.0 functions rarely
have outgoing `defines`/`contains` to compete with calls. Real-repo flows
still show module-defines pollution. Genuine fix requires decorator-aware
routing (item 8) and edge-category priorities (item 10) — both 0.4.0 work.

**What's out of 0.3.0 (all → 0.4.0):**
Schema redesign, ID scheme change, edge.kind, multicellular nodes, dense text,
binary format, mempalace bridge, `Node.extras`, `called_by` tool, namespace
packages, decorator AST, nested functions as nodes, inheritance/MRO in self-call
resolution, symbol-level imports, single-walk parsing, syntax-error recovery.

**Why simplification helped 0.4.0:** 0.4.0 is Rust greenfield, not a port.
Python 0.3.0 is not its spec — it's the last Python feature release.
Pretending 0.3.0 was a foundation would have locked Python into decisions
(qname canonicality, resolution policy, fixture bytes, notation sigils)
that 0.4.0 should be free to redesign.

---

**HISTORY — superseded plans:**
- 2026-04-16 earliest: "bundled data-architecture + AST" with schema v2 — dead, assumed Python would produce new format.
- 2026-04-16 mid: "AST-only Python-only" with SymbolTable subpackage, Node.extras bridge, three-release sequence (0.3.0/0.3.1/0.3.2) — dead, over-engineered.
- 2026-04-16 late: AST as improvement only, still framed as a public release — revised to dev-branch-never-ships after user decided Python-only-release splits user migrations.
- Current: dev-branch, fixtures + log are the artifact, Python impl is scaffolding.
