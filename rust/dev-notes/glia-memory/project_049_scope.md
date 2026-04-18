---
name: v0.4.9 scope — remaining language parsers only (no testing sweep)
description: v0.4.9 is parsers only; repo-testing sweep moved to v0.4.11 pre-publish; 22 items across core langs, frontend batch, DSL/config, cross-cutting
type: project
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**Decided 2026-04-17.**

### Scope change
User: "for 0.4.9 give me the language list and move repo-testing sweep to the pre publish step in 0.4.11"

v0.4.9 = parsers only. Repo-testing sweep → v0.4.11 (pre-publish validation gate before PyPI).

### v0.4.9 parser list (22 items)

**Done (Rust tree-sitter):** Python, Go, TypeScript (3)

**Core languages (11):**
1. Rust
2. Java/Kotlin
3. C#/.NET
4. Ruby
5. PHP
6. Swift
7. C/C++
8. Scala
9. Clojure
10. Dart
11. Elixir

**Frontend/template batch (5):**
12. React (JSX/TSX)
13. Angular (decorators + HTML templates)
14. Vue (SFCs)
15. HTML/CSS
16. SCSS

**DSL/config (2):**
17. Solidity
18. Terraform

**Cross-cutting extractors (4):**
19. data_sources (DB/cache/queue/blob/search/email)
20. CLI entrypoints
21. gRPC
22. Queues

### Updated v0.4.11
Was: "PyPI publish (0.4.0 public release)"
Now: "repo-testing sweep + PyPI publish (0.4.0 public release)" — sweep is the validation gate before irreversible publish.
