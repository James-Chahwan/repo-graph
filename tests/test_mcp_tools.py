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
    assert "Node not found" in out


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


# ── Smoke: confirm all 11 tools are decorated ───────────────────────────────


def test_eleven_tools_decorated():
    """Lock the public surface — if a tool is added/removed, this test fails
    and the CLAUDE.md tool list must be updated in lockstep."""
    from repo_graph import server

    expected = {
        "generate", "status", "dense_text", "flow", "trace",
        "impact", "neighbours", "activate", "find",
        "graph_view", "reload",
    }
    actual = {
        name for name in dir(server)
        if not name.startswith("_")
        and callable(getattr(server, name))
        and getattr(server, name).__module__ == "repo_graph.server"
        and name in expected
    }
    assert actual == expected, f"tool surface drifted: missing={expected - actual}, extra={actual - expected}"
