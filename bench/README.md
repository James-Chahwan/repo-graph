# repo-graph benchmark

An A/B harness that measures how much repo-graph changes an agent's efficiency on
real orientation tasks, headlessly and reproducibly. It's built to produce a
number a skeptic can't wave away: the metrics come from Claude Code's own result
JSON, the environment is controlled, and every cell runs several times so the
report shows spread, not a single lucky run.

## What it measures

For each `(repo, task)` it runs Claude Code twice per run:

- **without** — `--strict-mcp-config` with an *empty* MCP config: no repo-graph,
  and no other MCP servers either, so the only agent-side variable is the graph.
- **with** — `--strict-mcp-config` pointing at a repo-graph server, and the repo
  pre-seeded with `repo-graph-init` (graph built + the CLAUDE.md usage nudge).
  This is the product as a user actually installs it.

Both arms use the **same pinned model**, the **same prompt**, and the **same fresh
clone**. Metrics per run, taken verbatim from `claude -p --output-format json`:

- `cost` — `total_cost_usd` (unambiguous, model-pinned)
- `turns` — `num_turns`
- `explore_calls` — count of `Read`/`Grep`/`Glob`/`Bash` tool calls (how much
  blind exploration it did)
- `graph_calls` — count of `mcp__repo-graph__*` tool calls
- `tokens` — `usage.input_tokens + output_tokens`
- `time` — `duration_ms`
- `correct` — whether the answer or the files it touched mention the task's target

Reported as **median (p25–p75)** over N runs per arm, per `(repo, task)`.

## Run it

```bash
python bench/run_bench.py --smoke        # 1 repo / 1 task / 1 run on Haiku (validates the pipeline, cents)
python bench/run_bench.py                 # full matrix from bench/config.json
make bench                                # same as the full run
```

Requires the `claude` CLI on PATH, authenticated. Results are written to
`bench/RESULTS.md`. Clones are cached under `bench/.cache/` (git-ignored).

Config lives in `bench/config.json`: the model (default `claude-opus-4-8`), runs
per arm (default 4), and the repos/tasks/targets. Swap in your own repos or tasks
freely — targets are matched case-insensitively against the answer and the paths
the agent touched.

## Cost and time

The full default matrix is **4 repos × 3 tasks × 2 arms × 4 runs = 96 Opus
sessions**. Real agent sessions on real repos are the expensive part: budget on
the order of **$50–150 and 1–2 hours** depending on repo size and how much the
without-arm explores. Trim `runs`, the repo list, or `--max-turns` to cut it down;
`--model` overrides the pinned model for a cheaper dry run.

## Controls and honest limitations

- **Isolated MCP surface.** `--strict-mcp-config` guarantees the without arm has
  zero MCP servers and the with arm has only repo-graph — no figma/gmail/etc noise
  in either.
- **Fresh clones.** Each run copies a pinned clone; the without arm never sees a
  repo-graph `.mcp.json`/`CLAUDE.md`.
- **Residual confound.** The harness runs on your machine, so your global
  `~/.claude/CLAUDE.md` and installed plugins apply to *both* arms equally. They
  don't bias the delta, but for a pristine number run on a clean account. Pin
  clone refs to commits (not branches) for byte-exact reproducibility.
- **Correctness is a proxy.** It checks that the target file/symbol shows up in
  the answer or the agent's file footprint. It confirms the agent reached the
  right place; it is not a full grader.
