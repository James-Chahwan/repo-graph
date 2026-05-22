"""Tests for the cache-aware `get_graph()` path (engine v0.4.14+).

Verifies the load → is_stale → generate → save chain in `repo_graph.server`
behaves as documented: cold start writes the cache, warm start reads it,
source changes invalidate it.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest
import repo_graph_py


FIXTURES_DIR = Path(__file__).parent / "fixtures"


# The 0.4.14 surface is required for these tests. If a downgrade ever happens
# in dev, the suite skips cleanly rather than failing opaquely.
_HAS_CACHE_API = (
    hasattr(repo_graph_py, "load_from_gmap")
    and hasattr(repo_graph_py, "is_stale")
    and hasattr(repo_graph_py, "default_gmap_dir")
)

pytestmark = pytest.mark.skipif(
    not _HAS_CACHE_API,
    reason="repo-graph-py < 0.4.14 (no cache API)",
)


@pytest.fixture
def target_repo(tmp_path):
    dst = tmp_path / "target"
    shutil.copytree(FIXTURES_DIR / "http_stack_smoke", dst)
    return dst


@pytest.fixture
def server_isolated(target_repo, monkeypatch):
    """A server instance pointed at the target_repo, with the module-level
    cache fresh-zero. Each test gets its own."""
    from repo_graph import server

    monkeypatch.setattr(server, "REPO_PATH", str(target_repo))
    monkeypatch.setattr(server, "_graph", None)
    return server


def test_cold_start_generates_and_writes_cache(server_isolated, target_repo):
    gmap_dir = repo_graph_py.default_gmap_dir(str(target_repo))
    assert repo_graph_py.is_stale(gmap_dir, str(target_repo)), "fixture starts with no cache"

    g = server_isolated.get_graph()

    assert g.pygraph.node_count() > 0
    assert not repo_graph_py.is_stale(gmap_dir, str(target_repo)), \
        "first get_graph() should have written the cache"


def test_warm_start_reads_cache(server_isolated, target_repo, monkeypatch):
    # Warm the cache by calling get_graph once
    g1 = server_isolated.get_graph()
    n1 = g1.pygraph.node_count()

    # Reset module cache so get_graph() goes back to disk
    monkeypatch.setattr(server_isolated, "_graph", None)

    t0 = time.perf_counter()
    g2 = server_isolated.get_graph()
    warm_ms = (time.perf_counter() - t0) * 1000

    assert g2.pygraph.node_count() == n1
    # Warm load should be meaningfully faster than a fresh generate.
    # Small fixture so we just assert under 1s (cold generate is ~few ms here too;
    # the real win is on big repos — but we still want to confirm correctness).
    assert warm_ms < 1000, f"warm get_graph took {warm_ms:.0f}ms"


def test_source_change_invalidates_cache(server_isolated, target_repo, monkeypatch):
    g1 = server_isolated.get_graph()
    gmap_dir = repo_graph_py.default_gmap_dir(str(target_repo))
    assert not repo_graph_py.is_stale(gmap_dir, str(target_repo))

    # Modify a source file: append a real comment so content + mtime both
    # change. Sleep first so the new mtime is strictly > the cache mtime
    # (filesystem mtime resolution can be coarse).
    src = target_repo / "backend" / "server" / "server.go"
    time.sleep(1.1)
    src.write_text(src.read_text() + "\n// touched by test\n")

    assert repo_graph_py.is_stale(gmap_dir, str(target_repo)), \
        "stale after real source change"

    # Reset and reload — should regenerate and re-cache with a now-newer mtime
    monkeypatch.setattr(server_isolated, "_graph", None)
    g2 = server_isolated.get_graph()
    assert not repo_graph_py.is_stale(gmap_dir, str(target_repo)), \
        "regenerate path should rewrite the cache"
    assert g2.pygraph.node_count() == g1.pygraph.node_count()


def test_generate_tool_writes_cache(server_isolated, target_repo):
    gmap_dir = repo_graph_py.default_gmap_dir(str(target_repo))
    assert repo_graph_py.is_stale(gmap_dir, str(target_repo))

    out = server_isolated.generate()
    assert "Generated:" in out
    assert not repo_graph_py.is_stale(gmap_dir, str(target_repo)), \
        "generate() tool should persist the cache"


def test_cache_load_matches_fresh_generate(target_repo):
    """The PyGraph returned from load_from_gmap should be functionally
    equivalent to the one returned by generate."""
    pg_fresh = repo_graph_py.generate(str(target_repo))
    pg_fresh.save_to_default(str(target_repo))

    pg_cached = repo_graph_py.load_from_gmap(
        repo_graph_py.default_gmap_dir(str(target_repo))
    )

    assert pg_cached.node_count() == pg_fresh.node_count()
    assert pg_cached.edge_count() == pg_fresh.edge_count()
    assert pg_cached.cross_edge_count() == pg_fresh.cross_edge_count()
    assert pg_cached.dense_text() == pg_fresh.dense_text()
