#!/usr/bin/env python3
"""Diagnose WHERE a repo-graph benchmark session spends tokens/turns.

Runs one headless session (default: the repo-graph "with" arm) capturing the full
event stream, then reports: the cost/usage breakdown (fresh vs cache-creation vs
cache-read — cache is what actually drives cost), and every tool call with the
byte size of its result, so we can see if `dense_text`/`status` dumps are the
culprit. Reuses the repo dirs prepared by run_bench.

  python bench/diagnose.py <repo-name> <task-id> [--arm with|without]
  python bench/diagnose.py django-oscar trace-view
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_bench as rb  # noqa: E402

DIAG = rb.CACHE / "diag"


def load_task(repo_name: str, task_id: str) -> tuple[dict, dict]:
    cfg = json.loads((Path(__file__).resolve().parent / "config.json").read_text())
    for repo in cfg["repos"]:
        if repo["name"] == repo_name:
            for t in repo["tasks"]:
                if t["id"] == task_id:
                    return repo, t
    raise SystemExit(f"no such repo/task: {repo_name}/{task_id}")


def _blocks(events: list, role: str, btype: str):
    for e in events:
        if e.get("type") != role:
            continue
        for b in e.get("message", {}).get("content", []):
            if b.get("type") == btype:
                yield b


def _result_text(block: dict) -> str:
    c = block.get("content", "")
    if isinstance(c, list):
        return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in c)
    return c if isinstance(c, str) else json.dumps(c)


def analyze(events: list) -> None:
    result = next((e for e in reversed(events) if e.get("type") == "result"), None)
    if not result:
        print("  no result event"); return
    u = result.get("usage", {})
    fresh_in = u.get("input_tokens", 0)
    out = u.get("output_tokens", 0)
    cc = u.get("cache_creation_input_tokens", 0)
    cr = u.get("cache_read_input_tokens", 0)
    print(f"  cost ${result.get('total_cost_usd',0):.4f} | turns {result.get('num_turns')} | "
          f"{result.get('duration_ms',0)/1000:.0f}s | correct-ish result: {result.get('result','')[:80]!r}")
    print(f"  tokens: fresh_in={fresh_in}  output={out}  cache_create={cc}  cache_read={cr}")
    total_billed_ctx = fresh_in + cc + cr
    print(f"  context tokens moved (fresh+cache_create+cache_read) = {total_billed_ctx:,}  "
          f"<- cache_read dominates cost when turns pile up")

    # map tool_use id -> name, then size each tool result
    id_name = {}
    for b in _blocks(events, "assistant", "tool_use"):
        id_name[b.get("id")] = b.get("name", "?")
    print("\n  tool calls (result size = what got fed back into context):")
    sizes: dict[str, int] = {}
    for b in _blocks(events, "user", "tool_result"):
        name = id_name.get(b.get("tool_use_id"), "?")
        chars = len(_result_text(b))
        sizes[name] = sizes.get(name, 0) + chars
        print(f"    {name:<28} result ~{chars:>7,} chars  (~{chars//4:,} tok)")
    if sizes:
        print("\n  per-tool total result bytes:")
        for name, chars in sorted(sizes.items(), key=lambda kv: -kv[1]):
            print(f"    {name:<28} ~{chars:>8,} chars  (~{chars//4:,} tok)")


def run(repo_name: str, task_id: str, arm: str) -> None:
    repo_cfg, task = load_task(repo_name, task_id)
    wd = rb.CACHE / "work" / f"{repo_name}-{'rg' if arm == 'with' else 'clean'}"
    if not wd.is_dir():
        print(f"preparing {repo_name} (run bench first to cache) ...")
        prepared = rb.prepare_repo(repo_cfg)
        if not prepared:
            raise SystemExit("could not prepare repo")
        wd = prepared[1] if arm == "with" else prepared[0]
    rb._write_mcp_configs()
    mcp_cfg = rb.RG_MCP if arm == "with" else rb.EMPTY_MCP
    cmd = ["claude", "-p", task["prompt"], "--model",
           json.loads((Path(__file__).resolve().parent / "config.json").read_text())["model"],
           "--output-format", "json", "--mcp-config", str(mcp_cfg),
           "--strict-mcp-config", "--setting-sources", "project",
           "--permission-mode", "bypassPermissions", "--max-turns", "40"]
    env = dict(__import__("os").environ, REPO_GRAPH_WATCH="0")
    print(f"== {repo_name}/{task_id} [{arm}] ==\n  prompt: {task['prompt'][:90]}")
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=str(wd), env=env, capture_output=True, text=True)
    print(f"  (ran in {time.time()-t0:.0f}s)")
    try:
        events = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print("  FAILED:", (proc.stderr or proc.stdout)[:300]); return
    DIAG.mkdir(parents=True, exist_ok=True)
    raw = DIAG / f"{repo_name}-{task_id}-{arm}.json"
    raw.write_text(json.dumps(events, indent=2))
    analyze(events)
    print(f"  raw transcript: {raw}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("task")
    ap.add_argument("--arm", choices=["with", "without"], default="with")
    a = ap.parse_args()
    run(a.repo, a.task, a.arm)
    return 0


if __name__ == "__main__":
    sys.exit(main())
