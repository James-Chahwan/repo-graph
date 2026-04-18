---
name: 0.2.0 analyzers are not the ceiling for 0.4.x parsers
description: 0.2.0 Python regex analyzers are a hint about what concepts exist (route, import, function). They are NOT the upper bound on what 0.4.x AST parsers should extract. AST makes more available — capture it.
type: feedback
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
Rule: when designing a 0.4.x parser, don't frame its goal as "structural superset of the 0.2.0 analyzer". That's a floor, not a ceiling. AST-driven parsing catches things regex couldn't — nested defs, proper decorator targets, typed cross-file resolution, struct/interface/enum declarations, generics, typed routes. The v0.4.x bar is **what a proper AST parser can extract**, not **what the old regex script happened to capture**.

**Why:** 2026-04-17 during v0.4.3b scoping, I proposed the parser-go / parser-typescript shape as "the 0.2.0 files go.py/typescript.py/angular.py are the reference for what to extract; the AST rewrite is how". User verbatim: *"hold on they aren't since we are improving massively"*. The 0.2.0 regex analyzers miss a lot (Go structs, interfaces, methods with receivers; TS enums, generics, decorator-resolved component targets; Angular DI edges; etc.). Anchoring on them as the reference caps 0.4.x at 0.2.0's ceiling.

**How to apply:**
- Use 0.2.0 for concept discovery only ("routes exist, imports exist, fetch-calls exist").
- Design the 0.4.x parser from first principles on the AST — what does tree-sitter-go / tree-sitter-typescript make trivially available?
- Ask the user what "massively improve" means for the specific language before scoping — they may have specific things in mind (e.g., struct/interface/enum, DI graph, generic types, template refs).
- Structural-superset against 0.2.0 fixtures stays as a regression gate, not as a target.
- Don't claim "just the AST rewrite" when the shape of the output is also being improved — be honest that scope is bigger.
