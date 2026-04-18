---
name: repo-graph 8-step roadmap (2026-04-15)
description: Agreed implementation plan — discovery refactor, config, flow kinds, entrypoints, confidence, test edges, skills. Step 1 in progress.
type: project
originSessionId: e18af0c7-26eb-409e-8c0d-89cbaf6550d0
---
## Summary

User's step-by-step plan to land major repo-graph improvements. ~9–10 PRs total.
Currently on **Step 1**, mid-refactor.

## Step 1 — Source-first marker-anchored discovery [IN PROGRESS]

- New `repo_graph/discovery.py` with `FileIndex` class. One rglob in generator before any analyzer runs.
- Built-in skip list: node_modules, vendor, target, build, dist, .git, .next, __pycache__, .venv, venv, .cpcache, .shadow-cljs.
- Group files by nearest-ancestor manifest (go.mod, Cargo.toml, pyproject.toml, deps.edn, pom.xml, etc.). Fall back to repo root.
- Refactor all 20 analyzers: replace their own rglob / scan_project_dirs calls with `index.files_for(exts=[".py"])` and `index.roots_for("python")`.
- **Acceptance:** rerun 19-repo sweep, node/edge counts within ±5% of current.
- **Status:** discovery.py exists, generator wired, base.py takes index, 6/20 analyzers refactored (go, rust, ts, java, scala, csharp). 14 remaining.
- **Commit granularity:** may split into 2 PRs — discovery module + analyzer refactor.
- **Version:** 0.2.0 (breaking-ish).

## Step 2 — .ai/repo-graph/config.yaml escape hatch

- Loader in generator. Shape: `roots: [{path, kind}]` and `skip: [...]`. Merges with auto-detect (config wins).
- **Acceptance:** drop a config.yaml in a weird monorepo, watch it override heuristics.
- **Version:** 0.2.x patch.

## Step 3 — Flow `kind` field + graph_view tag display (bundled)

- Add `kind: str` to Flow dataclass. Existing HTTP flows get `kind="http"` at generation time.
- Flow YAMLs gain top-level `kind:` line. `graph.py` loads it. `server.py`'s flow tool accepts kind filter.
- `graph_view` prefixes flows with `[http]` / `[cli]` / etc. in its listing.
- **Acceptance:** regenerate, flow yamls have kind, graph_view shows tags.
- **Version:** 0.2.x patch.

## Step 4 — New entrypoint analyzers (3 sub-PRs)

Each shippable independently.

- **4a CLI:** Go cobra, Python click+argparse, Rust clap, JS commander+yargs. Node type `cli_command`, flow kind `cli`.
- **4b gRPC:** `.proto` files + `RegisterXxxServer` call-site detection. Node types `grpc_service`, `grpc_method`. Flow kind `grpc`.
- **4c Queue consumers:** `@celery.task`, Kafka consumer loops, Sidekiq workers, Oban workers, SQS pollers, NATS `Subscribe`. Node type `queue_consumer`. Flow kind `queue`.
- **Acceptance:** test each on 2 real repos per entrypoint type, confirm flows emit with right kind.
- **Version:** 0.3.0.

## Step 5 — Confidence tiers

- Add `confidence: str` to Flow/Node (values `strong` | `medium` | `weak`).
- Scoring rules per analyzer: resolved handler = strong, regex-only = medium, under `test/` or `examples/` = weak.
- `flow` tool gets `min_confidence` param. `graph_view` shows a tier icon next to weak flows.
- **Acceptance:** known-weak test fixtures score weak, primary routes score strong.

## Step 6 — Test → code edges (unit only)

- File pattern detection per language: `*_test.go`, `*.test.ts`, `*_test.py`, `*Test.java`, `*_spec.rb`, `*.spec.ts`.
- For each test file, parse imports using same logic as main analyzer, emit `tests` edges back to imported nodes.
- `impact` tool gains `--include-tests` flag to return affected tests.
- **Acceptance:** on a repo with known test coverage, `impact` surfaces relevant test files.

## Step 7

Folded into Step 3 (graph_view tag).

## Step 8 — Skills (`.claude/skills/` in this repo, docs for install)

- `/repo-graph-init` — checks for `.mcp.json`, runs `repo-graph-init` CLI, LLM-guided config.yaml if needed.
- `/repo-graph-trace`, `/repo-graph-flow`, `/repo-graph-impact`, `/repo-graph-visualise` — thin skills that direct Claude to call the respective MCP tools with user args.
- **Acceptance:** slash commands work end-to-end without MCP config (via CLI fallback) or via MCP (preferred).
- **Version:** 0.4.0.

## Rollout

- ~9–10 PRs total.
- Each top-level step = 1 PR. Step 4 splits into 3. Step 1 may split into 2.
- Version bumps:
  - Step 1 → 0.2.0 (breaking-ish refactor)
  - Steps 2, 3, 5, 6 → 0.2.x patches
  - Step 4 → 0.3.0
  - Step 8 → 0.4.0
