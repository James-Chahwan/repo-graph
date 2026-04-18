---
name: v0.4.11a scope — C3 and other cross-stack-adjacent followups
description: New followup-fix bucket between v0.4.11 and v0.4.12 PyPI cut, created 2026-04-17 when C3 severity was understood.
type: project
originSessionId: 5d22b623-66cd-4680-a7b3-62cb185a9f5d
---
v0.4.11a is the label for correctness fixes that emerged during the v0.4.11 cross-stack validation sweep but aren't blockers for cross-stack itself. Sits between v0.4.11 (code landed, e0137a9) and v0.4.12 (PyPI publish cut).

**Why it exists:** user realised on 2026-04-17 that C3 was under-scoped. Verbatim: *"ohmy gawd they should of all been added"* — on learning that 18 of 20 language parsers fall through to `build_typescript` during graph construction. Rescoped from v0.4.12 to v0.4.11a: *"this is now 0.4.11a - fixes like c3 we have to deal with"*.

**C3 — per-language graph building**
- **Where:** `rust/py/src/lib.rs:489–499`. Dispatch today is python/go/_default=typescript.
- **What breaks:** parsers for rust/java/csharp/ruby/php/swift/c_cpp/scala/clojure/dart/elixir/solidity/terraform/react/angular/vue (+ js/ts) all go through `build_typescript`. That resolver applies TS-shaped `./foo` closure path-resolution to their imports — wrong semantics for every non-TS language.
- **What still works:** parsing (20 languages), node emission, cross-stack resolvers (HttpStack/Grpc/Queue/GraphQL/WS/EventBus/SharedSchema/CliInvocation — operate on qnames + ROUTE nodes, language-agnostic).
- **What's degraded:** intra-repo CALLS resolution for the 18 affected languages. Parser emits call sites, symbol-table join under-fires because import resolution is TS-shaped.
- **Fix shape:** per-language `build_<lang>` functions (Rust use-resolution, Java package imports, C# using, PHP namespaces, Ruby require, etc.) — OR a generic `build_language<R: ImportResolver>` with a trait and per-language impls. The `extra_hook` seam in `resolve_calls` is already reserved for this.
- **Not a publish blocker:** cross-stack sweep still passed because cross-stack doesn't depend on CALLS density. But CALLS-edge correctness is first-class for the product.

## Confirmed v0.4.11a scope (2026-04-17)

User decisions:
- **D1 + C3 in:** *"yeah the d1 + c3 for sure"*
- **D1 shape:** *"yeah rewrite properly"* — full rewrite to Node-emitting ExtractResult shape, not substring detection. 6 categories (DB/Cache/Queue/BlobStore/Search/Email) need new NodeKinds + likely new EdgeCategory (DB_ACCESSES etc.).
- **Per-language route coverage:** *"that route extraction per language i guess should be done as a seperate tasks in this"* — each language parser's route-extraction gap is its own task inside v0.4.11a, not a single monolithic fix.
- **Audit scope for pre-work:** *"if you can do a quick audit on say java c# say php they usually the big guys for projects still"*

## Audit findings (Java / C# / PHP, 2026-04-17)

**Java (`rust/parsers/code/java/src/lib.rs:170–215`)** — matches 0.2.0 coverage:
- ✓ Spring `@GetMapping/Post/Put/Delete/Patch/@RequestMapping`
- ✓ JAX-RS `@Path + @GET/@POST/@PUT/@DELETE`
- Gaps (not 0.2.0 regressions): Kotlin Ktor, Spring WebFlux RouterFunction DSL, Micronaut.

**C# (`rust/parsers/code/csharp/src/lib.rs:219–253`)** — partial vs 0.2.0:
- ✓ ASP.NET attrs `[HttpGet/Post/Put/Delete/Patch]`
- ✓ Minimal API `app.MapGet/Post/Put/Delete/Patch`
- Gaps: `[Route("/path")]` standalone + class-level attribute (very common), `[Route("api/[controller]")]`, conventional `MapControllerRoute`.

**PHP (`rust/parsers/code/php/src/lib.rs:307–328`)** — **REGRESSION vs 0.2.0**:
- ⚠ Symfony `#[Route(...)]` only matches GET/POST, defaults to ANY for PUT/DELETE/PATCH
- ⚠ **Laravel has zero coverage** — no `Route::get/post/put/delete/patch`, no `Route::resource`, no route groups. 0.2.0 memory claims "Laravel/Symfony routes"; Laravel support was dropped in the Rust port.

## Full audit results (all 19 code parsers, 2026-04-17)

Grepped each `rust/parsers/code/<lang>/src/lib.rs` for route-extraction code. Cross-referenced against 0.2.0 per-analyzer framework coverage from CLAUDE.md.

**Parsers with route extraction matching 0.2.0:**
- `java` — Spring + JAX-RS (lines 170–215). Shape B.
- `go` — gin + generic `.METHOD(…)` (lines 490+). Shape A.

**Parsers with partial coverage (pre-existing gaps):**
- `csharp` (lines 219–253) — ASP.NET attrs + Minimal API. Missing `[Route(…)]` standalone/class-level + conventional `MapControllerRoute`.
- `rust` (lines 292–337) — Actix/Rocket `#[get/post]`. **Missing Axum `.route("/x", get(h))` — dominant modern Rust web framework.**
- `php` (lines 307–328) — Symfony partial, GET/POST only. **Laravel entirely absent** — `Route::get/post/put/delete/patch`, `Route::resource`, groups. Regression vs 0.2.0.

**Parsers with zero route extraction (regressions vs 0.2.0):**
- `python` (728 lines) — needed Flask/FastAPI/Django, has 0.
- `ruby` (357 lines) — needed Rails, has 0.
- `swift` (387 lines) — needed Vapor, only `import Vapor` string matched in source, no extraction.
- `dart` (410 lines) — needed go_router/shelf, has 0.
- `elixir` (437 lines) — needed Phoenix, only `Phoenix.Controller` string matched, no extraction.
- `scala` (395 lines) — needed Play/Akka HTTP/http4s, has 0.
- `clojure` (438 lines) — needed Compojure/Reitit, has 0.

**Thin-wrapper parsers (framework extraction regressions):** each ≤75 lines, just dispatches to `parser-typescript::parse_file` with a detection fn. 0.2.0 had full framework-specific extraction.
- `react` (54 lines) — no React Router, no hooks classification, no components as distinct node kinds.
- `angular` (58 lines) — no Angular Routes, no `@Injectable` DI classification, no component/service/guard/pipe/directive as distinct kinds.
- `vue` (75 lines) — only strips `<script>` tag, no template parsing, no Vue Router, no composables classification.

**No coverage needed:** `c_cpp`, `solidity`, `terraform`.

**Adjacent — `ts_routes` extractor (v0.4.11 S1 fix):** covers Next.js Pages Router, Next.js App Router (with `[id]→:id`), Express, Koa, Hono. Missing: tRPC, NestJS (`@Controller/@Get/@Post` decorators), Remix, fastify.

## Full v0.4.11a item list (19 items, 5 classes)

**Class A — dispatch/wire-up bugs (high severity, small fix):**
- C3: per-language graph build dispatch
- D1: data_sources extractor rewrite + wire-up

**Class B — route regressions vs 0.2.0 (high, one task per language):**
- R-python (Flask/FastAPI/Django)
- R-ruby (Rails)
- R-dart (go_router/shelf)
- R-scala (Play/Akka/http4s)
- R-clojure (Compojure/Reitit)
- R-php (Laravel + Symfony method coverage)
- R-swift (Vapor)
- R-elixir (Phoenix)

**Class C — route gaps in parsers that already have some coverage (medium):**
- R-rust-axum (Axum `.route` pattern)
- R-cs-route (`[Route]` attribute + conventional routing)
- R-ts-extras (tRPC, NestJS, Remix, fastify in ts_routes)

**Class D — framework-specific extraction regressions (high, large fix per framework):**
- F-react (Router, components-as-nodes, hooks classification)
- F-angular (Routes, DI classification, component/service/guard/pipe/directive node kinds)
- F-vue (Router, SFC template/composable awareness)

**Class E — new-framework additions (low, not regressions):**
- Ktor / Spring WebFlux / Micronaut on Java

Minimum-viable v0.4.11a = Classes A + B (10 items). Classes A–D (16 items) = full parity with 0.2.0 + modern Axum/NestJS coverage.

## Publish sequence

- v0.4.11 — committed e0137a9 (cross-stack C1–C5 + S1 + F1)
- v0.4.11a — C3 + D1 + per-language route fixes (each parser = own task)
- v0.4.12 — PyPI + MCP Registry + GitHub release
- v0.4.13 — candle / latent / SWE-bench Lite / multi-agent proof

**Full v0.4.11 validation report:** `dev-notes/0.4.11-sweep/post-patch-report.md`.
