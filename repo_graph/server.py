"""
repo-graph MCP server.

Structural navigation, context budgeting, and codebase health tools.
Powered by the Rust repo-graph engine via PyO3 bindings.

Usage:
    repo-graph --repo /path/to/your/repo
"""

import os
import re
import sys
import shutil
import hashlib
import tempfile
import subprocess
from collections import Counter
from typing import Annotated

from pydantic import Field
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

import repo_graph_py

from .graph import RustGraph

REPO_PATH = os.environ.get("REPO_GRAPH_REPO", os.getcwd())

mcp = FastMCP(
    "repo-graph",
    instructions=(
        "Structural map of this codebase — entities, relationships, and feature flows. "
        "BEFORE grepping or reading files, call `status` to orient, then `dense_text` for "
        "full graph context or `activate`/`find` to surface relevant nodes. "
        "Debugging an error? Paste the stacktrace, failing-test id, or diff into `locate` to "
        "jump straight to the code that matters, then `read` to pull a node's exact source. "
        "Also: feature flows (`flow`), shortest paths (`trace`), and blast radius before a "
        "change (`impact`). Works with any language/framework."
    ),
)

_graph: RustGraph | None = None


_GIT_URL_RE = re.compile(r"^(https?://|git@|ssh://|git\+)", re.IGNORECASE)


def _looks_like_git_url(spec: str) -> bool:
    """True if `spec` is a git remote URL rather than a local path."""
    return bool(_GIT_URL_RE.match(spec)) or spec.endswith(".git")


def _resolve_repo(spec: str) -> str:
    """Resolve a ``--repo`` / ``REPO_GRAPH_REPO`` value to a local directory.

    A local path is returned unchanged. A git URL is shallow-cloned once (cached
    under the temp dir, keyed by URL) and the checkout path is returned — so
    ``--repo https://github.com/org/repo`` works locally, and the hosted deploy
    (``REPO_GRAPH_REPO`` set to a git URL) maps a real repo with no manual clone.
    Requires ``git`` on PATH.
    """
    if not _looks_like_git_url(spec):
        return spec
    url = spec[4:] if spec.lower().startswith("git+") else spec
    cache_root = os.path.join(tempfile.gettempdir(), "repo-graph-clones")
    os.makedirs(cache_root, exist_ok=True)
    dest = os.path.join(cache_root, hashlib.sha256(spec.encode()).hexdigest()[:16])
    if os.path.isdir(dest) and os.listdir(dest):
        return dest  # reuse cached clone
    print(f"repo-graph: cloning {url} ...", file=sys.stderr)
    res = subprocess.run(
        ["git", "clone", "--depth", "1", url, dest],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        shutil.rmtree(dest, ignore_errors=True)
        raise RuntimeError(f"git clone failed for {url}: {res.stderr.strip()[:300]}")
    return dest


def _build_graph(target: str, incremental: bool = True) -> RustGraph:
    """Generate `target`'s graph, persist the `.gmap` cache, install it as live.

    `incremental` (default True, repo-graph-py >= 0.4.16) reuses the per-file
    parse cache at `<repo>/.ai/repo-graph/parse_cache.bin` so unchanged files
    skip tree-sitter re-parsing; `incremental=False` forces a full reparse.
    Shared by `get_graph` (cold regen), `generate`, and `reload`.
    """
    global _graph, REPO_PATH
    pg = repo_graph_py.generate(target, incremental=incremental)
    if hasattr(pg, "save_to_default"):
        try:
            pg.save_to_default(target)
        except Exception:
            # Best-effort: read-only fs / perms shouldn't break the live graph.
            pass
    REPO_PATH = target
    _graph = RustGraph(pg, target)
    return _graph


def get_graph() -> RustGraph:
    """Return the in-memory graph, lazy-loading on first access.

    Load order: cached `.gmap` if fresh → incremental `generate()` otherwise
    (reusing the parse cache so the regen is cheap). The cache-load path uses the
    `default_gmap_dir` convention introduced in repo-graph-py 0.4.14.
    """
    global _graph, REPO_PATH
    if _graph is not None:
        return _graph

    REPO_PATH = _resolve_repo(REPO_PATH)

    if hasattr(repo_graph_py, "load_from_gmap") and hasattr(repo_graph_py, "is_stale"):
        gmap_dir = repo_graph_py.default_gmap_dir(REPO_PATH)
        if not repo_graph_py.is_stale(gmap_dir, REPO_PATH):
            try:
                pg = repo_graph_py.load_from_gmap(gmap_dir)
                _graph = RustGraph(pg, REPO_PATH)
                return _graph
            except Exception:
                # Stale or unreadable cache — fall through to fresh generate.
                pass

    return _build_graph(REPO_PATH)


def _truncate(text: str, budget: int, what: str = "output") -> str:
    """Cap `text` at `budget` chars (line-aligned) with a marker. budget <= 0 = no cap.

    The shared char ceiling for the read tools so a result fits a small-model
    context window. Per-tool item caps still apply as sane defaults; this is the
    optional hard limit on top.
    """
    if budget <= 0 or len(text) <= budget:
        return text
    cut = text.rfind("\n", 0, budget)
    if cut <= 0:
        cut = budget
    return (
        text[:cut]
        + f"\n\n[... {what} truncated: {len(text) - cut} of {len(text)} chars omitted "
          f"to fit budget={budget}. Narrow the query or raise budget.]"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tier 0 — Generation
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool(annotations=ToolAnnotations(title="Generate Graph", readOnlyHint=False, openWorldHint=True))
def generate(
    repo_path: Annotated[str, Field(description="Absolute path to the repository to scan. Defaults to the repo the server was started with.", default="")] = "",
    incremental: Annotated[bool, Field(description="Reuse the per-file parse cache so unchanged files skip re-parsing (default True). Set False to force a full reparse.", default=True)] = True,
) -> str:
    """Scan the codebase and (re)build the structural graph using tree-sitter AST parsing. Auto-detects 20 languages and frameworks. Runs cross-stack resolvers (HTTP, gRPC, GraphQL, WebSocket, queues, events, CLI). Incremental by default — reuses a per-file parse cache so only changed files re-parse. Accepts a local path or a git URL (cloned on demand). Call on first use or after major refactors."""
    try:
        # Resolve a git URL (e.g. https://github.com/org/repo.git) to a local
        # clone before handing it to the engine, which only takes a directory.
        target = _resolve_repo(repo_path or REPO_PATH)
        g = _build_graph(target, incremental)
    except Exception as e:
        return f"Generation failed: {e}"

    pg = g.pygraph
    kind_counts: dict[str, int] = Counter(n["kind"] for n in g.nodes.values())
    type_summary = ", ".join(f"{count} {k}" for k, count in kind_counts.most_common())

    return (
        f"Generated: {pg.node_count()} nodes, {pg.edge_count()} edges, "
        f"{pg.cross_edge_count()} cross-stack edges\n"
        f"Kinds: {type_summary}\n"
        f"Flows: {len(g.flows)} auto-detected entry points\n"
        f"Engine: repo-graph-py {repo_graph_py.version()} (Rust + tree-sitter)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tier 1 — Navigation
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool(annotations=ToolAnnotations(title="Repo Status", readOnlyHint=True))
def status() -> str:
    """Repo overview: node/edge counts, detected kinds, entry points, and a dense text preview. Call this first to orient before using other tools."""
    g = get_graph()
    return _render_overview(g)


# Cap dense_text so a large monorepo's full dump can't blow past MCP-client
# tool-result limits (e.g. Claude Desktop's 25k tokens). Default ~50k chars stays
# well under it; override with REPO_GRAPH_DENSE_MAX_CHARS (0 = uncapped) for clients
# with bigger context budgets.
try:
    DENSE_TEXT_MAX_CHARS = int(os.environ.get("REPO_GRAPH_DENSE_MAX_CHARS", "50000"))
except ValueError:
    DENSE_TEXT_MAX_CHARS = 50_000


@mcp.tool(annotations=ToolAnnotations(title="Dense Graph Text", readOnlyHint=True))
def dense_text(
    seed: Annotated[str, Field(description="Optional node/qname to scope the map around (its activated neighbourhood). Blank = whole graph.", default="")] = "",
    budget: Annotated[int, Field(description="Max chars in the result. 0 = default cap (~50k, or REPO_GRAPH_DENSE_MAX_CHARS).", default=0, ge=0)] = 0,
) -> str:
    """Structural graph in dense sigil notation — the map of entities, relationships, and scopes. The primary context tool: feed it to the LLM so it can navigate without reading files. With `seed`, returns just that node's activated neighbourhood (scoped map) instead of the whole graph; otherwise the full map, truncated to budget."""
    g = get_graph()

    if seed:
        resolved = g.find_node(seed)
        if not resolved:
            return f"Seed node not found: '{seed}'"
        scores = g.pygraph.activate([resolved["id"]], 50)
        node_ids = [nid for nid, _ in scores] or [resolved["id"]]
        text = g.pygraph.dense_text_subset(node_ids)
        cap = budget  # scoped output is already small; honour explicit budget only
    else:
        text = g.pygraph.dense_text()
        cap = budget or DENSE_TEXT_MAX_CHARS

    what = "scoped dense_text" if seed else "dense_text"
    return _truncate(text, cap, what)


@mcp.tool(annotations=ToolAnnotations(title="Feature Flow", readOnlyHint=True))
def flow(
    feature: Annotated[str, Field(description="Feature name or keyword to match against entry points. Case-insensitive, supports partial matching.")],
    budget: Annotated[int, Field(description="Max chars in the result. 0 = no cap.", default=0, ge=0)] = 0,
) -> str:
    """End-to-end flow for a feature: entry point through service layer to data store, rendered as layered tiers. Call after `status` to drill into a specific feature."""
    g = get_graph()
    feature_lower = feature.lower().strip()

    flow_nodes = g.nodes_for_feature(feature_lower)
    if not flow_nodes:
        available = ", ".join(sorted(g.flows.keys())[:30])
        return f"No flow found for '{feature}'. Available entry points: {available}"

    return _truncate(_render_nodes_layered(feature, flow_nodes[:30], g), budget, "flow")


@mcp.tool(annotations=ToolAnnotations(title="Trace Path", readOnlyHint=True))
def trace(
    from_node: Annotated[str, Field(description="Starting node name or qname pattern.")],
    to_node: Annotated[str, Field(description="Target node name or qname pattern.")],
) -> str:
    """Shortest path between two nodes, showing each hop with tier transitions."""
    g = get_graph()

    from_resolved = g.find_node(from_node)
    to_resolved = g.find_node(to_node)

    if not from_resolved:
        return f"Node not found: '{from_node}'"
    if not to_resolved:
        return f"Node not found: '{to_node}'"

    path = g.shortest_path(from_resolved["id"], to_resolved["id"])
    if path is None:
        return f"No path between {from_resolved['name']} and {to_resolved['name']}"

    lines = [f"  Trace: {from_resolved['name']} -> {to_resolved['name']} ({len(path)} hops)", ""]

    prev_tier = None
    for i, node in enumerate(path):
        icon = _kind_icon(node["kind"])
        tier = _classify_tier(node["kind"])
        conf = _confidence_icon(node.get("confidence", "medium"))

        if tier != prev_tier:
            if prev_tier is not None:
                lines.append("      |")
                lines.append("      v")
            lines.append(f"  [{tier}]")
            prev_tier = tier

        arrow = "  -> " if i > 0 else "     "
        lines.append(f"  {arrow}{icon} {conf} {node['name']}  [{node['kind']}]")

    return "\n".join(lines)


@mcp.tool(annotations=ToolAnnotations(title="Impact Analysis", readOnlyHint=True))
def impact(
    nodes: Annotated[str, Field(description="One or more node names/qnames, comma-separated. A diff touching N files is one call.")],
    direction: Annotated[str, Field(description="'downstream' (what it affects) or 'upstream' (what it depends on).", default="downstream")] = "downstream",
    depth: Annotated[int, Field(description="How many hops to traverse. Default 3.", default=3, ge=1, le=10)] = 3,
    mode: Annotated[str, Field(description="'table' (tiered list) or 'prose' (primed prose for LLM context).", default="table")] = "table",
    budget: Annotated[int, Field(description="Max chars in the result. 0 = no cap.", default=0, ge=0)] = 0,
) -> str:
    """Blast radius analysis: fan out from one or more nodes to see everything they affect (downstream) or depend on (upstream), grouped by tier. Pass several comma-separated nodes to assess a whole diff at once."""
    g = get_graph()

    seeds = []
    for s in nodes.split(","):
        s = s.strip()
        if not s:
            continue
        r = g.find_node(s)
        if r:
            seeds.append(r)
    if not seeds:
        return f"No nodes found for: '{nodes}'"

    # Union per-seed traversals; keep the closest depth per affected node and
    # drop the seeds themselves from the result set.
    seed_ids = {s["id"] for s in seeds}
    closest: dict[int, dict] = {}
    for s in seeds:
        results = g.upstream(s["id"], depth) if direction == "upstream" else g.downstream(s["id"], depth)
        for r in results:
            if r["id"] in seed_ids:
                continue
            prev = closest.get(r["id"])
            if prev is None or r.get("depth", 0) < prev.get("depth", 0):
                closest[r["id"]] = r
    affected = list(closest.values())

    seed_label = ", ".join(s["name"] for s in seeds)
    if not affected:
        return f"No {direction} nodes found from {seed_label} (depth={depth})"

    if mode == "prose":
        node_ids = list(seed_ids) + [r["id"] for r in affected]
        return _truncate(g.pygraph.prose(node_ids), budget, "impact prose")

    lines = [f"  Impact {direction} from {seed_label} (depth={depth})", ""]

    by_tier: dict[str, list[dict]] = {}
    for r in affected:
        by_tier.setdefault(_classify_tier(r["kind"]), []).append(r)

    for tier_name in ["ENTRY", "SERVICE", "HANDLER", "DATA"]:
        items = by_tier.get(tier_name, [])
        if not items:
            continue
        lines.append(f"  [{tier_name}] ({len(items)} affected)")
        for n in items[:15]:
            icon = _kind_icon(n["kind"])
            conf = _confidence_icon(n.get("confidence", "medium"))
            lines.append(f"    {icon} {conf} {n['name']}  [{n['kind']}]")
        if len(items) > 15:
            lines.append(f"    ... and {len(items) - 15} more")

    lines.append("")
    lines.append(f"  -- {len(affected)} nodes affected")

    return _truncate("\n".join(lines), budget, "impact")


@mcp.tool(annotations=ToolAnnotations(title="Node Neighbours", readOnlyHint=True))
def neighbours(
    node: Annotated[str, Field(description="Node name or qname pattern to inspect.")],
    budget: Annotated[int, Field(description="Max chars in the result. 0 = no cap.", default=0, ge=0)] = 0,
) -> str:
    """All direct connections to and from a node, one hop in each direction."""
    g = get_graph()
    resolved = g.find_node(node)
    if not resolved:
        return f"Node not found: '{node}'"

    n = g.neighbours(resolved["id"])
    r_icon = _kind_icon(resolved["kind"])
    lines = [
        f"  {r_icon} {resolved['name']}",
        f"  |   [{resolved['kind']}] {resolved['qname']}",
    ]

    if n["outbound"]:
        lines.append("  |")
        lines.append(f"  +-->> Outbound ({len(n['outbound'])}):")
        for entry in n["outbound"][:20]:
            nn = entry["node"]
            icon = _kind_icon(nn.get("kind", "?"))
            lines.append(f"  |     {icon} {nn.get('name', '?')} --({entry['edge']})")
        if len(n["outbound"]) > 20:
            lines.append(f"  |     ... and {len(n['outbound']) - 20} more")

    if n["inbound"]:
        lines.append("  |")
        lines.append(f"  +--<< Inbound ({len(n['inbound'])}):")
        for entry in n["inbound"][:20]:
            nn = entry["node"]
            icon = _kind_icon(nn.get("kind", "?"))
            lines.append(f"        {icon} {nn.get('name', '?')} --({entry['edge']})")
        if len(n["inbound"]) > 20:
            lines.append(f"        ... and {len(n['inbound']) - 20} more")

    if not n["outbound"] and not n["inbound"]:
        lines.append("  (isolated node -- no connections)")

    return _truncate("\n".join(lines), budget, "neighbours")


@mcp.tool(annotations=ToolAnnotations(title="Read Source", readOnlyHint=True))
def read(
    node: Annotated[str, Field(description="Node name or qname to read the source for.")],
    context_lines: Annotated[int, Field(description="Lines of padding above and below the node's span. Default 0.", default=0, ge=0, le=200)] = 0,
    budget: Annotated[int, Field(description="Max chars in the result. 0 = no cap.", default=0, ge=0)] = 0,
) -> str:
    """Return the source code for a node, sliced from its file by the graph's line span. Use after `locate`/`find`/`activate` to read the exact code without grepping. Returns a code block headed by the qname and `path:start-end`."""
    g = get_graph()
    resolved = g.find_node(node)
    if not resolved:
        return f"Node not found: '{node}'"

    path = resolved.get("path")
    start = resolved.get("start_line")
    end = resolved.get("end_line") or start
    if not path or not start:
        return f"{resolved['name']} has no source span (synthetic or cross-stack node) — nothing to read."

    file_path = g.repo_path / path
    if not file_path.is_file():
        return f"Source file not found on disk: {path}"
    try:
        src_lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return f"Could not read {path}: {e}"

    lo = max(1, start - context_lines)
    hi = min(len(src_lines), end + context_lines)
    snippet = "\n".join(src_lines[lo - 1:hi])

    header = (
        f"  {resolved['qname']}  [{resolved['kind']}]\n"
        f"  {path}:{start}-{end}\n"
    )
    return _truncate(f"{header}\n```\n{snippet}\n```", budget, "source")


# ─────────────────────────────────────────────────────────────────────────────
# Tier 2 — Activation & Context
# ─────────────────────────────────────────────────────────────────────────────


_PROFILES = {"default", "repair", "review", "onboard"}


@mcp.tool(annotations=ToolAnnotations(title="Spreading Activation", readOnlyHint=True))
def activate(
    seeds: Annotated[str, Field(description="Comma-separated node names or qname patterns to seed activation from.")],
    top_k: Annotated[int, Field(description="Number of top results to return. Default 20.", default=20, ge=1, le=100)] = 20,
    profile: Annotated[str, Field(description="Edge-weight preset: 'default', 'repair' (up-weights call/data), 'review', or 'onboard' (up-weights entry/module).", default="default")] = "default",
    mode: Annotated[str, Field(description="'table' (ranked list) or 'prose' (primed prose for LLM context).", default="table")] = "table",
    budget: Annotated[int, Field(description="Max chars in the result. 0 = no cap.", default=0, ge=0)] = 0,
) -> str:
    """Spreading activation from seed nodes — finds the most relevant nodes in the graph relative to your seeds. Uses Personalized PageRank with domain-tuned edge weights. `profile` retunes the weights for a task (repair/review/onboard). `mode=prose` returns the ranked subgraph as primed prose instead of a score table."""
    g = get_graph()

    seed_ids = []
    seed_names = []
    for s in seeds.split(","):
        s = s.strip()
        if not s:
            continue
        resolved = g.find_node(s)
        if resolved:
            seed_ids.append(resolved["id"])
            seed_names.append(resolved["name"])

    if not seed_ids:
        return f"No seed nodes found for: {seeds}"

    prof = profile if profile in _PROFILES and profile != "default" else None
    scores = g.pygraph.activate(seed_ids, top_k, profile=prof)

    if mode == "prose":
        node_ids = [nid for nid, _ in scores] or seed_ids
        return _truncate(g.pygraph.prose(node_ids), budget, "activation prose")

    header = f"  Activation from: {', '.join(seed_names)}"
    if prof:
        header += f"  (profile={profile})"
    lines = [header, f"  Top {len(scores)} results:", ""]

    for nid, score in scores:
        node = g.nodes.get(nid)
        if not node:
            continue
        icon = _kind_icon(node["kind"])
        conf = _confidence_icon(node.get("confidence", "medium"))
        lines.append(f"    {score:.4f}  {icon} {conf} {node['name']}  [{node['kind']}]  {node['qname']}")

    return _truncate("\n".join(lines), budget, "activation")


@mcp.tool(annotations=ToolAnnotations(title="Find Nodes", readOnlyHint=True))
def find(
    query: Annotated[str, Field(description="Node name or qname pattern to search for. Supports partial matching.")],
    budget: Annotated[int, Field(description="Max chars in the result. 0 = no cap.", default=0, ge=0)] = 0,
) -> str:
    """Find nodes by name or qualified name pattern. Returns matching nodes with their kinds and qnames."""
    g = get_graph()

    results = g.find_nodes(query)
    if not results:
        single = g.find_node(query)
        if single:
            results = [single]

    if not results:
        return f"No nodes found matching '{query}'"

    lines = [f"  Found {len(results)} nodes matching '{query}':", ""]
    for node in results[:30]:
        icon = _kind_icon(node["kind"])
        conf = _confidence_icon(node.get("confidence", "medium"))
        lines.append(f"    {icon} {conf} {node['name']}  [{node['kind']}]  {node['qname']}")

    if len(results) > 30:
        lines.append(f"    ... and {len(results) - 30} more")

    return _truncate("\n".join(lines), budget, "find")


@mcp.tool(annotations=ToolAnnotations(title="Locate", readOnlyHint=True))
def locate(
    signal: Annotated[str, Field(description="Raw stacktrace, failing-test id (path::test_name), or a unified diff / changed-file list.")],
    kind: Annotated[str, Field(description="'stacktrace', 'test', 'diff', or 'auto' (sniff the shape).", default="auto")] = "auto",
    top_k: Annotated[int, Field(description="Number of ranked nodes to return. Default 20.", default=20, ge=1, le=100)] = 20,
    mode: Annotated[str, Field(description="'table' (ranked list) or 'prose' (primed prose for LLM context).", default="table")] = "table",
    budget: Annotated[int, Field(description="Max chars in the result. 0 = no cap.", default=0, ge=0)] = 0,
) -> str:
    """Resolve a failure signal — a stacktrace, a failing-test id, or a diff/changed-file list — to the most relevant nodes in the graph. Sniffs the signal shape, maps frames/symbols/paths to seed nodes, then ranks the surrounding subgraph by Personalized PageRank. The on-ramp for debugging: paste the error, get the code that matters."""
    g = get_graph()
    try:
        seed_ids = g.pygraph.resolve_signal(signal, kind)
    except Exception as e:
        return f"Locate failed: {e}"

    if not seed_ids:
        return (
            f"No graph nodes resolved from the {kind} signal — none of its frames/"
            f"symbols/paths matched a node. Fall back to `find` or `activate` with a keyword."
        )

    scores = g.pygraph.activate(seed_ids, top_k)

    if mode == "prose":
        node_ids = [nid for nid, _ in scores] or seed_ids
        return _truncate(g.pygraph.prose(node_ids), budget, "locate prose")

    lines = [
        f"  Located from {kind} signal -> {len(seed_ids)} seed node(s)",
        f"  Top {len(scores)} relevant nodes:",
        "",
    ]
    for nid, score in scores:
        node = g.nodes.get(nid)
        if not node:
            continue
        icon = _kind_icon(node["kind"])
        conf = _confidence_icon(node.get("confidence", "medium"))
        loc = f"  {node['path']}:{node['start_line']}" if node.get("path") else ""
        lines.append(f"    {score:.4f}  {icon} {conf} {node['name']}  [{node['kind']}]{loc}")

    return _truncate("\n".join(lines), budget, "locate")


# ─────────────────────────────────────────────────────────────────────────────
# Tier 3 — Health & Admin
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool(annotations=ToolAnnotations(title="Graph View", readOnlyHint=True))
def graph_view(
    node: Annotated[str, Field(description="Node name or qname to render as a tree. Leave blank for full overview.", default="")] = "",
    depth: Annotated[int, Field(description="Tree depth. Default 2.", default=2, ge=1, le=5)] = 2,
) -> str:
    """Visual ASCII graph. With node: tree of children and connections. Without: full overview with counts."""
    g = get_graph()

    if node:
        return _render_node_tree(g, node, depth)
    return _render_overview(g)


@mcp.tool(annotations=ToolAnnotations(title="Reload Graph", readOnlyHint=False))
def reload(
    incremental: Annotated[bool, Field(description="Reuse the per-file parse cache so unchanged files skip re-parsing (default True). Set False to force a full reparse.", default=True)] = True,
) -> str:
    """Re-generate the graph from source. Incremental by default — only changed files re-parse, so this is cheap to call after edits. Set incremental=False to force a full reparse."""
    try:
        target = _resolve_repo(REPO_PATH)
        g = _build_graph(target, incremental)
    except Exception as e:
        return f"Reload failed: {e}"
    return (
        f"Reloaded: {g.pygraph.node_count()} nodes, {g.pygraph.edge_count()} edges, "
        f"{g.pygraph.cross_edge_count()} cross-stack, {len(g.flows)} flows"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Rendering helpers
# ─────────────────────────────────────────────────────────────────────────────

_ENTRY_KINDS = {"route", "grpc_service", "queue_consumer", "graphql_resolver",
                "ws_handler", "event_handler", "cli_command", "cron_job"}
_SERVICE_KINDS = {"module", "package"}
_HANDLER_KINDS = {"function", "method", "class", "struct", "interface", "enum",
                  "component", "hook", "service", "directive", "pipe", "guard",
                  "composable", "attribute"}
_DATA_KINDS = {"endpoint", "grpc_client", "queue_producer", "graphql_operation",
               "ws_client", "event_emitter", "cli_invocation",
               "database", "cache", "blob_store", "search_index", "email_service",
               "data_entity", "config_key", "infra_resource", "package_dep"}


def _classify_tier(kind: str) -> str:
    if kind in _ENTRY_KINDS:
        return "ENTRY"
    if kind in _SERVICE_KINDS:
        return "SERVICE"
    if kind in _DATA_KINDS:
        return "DATA"
    return "HANDLER"


def _kind_icon(kind: str) -> str:
    icons = {
        "module": "◇", "package": "◈", "function": "ƒ", "method": "ƒ",
        "class": "□", "struct": "□", "route": "⟁", "interface": "◊",
        "enum": "▣", "endpoint": "↗",
        "grpc_service": "⟁", "grpc_client": "↗",
        "queue_consumer": "⟁", "queue_producer": "↗",
        "graphql_resolver": "⟁", "graphql_operation": "↗",
        "ws_handler": "⟁", "ws_client": "↗",
        "event_handler": "⟁", "event_emitter": "↗",
        "cli_command": "⟁", "cli_invocation": "↗",
        "cron_job": "⏲",
        "database": "⊟", "cache": "⊠", "blob_store": "⬢",
        "search_index": "⊙", "email_service": "✉",
        "component": "⬡", "hook": "⤴", "service": "⚙",
        "directive": "▾", "pipe": "▸", "guard": "⛊", "composable": "◉",
        "attribute": "⌗",
        "data_entity": "⊞", "config_key": "⚿",
        "infra_resource": "☁", "package_dep": "⊕",
    }
    return icons.get(kind, "●")


def _confidence_icon(confidence: str) -> str:
    return {"weak": "⚠", "medium": "·", "strong": "●"}.get(confidence, "·")


def _render_overview(g: RustGraph) -> str:
    kind_counts = Counter(n["kind"] for n in g.nodes.values())
    conf_counts = Counter(n["confidence"] for n in g.nodes.values())

    lines = [
        "  repo-graph",
        "  " + "=" * 40,
        "",
        f"  {g.pygraph.node_count()} nodes, {g.pygraph.edge_count()} edges, "
        f"{g.pygraph.cross_edge_count()} cross-stack",
        f"  Engine: repo-graph-py {repo_graph_py.version()} (Rust + tree-sitter)",
        "",
        f"  Confidence: {conf_counts.get('strong', 0)} strong, "
        f"{conf_counts.get('medium', 0)} medium, {conf_counts.get('weak', 0)} weak",
        "",
        "  Node kinds:",
    ]

    for kind, count in kind_counts.most_common(15):
        bar = "█" * min(count // 5, 30) or "▏"
        icon = _kind_icon(kind)
        lines.append(f"    {count:>5} {bar:30s} {icon} {kind}")

    if g.flows:
        lines.append("")
        flow_list = sorted(g.flows.keys())
        lines.append(f"  Entry points ({len(flow_list)} flows):")
        for f in flow_list[:20]:
            entry = g.flows[f][0] if g.flows[f] else None
            if entry:
                icon = _kind_icon(entry["kind"])
                conf = _confidence_icon(entry.get("confidence", "medium"))
                lines.append(f"    {icon} {conf} {f}  [{entry['kind']}]")
        if len(flow_list) > 20:
            lines.append(f"    ... and {len(flow_list) - 20} more")

    dt = g.pygraph.dense_text()
    preview_lines = dt.split("\n")[:30]
    lines.append("")
    lines.append("  Dense text preview (first 30 lines):")
    for line in preview_lines:
        lines.append(f"    {line}")
    if len(dt.split("\n")) > 30:
        lines.append(f"    ... ({len(dt.split(chr(10)))} total lines — use `dense_text` for full output)")

    return "\n".join(lines)


def _render_nodes_layered(feature: str, nodes: list[dict], g: RustGraph) -> str:
    tiers: dict[str, list[dict]] = {
        "ENTRY": [], "SERVICE": [], "HANDLER": [], "DATA": [],
    }

    for node in nodes:
        tier = _classify_tier(node["kind"])
        tiers[tier].append(node)

    lines = [f"  Flow: {feature}", "  " + "=" * (len(feature) + 6), ""]

    tier_icons = {"ENTRY": ">>", "SERVICE": "<>", "HANDLER": "[]", "DATA": "()"}
    rendered_any = False

    for tier_name in ["ENTRY", "SERVICE", "HANDLER", "DATA"]:
        items = tiers[tier_name]
        if not items:
            continue

        if rendered_any:
            lines.append("      |")
            lines.append("      v")

        lines.append(f"  {tier_icons[tier_name]} {tier_name}")
        lines.append("  " + "-" * 40)

        for node in items[:10]:
            icon = _kind_icon(node["kind"])
            conf = _confidence_icon(node.get("confidence", "medium"))
            lines.append(f"    {icon} {conf} {node['name']}  [{node['kind']}]")
        if len(items) > 10:
            lines.append(f"    ... and {len(items) - 10} more")

        rendered_any = True

    lines.append("")
    lines.append(f"  -- {len(nodes)} nodes in flow")
    return "\n".join(lines)


def _render_node_tree(g: RustGraph, query: str, depth: int) -> str:
    resolved = g.find_node(query)
    if not resolved:
        return f"Node not found: '{query}'"

    node_id = resolved["id"]
    icon = _kind_icon(resolved["kind"])
    conf = _confidence_icon(resolved.get("confidence", "medium"))

    lines = [
        f"  {icon} {conf} {resolved['name']}",
        f"  |   [{resolved['kind']}] {resolved['qname']}",
    ]

    _CHILD_EDGES = {"defines", "self_method"}
    out_edges = g.adjacency_out.get(node_id, [])
    in_edges = g.adjacency_in.get(node_id, [])

    children = [(tid, et) for tid, et in out_edges if et in _CHILD_EDGES]
    connections = [(tid, et) for tid, et in out_edges if et not in _CHILD_EDGES]

    if children:
        lines.append("  |")
        lines.append("  +-- Children:")
        for target_id, edge_type in children[:20]:
            target = g.nodes.get(target_id, {"name": str(target_id), "kind": "?"})
            t_icon = _kind_icon(target.get("kind", "?"))
            lines.append(f"  |     {t_icon} {target['name']} [{target.get('kind', '?')}]")

            if depth > 1:
                sub_children = [(sid, se) for sid, se in g.adjacency_out.get(target_id, []) if se in _CHILD_EDGES]
                for sub_id, _ in sub_children[:5]:
                    sub = g.nodes.get(sub_id, {"name": str(sub_id), "kind": "?"})
                    sub_icon = _kind_icon(sub.get("kind", "?"))
                    lines.append(f"  |       {sub_icon} {sub['name']}")
                if len(sub_children) > 5:
                    lines.append(f"  |       ... +{len(sub_children) - 5}")

        if len(children) > 20:
            lines.append(f"  |     ... and {len(children) - 20} more")

    if connections:
        lines.append("  |")
        lines.append("  +-->> Connects to:")
        for target_id, edge_type in connections[:15]:
            target = g.nodes.get(target_id, {"name": str(target_id), "kind": "?"})
            t_icon = _kind_icon(target.get("kind", "?"))
            lines.append(f"  |     {t_icon} {target['name']} --({edge_type})")
        if len(connections) > 15:
            lines.append(f"  |     ... and {len(connections) - 15} more")

    if in_edges:
        lines.append("  |")
        lines.append("  +--<< Used by:")
        for source_id, edge_type in in_edges[:15]:
            source = g.nodes.get(source_id, {"name": str(source_id), "kind": "?"})
            s_icon = _kind_icon(source.get("kind", "?"))
            lines.append(f"        {s_icon} {source['name']} --({edge_type})")
        if len(in_edges) > 15:
            lines.append(f"        ... and {len(in_edges) - 15} more")

    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="repo-graph MCP server")
    parser.add_argument(
        "--repo",
        default=os.environ.get("REPO_GRAPH_REPO", os.getcwd()),
        help="Path to the target repository, or a git URL to clone and map",
    )
    args = parser.parse_args()

    global REPO_PATH
    # Resolve a git URL to a local clone once at startup, so every tool (generate,
    # status, reload, ...) sees a real directory — not just the lazy get_graph path.
    REPO_PATH = _resolve_repo(args.repo)
    os.environ["REPO_GRAPH_REPO"] = REPO_PATH
    mcp.run()


if __name__ == "__main__":
    main()
