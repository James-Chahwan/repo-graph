"""Integration tests for every @mcp.tool in repo_graph.server.

Calls each tool function directly (the decorator returns the plain function,
so this is the same path the MCP runtime takes). The `mcp_server` fixture
wires the server's module-level globals to the http_stack_smoke fixture.

Assertions check output *shape*, not exact strings — tight enough to catch
regressions where a tool returns empty or crashes, loose enough to survive
cosmetic rendering changes.
"""

from __future__ import annotations

import pytest


# ── helpers ─────────────────────────────────────────────────────────────────


def _real_node_name(mcp_server) -> str:
    """Pick a real node name from the loaded graph for trace/impact/etc."""
    for n in mcp_server._graph.nodes.values():
        name = n.get("name")
        if name and len(name) > 1:
            return name
    pytest.skip("fixture produced no named nodes")


def _real_flow_key(mcp_server) -> str | None:
    keys = list(mcp_server._graph.flows.keys())
    return keys[0] if keys else None


# ── Tier 0: Generation ──────────────────────────────────────────────────────


def test_generate_returns_summary(mcp_server, tmp_path):
    # Use the fixture path the server is already wired to
    out = mcp_server.generate()
    assert out.startswith("Generated:"), out
    assert "nodes" in out and "edges" in out
    assert "Engine: repo-graph-py" in out


def test_generate_handles_bad_path(mcp_server):
    out = mcp_server.generate("/nonexistent/path/that/will/never/exist")
    assert "Generation failed" in out or "Generated:" in out


def test_generate_routes_git_url_through_resolver(mcp_server, monkeypatch):
    """A git URL must go through `_resolve_repo` (clone) before the engine, which
    only accepts a directory — otherwise it errors with 'not a directory'."""
    seen = {}

    def fake_resolve(spec):
        seen["spec"] = spec
        raise RuntimeError("RESOLVE_WAS_CALLED")  # surfaced via generate's try/except

    monkeypatch.setattr(mcp_server, "_resolve_repo", fake_resolve)
    out = mcp_server.generate("https://github.com/org/repo.git")
    assert seen.get("spec") == "https://github.com/org/repo.git"
    assert "RESOLVE_WAS_CALLED" in out


def test_resolve_repo_passes_local_path_through(mcp_server):
    assert mcp_server._resolve_repo("/home/x/proj") == "/home/x/proj"
    assert mcp_server._looks_like_git_url("https://github.com/o/r.git")
    assert mcp_server._looks_like_git_url("git@github.com:o/r.git")
    assert not mcp_server._looks_like_git_url("/home/x/proj")


# ── Tier 1: Navigation ──────────────────────────────────────────────────────


def test_status(mcp_server):
    out = mcp_server.status()
    assert "repo-graph" in out
    assert "Engine:" in out
    assert "Node kinds:" in out


def test_dense_text_non_empty(mcp_server):
    out = mcp_server.dense_text()
    assert out
    # Sigil notation header from projection-text crate
    assert "[LEGEND]" in out or len(out) > 100


def test_flow_unknown_lists_available(mcp_server):
    out = mcp_server.flow("definitely-not-a-real-feature-name")
    assert "No flow found" in out


def test_flow_known(mcp_server):
    key = _real_flow_key(mcp_server)
    if key is None:
        pytest.skip("fixture has no auto-detected flows")
    out = mcp_server.flow(key)
    assert "Flow:" in out
    assert "nodes in flow" in out


def test_trace_unknown_node(mcp_server):
    out = mcp_server.trace("zzz_definitely_bogus", "yyy_also_bogus")
    assert "Node not found" in out


def test_trace_same_node_is_one_hop(mcp_server):
    name = _real_node_name(mcp_server)
    out = mcp_server.trace(name, name)
    # Either "Trace:" with 1 hop or "No path" — depends on the engine. Both
    # are valid; we just need a real response, not a crash.
    assert "Trace:" in out or "No path" in out


def test_impact_downstream(mcp_server):
    name = _real_node_name(mcp_server)
    out = mcp_server.impact(name)
    assert "Impact downstream" in out or "No downstream" in out


def test_impact_upstream(mcp_server):
    name = _real_node_name(mcp_server)
    out = mcp_server.impact(name, "upstream", 3)
    assert "Impact upstream" in out or "No upstream" in out


def test_impact_unknown_node(mcp_server):
    out = mcp_server.impact("xxx_unknown_node_xxx")
    assert "No nodes found" in out


def test_impact_multi_seed(mcp_server):
    names = [n["name"] for n in mcp_server._graph.nodes.values() if n.get("name") and len(n["name"]) > 1]
    seeds = ",".join(names[:2])
    out = mcp_server.impact(seeds, depth=2)
    assert "Impact downstream" in out or "No downstream" in out


def test_impact_prose_mode(mcp_server):
    name = _real_node_name(mcp_server)
    out = mcp_server.impact(name, mode="prose")
    # prose is free text via the engine; just confirm a non-empty, non-error result
    assert out.strip() and "Node not found" not in out


def test_neighbours(mcp_server):
    name = _real_node_name(mcp_server)
    out = mcp_server.neighbours(name)
    # Either has connections or is marked isolated — both are valid renderings
    assert name in out
    assert (
        "Outbound" in out
        or "Inbound" in out
        or "isolated node" in out
    )


def test_neighbours_unknown(mcp_server):
    out = mcp_server.neighbours("xxx_unknown_node_xxx")
    assert "Node not found" in out


def _node_with_span(mcp_server) -> dict | None:
    for n in mcp_server._graph.nodes.values():
        if n.get("path") and n.get("start_line"):
            return n
    return None


def test_read_returns_source(mcp_server):
    node = _node_with_span(mcp_server)
    if node is None:
        pytest.skip("fixture produced no node with a source span")
    out = mcp_server.read(node["name"])
    assert node["path"] in out           # header carries the real path
    assert "```" in out                  # fenced code block


def test_read_unknown_node(mcp_server):
    out = mcp_server.read("xxx_unknown_node_xxx")
    assert "Node not found" in out


def test_read_context_lines_pads(mcp_server):
    node = _node_with_span(mcp_server)
    if node is None:
        pytest.skip("fixture produced no node with a source span")
    base = mcp_server.read(node["name"])
    padded = mcp_server.read(node["name"], context_lines=5)
    assert len(padded) >= len(base)


# ── Tier 2: Activation & Context ────────────────────────────────────────────


def test_find_known(mcp_server):
    name = _real_node_name(mcp_server)
    out = mcp_server.find(name)
    assert "Found" in out and "matching" in out


def test_find_unknown(mcp_server):
    out = mcp_server.find("xxx_definitely_not_a_real_symbol_xxx")
    assert "No nodes found" in out


def test_activate_known_seed(mcp_server):
    name = _real_node_name(mcp_server)
    out = mcp_server.activate(name, 10)
    assert "Activation from" in out
    assert "Top" in out


def test_activate_empty_seeds(mcp_server):
    out = mcp_server.activate("", 10)
    assert "No seed nodes found" in out


def test_activate_unknown_seed(mcp_server):
    out = mcp_server.activate("xxx_bogus_seed_xxx", 10)
    assert "No seed nodes found" in out


def test_activate_profile(mcp_server):
    name = _real_node_name(mcp_server)
    out = mcp_server.activate(name, 10, profile="repair")
    assert "profile=repair" in out


def test_activate_prose_mode(mcp_server):
    name = _real_node_name(mcp_server)
    out = mcp_server.activate(name, 10, mode="prose")
    assert out.strip() and "No seed nodes found" not in out


def test_locate_resolves_path(mcp_server):
    out = mcp_server.locate("backend/server/server.go", kind="diff", top_k=5)
    # either resolves to ranked nodes, or cleanly reports nothing matched
    assert "relevant nodes" in out or "No graph nodes resolved" in out


def test_locate_no_match(mcp_server):
    out = mcp_server.locate("zzz/nonexistent/file_xyz_qqq.go", kind="diff")
    assert "No graph nodes resolved" in out or "relevant nodes" in out


def test_dense_text_scoped_seed(mcp_server):
    name = _real_node_name(mcp_server)
    out = mcp_server.dense_text(seed=name)
    assert out.strip() and "not found" not in out.lower()


def test_dense_text_budget_truncates(mcp_server):
    full = mcp_server.dense_text()
    if len(full) <= 200:
        pytest.skip("fixture dense_text smaller than budget")
    out = mcp_server.dense_text(budget=200)
    assert "truncated" in out


# ── Tier 3: Health & Admin ──────────────────────────────────────────────────


def test_graph_view_no_arg_is_overview(mcp_server):
    out = mcp_server.graph_view()
    assert "repo-graph" in out
    assert "Node kinds:" in out


def test_graph_view_with_node(mcp_server):
    name = _real_node_name(mcp_server)
    out = mcp_server.graph_view(name, 2)
    assert name in out


def test_graph_view_unknown_node(mcp_server):
    out = mcp_server.graph_view("xxx_unknown_node_xxx", 2)
    assert "Node not found" in out


def test_reload(mcp_server):
    pre = mcp_server._graph.pygraph.node_count()
    out = mcp_server.reload()
    assert out.startswith("Reloaded:")
    # Should recover the same node count (graph is deterministic on same fixture)
    post = mcp_server._graph.pygraph.node_count()
    assert pre == post, f"reload changed node count: {pre} -> {post}"


# ── Smoke: confirm all 13 tools are registered ──────────────────────────────


def test_thirteen_tools_decorated():
    """Lock the public surface — checked against the actual MCP tool registry, so
    it catches both removed and added tools. If a tool changes, update both
    server.py and the CLAUDE.md tool list in lockstep."""
    from repo_graph import server

    expected = {
        "generate",                                   # Generation
        "status", "flow", "trace", "impact", "neighbours", "read",  # Navigation
        "activate", "find", "locate", "dense_text",   # Activation & Context
        "graph_view", "reload",                       # Health & Admin
    }
    actual = set(server.mcp._tool_manager._tools.keys())
    assert actual == expected, f"tool surface drifted: missing={expected - actual}, extra={actual - expected}"
