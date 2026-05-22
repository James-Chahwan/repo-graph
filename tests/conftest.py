"""Shared pytest fixtures for the MCP server tests.

Each fixture copies a fixtures/* repo to a tmp dir (so analyzers don't trip
on the '/tests/' skip rule) and runs `repo_graph_py.generate()` once per
session. Tests downstream get a (PyGraph, repo_path) tuple.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import repo_graph_py


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _copy_fixture(tmp_path_factory: pytest.TempPathFactory, name: str) -> Path:
    """Copy tests/fixtures/<name>/ to a tmp dir so analyzers see it as a real repo."""
    dst_root = tmp_path_factory.mktemp(name)
    dst = dst_root / name
    shutil.copytree(FIXTURES_DIR / name, dst)
    return dst


def _generate(repo: Path):
    pg = repo_graph_py.generate(str(repo))
    return pg, repo


@pytest.fixture(scope="session")
def py_smoke_graph(tmp_path_factory):
    return _generate(_copy_fixture(tmp_path_factory, "py_smoke"))


@pytest.fixture(scope="session")
def go_smoke_graph(tmp_path_factory):
    return _generate(_copy_fixture(tmp_path_factory, "go_smoke"))


@pytest.fixture(scope="session")
def ts_smoke_graph(tmp_path_factory):
    return _generate(_copy_fixture(tmp_path_factory, "ts_smoke"))


@pytest.fixture(scope="session")
def http_stack_graph(tmp_path_factory):
    """Cross-stack fixture: Go backend + TS frontend. Used as the canonical
    target for MCP tool tests because it exercises routes, methods, classes,
    and cross-stack resolution."""
    return _generate(_copy_fixture(tmp_path_factory, "http_stack_smoke"))


@pytest.fixture
def mcp_server(http_stack_graph, monkeypatch):
    """Wire `repo_graph.server` to the http_stack fixture so the @mcp.tool
    functions can be called directly. monkeypatch restores module state
    after the test."""
    from repo_graph import server
    from repo_graph.graph import RustGraph

    pg, repo = http_stack_graph
    monkeypatch.setattr(server, "REPO_PATH", str(repo))
    monkeypatch.setattr(server, "_graph", RustGraph(pg, str(repo)))
    return server
