#!/usr/bin/env python3
"""Recall/precision grader for the decisive (Claim-2) benchmark tasks.

The default `is_correct` in run_bench is a boolean OR of substrings over the
answer AND the files the agent touched — it saturates at N/N the moment a
convention filename shows up, which is why the old matrix couldn't resolve a
correctness difference. This grader replaces it for closure/linking tasks:

  * It scores the agent's DELIVERABLE only (`result_text`), never the file
    footprint — footprint credits grep for sweeping and the graph for reading a
    file it never names, both of which corrupt a recall measure.
  * RECALL is measured against a hand-enumerated answer key of dir-qualified
    locations, reported overall and per layer, landing in the open interval
    (0,1) instead of collapsing to a ceiling.
  * PRECISION counts any KNOWN-DEAD location the agent cites as a live dependent
    — the false positive that no substring-OR grader can express and the thing
    the live-vs-dead task turns on.

Binding is strict on purpose: a required item (dir-qualified `path` + a
distinctive `token`) is "named" only when BOTH appear in the deliverable, so a
bare-basename mention or a "list every directory" dump does not satisfy it.

  python bench/grade.py <answer_key.json> <transcript.txt>   # grade a saved answer
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _norm(s: str) -> str:
    """Lowercase, collapse whitespace, and normalize comma spacing so multi-field
    tokens ('w, p, m, l') match regardless of the agent's spacing ('w,p,m,l')."""
    t = re.sub(r"\s+", " ", (s or "").lower())
    return re.sub(r"\s*,\s*", ",", t)


# Words that, on the same line as a dead location, show the agent correctly
# identified it as dead code rather than citing it as a live dependent to change.
DEAD_MARKERS = (
    "dead", "not reached", "never reached", "not imported", "never imported",
    "unreachable", "unused", "no change", "not run", "never run", "does not run",
    "doesn't run", "not executed", "not called", "mirror", "orphan", "stale",
)


def _cited_as_dead(lines: list[str], item: dict) -> bool:
    """True if the item's path appears on a line that also flags it dead. The task
    asks the agent to name the dead mirrors AND label them dead, so a correctly
    labeled dead citation must NOT count against precision — only a dead location
    presented as a live dependent (no dead marker nearby) is a false positive."""
    path = item["path"].lower()
    return any(path in ln and any(m in ln for m in DEAD_MARKERS) for ln in lines)


def _has_path(text: str, path: str) -> bool:
    """The full repo-relative path must appear verbatim. Anchors are authored as
    full paths ('src/compute/compute_oci.py', or a root file 'pipeline.py'), so a
    bare basename that is ambiguous with a dead twin ('compute_oci.py') never
    binds a 'src/compute/...' required item — the full string simply isn't there."""
    return path.lower() in text


def _has_token(text: str, token: str | None) -> bool:
    return token is None or _norm(token) in text


def _named(text: str, item: dict) -> bool:
    """A location is named only if BOTH its dir-qualified path and its
    distinctive token appear in the deliverable."""
    return _has_path(text, item["path"]) and _has_token(text, item.get("token"))


def _anchor(item: dict) -> str:
    return item["path"] + (f"::{item['token']}" if item.get("token") else "")


def grade(result_text: str, key: dict) -> dict:
    """Score a deliverable against an answer key. Returns recall, precision, the
    per-layer recall breakdown, and the concrete missed / wrongly-cited-dead
    lists so a run is auditable, not just a number."""
    flat = _norm(result_text)
    lines = (result_text or "").lower().splitlines()
    required = key.get("required", [])
    dead = key.get("dead", [])

    named = [it for it in required if _named(flat, it)]
    missed = [it for it in required if it not in named]

    # A dead location is a false positive only when cited WITHOUT a dead label —
    # i.e. presented as a live dependent. Correctly flagging it dead is what the
    # task asks and must not be penalized.
    dead_present = [it for it in dead if _named(flat, it)]
    dead_as_live = [it for it in dead_present if not _cited_as_dead(lines, it)]
    dead_flagged = [it for it in dead_present if _cited_as_dead(lines, it)]

    recall = (len(named) / len(required)) if required else None
    denom = len(named) + len(dead_as_live)
    precision = (len(named) / denom) if denom else None

    layers: dict[str, list[int]] = {}
    for it in required:
        lyr = layers.setdefault(it.get("layer", "?"), [0, 0])
        lyr[1] += 1
        if it in named:
            lyr[0] += 1

    return {
        "recall": recall,
        "precision": precision,
        "required": len(required),
        "named": len(named),
        "missed": [_anchor(it) for it in missed],
        "dead_cited_as_live": [_anchor(it) for it in dead_as_live],
        "dead_flagged_ok": [_anchor(it) for it in dead_flagged],
        "layer_recall": {lyr: round(c / n, 3) for lyr, (c, n) in layers.items()},
    }


def passed(scores: dict, min_recall: float = 0.80, min_precision: float = 0.90) -> bool:
    """The decisive-task pass gate. Recall AND precision must clear the bar; a
    single wrongly-cited dead location can fail precision even at full recall."""
    r = scores.get("recall")
    p = scores.get("precision")
    return (r is not None and r >= min_recall) and (p is None or p >= min_precision)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    key = json.loads(Path(sys.argv[1]).read_text())
    text = Path(sys.argv[2]).read_text()
    scores = grade(text, key)
    print(json.dumps(scores, indent=2))
    print(f"\nPASS: {passed(scores)}  (recall={scores['recall']}, precision={scores['precision']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
