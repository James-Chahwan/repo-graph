# repo-graph benchmark — results

> **Status: harness validated; full matrix not yet run.**
> The pipeline below was validated with a Haiku smoke (`python bench/run_bench.py
> --smoke`). To produce the real numbers, run `make bench` (or
> `python bench/run_bench.py`), which overwrites this file with the full
> Opus matrix across 4 repos × 3 task types × 4 runs per arm. See
> [bench/README.md](README.md) for method, controls, and cost (~$50–150).

## Pipeline validation (smoke)

Model `claude-haiku-4-5-20251001`, 1 run per arm, on the repo-graph repo itself.
This only proves the harness runs both arms and reports real per-run metrics from
Claude Code's own result JSON — it is **not** a product comparison (one Haiku run
on a trivially-locatable target).

| Repo | Task | Arm | Correct | Cost | Turns | Explore calls | Graph calls | Tokens | Time |
|------|------|-----|---------|------|-------|---------------|-------------|--------|------|
| repo-graph-self | entry-point | without | 1/1 | $0.063 | 4 | 3 | 0 | 880 | 19s |
| repo-graph-self | entry-point | with | 1/1 | $0.064 | 4 | 3 | 0 | 912 | 16s |

## How to read the full report

Once `make bench` has run, each `(repo, task)` shows a `without` and a `with` row
with **median (p25–p75)** over the runs. The story to look for:

- `with` should need fewer **turns** and far fewer **explore_calls** (Read/Grep/
  Glob/Bash) because the agent jumps to the right file via `graph_calls` instead of
  hunting, which shows up as lower **cost** and **time**.
- The **easy-locate** task is the control: when the target is trivial to grep, the
  gap should shrink or vanish. That's the point — it proves the win isn't just a
  needle-in-a-monorepo artifact.
- **correct** should stay at parity (repo-graph should not trade accuracy for
  speed).
