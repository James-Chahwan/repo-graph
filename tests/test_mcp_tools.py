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


#: Containers connect through IMPORTS/CONTAINS/DEFINES, which blast_radius
#: excludes as structural — so seeding one is a legitimate empty answer, not a
#: working impact call. `test_impact_container_seed` covers that case on purpose.
_CONTAINER_KINDS = {"module", "package", "project", "region", "doc_section"}


def _real_node_name(mcp_server) -> str:
    """Pick a real node name from the loaded graph for trace/impact/etc.

    Prefers a node that actually has a blast radius, so the impact tests
    exercise the answering path rather than the (equally valid, separately
    tested) empty one. A container or an edgeless leaf is the fallback."""
    fallback = None
    for n in mcp_server._graph.nodes.values():
        name = n.get("name")
        if not name or len(name) <= 1:
            continue
        fallback = fallback or name
        if n.get("kind") in _CONTAINER_KINDS:
            continue
        try:
            env = mcp_server._graph.pygraph.blast_radius(
                [n["qname"]], "both", 4, None, False)
        except Exception:
            continue
        if env.get("results"):
            return name
    if fallback:
        return fallback
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
    assert "Engine: glia-py" in out


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
    assert "No answer" in out and "no_match" in out


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
    assert "No answer" in out and "no_match" in out


def test_find_expand_neighbourhood(mcp_server):
    """expand=True fans out to the PPR-ranked neighbourhood (old `activate`)."""
    name = _real_node_name(mcp_server)
    out = mcp_server.find(name, expand=True, top_k=10)
    assert "expanded" in out or "relevant" in out


def test_find_signal_diff(mcp_server):
    """A file-path / diff signal resolves via the engine (old `locate`)."""
    out = mcp_server.find("backend/server/server.go", kind="diff", top_k=5)
    # either resolves to ranked nodes, or falls back cleanly to keyword/no-match
    assert "from signal" in out or "matching" in out or "No answer" in out


def test_find_signal_no_match(mcp_server):
    out = mcp_server.find("zzz/nonexistent/file_xyz_qqq.go", kind="diff")
    assert "No answer" in out or "from signal" in out


def test_absence_carries_reason_and_tier(mcp_server):
    """An empty answer is an engine `absence` envelope, not a wrapper guess: it
    names the reason and whether it's fact or heuristic (LD.8a)."""
    out = mcp_server.find("xxx_definitely_not_a_real_symbol_xxx")
    assert "No answer" in out
    assert "fact" in out or "heuristic" in out  # lowercase since glia 0.5.4
    assert "searched" in out and "nodes" in out


def test_find_empty(mcp_server):
    out = mcp_server.find("   ")
    assert "Empty query" in out


# ── impact (← impact + neighbours) ──────────────────────────────────────────


def test_impact_both(mcp_server):
    name = _real_node_name(mcp_server)
    out = mcp_server.impact(name)
    assert "Impact (both)" in out or "No answer" in out


def test_impact_backward(mcp_server):
    name = _real_node_name(mcp_server)
    out = mcp_server.impact(name, "backward", 3)
    assert "Impact (backward)" in out or "No answer" in out


def test_impact_downstream_alias(mcp_server):
    """The old 'downstream' vocabulary still maps to the engine's 'forward'."""
    name = _real_node_name(mcp_server)
    out = mcp_server.impact(name, "downstream", 3)
    assert "Impact (forward)" in out or "No answer" in out


def test_impact_unknown_node(mcp_server):
    out = mcp_server.impact("xxx_unknown_node_xxx")
    assert "No answer" in out and "unknown_symbol" in out


def test_impact_container_seed_explains_itself(mcp_server):
    """A module/package seed is an empty blast radius by design — structural
    import/containment edges are excluded. The engine's absence says so (it
    replaced the wrapper's hand-written hint, LD.5)."""
    container = next((n for n in mcp_server._graph.nodes.values()
                      if n.get("kind") == "module" and n.get("name")), None)
    if container is None:
        pytest.skip("fixture has no module nodes")
    out = mcp_server.impact(container["qname"])
    if "No answer" not in out:
        return  # the container did have carry edges — fine
    assert "no_edges" in out


def test_impact_reports_unresolved_seeds(mcp_server):
    """Unknown names come back in the engine's `unresolved` list rather than
    failing the whole call (LD.5: one walk, many seeds)."""
    name = _real_node_name(mcp_server)
    out = mcp_server.impact(f"{name},xxx_not_a_real_seed_xxx", depth=2)
    assert "xxx_not_a_real_seed_xxx" in out


def test_impact_multi_seed(mcp_server):
    names = [n["name"] for n in mcp_server._graph.nodes.values()
             if n.get("name") and len(n["name"]) > 1
             and n.get("kind") not in _CONTAINER_KINDS]
    if len(names) < 2:
        pytest.skip("fixture has fewer than two non-container nodes")
    seeds = ",".join(names[:2])
    out = mcp_server.impact(seeds, depth=2)
    assert "Impact (" in out or "No answer" in out


def test_impact_live_only(mcp_server):
    """live_only must not crash and must produce a valid impact result or a clean
    'nothing live' message."""
    name = _real_node_name(mcp_server)
    out = mcp_server.impact(name, live_only=True)
    # Since glia 0.5.1 a radius that is all dead comes back as the engine's own
    # absence ("none reachable from an entry point (live_only)").
    assert ("Impact (" in out or "nodes found" in out
            or ("No answer (" in out and "live_only" in out))


def test_impact_rows_are_never_nameless(mcp_server):
    """glia 0.5.4 leaves `name` out of a cut answer's row when it repeats the
    qname tail. The wrapper falls back to that tail, never prints `?`."""
    name = _real_node_name(mcp_server)
    out = mcp_server.impact(name)
    if "Impact (" not in out:
        pytest.skip("fixture node has no blast radius")
    rows = [l for l in out.splitlines() if l.startswith("    ") and "[" in l]
    assert rows and not any(" ? [" in l or l.strip().startswith("? ") for l in rows)


def _fake_impact(monkeypatch, env, calls=None):
    from types import SimpleNamespace
    from repo_graph import server

    def blast(*a, **k):
        if calls is not None:
            calls.append((a, k))
        return env
    g = SimpleNamespace(nodes={}, pygraph=SimpleNamespace(blast_radius=blast))
    monkeypatch.setattr(server, "get_graph", lambda: g)
    return server


_CUT_ENV = {
    "seeds": [{"qname": "engine::answers::blast_radius"}],
    "results": [
        {"qname": "engine::answers::BlastOptions::default", "kind": "METHOD", "reason": "CALLS",
         "depth": 2, "score": 0.02475, "live": True, "file": "engine/src/answers.rs",
         "line": 1118, "seed_index": 0},
        {"qname": "py::blast::PyGraph::blast", "name": "blast_radius_py", "kind": "METHOD",
         "reason": "CALLS", "depth": 1, "score": 0.0211, "live": False, "file": "py/src/blast.rs",
         "line": 9, "seed_index": 0},
    ],
    "files": [{"rank": 1, "file": "core/src/lib.rs", "ppr": 0.003, "rows": 0},
              {"rank": 2, "file": "graph/src/blast.rs", "cochange": 0.4, "rows": 3}],
    "areas": [{"area": "glia-engine", "rows": 3447, "files": 300,
               "top_file": "engine/src/answers.rs", "scope": "glia-engine"},
              {"area": "glia-py", "rows": 279, "files": 50, "top_file": "py/src/blast.rs",
               "scope": "py"}],
    "selection": {"set": "SELh0", "shape": "k1", "pick": "H10", "source": "fallback",
                  "reason": "absent", "test_commits": 0},
    "truncated": {"results": 6723, "seeds": 0, "areas": 32,
                  "next": {"scope": "glia-engine", "offset": 25}},
    "blind": [{"tier": "fact", "mechanism": "http", "verdict": "DEGRADED",
               "reason": "clients_unpaired", "measure": "clients paired 7% of 14"}],
}


def test_impact_renders_the_overview_answer(monkeypatch):
    """glia 0.5.4's compact blast radius: slim rows, then where the rest went,
    the likely files, the ranking used, and what the graph is blind to."""
    server = _fake_impact(monkeypatch, _CUT_ENV)
    out = server.impact("blast_radius")
    assert "default  [method]" in out  # name left out → qname tail
    assert "blast_radius_py  [method]" in out  # name given → kept
    assert "rows 1-2 of 6723 in blast radius" in out
    assert "next page: scope=glia-engine offset=25" in out
    assert "glia-engine: 3447 rows in 300 files, most in engine/src/answers.rs" in out
    assert "    py: 279 rows" in out  # the area's `scope`, the value to pass back
    assert "likely files: core/src/lib.rs, graph/src/blast.rs (co-change)" in out
    assert "ranked by H10 (fallback: absent)" in out
    assert "⚠ DEGRADED on http: clients paired 7% of 14" in out


def test_impact_passes_page_scope_and_full_through(monkeypatch):
    """`top_k` 0 is the engine's overview (None), `scope` / `offset` page it, and
    `full` drops both, since the engine refuses `full` with `top_k` / `offset`."""
    calls = []
    server = _fake_impact(monkeypatch, {"results": [], "seeds": []}, calls)
    server.impact("x")
    server.impact("x", top_k=10, scope="py", offset=25)
    server.impact("x", top_k=10, offset=25, full=True)
    (a0, k0), (a1, k1), (a2, k2) = calls
    assert a0[3] is None and a0[5] is None and k0 == {"full": False, "offset": 0}
    assert a1[3] == 10 and a1[5] == "py" and k1 == {"full": False, "offset": 25}
    assert a2[3] is None and k2 == {"full": True, "offset": 0}


def test_impact_full_answer_has_no_overview_footer(monkeypatch):
    """A full answer (glia 0.5.4 `full=True`) carries no `truncated` / `areas`."""
    env = {k: v for k, v in _CUT_ENV.items() if k not in ("truncated", "areas", "blind")}
    server = _fake_impact(monkeypatch, env)
    out = server.impact("blast_radius", full=True, top_k=1)
    assert "-- 1 nodes in blast radius" in out
    assert "next page" not in out and "areas" not in out


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
    assert "No answer" in out or "Trace:" in out or "Flow:" in out


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
    names = mcp_server._CELL_TYPE_NAMES
    surfaced = set(mcp_server._READ_CELL_LABELS)
    target = None
    for n in g.nodes.values():
        try:
            cells = g.pygraph.node_cells(n["id"])
        except Exception:
            continue
        # An empty payload (e.g. `imports: []`) renders to nothing on purpose,
        # so only a cell with real content guarantees a footer.
        if any(tid in surfaced and mcp_server._cell_text(names.get(tid, ""), c)
               for tid, c in cells):
            target = n
            break
    if target is None:
        pytest.skip("fixture has no nodes with surfaced context cells")
    out = mcp_server.read(target["qname"])
    assert "context:" in out


def _footer_for(server, *payloads, cell="ENDPOINT_HIT"):
    """`_node_context` over a node whose only cells are these payloads."""
    from types import SimpleNamespace
    tid = next(t for t, n in server._CELL_TYPE_NAMES.items() if n == cell)
    g = SimpleNamespace(pygraph=SimpleNamespace(
        node_cells=lambda _id: [(tid, p) for p in payloads]))
    return server._node_context(g, 0)


def test_read_client_endpoint_hit_is_a_dial_target():
    """glia 0.5.1: a WS / gRPC / GraphQL / tRPC client's ENDPOINT_HIT names the
    host it dials. Labelling that "called by (cross-stack)" names the dial
    target as a caller."""
    from repo_graph import server
    out = _footer_for(server, '{"via":"ws","host":"chat:8080"}')
    assert "dials: chat:8080 (ws)" in out
    assert "called by" not in out
    assert "dials: api.a, api.b (graphql)" in _footer_for(
        server, '{"via":"graphql","hosts":["api.a","api.b"]}')
    # quokka's gRPC clients name no literal host; one row however many sites.
    out = _footer_for(server, '{"via":"grpc"}', '{"via":"grpc"}')
    assert out.count("dials: host not named in source (grpc)") == 1


def test_blind_spot_footer_caps_each_note():
    """orient prints this footer every call; glia 0.5.1 notes run to ~1,000 chars."""
    from types import SimpleNamespace
    from repo_graph import server
    long_note = "repo markdown is ingested only from the well-known files " * 20
    g = SimpleNamespace(pygraph=SimpleNamespace(coverage=lambda: {"results": [
        {"language": "*", "edge_category": "DOCUMENTS", "edges_found": 3, "note": long_note},
        {"language": "*", "edge_category": "CALLS", "edges_found": 9, "note": "short one"},
    ]}))
    out = server._coverage_note(g)
    docs, calls = [l for l in out.splitlines() if "⚠" in l]
    assert docs.endswith(" …") and len(docs) < server._COVERAGE_NOTE_CAP + 40
    assert calls.endswith(": short one")


def test_read_http_endpoint_hit_keeps_caller_label():
    from repo_graph import server
    out = _footer_for(server, '{"method":"GET","path":"/api/x","file":"web/a.ts",'
                              '"line":3,"col":5,"confidence":"strong","external":true}')
    assert "called by (cross-stack): method=GET path=/api/x file=web/a.ts" in out
    assert "dials" not in out


def test_read_graphql_transport_is_an_http_call_site():
    """glia 0.5.2: an Apollo / urql client's POST /graphql is an HTTP call site
    that also carries `via`. It has a caller, not a dial target."""
    from repo_graph import server
    out = _footer_for(server, '{"method":"POST","path":"/graphql","file":"admin/src/client.ts",'
                              '"line":4,"col":8,"confidence":"strong",'
                              '"host":"localhost:8080","via":"graphql"}')
    assert "called by (cross-stack): method=POST path=/graphql" in out
    assert "dials" not in out


def test_read_external_dial_target_says_so():
    """glia 0.5.2 marks a client whose every host is public and unconfigured."""
    from repo_graph import server
    out = _footer_for(server, '{"via":"ws","host":"stream.binance.com","external":true}')
    assert "dials: stream.binance.com (ws, external)" in out


def test_read_evm_client_names_library_and_abi():
    """glia 0.5.2 EVM clients name no host: the library and ABI are the target."""
    from repo_graph import server
    out = _footer_for(server, '{"via":"evm","lib":"ethers","args":[1],'
                              '"abi_ref":{"name":"SHOP_ABI","from":"./abi"},"abi_from":"src/abi.ts"}')
    assert "dials: contract via ethers, ABI SHOP_ABI from src/abi.ts (evm)" in out
    assert "host not named" not in out
    assert "dials: contract via geth (evm)" in _footer_for(
        server, '{"via":"evm","lib":"geth","args":[1]}')


def test_read_model_fields_render_as_name_type():
    """glia 0.5.2 SCHEMA_FIELDS: `name: type`, `?` on an optional field."""
    from repo_graph import server
    out = _footer_for(server, '{"fields":[{"name":"id","required":true,"type":"string"},'
                              '{"name":"joinedAt","required":false,"type":"string"}],'
                              '"format":"ts"}', cell="SCHEMA_FIELDS")
    assert "fields: id: string, joinedAt?: string (ts)" in out
    out = _footer_for(server, '{"extends":["Base"],"fields":[{"name":"n","type":"int"}],'
                              '"format":"go"}', cell="SCHEMA_FIELDS")
    assert "fields: extends Base; n: int (go)" in out
    out = _footer_for(server, '{"extends":"Base","fields":[]}', cell="SCHEMA_FIELDS")
    assert "fields: extends Base\n" in out + "\n"


def test_read_main_guard_is_not_a_declared_entry():
    """glia 0.5.2 reads an entry off a `__main__` guard; nobody declared it."""
    from repo_graph import server
    out = _footer_for(server, '{"decl":"scripts/tool.py:12","source":"main_guard"}',
                      cell="ENTRYPOINT")
    assert "· entry point: scripts/tool.py:12 (__main__ guard)" in out
    assert "declared" not in out
    declared = _footer_for(server, '{"decl":"cmd/run.go:3","source":"overlay"}',
                           cell="ENTRYPOINT")
    assert "declared entry point: cmd/run.go:3 overlay" in declared


def test_read_entries_glia_reads_off_the_code(monkeypatch):
    """glia 0.5.6: a TS / JS guard writes `main_guard` too, scripts are entries
    by `shebang` / `script_arg`, and `host:<h>` names what starts the code."""
    from repo_graph import server
    cases = {
        '{"decl":"scripts/gen.ts:40","source":"main_guard"}':
            "· entry point: scripts/gen.ts:40 (main guard)",
        '{"decl":"bin/tool.lua:1","source":"shebang"}':
            "· entry point: bin/tool.lua:1 (#! script)",
        '{"decl":"run.lua:1","source":"script_arg"}':
            "· entry point: run.lua:1 (script)",
        '{"decl":"api/main.py:1","source":"host:compose","host":"infra:service:api",'
        '"trigger":"container_start"}':
            "· entry point: api/main.py:1 (started by compose on container start via infra:service:api)",
        '{"decl":"src/extension.ts:5","source":"host:vscode"}':
            "· entry point: src/extension.ts:5 (started by vscode)",
    }
    for payload, want in cases.items():
        out = _footer_for(server, payload, cell="ENTRYPOINT")
        assert want in out, (payload, out)
        assert "declared" not in out and "__main__" not in out


def test_trace_says_when_the_graph_is_blind():
    """glia 0.5.4 puts `blind` on a trace answer when a mechanism is BLIND /
    DEGRADED: the trace may be missing hops through it."""
    from repo_graph import server
    env = {"paths": [], "blind": [{"mechanism": "grpc", "verdict": "BLIND",
                                   "reason": "no_servers", "measure": "0 servers"}]}
    out = server._render_trace("checkout", env, [])
    assert "⚠ BLIND on grpc: 0 servers" in out


def test_identity_note_counts_members_a_capped_answer_cut():
    """glia 0.5.4 cuts `also_in` to 3 in a capped answer and counts the rest."""
    from repo_graph import server
    ident = dict(_IDENTITY, also_in=_IDENTITY["also_in"][:2], also_in_count=7)
    assert "+5 more" in server._identity_note(ident, "")


_IDENTITY = {"tier": "derived", "rules": ["http_model"], "diverged": True, "also_in": [
    {"repo": "shop", "qname": "web::models::Order", "file": "web/models.ts", "line": 60},
    {"repo": "shop", "qname": "api::models::Order", "file": "api/models.go", "line": 20},
]}


def test_identity_note_lists_folded_members():
    """glia 0.5.2 folds a client model and its server struct into one row; the
    others ride in `identity.also_in`. One repo, so no repo label."""
    from repo_graph import server
    note = server._identity_note(_IDENTITY, "  ")
    assert note == "\n  ≡ also in: web/models.ts:60; api/models.go:20  (http_model, diverged)"
    assert server._identity_note(None, "  ") == ""
    assert server._identity_note({"also_in": []}, "  ") == ""


def test_identity_note_labels_repos_when_they_differ():
    from repo_graph import server
    ident = {"rules": ["package_name"], "also_in": [
        {"repo": "web", "qname": "pkg:left-pad"},
        {"repo": "api", "qname": "pkg:left-pad", "file": "api/package.json", "line": 3},
    ]}
    note = server._identity_note(ident, "")
    assert "web: pkg:left-pad; api: api/package.json:3  (package_name)" in note


def test_folded_rows_render_in_find_impact_and_trace(monkeypatch):
    """find / impact rows carry `identity`, a trace hop `to_identity`."""
    from types import SimpleNamespace
    from repo_graph import server
    row = {"id": 1, "qname": "app::models::Order", "name": "Order", "kind": "CLASS",
           "file": "app/models.dart", "line": 5, "live": True, "identity": _IDENTITY}
    g = SimpleNamespace(
        nodes={},
        find_records=lambda q, k: ([row], None),
        pygraph=SimpleNamespace(
            blast_radius=lambda *a, **k: {"results": [dict(row, reason="CALLS", depth=1)],
                                     "seeds": [{"qname": "x"}], "unresolved": []}))
    monkeypatch.setattr(server, "get_graph", lambda: g)
    also = "≡ also in: web/models.ts:60; api/models.go:20"
    assert also in server.find("Order")
    assert also in server.impact("x")
    hop = server._render_hop({"mechanism": "CALLS", "from_qname": "a", "to_qname": "b",
                              "to_kind": "CLASS", "to_identity": _IDENTITY})
    assert also in hop


# ── Smoke: confirm exactly the 6 tools are registered ───────────────────────


def test_six_tools_decorated():
    """Lock the public surface — checked against the actual MCP tool registry, so
    it catches both removed and added tools. If a tool changes, update server.py,
    installer/constants.py TOOL_NAMES, and the CLAUDE.md tool list in lockstep."""
    from repo_graph import server

    expected = {"orient", "find", "impact", "trace", "read", "refresh"}
    actual = set(server.mcp._tool_manager._tools.keys())
    assert actual == expected, f"tool surface drifted: missing={expected - actual}, extra={actual - expected}"
