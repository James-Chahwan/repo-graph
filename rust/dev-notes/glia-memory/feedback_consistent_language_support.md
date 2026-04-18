---
name: Analyzer consistency across all supported languages
description: When upgrading analyzer capability (AST, framework detection, etc), apply it uniformly across all supported languages — don't leave a patchwork
type: feedback
originSessionId: e18af0c7-26eb-409e-8c0d-89cbaf6550d0
---
User rejected the idea of Python-stdlib-ast-first-then-tree-sitter-later on 2026-04-15: "nah it seems like we should put ast's for every language we support in 0.3.0" and later "0.3.0 should really be our ast jump for every language we support how does that sound ? would that help with our analysers"

**Why:** a patchwork where Python has AST but Go is still regex means users get unpredictable behaviour depending on their stack. Consistent capability across languages is part of the product promise — it's why the tool handles 20 languages in the first place.

**How to apply:** when adding an analyzer capability upgrade, scope it across ALL currently-supported languages as one workstream. Staging is acceptable (tier 1/tier 2 split) as long as each tier delivers complete capability for its languages. Don't ship "Python has X, the others don't" as a baseline state.

Corollary: when adding new cross-cutting features (test framework confirmation, confidence tiers), do them for all languages at once. We already did this for the 0.2.0 test framework confirmation — correct instinct.
