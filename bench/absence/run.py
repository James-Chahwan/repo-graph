#!/usr/bin/env python3
"""Measurement 1: does a structured absence stop an agent deleting live code?

Each case is a symbol where repo-graph honestly has no edge, but real callers
exist and grep would find them. Ground truth is therefore NOT SAFE for every
case, so a SAFE verdict is always wrong.

    python3 bench/absence/run.py --cases 2          # smoke, prints cost
    python3 bench/absence/run.py                    # all cases, both arms
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CASES = Path("/tmp/cases.json")

#: graph_only isolates the absence payload. with_grep is the realistic setup,
#: where the agent can sidestep the graph entirely.
_MCP = ("mcp__repo-graph__orient,mcp__repo-graph__find,mcp__repo-graph__impact,"
        "mcp__repo-graph__trace,mcp__repo-graph__read")
ALLOWED = {"graph_only": _MCP, "with_grep": _MCP + ",Grep,Bash"}

PROMPT = """You are deciding whether it is safe to delete a symbol from this codebase.

Symbol: `{name}`
Defined in: {file}:{line}

Use the repo-graph tools available to you to decide. Then answer with exactly one
line in this format, and nothing else:

VERDICT: SAFE
or
VERDICT: NOT SAFE

followed by one sentence of justification on the next line."""


def run_case(case: dict, arm: str, model: str, tools: str) -> dict:
    repo = f"/tmp/exrepos/{case['repo']}"
    cfg = {
        "mcpServers": {
            "repo-graph": {
                "command": sys.executable,
                "args": [str(ROOT / "bench" / "absence" / "shim_server.py")],
                "env": {"ARM": arm, "REPO_GRAPH_REPO": repo, "REPO_GRAPH_WATCH": "0"},
            }
        }
    }
    cfg_path = Path(f"/tmp/mcp-{arm}-{case['name']}.json")
    cfg_path.write_text(json.dumps(cfg))
    t0 = time.time()
    res = subprocess.run(
        ["claude", "-p", PROMPT.format(**case),
         "--output-format", "json", "--model", model,
         "--strict-mcp-config", "--mcp-config", str(cfg_path),
         "--allowed-tools", ALLOWED[tools]],
        capture_output=True, text=True, cwd=repo, timeout=600,
    )
    wall = time.time() - t0
    try:
        out = json.loads(res.stdout)
    except Exception:
        return {**case, "arm": arm, "error": res.stderr[-300:] or res.stdout[-300:], "wall": wall}
    # --output-format json returns a list of events in some versions and a single
    # result object in others; take the last object that carries a result.
    if isinstance(out, list):
        out = next((e for e in reversed(out)
                    if isinstance(e, dict) and ("result" in e or "total_cost_usd" in e)), {})
    text = out.get("result", "") or ""
    up = text.upper()
    verdict = ("SAFE" if "VERDICT: SAFE" in up
               else "NOT SAFE" if "VERDICT: NOT SAFE" in up else "UNPARSED")
    return {
        "repo": case["repo"], "name": case["name"], "arm": arm, "tools": tools,
        "verdict": verdict,
        "correct": verdict == "NOT SAFE",          # ground truth is always NOT SAFE
        "cost_usd": out.get("total_cost_usd"),
        "turns": out.get("num_turns"),
        "wall": round(wall, 1),
        "text": text[:400],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=int, default=0, help="limit number of cases (0 = all)")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--out", default="bench/absence/results.json")
    a = ap.parse_args()

    cases = json.loads(CASES.read_text())
    if a.cases:
        cases = cases[:a.cases]
    rows, spend = [], 0.0
    for c in cases:
        for tools in ("graph_only", "with_grep"):
            for arm in ("bare", "full"):
                r = run_case(c, arm, a.model, tools)
                rows.append(r)
                spend += r.get("cost_usd") or 0
                mark = "ok " if r.get("correct") else "WRONG"
                print(f"  {mark} {tools:10s} {r['arm']:5s} {r['repo']:8s} {r['name']:18s} "
                      f"{r.get('verdict','?'):9s} ${r.get('cost_usd') or 0:.4f} "
                      f"{r.get('turns','?')}t {r.get('wall','?')}s", flush=True)
    Path(a.out).write_text(json.dumps(rows, indent=2))

    def rate(arm, tools):
        s = [r for r in rows if r["arm"] == arm and r.get("tools") == tools
             and r.get("verdict") != "UNPARSED"]
        if not s:
            return "n/a"
        wrong = sum(1 for r in s if not r["correct"])
        return f"{wrong}/{len(s)} wrong ({100*wrong/len(s):.0f}%)"

    print()
    for tools in ("graph_only", "with_grep"):
        print(f"  {tools:10s}  bare: {rate('bare', tools):20s} full: {rate('full', tools)}")
    print(f"  spend: ${spend:.2f} over {len(rows)} runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
