"""Tests for the decisive-benchmark recall/precision grader (bench/grade.py).

The grader only earns its place if it (a) separates a graph-arm answer that names
live dir-qualified locations from a grep-arm answer that names a class + a couple
files and mis-cites a dead mirror, and (b) can't be gamed by a hedging 'the change
spans src/utils, src/normalize, ...' dump. Both are asserted here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent.parent / "bench"
sys.path.insert(0, str(BENCH))
import grade  # noqa: E402

KEY = json.loads((BENCH / "answer_keys" / "oci-schema-blast.json").read_text())


def test_full_answer_scores_perfect():
    # Names every required path+token, cites no dead file.
    text = "\n".join(f"{it['path']} — {it['token']}" for it in KEY["required"])
    s = grade.grade(text, KEY)
    assert s["recall"] == 1.0
    assert s["precision"] == 1.0
    assert grade.passed(s)


def test_grep_arm_answer_underscores_and_mis_cites_dead():
    # A class-name-grep answer: finds the ORM class + the dead mirror (grep can't
    # tell it's unreachable and lists it as a dependent), misses the raw-SQL /
    # dict / json / frontend layers.
    text = (
        "The schema lives in src/utils/db.py as OCIComponent. "
        "It's also read in src/process/compute_oci.py get_oci_rankings."
    )
    s = grade.grade(text, KEY)
    assert s["recall"] < 0.3                       # only the DB layer found
    assert s["dead_cited_as_live"]                 # cited a dead file as a live dependent
    assert s["precision"] < 1.0
    assert not grade.passed(s)


def test_correct_partition_not_penalized():
    # Names every live dependent AND correctly labels the dead mirrors as dead —
    # exactly what the task asks. Precision must stay 1.0 (the HIGH-bug fix).
    live = "\n".join(f"{it['path']} — {it['token']}" for it in KEY["required"])
    deadlines = "\n".join(
        f"{it['path']} — {it['token']} — DEAD, never imported, does not run"
        for it in KEY["dead"]
    )
    s = grade.grade(live + "\n" + deadlines, KEY)
    assert s["recall"] == 1.0
    assert s["precision"] == 1.0                    # correctly-flagged dead not penalized
    assert s["dead_flagged_ok"] and not s["dead_cited_as_live"]
    assert grade.passed(s)


def test_directory_dump_does_not_bind():
    # A hedging 'lists every directory' dump must NOT satisfy required items,
    # because binding needs the full dir-qualified path, not a dir prefix.
    text = "The change spans src/utils, src/normalize, src/compute, src/api and the frontend."
    s = grade.grade(text, KEY)
    assert s["named"] == 0
    assert s["recall"] == 0.0


def test_bare_basename_does_not_bind():
    # 'compute_oci.py' alone is ambiguous with the dead twin and must not bind
    # the live src/compute item.
    text = "The value is assigned in compute_oci.py by _status_from_oci."
    s = grade.grade(text, KEY)
    named = [m for m in s["missed"]]
    # the src/compute/compute_oci.py::_status_from_oci item stays MISSED
    assert any("src/compute/compute_oci.py::_status_from_oci" == m for m in s["missed"])


def test_dead_only_citation_tanks_precision():
    # Cites a dead file as a live dependent (no dead label) and nothing else.
    text = "src/process/compute_oci.py get_oci_rankings reads the fields."
    s = grade.grade(text, KEY)
    assert s["named"] == 0
    assert s["dead_cited_as_live"]
    assert s["precision"] == 0.0


def test_layer_recall_reported():
    text = "src/utils/db.py OCIComponent upsert_oci_component"
    s = grade.grade(text, KEY)
    assert s["layer_recall"]["db"] == 1.0
    assert s["layer_recall"].get("frontend", 0) == 0.0
