"""Tests for the background file watcher (Phase 2 freshness).

Covers the ignore filter, the trailing debounce, and a real filesystem round-trip
through watchdog (guarded so the suite still runs without it installed).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from repo_graph.watcher import Debouncer, is_ignored, start_watcher, SKIP_DIRS


def test_is_ignored_skips_cache_and_vcs():
    assert is_ignored("/repo/.ai/repo-graph/graph.gmap")  # our own cache -> no loop
    assert is_ignored("/repo/.git/index")
    assert is_ignored("/repo/node_modules/x/index.js")
    assert is_ignored("/repo/__pycache__/m.pyc")
    assert not is_ignored("/repo/src/main.py")
    assert not is_ignored("/repo/app/routes/users.go")


def test_ai_dir_is_skipped():
    # The rebuild writes under .ai; watching it would loop forever.
    assert ".ai" in SKIP_DIRS


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
        cache = tmp_path / ".ai" / "repo-graph"
        cache.mkdir(parents=True)
        (cache / "graph.gmap").write_text("x")
        # A write under .ai must NOT trigger a rebuild (else infinite loop).
        assert not fired.wait(0.6)
    finally:
        observer.stop()
        observer.join(timeout=2)
