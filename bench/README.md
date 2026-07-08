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

The full default matrix is **4 repos × 3 tasks × 2 arms × 4 runs = 96 sessions**,
pinned to `claude-sonnet-5`.

What that costs depends on how you're authenticated (check `apiKeySource` in the
session JSON):

- **Metered API key** — you pay per token. The `total_cost_usd` in each result is
  the real bill. Ballpark for 96 Sonnet sessions on real repos: low tens of
  dollars; on Opus it's several times that.
- **Claude subscription** (`apiKeySource: none`) — no per-run charge. The runs
  consume your 5-hour / weekly usage limits instead, so the real cost is wall time
  and possible throttling, not money. With overage disabled you can't be billed
  past the plan.

Either way, trim it with fewer `runs`, fewer repos, or a lower `--max-turns`.
`--model opus` (or any alias / exact id) overrides the pinned model.

## Controls and honest limitations

- **Isolated MCP surface.** `--strict-mcp-config` guarantees the without arm has
  zero MCP servers and the with arm has only repo-graph — no figma/gmail/etc noise
  in either.
- **Fresh clones.** Each run copies a pinned clone; the without arm never sees a
  repo-graph `.mcp.json`/`CLAUDE.md`.
- **Operator-config isolation.** The harness passes `--setting-sources project`
  so the agent loads ONLY the target repo's settings — not your user-level plugins
  and hooks. This matters: a user-installed **Stop hook** (e.g. a memory-save
  plugin) otherwise fires *inside* the agent's session and derails long runs into
  off-task work — and it does NOT cancel out across arms, because it bites the arm
  that takes more turns harder. (Auth survives `--setting-sources project`.) For a
  fully pristine number, also run under a clean `CLAUDE_CONFIG_DIR`. Pin clone
  refs to commits (not branches) for byte-exact reproducibility.
- **Correctness is a proxy.** It checks that the target file/symbol shows up in
  the answer or the agent's file footprint. It confirms the agent reached the
  right place; it is not a full grader.
