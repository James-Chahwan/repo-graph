---
name: v0.4.11 patches for C1-C5 + S1 — post-sweep validated
description: 2026-04-17 landed fixes for 5 critical cross-stack bugs + ts-route extraction, validated by re-run 99-repo sweep. F1 fanout is new followup.
type: project
originSessionId: 5d22b623-66cd-4680-a7b3-62cb185a9f5d
---
All 5 critical bugs (C1-C5) + secondary gap (S1) from project_0411_sweep_findings addressed and validated by a same-day post-patch re-run of the full 99-repo sweep on 2026-04-17.

**Why:** pre-publish validation found 0 cross-stack edges across 99 repos despite both sides existing. Fixes unlocked the dormant cross-stack layer without changing the parser layer.

**How to apply:** when extending the cross-cutting layer, reference these fix shapes (full post-patch report at `dev-notes/0.4.11-sweep/post-patch-report.md`):

- **C1 (6 extractors wired):** `rust/py/src/lib.rs` `apply_cross_cutting_extractors()` — runs on every parsed file: queues, cli, websocket, eventbus, graphql, grpc-client. Every specialty kind went from 0 → meaningful counts (GRPC_CLIENT 2500, EVENT_HANDLER 1248, GRAPHQL_OPERATION 571, QUEUE_PRODUCER 440, CLI_INVOCATION 511, etc.).
- **C5 (tests edges):** `emit_tests_edges()` post-pass, runs after all resolvers. Path-derived qname detection, `test_`/`_test`/`_spec`/`.test`/`.spec` stripping. **Has fanout issue — see F1 below.**
- **S1 (TS backend routes):** `rust/parsers/code/extractors/src/ts_routes.rs` — Next.js Pages Router, App Router (with `[id]`→`:id`), Express/Hono/Koa `.METHOD('/path')`. Lang-gated on `typescript|react|angular|vue`. Emits one Route node per path with stacked ROUTE_METHOD cells (matches parser-go shape). ROUTE nodes grew 822 → 4223 across the sweep.
- **C4a (path downgrade):** `downgrade_test_paths()` walks all nodes, downgrades to Weak if any `::`-segment matches `tests/test/__tests__/spec/fixtures/examples/e2e/__mocks__/mocks/testdata`. Skips `route:*`. Confidence dist shifted from 99.97% strong → 63.7% strong / 35.8% weak.
- **C2 (HttpStackResolver compat):** `rust/graph/src/lib.rs::index_route_node()` accepts both qname shapes — `route:<path>` + JSON cells AND legacy `<METHOD> <path>` + Text cell. 0 → 203 HTTP_CALLS edges. Root cause turned out to be S1, not resolver logic — once ts_routes emitted shape-A, the real resolver bug became the cross-parser shape split, fixed in one place.
- **C4b (match tiering):** `demote_unmatched_http_nodes()` — ROUTE/ENDPOINT not in HTTP_CALLS cross-edge set drops Strong→Medium. Contributes to the 9,145 medium nodes (up from 412).

**Patch order that worked:** C1 → C5 → S1 → C4a → C2 → C4b. Each fix was verifiable on a small smoke fixture before running the full sweep.

**F1 fix landed (v0.4.11b, same-day):** user authorized ("yeah sounds good"). `select_test_targets()` in `rust/py/src/lib.rs` now ranks candidates by longest common package prefix with the test module's parent qname and caps at MAX_TEST_TARGETS=3. Smoke fixture: 3 monorepo packages with `utils.ts` + `utils.test.ts` each → 3 correct TESTS edges (vs 9 with tail-only matching).

**F1 post-sweep (post-patch-b) validated 2026-04-17:** TESTS edges 1,348,676 → 27,113 (98% reduction). vercel/next.js 818,418 → 1,480 (552×). medusajs/medusa 389,556 → 1,190 (327×). metabase 30,826 → 2,285. mattermost 29,709 → 1,910. strapi 13,695 → 597. pingcap/tidb 9,192 → 2,096. cal.com 1,249 → 361. Other cross-stack axes unchanged (HTTP_CALLS 203→204, QUEUE_FLOWS 30, WS_CONNECTS 197, EVENT_FLOWS 140, GRPC_CALLS 2, GRAPHQL_CALLS 36, CLI_INVOKES 5). Parser stability 99/99 across both post-patch sweeps.

**Committed 2026-04-17 as `e0137a9`** — `feat(rust): v0.4.11 — cross-stack fixes (C1–C5 + S1 + F1) validated on 99-repo sweep`. 17 files, +2510/-24.

**Publish status:** v0.4.11 code landed. PyPI/Registry publish still requires version bump + release flow (not yet authorized).

**C3 rescoped to v0.4.11a (user 2026-04-17: "this is now 0.4.11a - fixes like c3 we have to deal with"):** 18/20 language parsers fall through to `build_typescript` at `rust/py/src/lib.rs:493` during graph construction. Parsers correctly emit nodes (all 20 languages work), but intra-repo CALLS resolution under-resolves for everything except Python/Go because `build_typescript` applies TS-shaped import resolution (the `./foo` closure) to Java/Rust/C#/PHP/Ruby/etc. Cross-stack layer unaffected — operates on qnames + ROUTE nodes. Fix shape: per-language `build_<lang>` functions (or a generic `build_language` with resolver trait). User reaction on realising: *"ohmy gawd they should of all been added"*.

User verbatim re-scoping: v0.4.11a is now the followup-fix label (was v0.4.12). v0.4.12 remains the PyPI-publish cut.
