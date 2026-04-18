---
name: Language analyzer expansion
description: 20 analyzers total — 13 original + 7 added 2026-04-15 (Scala, Dart/Flutter, Clojure, Vue, Elixir, Solidity, Terraform).
type: project
originSessionId: 0e62cb6a-08b1-4aa8-869a-5e18a4072869
---
**Current total:** 20 analyzers.

**Original 13 (through 2026-04-13):** Go, Rust, TypeScript, React, Angular, Python, Java/Kotlin, C#/.NET, Ruby, PHP, Swift, C/C++, SCSS.

**Added 2026-04-15:** Scala, Clojure, Vue, Dart/Flutter, Elixir/Phoenix, Solidity, Terraform. Driver was community requests (Scala, Clojure as Lisp-dialect choice) plus obvious gaps (Vue to round out React/Angular; Elixir and Solidity/Terraform as underserved domains).

**Why:** User prefers additive coverage when a gap is visible — Perl was explicitly dropped as low-ROI. Lisp request resolved as Clojure specifically (CL/Scheme punted as too niche for regex heuristics).

**How to apply:** All 20 registered in `_analyzer_classes()` in `repo_graph/analyzers/__init__.py`, ordered by specificity. Vue slotted after React/Angular but before TypeScript (all check `package.json` deps). Scala/Clojure slotted among JVM block. Solidity and Terraform are additive — their markers (.sol, .tf files) never conflict with other stacks.

**Design notes from this pass:**
- Solidity detection must skip child dirs when parent is already a root (contracts/ under a foundry.toml project would otherwise double-register).
- Terraform treats every dir containing .tf files as its own `tf_module`, with `sources` edges from module calls to local/remote module targets.
- Vue router detection requires `createRouter`/`createWebHistory` markers, not just `routes` strings (avoids false positives).
- Elixir route scopes are resolved by nearest-preceding scope position (best-effort prefix concat).
