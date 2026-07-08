"""Integration tests for every @mcp.tool in repo_graph.server.

Calls each tool function directly (the decorator returns the plain function,
so this is the same path the MCP runtime takes). The `mcp_server` fixture
wires the server's module-level globals to the http_stack_smoke fixture.

Six tools: orient, find, impact, trace, read, refresh.

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


def _node_with_span(mcp_server) -> dict | None:
    for n in mcp_server._graph.nodes.values():
        if n.get("path") and n.get("start_line"):
            return n
    return None


def _real_flow_key(mcp_server) -> str | None:
    keys = list(mcp_server._graph.flows.keys())
    return keys[0] if keys else None


# ── refresh (← generate + reload) ───────────────────────────────────────────


def test_refresh_returns_summary(mcp_server):
    out = mcp_server.refresh()
    assert out.startswith("Rebuilt"), out
    assert "nodes" in out and "edges" in out
    assert "Engine: repo-graph-py" in out


def test_refresh_deterministic_node_count(mcp_server):
    pre = mcp_server._graph.pygraph.node_count()
    mcp_server.refresh()
    post = mcp_server._graph.pygraph.node_count()
    assert pre == post, f"refresh changed node count: {pre} -> {post}"


def test_refresh_full_reparse(mcp_server):
    out = mcp_server.refresh(full=True)
    assert "full reparse" in out


def test_refresh_handles_bad_path(mcp_server):
    out = mcp_server.refresh("/nonexistent/path/that/will/never/exist")
    assert "Refresh failed" in out or out.startswith("Rebuilt")


def test_refresh_routes_git_url_through_resolver(mcp_server, monkeypatch):
    """A git URL must go through `_resolve_repo` (clone) before the engine, which
    only accepts a directory — otherwise it errors with 'not a directory'."""
    seen = {}

    def fake_resolve(spec):
        seen["spec"] = spec
        raise RuntimeError("RESOLVE_WAS_CALLED")  # surfaced via refresh's try/except

    monkeypatch.setattr(mcp_server, "_resolve_repo", fake_resolve)
    out = mcp_server.refresh("https://github.com/org/repo.git")
    assert seen.get("spec") == "https://github.com/org/repo.git"
    assert "RESOLVE_WAS_CALLED" in out


def test_resolve_repo_passes_local_path_through(mcp_server):
    assert mcp_server._resolve_repo("/home/x/proj") == "/home/x/proj"
    assert mcp_server._looks_like_git_url("https://github.com/o/r.git")
    assert mcp_server._looks_like_git_url("git@github.com:o/r.git")
    assert not mcp_server._looks_like_git_url("/home/x/proj")


# ── orient (← status + dense_text + graph_view + coverage) ──────────────────


def test_orient_overview(mcp_server):
    out = mcp_server.orient()
    assert "repo-graph" in out
    assert "Node kinds:" in out
    assert "Engine:" in out


def test_orient_overview_omits_whole_graph_dump(mcp_server):
    """orient's default view is cheap orientation — it must not inline the dense
    map (the whole-graph token sink). It points the agent at `orient full=true`."""
    out = mcp_server.orient()
    assert "[LEGEND]" not in out           # the dense_text sigil header is not inlined
    assert "full=true" in out              # but the overview points at the full map


def test_orient_full_map(mcp_server):
    out = mcp_server.orient(full=True)
    assert out
    assert "[LEGEND]" in out or len(out) > 100


def test_orient_scoped_seed(mcp_server):
    name = _real_node_name(mcp_server)
    out = mcp_server.orient(seed=name)
    assert out.strip() and "not found" not in out.lower()


def test_orient_scoped_unknown_seed(mcp_server):
    out = mcp_server.orient(seed="xxx_unknown_node_xxx")
    assert "not found" in out.lower()


def test_orient_full_budget_truncates(mcp_server):
    full = mcp_server.orient(full=True)
    if len(full) <= 200:
        pytest.skip("fixture dense map smaller than budget")
    out = mcp_server.orient(full=True, budget=200)
    assert "truncated" in out


# ── find (← find + locate + activate) ───────────────────────────────────────


def test_find_keyword_match(mcp_server):
    name = _real_node_name(mcp_server)
    out = mcp_server.find(name)
    assert "matching" in out
    assert name in out


def test_find_keyword_shows_location(mcp_server):
    """Every find row carries `path:line` so it's actionable without a round-trip."""
    node = _node_with_span(mcp_server)
    if node is None:
        pytest.skip("fixture produced no node with a source span")
    out = mcp_server.find(node["name"])
    assert node["path"] in out


def test_find_unknown(mcp_server):
    out = mcp_server.find("xxx_definitely_not_a_real_symbol_xxx")
    assert "No nodes matched" in out


def test_find_expand_neighbourhood(mcp_server):
    """expand=True fans out to the PPR-ranked neighbourhood (old `activate`)."""
    name = _real_node_name(mcp_server)
    out = mcp_server.find(name, expand=True, top_k=10)
    assert "expanded" in out or "relevant" in out


def test_find_signal_diff(mcp_server):
    """A file-path / diff signal resolves via the engine (old `locate`)."""
    out = mcp_server.find("backend/server/server.go", kind="diff", top_k=5)
    # either resolves to ranked nodes, or falls back cleanly to keyword/no-match
    assert "from signal" in out or "matching" in out or "No nodes matched" in out


def test_find_signal_no_match(mcp_server):
    out = mcp_server.find("zzz/nonexistent/file_xyz_qqq.go", kind="diff")
    assert "No nodes matched" in out or "from signal" in out


def test_find_empty(mcp_server):
    out = mcp_server.find("   ")
    assert "Empty query" in out


# ── impact (← impact + neighbours) ──────────────────────────────────────────


def test_impact_both(mcp_server):
    name = _real_node_name(mcp_server)
    out = mcp_server.impact(name)
    assert "Impact (both)" in out or "nodes found from" in out or "nodes found" in out


def test_impact_backward(mcp_server):
    name = _real_node_name(mcp_server)
    out = mcp_server.impact(name, "backward", 3)
    assert "Impact (backward)" in out or "backward nodes found" in out


def test_impact_downstream_alias(mcp_server):
    """The old 'downstream' vocabulary still maps to the engine's 'forward'."""
    name = _real_node_name(mcp_server)
    out = mcp_server.impact(name, "downstream", 3)
    assert "Impact (forward)" in out or "forward nodes found" in out


def test_impact_unknown_node(mcp_server):
    out = mcp_server.impact("xxx_unknown_node_xxx")
    assert "No nodes found" in out


def test_impact_multi_seed(mcp_server):
    names = [n["name"] for n in mcp_server._graph.nodes.values()
             if n.get("name") and len(n["name"]) > 1]
    seeds = ",".join(names[:2])
    out = mcp_server.impact(seeds, depth=2)
    assert "Impact (" in out or "nodes found" in out


def test_impact_live_only(mcp_server):
    """live_only must not crash and must produce a valid impact result or a clean
    'nothing live' message."""
    name = _real_node_name(mcp_server)
    out = mcp_server.impact(name, live_only=True)
    assert "Impact (" in out or "nodes found" in out


# ── trace (← flow + trace) ──────────────────────────────────────────────────


def test_trace_path_unknown_node(mcp_server):
    out = mcp_server.trace("zzz_definitely_bogus", "yyy_also_bogus")
    assert "Node not found" in out


def test_trace_path_same_node(mcp_server):
    name = _real_node_name(mcp_server)
    out = mcp_server.trace(name, name)
    assert "Trace:" in out or "No path" in out


def test_trace_feature(mcp_server):
    """One-arg trace: feature across the stack (cross_stack_trace, or the flow
    fallback, or a clean 'no trace' with the entry-point list)."""
    key = _real_flow_key(mcp_server)
    feature = key or "definitely-not-a-real-feature-name"
    out = mcp_server.trace(feature)
    assert "Trace:" in out or "Flow:" in out or "No trace found" in out


def test_trace_feature_unknown_lists_entry_points(mcp_server):
    out = mcp_server.trace("definitely-not-a-real-feature-xyz")
    assert "No trace found" in out or "Trace:" in out or "Flow:" in out


# ── read (unchanged) ────────────────────────────────────────────────────────


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


def test_read_batch_multiple_nodes(mcp_server):
    """Comma-separated nodes are sliced in one call — the ranked-set read."""
    spans = [n for n in mcp_server._graph.nodes.values()
             if n.get("path") and n.get("start_line")]
    if len(spans) < 2:
        pytest.skip("fixture produced fewer than two nodes with spans")
    a, b = spans[0]["name"], spans[1]["name"]
    out = mcp_server.read(f"{a},{b}")
    assert out.count("```") >= 4          # two fenced blocks (open+close each)


def test_read_surfaces_context_cells(mcp_server):
    """read appends a `context:` footer from node_cells (method / cross-stack
    callers / tests / imports) — facts the source slice alone doesn't show."""
    g = mcp_server._graph
    surfaced = set(mcp_server._READ_CELL_LABELS)
    target = None
    for n in g.nodes.values():
        try:
            cells = g.pygraph.node_cells(n["id"])
        except Exception:
            continue
        if any(tid in surfaced for tid, _ in cells):
            target = n
            break
    if target is None:
        pytest.skip("fixture has no nodes with surfaced context cells")
    out = mcp_server.read(target["name"])
    assert "context:" in out


# ── Smoke: confirm exactly the 6 tools are registered ───────────────────────


def test_six_tools_decorated():
    """Lock the public surface — checked against the actual MCP tool registry, so
    it catches both removed and added tools. If a tool changes, update server.py,
    installer/constants.py TOOL_NAMES, and the CLAUDE.md tool list in lockstep."""
    from repo_graph import server

    expected = {"orient", "find", "impact", "trace", "read", "refresh"}
    actual = set(server.mcp._tool_manager._tools.keys())
    assert actual == expected, f"tool surface drifted: missing={expected - actual}, extra={actual - expected}"
