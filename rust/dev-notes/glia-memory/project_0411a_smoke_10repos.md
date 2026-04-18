---
name: v0.4.11a 10-repo smoke — language + cross-stack validation
description: 10-repo post-v0.4.11a smoke 2026-04-18; 10/10 pass, confirms C1–C5+D1 fixes live in emitted data.
type: project
originSessionId: 5d22b623-66cd-4680-a7b3-62cb185a9f5d
---
Ran the v0.4.11-sweep harness (`dev-notes/0.4.11-sweep/sweep.py`) with a curated 10-repo list (`repos-10.txt`) on 2026-04-18 to verify v0.4.11a regression fixes and new extractors land in real-world output. Results at `dev-notes/0.4.11-sweep/results-10.jsonl`.

## Outcome: 10/10 succeeded

| repo | nodes | edges | cross | ROUTE | COMPONENT |
|------|------:|------:|------:|------:|----------:|
| fastapi-template | 720 | 452 | 10 | 30 | 162 |
| gin-gonic/examples | 275 | 220 | 4 | 37 | – |
| spring-petclinic | 284 | 258 | 0 | 21 | – |
| mastodon | 16,781 | 14,418 | 1,126 | 164 | 448 |
| tokio-rs/axum | 2,467 | 2,309 | 1 | 198 | – |
| laravel/laravel | 59 | 34 | 0 | 1 | – |
| dotnet/eShop | 2,341 | 2,297 | 1 | 28 | – |
| phoenixframework/phoenix | 2,405 | 2,352 | 71 | 419 | – |
| calcom/cal.com | 17,749 | 13,934 | 393 | 433 | 1,281 |
| angular/angular-cli | 3,767 | 3,579 | 178 | 142 | 2 |

Aggregate kinds (non-zero): ROUTE 1,473 · COMPONENT 1,897 · HOOK 288 · COMPOSABLE 288 · SERVICE 201 · QUEUE_CONSUMER 89 · ENDPOINT 81 · GRPC_METHOD 71 · CLI_COMMAND 37 · WS_HANDLER 15 · GRAPHQL_RESOLVER 14 · DATA_SOURCE 13 · CLI_INVOCATION 9 · EVENT_HANDLER 7 · QUEUE_PRODUCER 6 · CACHE 6 · EMAIL_SERVICE 6 · GRPC_CLIENT 5 · GUARD 3 · SEARCH_INDEX 3 · DIRECTIVE 2 · GRPC_SERVICE 2 · GRAPHQL_OPERATION 2 · SHARED_SCHEMA 1.

Aggregate edges: DEFINES 30,690 · CALLS 4,442 · TESTS 1,739 · ACCESSES_DATA 1,664 · CONTAINS 1,112 · HANDLED_BY 161 · HTTP_CALLS 32 · WS_SENDS 6 · GRAPHQL_CALLS 2 · QUEUE_SENDS 2 · EVENTBUS_EMITS 2 · GRPC_CALLS 1.

Confidence: strong 37,489 / medium 4,342 / weak 5,017 (vs 99.97% strong in pre-patch v0.4.11 sweep — C4 tiering confirmed live).

## What this confirms

- C1 extractor wiring: QUEUE_CONSUMER/CLI_COMMAND/WS_HANDLER/GRAPHQL_RESOLVER/EVENT_HANDLER/GRPC_CLIENT all non-zero (were 0 pre-v0.4.11).
- C4 confidence tiering: medium + weak populated.
- C5 TESTS edges: 1,739 emitted across repos.
- D1 data_sources rewrite: 1,664 ACCESSES_DATA edges + all 4 non-DB kinds (CACHE/BLOB_STORE/SEARCH_INDEX/EMAIL_SERVICE) emitting.
- v0.4.11a R-* fixes: ROUTE non-zero on python/go/rust/java/csharp/php/ruby/elixir/angular/ts.
- v0.4.11a F-* frontend extractors: COMPONENT/HOOK/SERVICE/COMPOSABLE/DIRECTIVE/GUARD all emitting.

Outliers (expected, not bugs):
- spring-petclinic, laravel/laravel, tokio-rs/axum, dotnet/eShop have cross=0-1 — single-side repos (backend-only or example-only). Cross-stack needs both halves.

## Harness notes

- `repo-graph-py` must be installed via `maturin build --release` + `pip install --force-reinstall <wheel>` before running. `maturin develop --release` reported install success but didn't put the module on Python's import path in this environment.
- Harness is resumable — dedupes by `repo_spec` in `results.jsonl`.
- Full 10-repo run: ~1 minute elapsed (mastodon 2.4s and cal.com 5s dominate).

## Still pending for v0.4.12 PyPI cut

1. `server.json` version bump 0.2.0 → 0.4.12 (both top-level and `packages[0].version`).
2. Full 99-repo sweep re-run (last full sweep was pre-C1–C5 patches).
3. README vs CLAUDE.md language-list drift check.
4. `mcp-publisher login github` fresh at publish time (token is per-session).
5. Clean/gitignore untracked: `entities.json`, `mempalace.yaml`, `quokka-output-test/`.
