"""Smoke tests for the 0.3.0 AST-based PythonAnalyzer.

Locks the fixture contract: py_method nodes, absolute import edges,
cross-file + self + constructor + module.func calls, and dropped
unresolvable calls.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pytest

from repo_graph.analyzers.python_lang import PythonAnalyzer
from repo_graph.discovery import build_index
from repo_graph.generator import _auto_flows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(repo: Path):
    """Scan a repo with PythonAnalyzer; return (nodes, edges) lists of dicts."""
    index = build_index(repo)
    analyzer = PythonAnalyzer(repo_root=repo, index=index)
    assert PythonAnalyzer.detect(index)
    result = analyzer.scan()
    return (
        [asdict(n) for n in result.nodes],
        [asdict(e) for e in result.edges],
    )


def _ids_by_type(nodes, node_type):
    return {n["id"] for n in nodes if n["type"] == node_type}


def _edges_of_type(edges, etype):
    return {(e["from_id"], e["to_id"]) for e in edges if e["type"] == etype}


# Fixture IDs (derived, used across assertions)
MOD_USERS = "py_mod_myapp_users"
MOD_HELPERS = "py_mod_myapp_helpers"
MOD_AUTH = "py_mod_myapp_auth"
MOD_INIT = "py_mod_myapp"

CLASS_USER = f"py_class_{MOD_USERS}_User"

METHOD_LOGIN = f"py_method_{CLASS_USER}_login"
METHOD_SAVE = f"py_method_{CLASS_USER}_save"

FUNC_HASH = f"py_func_{MOD_HELPERS}_hash_password"
FUNC_INNER = f"py_func_{MOD_HELPERS}__inner"
FUNC_DO_LOGIN = f"py_func_{MOD_AUTH}_do_login"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_methods_exist(py_smoke_repo):
    """py_method nodes are emitted for every method with the
    py_method_{class_id}_{name} shape."""
    nodes, _ = _run(py_smoke_repo)
    methods = _ids_by_type(nodes, "py_method")
    assert METHOD_LOGIN in methods
    assert METHOD_SAVE in methods


def test_method_defines_edges(py_smoke_repo):
    """Class nodes define their methods."""
    _, edges = _run(py_smoke_repo)
    defines = _edges_of_type(edges, "defines")
    assert (CLASS_USER, METHOD_LOGIN) in defines
    assert (CLASS_USER, METHOD_SAVE) in defines


def test_absolute_imports_resolve(py_smoke_repo):
    """Both absolute import forms produce module→module edges:
      - `from pkg.mod import Name` → edge to pkg.mod
      - `from pkg import mod`       → edge to pkg.mod (submodule resolution)
    """
    _, edges = _run(py_smoke_repo)
    imports = _edges_of_type(edges, "imports")
    # `from myapp.users import User`
    assert (MOD_AUTH, MOD_USERS) in imports
    # `from myapp import helpers` — helpers is a submodule, edge goes to it
    assert (MOD_AUTH, MOD_HELPERS) in imports


def test_relative_import_resolves(py_smoke_repo):
    """`from .helpers import hash_password` → edge to helpers module."""
    _, edges = _run(py_smoke_repo)
    imports = _edges_of_type(edges, "imports")
    assert (MOD_USERS, MOD_HELPERS) in imports


def test_calls_edges(py_smoke_repo):
    """Four resolvable call sites produce edges; unresolvable ones drop silently.

    Resolvable:
      - User.login → helpers.hash_password    (cross-file via local import)
      - User.save  → User.login                (self.method inside class)
      - helpers.hash_password → helpers._inner (same-file bare name)
      - auth.do_login → myapp.users.User       (constructor — User() call)
      - auth.do_login → helpers.hash_password  (helpers.hash_password via alias)

    Dropped:
      - auth.do_login → u.login()  (u's type is unknown → no edge to login method)
    """
    _, edges = _run(py_smoke_repo)
    calls = _edges_of_type(edges, "calls")

    assert (METHOD_LOGIN, FUNC_HASH) in calls
    assert (METHOD_SAVE, METHOD_LOGIN) in calls
    assert (FUNC_HASH, FUNC_INNER) in calls
    assert (FUNC_DO_LOGIN, CLASS_USER) in calls
    assert (FUNC_DO_LOGIN, FUNC_HASH) in calls

    # The u.login() call should NOT resolve to User.login — u's type is unknown.
    assert (FUNC_DO_LOGIN, METHOD_LOGIN) not in calls


def test_no_spurious_calls_edges(py_smoke_repo):
    """Sanity: total calls edge count is the five expected ones (no extras from
    unresolvable call sites leaking through)."""
    _, edges = _run(py_smoke_repo)
    calls = _edges_of_type(edges, "calls")
    assert len(calls) == 5, f"Expected 5 calls edges, got {len(calls)}: {calls}"


# ---------------------------------------------------------------------------
# _auto_flows prefer-calls test — in-memory nodes/edges, no fixture coupling
# ---------------------------------------------------------------------------


def _node(nid, ntype, name=None):
    return {"id": nid, "type": ntype, "name": name or nid, "file_path": "f.py", "confidence": "medium"}


def _edge(f, t, etype):
    return {"from": f, "to": t, "type": etype}


def test_flows_prefer_calls_from_function_source():
    """A function source with outgoing `calls` follows only calls — its other
    outgoing edges (defines/contains to nested symbols) are skipped.

    Module and class sources without outgoing calls still follow defines
    (explicitly accepted for 0.3.0 — see dev-notes item 10). This test
    exercises the rule where it actually bites: at the function level."""
    nodes = [
        _node("route_POST_x", "route", name="POST /x"),
        _node("py_func_handler", "py_function"),
        _node("py_func_callee", "py_function"),
        _node("py_func_nested_helper", "py_function"),  # defined by handler but not called
    ]
    edges = [
        # handled_by points directly to the handler (synthetic — tests the rule
        # at the function source, which is where 0.3.0's prefer-calls applies).
        _edge("route_POST_x", "py_func_handler", "handled_by"),
        _edge("py_func_handler", "py_func_callee", "calls"),
        _edge("py_func_handler", "py_func_nested_helper", "defines"),
    ]
    flows = _auto_flows(nodes, edges)
    assert flows, f"Expected a flow, got none: {flows}"
    flow_text = next(iter(flows.values()))

    assert "py_func_handler" in flow_text
    assert "py_func_callee" in flow_text
    # handler has outgoing calls → skip its defines edge → nested helper absent
    assert "py_func_nested_helper" not in flow_text


def test_flows_fall_back_when_no_calls():
    """Source with no outgoing `calls` still follows defines/contains (no regression)."""
    nodes = [
        _node("route_GET_y", "route", name="GET /y"),
        _node("py_mod_legacy", "py_module"),
        _node("py_func_legacy_foo", "py_function"),
    ]
    edges = [
        _edge("route_GET_y", "py_mod_legacy", "handled_by"),
        _edge("py_mod_legacy", "py_func_legacy_foo", "defines"),
    ]
    flows = _auto_flows(nodes, edges)
    assert flows, f"Expected a flow, got none: {flows}"
    flow_text = next(iter(flows.values()))
    # Function still reachable via defines because handler module has no calls out
    assert "py_func_legacy_foo" in flow_text
