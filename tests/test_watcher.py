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


def test_skip_dirs_above_the_repo_dont_count(tmp_path):
    """Only the path under the watched repo is checked. A repo that sits under a
    dir named `build` / `env` / `target` used to have every event dropped."""
    root = str(tmp_path / "target" / "shop")
    assert not is_ignored(f"{root}/src/main.py", root=root)
    assert is_ignored(f"{root}/node_modules/x/index.js", root=root)
    assert is_ignored(f"{root}/target/debug/build.rs", root=root)


def test_start_watcher_fires_for_a_repo_under_a_skip_dir_name(tmp_path):
    pytest.importorskip("watchdog")
    repo = tmp_path / "build" / "shop"
    repo.mkdir(parents=True)
    fired = threading.Event()
    observer = start_watcher(str(repo), fired.set, delay=0.05)
    assert observer is not None
    try:
        (repo / "main.py").write_text("print(1)\n")
        assert fired.wait(5.0), "watcher dropped an edit because a parent dir is named build"
    finally:
        observer.stop()
        observer.join(timeout=2)


# ── The held watch session (glia 0.5.2 WatchSession) ────────────────────────
# The server keeps one engine session per repo: a change re-reads only what the
# session's stat scan finds and rebuilds only the language groups it feeds,
# instead of a whole `generate` + layout write per change.

import shutil

import glia_py

_FIXTURE = Path(__file__).parent / "fixtures" / "http_stack_smoke"

needs_session = pytest.mark.skipif(
    not hasattr(glia_py, "WatchSession"), reason="glia-py < 0.5.2 (no WatchSession)")


@pytest.fixture
def served(tmp_path, monkeypatch):
    """A server pointed at a copy of the HTTP fixture, its session state fresh."""
    from repo_graph import server
    repo = tmp_path / "target"
    shutil.copytree(_FIXTURE, repo)
    for name, value in (("REPO_PATH", str(repo)), ("_graph", None), ("_session", None),
                        ("_session_repo", None), ("_session_seq", 0),
                        ("_session_dirty", False), ("_last_persist", 0.0)):
        monkeypatch.setattr(server, name, value)
    return server, repo


def _edit(repo: Path, fn: str) -> None:
    src = repo / "backend" / "server" / "server.go"
    src.write_text(src.read_text() + f"\nfunc {fn}() {{}}\n")


@needs_session
def test_session_update_serves_the_edit(served, monkeypatch):
    server, repo = served
    monkeypatch.setattr(server, "PERSIST_EVERY_SEC", 3600.0)
    server._open_session(str(repo))
    assert server._session is not None
    before = server.get_graph().pygraph.node_count()

    _edit(repo, "SessionProbe")
    server._watch_rebuild()

    g = server.get_graph()
    assert g.pygraph.node_count() == before + 1
    assert "SessionProbe" in server.find("SessionProbe")
    # Persisted on the interval, never per change.
    assert server._session_dirty


@needs_session
def test_session_quiet_scan_keeps_the_served_graph(served):
    server, repo = served
    server._open_session(str(repo))
    g = server.get_graph()
    server._watch_rebuild()  # nothing changed
    assert server.get_graph() is g


@needs_session
def test_session_matches_a_clean_build(served):
    """The handoff's parity check: an updated session equals a fresh generate."""
    server, repo = served
    server._open_session(str(repo))
    _edit(repo, "ParityProbe")
    server._watch_rebuild()
    fresh = glia_py.generate(str(repo), incremental=False)
    served_graph = server.get_graph().pygraph
    assert served_graph.node_count() == fresh.node_count()
    assert served_graph.edge_count() == fresh.edge_count()


@needs_session
def test_session_persists_on_the_interval_and_at_exit(served, monkeypatch):
    server, repo = served
    layout = glia_py.default_gmap_dir(str(repo))

    monkeypatch.setattr(server, "PERSIST_EVERY_SEC", 0.0)
    server._open_session(str(repo))
    _edit(repo, "IntervalProbe")
    server._watch_rebuild()
    assert not server._session_dirty
    n = server.get_graph().pygraph.node_count()
    assert glia_py.load_from_gmap(layout, str(repo)).node_count() == n

    monkeypatch.setattr(server, "PERSIST_EVERY_SEC", 3600.0)
    _edit(repo, "ExitProbe")
    server._watch_rebuild()
    assert server._session_dirty
    server._persist_at_exit()
    assert not server._session_dirty
    assert glia_py.load_from_gmap(layout, str(repo)).node_count() == n + 1


def test_watch_falls_back_to_a_rebuild_without_a_session(served):
    """Before the session opens (or if it can't), a change is a whole rebuild."""
    server, repo = served
    before = server.get_graph().pygraph.node_count()
    _edit(repo, "FallbackProbe")
    server._watch_rebuild()
    assert server._session is None
    assert server.get_graph().pygraph.node_count() == before + 1


@needs_session
def test_session_opened_for_an_old_target_is_dropped(served, tmp_path, monkeypatch):
    server, repo = served
    monkeypatch.setattr(server, "REPO_PATH", str(tmp_path / "elsewhere"))
    server._open_session(str(repo))
    assert server._session is None


@needs_session
def test_refresh_drops_or_reopens_the_session(served, tmp_path, monkeypatch):
    """A full refresh starts the session clean; a retarget drops it, since the
    watcher still watches the old repo."""
    server, repo = served
    server._open_session(str(repo))
    reopened = []
    monkeypatch.setattr(server, "_open_session", reopened.append)

    server.refresh()  # incremental, same repo: the session carries on
    assert server._session is not None and reopened == []

    server.refresh(full=True)
    assert server._session is None
    deadline = time.monotonic() + 5
    while not reopened and time.monotonic() < deadline:
        time.sleep(0.01)
    assert reopened == [str(repo)]

    # Retarget with a session open on the old repo (nothing waiting to persist).
    other = tmp_path / "other"
    shutil.copytree(_FIXTURE, other)
    monkeypatch.setattr(server, "_session", object())
    monkeypatch.setattr(server, "_session_repo", str(repo))
    server.refresh(str(other))
    assert server._session is None
    assert reopened == [str(repo)]  # not re-opened for the new target
