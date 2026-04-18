---
name: v0.4.9 complete — all language parsers built
description: v0.4.9 done 2026-04-17: 20 parser crates + 1 extractor crate, 150 tests, clippy clean; tree-sitter quirks documented
type: project
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**Completed 2026-04-17.**

### Final inventory (23 workspace crates total)

**Core language parsers (16 crates, each with tree-sitter AST):**
Python, Go, TypeScript, Rust, Java, C#, Ruby, PHP, Swift, C/C++, Scala, Clojure, Dart, Elixir, Solidity, Terraform

**Framework overlay parsers (3 crates, delegate to TS parser):**
React, Angular, Vue

**Cross-cutting extractors (1 crate with 4 modules):**
`repo-graph-code-extractors`: data_sources, cli, grpc, queues

**Not created as separate crates:** HTML/CSS, SCSS — no meaningful AST entities; handled by graph crate's file indexing.

### Stats
- 150 tests, 0 failures, 0 clippy warnings
- All parsers produce FileParse (nodes, edges, imports, calls, refs, nav)
- Graph integration (build_<lang> + resolve_imports_<lang>) NOT done — deferred to graph crate

### Tree-sitter grammar quirks encountered

1. **tree-sitter-clojure v0.1** links tree-sitter 0.25, conflicts with workspace's 0.26. Switched to `tree-sitter-clojure-orchard v0.2` (uses tree-sitter-language, no conflict).

2. **tree-sitter-swift v0.7.1** uses `class_declaration` for ALL type declarations (class/struct/enum/actor/protocol). Distinguished by unnamed keyword child. Fixed with `swift_type_kind()` helper. Body found by `_body` suffix match, not field name.

3. **tree-sitter-dart v0.1** uses `class_declaration` (not `class_definition`), no field-named `name` — identifier is unnamed child. Same for enums. Fixed with `find_identifier()` helper.

4. **tree-sitter-elixir v0.3** — `arguments` is NOT field-named (just a named child). Module names are `alias` nodes. Function names in `def` are nested inside a `call` node in arguments. `Repo.get` is a `dot` target node. Fixed with `find_args()` helper.

5. **tree-sitter-hcl v1.1** root is `config_file` → `body` → `block` (extra body wrapper). `string_lit` has nested `quoted_template_start`/`template_literal`/`quoted_template_end` structure.

### Crate dependency note
- Framework parsers (React/Angular/Vue) depend on `repo-graph-parser-typescript`
- Cross-cutting extractors use `repo-graph-core` only (no tree-sitter), `repo-graph-code-domain` as dev-dep for tests
- All tree-sitter grammars using `tree-sitter-language` crate (dart, elixir, solidity, hcl, clojure-orchard) avoid the native linking conflict
