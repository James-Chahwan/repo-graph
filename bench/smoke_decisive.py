#!/usr/bin/env python3
"""One-task decisive smoke: prove the recall/precision grader resolves a real
correctness/liveness difference on the oci schema-blast task.

Runs the task on both arms (without / with repo-graph), grades each DELIVERABLE
with bench/grade.py against the checked-in answer key, and prints the split:
recall, precision, and how many DEAD locations each arm wrongly cited as live —
the dimension the old boolean grader was blind to.

Gated spend: RUNS/arm x 2 arms headless Sonnet sessions. Reuses run_bench's
session machinery; grades against the working-tree-verified key (not yet pinned).

  python bench/smoke_decisive.py [--runs N]
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH))
import run_bench as rb          # noqa: E402
import grade                    # noqa: E402

MODEL = "claude-sonnet-5"
REPO = {"name": "oci", "dir": "/home/ivy/Code/oci", "tasks": []}
KEY = json.loads((BENCH / "answer_keys" / "oci-schema-blast.json").read_text())


def _fmt_p(p) -> str:
    return f"{p:.2f}" if p is not None else "n/a"


def _median(xs, default=None):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else default


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=2, help="runs per arm")
    args = ap.parse_args()

    if shutil.which("claude") is None:
        print("error: `claude` CLI not on PATH", file=sys.stderr)
        return 2

    rb._write_mcp_configs()
    print(f"preparing oci (working tree, key verified against HEAD "
          f"{KEY['verified_against']['head']} dirty) ...", flush=True)
    prepared = rb.prepare_repo(REPO)
    if not prepared:
        print("error: could not prepare oci", file=sys.stderr)
        return 1
    clean, withd = prepared
    prompt = KEY["question"]

    diag = BENCH / ".cache" / "diag"
    diag.mkdir(parents=True, exist_ok=True)

    # (label, workdir, arm, force_graph). 'with-forced' takes text search away
    # (--disallowedTools Grep/Glob/Bash) so the agent MUST navigate via repo-graph
    # tools + Read — isolating the graph's value from whether Sonnet *chooses* to
    # call it. A normal 'with' run just greps (graph=0), so it can't test the
    # features. Add ('with', withd, 'with', False) back to also see adoption.
    arms = [
        ("without", clean, "without", False),
        ("with-forced", withd, "with", True),
    ]
    results: dict[str, list[dict]] = {label: [] for label, *_ in arms}

    for label, wd, arm, fg in arms:
        for i in range(args.runs):
            m = rb.run_with_retries(prompt, wd, arm, MODEL, 40, force_graph=fg)
            txt = m.get("result_text", "") or ""
            s = grade.grade(txt, KEY)
            (diag / f"decisive-oci-{label}-{i}.txt").write_text(txt)
            results[label].append({"m": m, "s": s})
            print(f"  {label:<12} run {i + 1}/{args.runs}: "
                  f"recall={s['recall']:.2f} precision={_fmt_p(s['precision'])} "
                  f"dead_as_live={len(s['dead_cited_as_live'])} pass={grade.passed(s)} | "
                  f"${m.get('cost', 0):.3f} turns={m.get('turns', '?')} "
                  f"graph={m.get('graph_calls', '?')} explore={m.get('explore_calls', '?')}",
                  flush=True)

    print("\n=== SUMMARY (median over runs) ===")
    for label in results:
        rs = [r["s"]["recall"] for r in results[label]]
        ps = [r["s"]["precision"] for r in results[label]]
        dc = [len(r["s"]["dead_cited_as_live"]) for r in results[label]]
        gc = [r["m"].get("graph_calls", 0) for r in results[label]]
        cost = [r["m"].get("cost", 0) for r in results[label]]
        print(f"  {label:<12} recall~{_median(rs, 0):.2f}  precision~{_fmt_p(_median(ps))}  "
              f"dead_as_live~{_median(dc, 0):.1f}  graph_calls~{_median(gc, 0):.0f}  "
              f"${_median(cost, 0):.3f}")

    # Structural gap: what the best 'without' run missed / wrongly kept as live.
    best_wo = max(results["without"], key=lambda r: r["s"]["recall"], default=None)
    if best_wo:
        print(f"\n  best WITHOUT run missed: {best_wo['s']['missed']}")
        print(f"  best WITHOUT dead cited as live: {best_wo['s']['dead_cited_as_live']}")
    print(f"\n  transcripts: {diag}/decisive-oci-*.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
