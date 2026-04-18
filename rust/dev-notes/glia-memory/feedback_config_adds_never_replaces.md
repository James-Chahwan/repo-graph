---
name: Config extends, never replaces auto-detection
description: Repo-graph config.yaml roots/skip always union with auto-detection — never swap it out. Preserves heuristic value for users who only need to patch edge cases.
type: feedback
originSessionId: e18af0c7-26eb-409e-8c0d-89cbaf6550d0
---
When wiring new config knobs into repo-graph, config values must extend heuristics, not replace them.

**Why:** Users hit config when auto-detection *misses* something (weird monorepo, custom layout). If config replaced heuristics, they'd have to redeclare every root the heuristics already found — friction that makes config useless for the common "one-off patch" case. This pattern was baked into Step 2 by design.

**How to apply:**
- `skip:` extends FileIndex's built-in skip set (node_modules, target, etc.), never replaces it
- `roots:` unions with each analyzer's auto-detected roots via `extra_roots(kind)` — never short-circuits detection
- When adding new config fields (Step 3+: flow kinds, entrypoints), keep the same shape — config fields are *additional*, not authoritative

Concretely: `_find_X_roots` in every analyzer ends with `return sorted(set(auto) | set(index.extra_roots("X")))` — not `return config_roots or auto`.
