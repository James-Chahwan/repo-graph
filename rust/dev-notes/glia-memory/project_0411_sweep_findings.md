---
name: v0.4.11 sweep — 5 critical cross-stack bugs
description: Concrete v0.4.10 bugs surfaced by the 99-repo sweep 2026-04-17; root causes + file locations. Patch targets for 0.4.11.
type: project
originSessionId: 5d22b623-66cd-4680-a7b3-62cb185a9f5d
---
The sweep (99 repos, 2,083,755 nodes aggregate) showed **0 cross-stack edges across the entire set**. Parser layer is solid; cross-stack layer is almost entirely unwired.

**Why:** these bugs are systemic (single-location fixes, high blast radius), not per-repo. Likely introduced when v0.4.9 parsers and v0.4.10 resolvers landed but the extractor→resolver plumbing between them was skipped. Important to address before first Rust-backed PyPI release (would ship a feature-empty pipeline).

**How to apply:** when touching the Rust pipeline in `rust/py/src/lib.rs` or any `rust/parsers/code/extractors/src/*.rs`, start from this list rather than re-discovering. Locations & evidence:

- **C1: 6 of 8 cross-cutting extractors never invoked.** `rust/py/src/lib.rs:155-227` only hard-codes `extract_grpc_service_nodes` for `.proto` files (line 179). `queues/cli/websocket/eventbus/graphql/grpc-client` extractors exist (`pub fn extract_*_nodes` in each file under `rust/parsers/code/extractors/src/`) but are dead code. Sweep totals: QUEUE_CONSUMER 0, CLI_COMMAND 0, WS_HANDLER 0, GRAPHQL_RESOLVER 0, EVENT_HANDLER 0, GRPC_CLIENT 0 — despite repos chosen specifically to exercise each (celery, sidekiq, bullmq, cobra, clap, click, socket.io, apollo-server, graphql-js). Fix shape: extend the file loop to call each extractor on each parsed source. This is the single highest-leverage fix.

- **C2: HttpStackResolver emits 0 edges even when both sides exist.** `rust/py/src/lib.rs:220-227` runs all 8 resolvers, but `dotnet/aspnetcore` (394 ROUTE + 7 ENDPOINT) and `spring-projects/spring-boot` (96 ROUTE) both produce 0 cross edges. Queue/GraphQL/WS/Event/CLI resolver nulls are blocked by C1, but Http is independent. Probable cause: URL normalisation or method-match mismatch. Fix shape: add per-resolver counter instrumentation (candidates in/matched/rejected-with-reason) before patching blindly.

- **C3: 18 of 20 parsers fall through to `build_typescript`.** `rust/py/src/lib.rs:201-211` — only `"python"` and `"go"` have dedicated graph builders; everything else uses `_ => build_typescript(repo, parses, |_, _| None)`. Evidence of data loss: `metabase/metabase` (Clojure/Compojure) produces 0 ROUTE despite being route-famous; `playframework/playframework` 1 ROUTE vs Spring 96 under same fall-through. May be deferrable to 0.4.12 if specialty extraction (C1) gives enough wins first.

- **C4: Confidence tiering inactive.** 2,083,186 strong / 412 medium / 157 weak across the sweep (99.97% strong). 0.2.0 Python pipeline had test/fixture → weak and unmatched-route → medium downgrades; not ported to Rust. `minimal_read` / `hotspots` budgeting loses signal. Fix shape: port downgrade rules, likely in each `build_*` graph builder or as a post-pass.

- **C5: TESTS edges never emitted.** Edge category 7 appears *once* in the Rust tree — as an activation weight in `rust/graph/src/lib.rs:1300`. No extractor produces it. 0.2.0 had a `test_edges.py` post-pass (test_file nodes + `tests` edges for Py/JS/TS/Go/Ruby) that wasn't ported. Fix shape: add a final post-pass in `generate_repo_inner`.

**Secondary gap (S1):** backend route extraction for JS/TS monorepos is absent — every fullstack TS repo in the sweep (cal.com, medusa, supabase, immich, twenty, strapi, outline, novuhq, chatwoot, metabase, firefly-iii, appwrite, keystonejs) showed 0 ROUTE. Likely missing: Next.js `pages/api/*` file-based routes, Nest `@Controller` decorators, Express `app.METHOD`, Remix loaders. This is the upstream cause of many HttpStackResolver misses in C2.

**Recommended patch order:** C1 → C5 → S1 → C2 (with instrumentation) → C4 → defer C3.
