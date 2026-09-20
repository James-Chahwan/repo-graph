"""Tests for the background file watcher (Phase 2 freshness).

Covers the ignore filter, the trailing debounce, and a real filesystem round-trip
through watchdog (guarded so the suite still runs without it installed).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from repo_graph.watcher import (
    Debouncer, is_ignored, start_watcher, SKIP_DIRS, WRITE_EVENTS,
)


def test_is_ignored_skips_cache_and_vcs():
    assert is_ignored("/repo/.ai/repo-graph/graph.gmap")  # legacy 0.4.x layout
    assert is_ignored("/repo/.git/index")
    assert is_ignored("/repo/node_modules/x/index.js")
    assert is_ignored("/repo/__pycache__/m.pyc")
    assert not is_ignored("/repo/src/main.py")
    assert not is_ignored("/repo/app/routes/users.go")


def test_layout_dir_skipped_by_prefix(tmp_path):
    """`<repo>/.glia/graph` is our own write — skip it, or every rebuild
    schedules the next one."""
    layout = str(tmp_path / ".glia" / "graph")
    assert is_ignored(str(tmp_path / ".glia" / "graph" / "parse_cache.bin"), layout)
    assert is_ignored(str(tmp_path / ".glia" / "graph" / "repo-1.gmap"), layout)


def test_glia_inputs_still_rebuild(tmp_path):
    """`.glia/` also holds committed *inputs* (overlay.toml, cells.jsonl) whose
    edits must rebuild — so the skip is the layout prefix, never the `.glia`
    name."""
    layout = str(tmp_path / ".glia" / "graph")
    assert not is_ignored(str(tmp_path / ".glia" / "overlay.toml"), layout)
    assert not is_ignored(str(tmp_path / ".glia" / "cells.jsonl"), layout)
    assert not is_ignored(str(tmp_path / ".glia" / "vectors.jsonl"), layout)
    assert ".glia" not in SKIP_DIRS, "a blanket .glia skip would swallow overlay edits"


def test_read_only_events_are_not_write_events():
    """watchdog >= 6.0 emits `opened` / `closed_no_write` on Linux. A rebuild
    opens every source file, so triggering on those makes each rebuild schedule
    the next one — the loop that wrote ~1.2 TB in a day while idle."""
    assert "opened" not in WRITE_EVENTS
    assert "closed_no_write" not in WRITE_EVENTS
    for ev in ("created", "modified", "moved", "deleted"):
        assert ev in WRITE_EVENTS


def test_debouncer_coalesces_burst():
    calls = []
    done = threading.Event()

    def fn():
        calls.append(1)
        done.set()

    d = Debouncer(0.05, fn)
    for _ in range(10):  # a burst
        d.trigger()
        time.sleep(0.005)
    assert done.wait(1.0)
    time.sleep(0.05)
    assert calls == [1]  # ten triggers -> one call


def test_debouncer_cancel_prevents_call():
    calls = []
    d = Debouncer(0.1, lambda: calls.append(1))
    d.trigger()
    d.cancel()
    time.sleep(0.2)
    assert calls == []


def test_start_watcher_none_for_missing_dir(tmp_path):
    assert start_watcher(str(tmp_path / "nope"), lambda: None) is None


def test_start_watcher_fires_on_edit(tmp_path):
    pytest.importorskip("watchdog")
    fired = threading.Event()
    observer = start_watcher(str(tmp_path), fired.set, delay=0.05)
    assert observer is not None
    try:
        (tmp_path / "main.py").write_text("print(1)\n")
        assert fired.wait(5.0), "watcher did not fire on a source edit"
    finally:
        observer.stop()
        observer.join(timeout=2)


def test_start_watcher_ignores_cache_writes(tmp_path):
    pytest.importorskip("watchdog")
    fired = threading.Event()
    observer = start_watcher(str(tmp_path), fired.set, delay=0.05)
    assert observer is not None
    try:
        cache = tmp_path / ".glia" / "graph"
        cache.mkdir(parents=True)
        (cache / "repo-1.gmap").write_text("x")
        # A write under the layout dir must NOT trigger a rebuild (else loop).
        assert not fired.wait(0.6)
    finally:
        observer.stop()
        observer.join(timeout=2)


def test_start_watcher_ignores_reads(tmp_path):
    """Reading a source file must not trigger a rebuild. This is the loop guard:
    a rebuild reads the whole tree, so if reads fired, it would never settle."""
    pytest.importorskip("watchdog")
    src = tmp_path / "main.py"
    src.write_text("print(1)\n")
    fired = threading.Event()
    observer = start_watcher(str(tmp_path), fired.set, delay=0.05)
    assert observer is not None
    try:
        time.sleep(0.3)      # let the create settle
        fired.clear()
        for _ in range(5):   # what a rebuild does to every file
            src.read_text()
        assert not fired.wait(0.6), "reading a file triggered a rebuild"
    finally:
        observer.stop()
        observer.join(timeout=2)
