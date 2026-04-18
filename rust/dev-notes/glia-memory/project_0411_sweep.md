---
name: v0.4.11 pre-publish validation sweep
description: 99-repo sweep ran 2026-04-17; surfaced 5 critical cross-stack bugs (C1-C5). Report at dev-notes/0.4.11-sweep/report.md. Harness reusable.
type: project
originSessionId: 5d22b623-66cd-4680-a7b3-62cb185a9f5d
---
v0.4.11 is the pre-publish validation checkpoint after v0.4.10 landed stack resolvers + pyo3 bindings + Python clean break.

**Status (2026-04-17):** sweep RUN, report written, **patches pending**. 99/99 clones succeeded, 0 parse crashes, median 1.4s. Parser layer validated. Cross-stack layer found to be mostly unwired — publish blocked until C1–C5 addressed. See `project_0411_sweep_findings.md` for the bug list.

**Why:** v0.4.9 added 20 parser crates and v0.4.10 added cross-stack resolvers; both were untested on external repos at scale. This sweep went to 99 (vs previous 19) to shake out rarer bugs before the first Rust-backed PyPI release.

**How to apply:** harness lives at `dev-notes/0.4.11-sweep/` — `sweep.py` (clones + subprocess-isolated generate), `run_one.py` (per-repo → JSON), `analyze.py` (summary + anomalies), `drill.py` (specialty-kind breakdown per repo), `repos.txt`, `results.jsonl`, `report.md`. Reuse shape for future sweeps: clone `--depth=1`, subprocess-isolated generate with 300s timeout, JSONL log, analyze reads log. Full sweep ≈ 17 min runtime, ~2-3GB peak disk (clones deleted after measurement). Resumable — dedupes by `repo_spec`, so removing lines from `results.jsonl` re-tests just those.

Mix: ~37 depth (full-stack monorepos, queue-heavy, gRPC, GraphQL, WS, CLI) + ~62 breadth (≥2 repos per supported language). Do NOT fix bugs mid-sweep — collate, review, then patch.
