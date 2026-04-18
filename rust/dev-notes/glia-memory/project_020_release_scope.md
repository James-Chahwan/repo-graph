---
name: 0.2.0 release — SHIPPED 2026-04-16
description: What shipped in 0.2.0, validation results, publish URLs — released 2026-04-16 commit 1d90b02
type: project
originSessionId: e18af0c7-26eb-409e-8c0d-89cbaf6550d0
---
**SHIPPED 2026-04-16 — commit 1d90b02.** Live on PyPI, MCP Registry, GitHub release v0.2.0, GitLab tag v0.2.0.

0.2.0 bundles steps 2–6 + 8 of the 8-step roadmap into a single release (user's call — "how is it a week long task, we are gonna fly through most of theses").

**Why:** user rejected per-step releases in favour of a stronger single-release narrative; with LLM execution the individual steps are hours not days.

**How to apply:** when discussing 0.2.0 features with user, reference the bundled scope; when adding a new feature, consider whether it extends an existing 0.2.0 primitive (flow kinds, confidence tiers, entrypoint types) before adding a new abstraction.

Features shipped:
- Config.yaml escape hatch (`skip:` / `roots:`) — additive union with heuristics
- Flow kind field: http / page / cli / grpc / queue
- Confidence tiers: strong / medium / weak with ● / · / ⚠ icons
- Test → code edges: `test_file` nodes + `tests` edges (Py/JS/TS/Go/Ruby). Two-factor: filename pattern + framework import/signal (import pytest/unittest, describe/it/test, import "testing"/func Test, RSpec.describe etc.)
- CLI entrypoint analyzer (click/commander/yargs/cobra/clap)
- gRPC entrypoint analyzer (.proto service/rpc parsing)
- Queue consumer analyzer (Celery/Dramatiq/BullMQ/Sidekiq/Oban/NATS)
- Claude Code skills in `skills/` — init/trace/flow/impact/visualise

Architectural changes:
- `_resolve_file_edges` rewires both `from` and `to` anchors (was from-only — broke CLI handled_by edges)
- `_auto_flows` unified over entrypoint types via `_ENTRYPOINT_KIND` dict (route/cli_command/grpc_method/queue_consumer)
- Scoring centralised in `generator._score_confidence` — no per-analyzer churn

Validation (2026-04-15, 20+ repos):
- quokka-stack: 577 nodes (+11 from 0.1.3 baseline of 566) — added gRPC service/method, 4 test files, 1 NATS consumer; cross-stack linking still 18 edges
- grpc-go: 12 gRPC flows auto-generated from real .proto files
- webplatform (C#): 5627 nodes, 390 flows — heavy-scale no regression
- webplatformfrontend / splorts-frontend: previously had false-positive Queue/CLI detection — fixed by tightening detect() prefilters
- Confidence distribution on quokka-stack: 64 strong / 508 medium / 4 weak

Validation (2026-04-15, 52-repo external GitHub/GitLab sweep):
- 52 clones, 52 scans, 0 failures
- Totals: 59,760 nodes / 71,761 edges / 899 flows / 5,871 test_file / 18,672 tests edges
- File-anchor resolver: 1,218 resolved / 4 dropped (0.3% — bidirectional rewrite validated)
- Flow kinds fired: http 646, queue 120, cli 71, page 48, grpc 14 — all five kinds exercised on real repos
- Confidence tiers skew heavily medium: strong 0.8% / medium 67.4% / weak 31.8%. Strong only fires on routes with resolved handlers — reality check that 0.3.0 AST targets.
- Test-edge resolver quality ranking: **PHP `use` qualified-name resolver strongest** (laravel/framework: 743 test_files, 6,774 tests edges). Swift module import, Go sibling, Java qualified-name also solid. **Weak: Python absolute imports** (drf: 60 test_files, 0 edges), **Ruby require_relative** (rubocop: 745, 1), **Kotlin qualified** (ktor-samples: 29, 1) — known limitations, 0.3.0 AST addresses.
- Pure-JS projects (express 1 node, fastify 0 edges) still gated by TS analyzer's tsconfig.json requirement — pre-existing `project_js_analyzer_gap`.
- All 20 language analyzers + 4 cross-cutting fired at least once across the sweep.
