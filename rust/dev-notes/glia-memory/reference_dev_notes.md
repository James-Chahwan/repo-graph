---
name: dev-notes/0.3.0-decisions.md — decisions log and tag convention
description: Running log of 0.3.0 implementation decisions; together with fixtures it is the 0.4.0 Rust spec
type: reference
originSessionId: f5091c3e-4ad2-47ca-be6b-233c911fb6a7
---
**Location:** `dev-notes/0.3.0-decisions.md` in repo root. Excluded from
sdist via `MANIFEST.in`. Never shipped to users.

**Role:** Pair artifact with `tests/fixtures/py_smoke/`. Verbatim user
framing: "Fixtures tell Rust what to do. Log tells Rust why."

**Entry format (enforced):**
```
## YYYY-MM-DD: <topic>
**Category:** [SCOPE-DRIVEN] | [PRINCIPLED]
**Decision:** one sentence
**Considered:** alternatives rejected
**Why this:** rationale for Python 0.3.0
**Rust implication:** what 0.4.0 should do
```

**Tag semantics:**
- `[SCOPE-DRIVEN]` — Python choice forced by stdlib/regex/scope limits.
  Entry is directive: "Rust should do X instead." Gives Rust permission
  to diverge. These are candidates for improvement in 0.4.0.
- `[PRINCIPLED]` — semantic decision standing on its merits. Entry is
  contextual: "decided X because Y; Rust inherits or chooses." These are
  contracts Rust honours unless it has a reason to break them.

**Seeded entries (2026-04-16):** 13 items covering ID shape, type
vocabulary, calls confidence, self-call scope, call source granularity,
import granularity, namespace packages, route AST, nested functions,
auto-flows rule, parsing passes, qname separator, syntax-error handling.

**How to use in future sessions:**
- When Rust 0.4.0 work starts, read this log in full — each `Rust implication`
  field is prescriptive for SCOPE-DRIVEN items, contextual for PRINCIPLED.
- Add new entries chronologically as implementation surfaces decisions.
- Do not rewrite past entries. If a decision reverses, add a new entry
  dated the reversal and cross-reference the prior.
- If a PRINCIPLED decision proves wrong, the new entry upgrades it to
  SCOPE-DRIVEN (Python was forced into it) and gives Rust the corrected
  direction.

**Related:**
- `tests/fixtures/py_smoke/` — the fixture half of the Rust spec.
  Two modules, one class, relative + absolute imports, cross-file and
  self calls, one deliberately-dropped call (`u.login()` where `u` is
  a local variable of unknown type).
- `tests/test_py_smoke.py` — 8 assertions locking the fixture contract.
