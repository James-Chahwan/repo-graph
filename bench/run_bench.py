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


def run_agent(prompt: str, workdir: Path, arm: str, model: str, max_turns: int) -> dict:
    """Run one headless Claude session; return parsed metrics (or {'error':...})."""
    mcp_cfg = RG_MCP if arm == "with" else EMPTY_MCP
    cmd = [
        "claude", "-p", prompt,
        "--model", model,
        "--output-format", "json",
        "--mcp-config", str(mcp_cfg),
        "--strict-mcp-config",              # ONLY these servers -> fair, isolated
        "--permission-mode", "bypassPermissions",
        "--max-turns", str(max_turns),
    ]
    env = dict(os.environ, REPO_GRAPH_WATCH="0")
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=str(workdir), env=env, capture_output=True, text=True)
    wall = time.time() - t0
    if proc.returncode != 0 and not proc.stdout.strip():
        return {"error": (proc.stderr or "no output")[:300], "wall": wall}
    try:
        events = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": "unparseable JSON output", "wall": wall}
    return _metrics(events, wall)


def _metrics(events: list, wall: float) -> dict:
    result = next((e for e in reversed(events) if e.get("type") == "result"), None)
    if result is None:
        return {"error": "no result event", "wall": wall}
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
    )
    clean = CACHE / "work" / f"{name}-clean"
    withd = CACHE / "work" / f"{name}-rg"
    for d in (clean, withd):
        if d.exists():
            shutil.rmtree(d)
        shutil.copytree(src, d, ignore=ignore)
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
    q = statistics.quantiles(s, n=4) if len(s) >= 2 else [s[0], s[0], s[0]]
    return {"median": statistics.median(s), "p25": q[0], "p75": q[2], "n": len(s)}


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
    args = ap.parse_args()

    if shutil.which("claude") is None:
        print("error: `claude` CLI not found on PATH.", file=sys.stderr)
        return 2

    cfg = json.loads(Path(args.smoke and str(BENCH_DIR / "config.smoke.json") or args.config).read_text())
    model = args.model or cfg["model"]
    runs = args.runs or cfg.get("runs", 4)
    _write_mcp_configs()

    rows = []
    for repo in cfg["repos"]:
        prepared = prepare_repo(repo)
        if prepared is None:
            continue
        clean, withd = prepared
        for task in repo["tasks"]:
            print(f"== {repo['name']} / {task['id']} ==", flush=True)
            arm_runs = {"without": [], "with": []}
            for arm, wd in (("without", clean), ("with", withd)):
                for i in range(runs):
                    m = run_agent(task["prompt"], wd, arm, model, args.max_turns)
                    m["correct"] = is_correct(m, task["targets"])
                    arm_runs[arm].append(m)
                    tag = "OK" if m["correct"] else ("ERR" if m.get("error") else "miss")
                    print(f"   {arm:<7} run {i+1}/{runs}: {tag}  "
                          f"${m.get('cost',0):.3f} turns={m.get('turns','?')} "
                          f"explore={m.get('explore_calls','?')} graph={m.get('graph_calls','?')}",
                          flush=True)
            rows.append({
                "repo": repo["name"], "task": task["id"],
                "without": summarize(arm_runs["without"]),
                "with": summarize(arm_runs["with"]),
            })

    when = time.strftime("%Y-%m-%d", time.gmtime()) if os.environ.get("BENCH_DATE") is None else os.environ["BENCH_DATE"]
    md = render_markdown(rows, model, when)
    Path(args.out).write_text(md)
    print("\n" + md)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
