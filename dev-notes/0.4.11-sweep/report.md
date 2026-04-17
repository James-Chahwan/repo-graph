# v0.4.11 validation sweep — 99-repo report

**Date:** 2026-04-17
**Scope:** 99 GitHub repos (shallow-cloned), run through `repo_graph_py.generate()` in isolated subprocesses.
**Harness:** `dev-notes/0.4.11-sweep/{sweep.py, run_one.py, analyze.py, drill.py, repos.txt, results.jsonl}`
**Mix:** 37 depth (full-stack monorepos + queue/gRPC/GraphQL/WS/CLI libs) + 62 breadth (≥2–3 repos per supported language).

---

## Headline

**Parser stability is excellent. Cross-stack layer is mostly unwired and should block publish.**

| | result |
| --- | --- |
| Repos attempted | 99 |
| Clone failures | 0 |
| Generate failures | 0 |
| Generate timeouts | 0 |
| **Cross-stack edges produced** | **0 across all 99 repos** |

---

## Distribution snapshot (ok repos, n=99)

| metric | min | median | p90 | max |
| --- | ---: | ---: | ---: | ---: |
| nodes | 53 | 5,746 | 60,500 | 342,804 (elasticsearch) |
| edges | 24 | 4,979 | 65,667 | 336,081 |
| **cross_edges** | **0** | **0** | **0** | **0** |
| elapsed (s) | 0.0 | 1.4 | 10.4 | 73.1 (kotlin 683MB) |
| size (MB) | 1 | 30 | 280 | 1,332 |

Total across sweep: **2,083,755 nodes, 2,243,664 edges, 0 cross-stack edges.**

---

## CRITICAL issues (block publish)

### C1 — Six of eight cross-cutting extractors are never invoked
**Where:** `rust/py/src/lib.rs:155-227` (`generate_repo_inner`).
**What:** The function iterates source files and dispatches to a per-language parser, *plus* a single hard-coded call to `extract_grpc_service_nodes` for `.proto` files (line 179). No other cross-cutting extractor is called anywhere in `rust/py/` or `rust/graph/` (confirmed by grep outside tests).

**Consequence — aggregate specialty-node counts across the whole 99-repo sweep:**

| kind | count | expected repos that should have contributed |
| --- | ---: | --- |
| ROUTE | 822 | ✓ (emitted by language parsers) |
| ENDPOINT | 1,245 | ✓ (emitted by TS/React/Vue/Angular) |
| GRPC_SERVICE | 87 | ✓ (only specialty extractor that's wired) |
| **GRPC_CLIENT** | **0** | grpc-go, etcd, tikv, temporal, tidb |
| **QUEUE_CONSUMER** | **0** | celery, sidekiq, taskforcesh/bullmq, oban, nats-server |
| **QUEUE_PRODUCER** | **0** | same set + any repo using Celery/Sidekiq/BullMQ |
| **GRAPHQL_RESOLVER** | **0** | graphql-js, apollo-server, dgraph, graphql-ruby |
| **GRAPHQL_OPERATION** | **0** | same set |
| **WS_HANDLER** | **0** | socket.io, centrifugo |
| **WS_CLIENT** | **0** | same |
| **EVENT_HANDLER** | **0** | (no dedicated repo, but expected in nest/immich/novu) |
| **EVENT_EMITTER** | **0** | same |
| **CLI_COMMAND** | **0** | cobra, clap, click, urfave/cli, commander.js |
| **CLI_INVOCATION** | **0** | same |

Extractor code *exists* (`rust/parsers/code/extractors/src/{queues,cli,websocket,eventbus,graphql,grpc}.rs` — all with `pub fn extract_*_nodes`), it's just not called by the pipeline.

**Fix shape:** extend the file loop in `generate_repo_inner` to call each extractor on each parsed file's source (or push them into per-language parsers, à la the `.proto` shortcut). The 8 resolvers further down the function are waiting on this upstream output.

---

### C2 — 0 cross-stack edges across the entire sweep
**Where:** `rust/py/src/lib.rs:220-227` — `MergedGraph::run()` is called for all 8 resolvers (Http, Grpc, Queue, GraphQL, WebSocket, EventBus, SharedSchema, CliInvocation). Every single one produces 0 edges on every repo.

**Root causes (split):**
- For Queue/GraphQL/WebSocket/Event/Cli resolvers: blocked by C1 — nothing to match on the "consumer" side.
- For **HttpStackResolver**: standalone bug, not blocked by C1. The ROUTE + ENDPOINT nodes *do* exist in sibling per-language graphs, yet no cross edges are emitted. Clear evidence:
  - `dotnet/aspnetcore` → 394 ROUTE + 7 ENDPOINT + **0 cross**
  - `spring-projects/spring-boot` → 96 ROUTE + **0 cross** (but few ENDPOINTS in that repo, so partial blame on extraction)
  - Full-stack monorepos (cal.com, medusa, supabase, immich, twenty, strapi, metabase, outline, novuhq, chatwoot, firefly-iii) all produced ENDPOINT nodes (13–336 each) but **0 ROUTE in the same graph**, so there's nothing in-repo to link to.

**Hypothesis for HttpStackResolver producing 0 even when both sides exist:**
1. URL normalisation mismatch (route literal `/api/widgets/{id}` vs endpoint fetch `/api/widgets/123`) — worth logging unmatched pairs.
2. Resolver may require method (GET/POST) match; extractors may emit one side without method.
3. `dotnet/aspnetcore`'s 7 ENDPOINTs are almost certainly framework self-tests (not a cross-stack opportunity) — expected miss.

**Fix shape:** add counter instrumentation to each resolver's `run()` (candidates in, candidates matched, reasons rejected) and re-run on 3 known-good fullstack pairs (cal.com, medusa, supabase) to pinpoint the mismatch.

---

### C3 — 18 of 20 language parsers route through the TypeScript graph builder
**Where:** `rust/py/src/lib.rs:201-211`:
```rust
for (lang, parses) in parses_by_lang {
    let graph = match lang {
        "python" => repo_graph_graph::build_python(repo, parses),
        "go" => repo_graph_graph::build_go(repo, parses),
        _ => repo_graph_graph::build_typescript(repo, parses, |_, _| None),
    };
```

Everything that isn't Python or Go — rust, java, csharp, ruby, php, swift, c_cpp, scala, clojure, dart, elixir, solidity, terraform, react, angular, vue, typescript itself — gets funnelled into `build_typescript`. That builder likely has TS-specific resolution (self-method → class, import resolution, etc) that doesn't map cleanly to other AST shapes.

**Evidence this causes real loss:**
- `metabase/metabase` (Clojure backend + TS frontend): 0 ROUTE nodes despite Compojure/Reitit being the primary framework it's famous for. The 336 nodes reported are ENDPOINT from the TS frontend.
- `playframework/playframework` (Scala): 1 ROUTE total (vs 96 for spring-boot via same fall-through — inconsistent signal, suggests parser emits routes but some are dropped downstream).
- Clojure-specific node kinds absent in the sweep entirely.

**Fix shape:** either (a) per-language graph builders for the other 18, or (b) a generic `build_generic(parses)` that does language-neutral wiring and only opts into language-specific steps when the parser flags them.

---

### C4 — Confidence tiering is effectively inactive
Aggregate over 2.08M nodes:
- strong: 2,083,186 (100.0%)
- medium: 412 (0.02%)
- weak: 157 (0.008%)

The tiering system from 0.2.0 (route with resolved handler → strong, test/fixture paths → weak) doesn't appear to be ported. In the Rust pipeline every parser emits `Confidence::Strong` by default and nothing downgrades. `minimal_read` / `hotspots` budgeting tools that rely on this signal are getting uniform input.

**Fix shape:** port the 0.2.0 downgrade rules — at minimum, mark nodes in test/example/fixture paths as `Weak`; mark ROUTE/ENDPOINT nodes without a cross-stack match as `Medium`.

---

### C5 — No TESTS edges produced (test → code post-pass missing)
`TESTS` (edge category 7) appears exactly once in `rust/graph/src/lib.rs:1300` — as an activation weight (`2.0`). Nothing emits this category. 0 TESTS edges across the 99-repo sweep.

**Fix shape:** port `test_edges.py` from the 0.2.0 Python pipeline (test_file nodes + `tests` edges from detected test files for Py/JS/TS/Go/Ruby).

---

## SECONDARY issues (file but not release-blocking)

### S1 — Backend route extraction weak for JS/TS monorepos
Every full-stack TS monorepo (cal.com, medusa, supabase, immich, twenty, strapi, outline, novuhq, chatwoot, metabase, firefly-iii, appwrite, keystonejs) shows **0 ROUTE nodes** despite running real Next.js / Nest / Express / Remix / Koa backends. Frontend-side ENDPOINT extraction works (13–336 per repo) but the matching backend routes aren't being emitted.

Likely cause: the TS parser doesn't detect `app.get('/...')`, Next.js file-based `pages/api/*`, Nest `@Controller` decorators, or Remix loaders as ROUTE-kind nodes.

This is the upstream cause of many zero-cross-edge fullstack cases in C2.

### S2 — Only 59 of 99 repos produced any specialty node
Raw parser-only detection: 40 repos have 0 specialty nodes (ROUTE / ENDPOINT / GRPC_*). Includes stdlib/utility repos where that's expected (tokio, ripgrep, redis, curl, fmt, nlohmann/json, vue/pinia, etc.) but also `vapor/vapor` (Swift HTTP framework — should have ROUTE), `phoenixframework/phoenix` (Elixir HTTP — should have ROUTE), `rails/rails` (should have ROUTE), `django/django` (should have ROUTE), `laravel/laravel` (should have ROUTE), `symfony/symfony` (31 ROUTE — ✓ partial credit).

### S3 — METHOD vs FUNCTION kind split may be noisy
53.4% of all nodes are METHOD (kind 4) vs 15.0% FUNCTION (kind 3). That's ~1.1M method nodes across 99 repos. Worth reviewing whether the split pays for itself in downstream queries, or whether consolidating them (with a `is_method: bool` attribute) would simplify.

### S4 — Perf outliers are reasonable
Only 2 repos > 30s:
- `JetBrains/kotlin` — 73.1s on 683MB, 246k nodes. Acceptable.
- `elastic/elasticsearch` — 31.3s on 580MB, 343k nodes. Acceptable.

Median 1.4s is excellent. No fixes needed.

---

## Positive signal (what's working)

- **Clone + parse pipeline:** 99/99 success on a deliberately diverse repo set. Tree-sitter grammar integration is solid — no crashes on any of the 20 supported languages or on the edge cases (large repos, monorepos, shallow clones).
- **Go route extraction:** gin 93, echo 94, vault 7, consul 3 — consistent and matches framework conventions.
- **Spring Boot route extraction:** 96 routes detected.
- **ASP.NET route extraction:** 394 routes — best in class for this sweep.
- **gRPC service extraction (`.proto`-based):** etcd 8, grpc-go 8, temporal 6, tikv (no output — worth spot-check), consul 13 (likely via embedded proto).
- **TS endpoint extraction (frontend fetch/axios):** cal.com 68, medusa 13, twenty 188, vercel/next.js 129, metabase 336.
- **Terraform module detection:** hashicorp/terraform 7 GRPC_SERVICE (these are the provider plugin interfaces — detected correctly as gRPC).

---

## Suggested 0.4.11 patchset order

Assuming you want to ship this as 0.4.11 before publishing to PyPI:

1. **C1** — wire the 6 unused extractors into `generate_repo_inner`. Biggest blast radius per line of code. After this, re-run the sweep and diff specialty-node counts.
2. **C5** — port test-edge post-pass. Small, mechanical.
3. **C2 (Http)** — add per-resolver counter logging, re-run, diagnose URL-match failures. May depend on S1 landing first to see any match.
4. **S1** — backend TS route extraction (Next.js API, Nest `@Controller`, Express `app.METHOD`, Remix loaders). Probably the biggest parser delta.
5. **C4** — confidence downgrade rules for test/fixture paths and unmatched routes.
6. **C3** — leave for 0.4.12+ unless the per-language evidence is overwhelming; the TS builder fall-through may be "works fine" for most non-Python/Go cases.

Re-running `dev-notes/0.4.11-sweep/sweep.py` after each of the first three fixes takes ~17 minutes and requires no manual curation.

---

## Artifacts

- `dev-notes/0.4.11-sweep/results.jsonl` — raw per-repo record (99 lines)
- `dev-notes/0.4.11-sweep/analysis.txt` — full analysis output
- `dev-notes/0.4.11-sweep/sweep.log` — live progress log
- `dev-notes/0.4.11-sweep/{sweep,run_one,analyze,drill}.py` — re-runnable harness
- `dev-notes/0.4.11-sweep/repos.txt` — the 99-repo list
