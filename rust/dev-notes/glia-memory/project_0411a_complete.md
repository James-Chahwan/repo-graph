---
name: v0.4.11a complete — route regressions + frontend framework extractors
description: v0.4.11a bucket (18 items) finished 2026-04-17, commit dd23030; internal version, no PyPI publish (v0.4.12 is the cut).
type: project
originSessionId: 5d22b623-66cd-4680-a7b3-62cb185a9f5d
---
All 18 v0.4.11a followup items done and committed as dd23030 on 2026-04-17, rolling up 17 sub-commits. 33 commits ahead of `github/main`.

**User directive that kicked off the bucket execution:** *"okay your doing them all one by one"* — meaning tackle every v0.4.11a item sequentially.

## What shipped

- **C3** — per-language graph build dispatch (was routing 18/20 langs through `build_typescript`). Sub-commit 861b619.
- **D1** — data_sources extractor full rewrite (*"yeah rewrite properly"*): substring detection → Node-emitting ExtractResult. Commit ec55ff0.
- **R-python** Flask/FastAPI/Django routes restored (3ba010d).
- **R-ruby** Rails routes (60d4465).
- **R-dart** go_router/shelf (692a9ef).
- **R-scala** Akka HTTP + http4s (fa3f211).
- **R-clojure** Compojure + Reitit (746b89e).
- **R-php** Laravel + Symfony full method coverage (incl. `Route::resource` REST expansion) (821eb38).
- **R-swift** Vapor (4e8f2bd).
- **R-elixir** Phoenix with scope stack tracking (1c1bc27).
- **R-rust-axum** Axum `.route("/path", get(h).post(h2))` chain (4772c9a).
- **R-cs-route** `[Route]` attribute + HEAD/OPTIONS verbs (8049fd4).
- **R-ts-extras** NestJS (@Controller+@Get/etc. prefix combine) + SvelteKit (+server.ts path inference) via `ts_routes` extractor (23f0a85).
- **F-react** NEW `extractors/src/react.rs` — COMPONENT/HOOK/ROUTE (4078856).
- **F-angular** NEW `extractors/src/angular.rs` — COMPONENT/SERVICE/DIRECTIVE/PIPE/GUARD/ROUTE (a218003).
- **F-vue** NEW `extractors/src/vue.rs` — COMPONENT/COMPOSABLE/ROUTE (7d08f1b).
- **Java ecosystem** — Ktor (Kotlin DSL), Spring WebFlux, Micronaut (27d9f36).
- **Version bump** — `pyproject.toml` + `rust/py/Cargo.toml` → 0.4.11 (dd23030).

## New NodeKinds added in code-domain

7 kinds registered for frontend framework entities:

| ID | Name |
|----|------|
| 28 | COMPONENT |
| 29 | HOOK |
| 30 | SERVICE |
| 31 | DIRECTIVE |
| 32 | PIPE |
| 33 | GUARD |
| 34 | COMPOSABLE |

## Engineering technique — text-scan false-positive gating

For frameworks where AST signatures are ambiguous (Ktor Kotlin DSL, Axum method chains, Phoenix scopes, Laravel Route facade), parsers use text-scan extraction. Two gates prevent false positives:

1. **Word-start gating** — reject matches where the preceding char is alnum/`_` (e.g., `forget("x")` must not match `get(`).
2. **Brace-lookahead** — for block DSLs like Ktor, require `{` after the call to confirm it's a route definition, not an arbitrary helper.

Used throughout the new extractors. Confidence is **Medium** for text-scan routes (vs **Strong** for AST-anchored).

## Publish state

- v0.4.11 / v0.4.11a = internal validation + regression fixes. No PyPI/MCP Registry publish.
- v0.4.12 = PyPI publish cut (next).
- v0.4.13 = candle / latent / SWE-bench Lite / multi-agent.

Full cargo test passed across workspace after all changes.
