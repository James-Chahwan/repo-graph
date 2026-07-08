#!/usr/bin/env python3
"""A/B benchmark harness for repo-graph.

Measures how much repo-graph changes an agent's efficiency on real orientation
tasks, headlessly and reproducibly. For each (repo, task) it runs Claude Code via
`claude -p --output-format json` twice per run:

  without  -- --strict-mcp-config with an empty MCP config: no repo-graph, and no
              other MCP servers either (the only agent-side difference is the graph)
  with     -- --strict-mcp-config pointing at a repo-graph server, and the repo
              pre-seeded with `repo-graph-init` (graph built + CLAUDE.md nudge)

Both arms: same pinned model, same prompt, same fresh clone. It records cost,
turns, exploration tool-calls (Read/Grep/Glob/Bash), duration, and a correctness
check, then reports median + IQR over N runs per arm and writes a markdown table.

Metrics come straight from Claude's own result JSON (total_cost_usd, num_turns,
usage) so the numbers aren't ours to fudge. See bench/README.md for controls and
cost. Run: `python bench/run_bench.py [--smoke] [--config bench/config.json]`.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
CACHE = BENCH_DIR / ".cache"
EMPTY_MCP = CACHE / "empty-mcp.json"
RG_MCP = CACHE / "repo-graph-mcp.json"


# ── running one agent session ─────────────────────────────────────────────────


def _write_mcp_configs() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    EMPTY_MCP.write_text(json.dumps({"mcpServers": {}}))
    RG_MCP.write_text(json.dumps({
        "mcpServers": {
            "repo-graph": {"command": "repo-graph", "args": ["--repo", "."]}
        }
    }))


MAX_RETRIES = 8               # per run, across rate-limit waits + transient errors
_RL_PHRASES = ("rate limit", "usage limit", "rate_limit", "resets at",
               "too many requests", "429", "overloaded")


def _looks_rate_limited(text: str) -> bool:
    t = (text or "").lower()
    return any(p in t for p in _RL_PHRASES)


def _rate_limit_from_events(events: list, result: dict | None) -> tuple[bool, int | None]:
    limited, resets = False, None
    for e in events:
        if e.get("type") == "rate_limit_event":
            info = e.get("rate_limit_info", {})
            if info.get("status") not in (None, "allowed"):
                limited = True
            if info.get("resetsAt"):
                resets = info.get("resetsAt")
    if result and result.get("is_error") and _looks_rate_limited(result.get("result", "")):
        limited = True
    return limited, resets


def run_agent(prompt: str, workdir: Path, arm: str, model: str, max_turns: int,
              force_graph: bool = False) -> dict:
    """Run one headless Claude session; return parsed metrics (or {'error':...})."""
    mcp_cfg = RG_MCP if arm == "with" else EMPTY_MCP
    cmd = [
        "claude", "-p", prompt,
        "--model", model,
        "--output-format", "json",
        "--mcp-config", str(mcp_cfg),
        "--strict-mcp-config",              # ONLY these servers -> fair, isolated
        # Load ONLY project settings — NOT the operator's user-level plugins/hooks.
        # Without this, a user-installed Stop hook (e.g. a memory-save plugin) fires
        # inside the agent's session and derails long runs into off-task work,
        # silently contaminating every result. Auth is unaffected.
        "--setting-sources", "project",
        "--permission-mode", "bypassPermissions",
        "--max-turns", str(max_turns),
    ]
    if arm == "with" and force_graph:
        # Isolate the graph's intrinsic value: take away text search so the agent
        # MUST navigate via repo-graph tools (+ Read), removing the "weak model
        # never calls the tool" confound.
        cmd += ["--disallowedTools", "Grep", "Glob", "Bash"]
    env = dict(os.environ, REPO_GRAPH_WATCH="0")
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=str(workdir), env=env, capture_output=True, text=True)
    wall = time.time() - t0
    if proc.returncode != 0 and not proc.stdout.strip():
        err = proc.stderr or "no output"
        return {"error": err[:300], "wall": wall,
                "rate_limited": _looks_rate_limited(err), "resets_at": None}
    try:
        events = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": "unparseable JSON output", "wall": wall,
                "rate_limited": _looks_rate_limited(proc.stdout + proc.stderr), "resets_at": None}
    return _metrics(events, wall)


def run_with_retries(prompt: str, wd: Path, arm: str, model: str, max_turns: int,
                     force_graph: bool = False) -> dict:
    """Run one session, waiting out rate limits (until reset) and retrying
    transient errors, so an unattended full matrix completes whenever it can."""
    m: dict = {}
    for attempt in range(1, MAX_RETRIES + 1):
        m = run_agent(prompt, wd, arm, model, max_turns, force_graph)
        if m.get("rate_limited"):
            now = time.time()
            resets = m.get("resets_at")
            wait = (resets - now + 30) if (resets and resets > now) else 900
            wait = max(60, min(wait, 6 * 3600))
            print(f"      rate limited; sleeping {int(wait)}s until reset "
                  f"(attempt {attempt}/{MAX_RETRIES}) ...", flush=True)
            time.sleep(wait)
            continue
        if m.get("error") and attempt < MAX_RETRIES:
            print(f"      error: {str(m['error'])[:120]} -- retry in 30s "
                  f"(attempt {attempt}/{MAX_RETRIES})", flush=True)
            time.sleep(30)
            continue
        return m
    return m


def _metrics(events: list, wall: float) -> dict:
    result = next((e for e in reversed(events) if e.get("type") == "result"), None)
    if result is None:
        limited, resets = _rate_limit_from_events(events, None)
        return {"error": "no result event", "wall": wall,
                "rate_limited": limited, "resets_at": resets}
    explore = graph = 0
    reads: list[str] = []
    for e in events:
        if e.get("type") != "assistant":
            continue
        for block in e.get("message", {}).get("content", []):
            if block.get("type") != "tool_use":
                continue
            name = block.get("name", "")
            if name.startswith("mcp__repo-graph__"):
                graph += 1
            elif name in ("Read", "Grep", "Glob", "Bash"):
                explore += 1
                inp = block.get("input", {})
                for k in ("file_path", "path", "pattern", "command"):
                    if k in inp:
                        reads.append(str(inp[k]))
    usage = result.get("usage", {})
    limited, resets = _rate_limit_from_events(events, result)
    return {
        "error": None if not result.get("is_error") else (result.get("result") or "error")[:200],
        "cost": result.get("total_cost_usd", 0.0),
        "turns": result.get("num_turns", 0),
        "explore_calls": explore,
        "graph_calls": graph,
        "tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        "duration_ms": result.get("duration_ms", int(wall * 1000)),
        "result_text": result.get("result", ""),
        "footprint": " ".join(reads),
        "rate_limited": limited,
        "resets_at": resets,
    }


def is_correct(m: dict, targets: list[str]) -> bool:
    """A run is correct if any target token appears in the final answer or in the
    files/paths the agent actually touched."""
    if m.get("error"):
        return False
    hay = (m.get("result_text", "") + " " + m.get("footprint", "")).lower()
    return any(t.lower() in hay for t in targets)


# ── repo prep ─────────────────────────────────────────────────────────────────


def prepare_repo(repo: dict) -> tuple[Path, Path] | None:
    """Clone (pinned) and return (clean_dir, with_dir). The with_dir is seeded by
    repo-graph-init (graph + CLAUDE.md). Returns None if the clone fails."""
    name = repo["name"]
    if repo.get("dir"):  # local repo, no clone (used by --smoke)
        src = Path(repo["dir"]).resolve()
        if not src.is_dir():
            print(f"  local dir not found for {name}: {src}", file=sys.stderr)
            return None
    else:
        src = CACHE / "repos" / name
        if not src.exists():
            src.parent.mkdir(parents=True, exist_ok=True)
            args = ["git", "clone", "--depth", "1"]
            if repo.get("ref"):
                args += ["--branch", repo["ref"]]
            args += [repo["url"], str(src)]
            clone = subprocess.run(args, capture_output=True, text=True)
            if clone.returncode != 0:
                print(f"  clone failed for {name}: {clone.stderr.strip()[:200]}", file=sys.stderr)
                return None
    ignore = shutil.ignore_patterns(
        ".git", ".venv", "venv", "node_modules", ".ai", "__pycache__",
        "dist", "build", "target", "*.egg-info", ".pytest_cache", ".cache",
        "*.mp4", "*.vsix", "*.mcpb",
        # big non-code binaries (oci ships a 300MB tarball + 39MB dump)
        "*.tar.gz", "*.tar", "*.dump", "*.sqlite", "*.zip", "*.bin",
    )
    clean = CACHE / "work" / f"{name}-clean"
    withd = CACHE / "work" / f"{name}-rg"
    for d in (clean, withd):
        if d.exists():
            shutil.rmtree(d)
        # symlinks=True + ignore_dangling: some templates ship broken skill symlinks
        # (e.g. .claude/skills/*) that would otherwise crash copytree.
        shutil.copytree(src, d, ignore=ignore, symlinks=True, ignore_dangling_symlinks=True)
    # Seed the "with" arm: build graph + inject the CLAUDE.md nudge.
    env = dict(os.environ, REPO_GRAPH_WATCH="0")
    subprocess.run(["repo-graph-init", "--repo", str(withd)], env=env,
                   capture_output=True, text=True)
    return clean, withd


# ── aggregation ───────────────────────────────────────────────────────────────


def _agg(values: list[float]) -> dict:
    if not values:
        return {"median": None, "p25": None, "p75": None, "n": 0}
    s = sorted(values)
    if len(s) >= 4:
        q = statistics.quantiles(s, n=4, method="inclusive")  # no out-of-range extrapolation
        lo, hi = q[0], q[2]
    else:
        lo, hi = s[0], s[-1]  # small n: show min-max, not nonsense quantiles
    return {"median": statistics.median(s), "p25": lo, "p75": hi, "n": len(s)}


def summarize(runs: list[dict]) -> dict:
    ok = [r for r in runs if not r.get("error")]
    return {
        "runs": len(runs),
        "correct": sum(1 for r in runs if r.get("correct")),
        "cost": _agg([r["cost"] for r in ok]),
        "turns": _agg([r["turns"] for r in ok]),
        "explore_calls": _agg([r["explore_calls"] for r in ok]),
        "graph_calls": _agg([r["graph_calls"] for r in ok]),
        "tokens": _agg([r["tokens"] for r in ok]),
        "duration_ms": _agg([r["duration_ms"] for r in ok]),
    }


def _fmt(agg: dict, kind: str) -> str:
    if agg["median"] is None:
        return "-"
    m, lo, hi = agg["median"], agg["p25"], agg["p75"]
    if kind == "cost":
        return f"${m:.3f} ({lo:.3f}-{hi:.3f})"
    if kind == "int":
        return f"{m:.0f} ({lo:.0f}-{hi:.0f})"
    if kind == "sec":
        return f"{m/1000:.0f}s ({lo/1000:.0f}-{hi/1000:.0f})"
    return f"{m:.0f}"


def render_markdown(rows: list[dict], model: str, when: str) -> str:
    out = [
        "# repo-graph benchmark",
        "",
        f"Model: `{model}` · {when} · median (p25-p75) over N runs per arm.",
        "Metrics are from Claude Code's own result JSON (`total_cost_usd`, "
        "`num_turns`, `usage`). Controls: same model, same prompt, fresh clone, "
        "`--strict-mcp-config` (the without arm has no MCP servers at all; the with "
        "arm has only repo-graph). See bench/README.md.",
        "",
        "| Repo | Task | Arm | Correct | Cost | Turns | Explore calls | Graph calls | Tokens | Time |",
        "|------|------|-----|---------|------|-------|---------------|-------------|--------|------|",
    ]
    for r in rows:
        for arm in ("without", "with"):
            s = r[arm]
            out.append(
                f"| {r['repo']} | {r['task']} | {arm} | {s['correct']}/{s['runs']} "
                f"| {_fmt(s['cost'],'cost')} | {_fmt(s['turns'],'int')} "
                f"| {_fmt(s['explore_calls'],'int')} | {_fmt(s['graph_calls'],'int')} "
                f"| {_fmt(s['tokens'],'int')} | {_fmt(s['duration_ms'],'sec')} |"
            )
    return "\n".join(out) + "\n"


# ── main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description="repo-graph A/B benchmark")
    ap.add_argument("--config", default=str(BENCH_DIR / "config.json"))
    ap.add_argument("--smoke", action="store_true",
                    help="1 repo/1 task/1 run on a cheap model to validate the pipeline")
    ap.add_argument("--runs", type=int, default=None, help="override runs per arm")
    ap.add_argument("--model", default=None, help="override the pinned model")
    ap.add_argument("--out", default=str(BENCH_DIR / "RESULTS.md"))
    ap.add_argument("--max-turns", type=int, default=40)
    ap.add_argument("--fresh", action="store_true", help="ignore any checkpoint and start over")
    ap.add_argument("--force-graph", action="store_true",
                    help="with-arm must navigate via repo-graph: disallow Grep/Glob/Bash "
                         "(isolates the graph's value from whether the model chooses to call it)")
    args = ap.parse_args()

    if shutil.which("claude") is None:
        print("error: `claude` CLI not found on PATH.", file=sys.stderr)
        return 2

    cfg = json.loads(Path(args.smoke and str(BENCH_DIR / "config.smoke.json") or args.config).read_text())
    model = args.model or cfg["model"]
    runs = args.runs or cfg.get("runs", 4)
    _write_mcp_configs()
    CACHE.mkdir(parents=True, exist_ok=True)

    # Resume from a checkpoint so a killed/throttled long run continues instead of
    # rerunning completed cells. Keyed by model so switching models starts clean.
    ckpt_path = CACHE / f"checkpoint-{Path(args.out).stem}.json"
    ckpt = {}
    if not args.fresh and ckpt_path.is_file():
        try:
            ckpt = json.loads(ckpt_path.read_text())
        except Exception:
            ckpt = {}
    if ckpt.get("model") != model:
        ckpt = {"model": model, "cells": {}}
    cells = ckpt.setdefault("cells", {})

    when = os.environ.get("BENCH_DATE") or time.strftime("%Y-%m-%d", time.gmtime())

    def flush() -> None:
        ckpt_path.write_text(json.dumps(ckpt, indent=2))
        Path(args.out).write_text(render_markdown(list(cells.values()), model, when))

    total = sum(len(r["tasks"]) for r in cfg["repos"])
    done = 0
    for repo in cfg["repos"]:
        pending = [t for t in repo["tasks"] if f"{repo['name']}/{t['id']}" not in cells]
        done += len(repo["tasks"]) - len(pending)
        if not pending:
            print(f"== {repo['name']} == (all {len(repo['tasks'])} cells cached)", flush=True)
            continue
        prepared = prepare_repo(repo)
        if prepared is None:
            continue
        clean, withd = prepared
        for task in pending:
            key = f"{repo['name']}/{task['id']}"
            done += 1
            print(f"== {key} == (cell {done}/{total}) ==", flush=True)
            arm_runs = {"without": [], "with": []}
            for arm, wd in (("without", clean), ("with", withd)):
                for i in range(runs):
                    m = run_with_retries(task["prompt"], wd, arm, model, args.max_turns, args.force_graph)
                    m["correct"] = is_correct(m, task["targets"])
                    arm_runs[arm].append(m)
                    tag = "OK" if m["correct"] else ("ERR" if m.get("error") else "miss")
                    print(f"   {arm:<7} run {i+1}/{runs}: {tag}  "
                          f"${m.get('cost',0):.3f} turns={m.get('turns','?')} "
                          f"explore={m.get('explore_calls','?')} graph={m.get('graph_calls','?')}",
                          flush=True)
            cells[key] = {
                "repo": repo["name"], "task": task["id"],
                "without": summarize(arm_runs["without"]),
                "with": summarize(arm_runs["with"]),
            }
            flush()  # checkpoint + incremental RESULTS.md after every cell

    flush()
    print("\n" + Path(args.out).read_text())
    print(f"wrote {args.out}  (checkpoint: {ckpt_path})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
