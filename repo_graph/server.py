"""
repo-graph MCP server.

Structural navigation, context budgeting, and codebase health tools.
Powered by the Rust repo-graph engine via PyO3 bindings.

Usage:
    repo-graph --repo /path/to/your/repo
"""

import os
from collections import Counter
from typing import Annotated

from pydantic import Field
from mcp.server.fastmcp import FastMCP

import repo_graph_py

from .graph import RustGraph

REPO_PATH = os.environ.get("REPO_GRAPH_REPO", os.getcwd())

mcp = FastMCP(
    "repo-graph",
    instructions=(
        "Structural map of this codebase — entities, relationships, and feature flows. "
        "BEFORE grepping or reading files, call `status` to orient, then use `dense_text` "
        "for full graph context or `activate` to find relevant nodes from seeds. "
        "Use for: finding feature flows, tracing paths between components, impact analysis, "
        "context cost estimation. Works with any language/framework."
    ),
)

_graph: RustGraph | None = None


def get_graph() -> RustGraph:
    global _graph
    if _graph is None:
        pg = repo_graph_py.generate(REPO_PATH)
        _graph = RustGraph(pg, REPO_PATH)
    return _graph


# ─────────────────────────────────────────────────────────────────────────────
# Tier 0 — Generation
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def generate(
    repo_path: Annotated[str, Field(description="Absolute path to the repository to scan. Defaults to the repo the server was started with.", default="")] = "",
) -> str:
    """Scan the codebase and (re)build the structural graph using tree-sitter AST parsing. Auto-detects 20 languages and frameworks. Runs cross-stack resolvers (HTTP, gRPC, GraphQL, WebSocket, queues, events, CLI). Call on first use or after major refactors."""
    target = repo_path or REPO_PATH

    try:
        pg = repo_graph_py.generate(target)
    except Exception as e:
        return f"Generation failed: {e}"

    global _graph
    _graph = RustGraph(pg, target)

    kind_counts: dict[str, int] = Counter(n["kind"] for n in _graph.nodes.values())
    type_summary = ", ".join(f"{count} {k}" for k, count in kind_counts.most_common())

    return (
        f"Generated: {pg.node_count()} nodes, {pg.edge_count()} edges, "
        f"{pg.cross_edge_count()} cross-stack edges\n"
        f"Kinds: {type_summary}\n"
        f"Flows: {len(_graph.flows)} auto-detected entry points\n"
        f"Engine: repo-graph-py {repo_graph_py.version()} (Rust + tree-sitter)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tier 1 — Navigation
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def status() -> str:
    """Repo overview: node/edge counts, detected kinds, entry points, and a dense text preview. Call this first to orient before using other tools."""
    g = get_graph()
    return _render_overview(g)


@mcp.tool()
def dense_text() -> str:
    """Full structural graph in dense sigil notation — the complete map of entities, relationships, and scopes. This is the primary context tool: feed it to the LLM so it can navigate without reading files."""
    g = get_graph()
    return g.pygraph.dense_text()


@mcp.tool()
def flow(
    feature: Annotated[str, Field(description="Feature name or keyword to match against entry points. Case-insensitive, supports partial matching.")],
) -> str:
    """End-to-end flow for a feature: entry point through service layer to data store, rendered as layered tiers. Call after `status` to drill into a specific feature."""
    g = get_graph()
    feature_lower = feature.lower().strip()

    flow_nodes = g.nodes_for_feature(feature_lower)
    if not flow_nodes:
        available = ", ".join(sorted(g.flows.keys())[:30])
        return f"No flow found for '{feature}'. Available entry points: {available}"

    return _render_nodes_layered(feature, flow_nodes[:30], g)


@mcp.tool()
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


@mcp.tool()
def impact(
    node: Annotated[str, Field(description="Node name or qname pattern to analyze.")],
    direction: Annotated[str, Field(description="'downstream' or 'upstream'.", default="downstream")] = "downstream",
    depth: Annotated[int, Field(description="How many hops to traverse. Default 3.", default=3, ge=1, le=10)] = 3,
) -> str:
    """Blast radius analysis: fan out from a node to see everything it affects (downstream) or depends on (upstream), grouped by tier."""
    g = get_graph()
    resolved = g.find_node(node)
    if not resolved:
        return f"Node not found: '{node}'"

    if direction == "upstream":
        results = g.upstream(resolved["id"], depth)
    else:
        results = g.downstream(resolved["id"], depth)

    if not results:
        return f"No {direction} nodes found from {resolved['name']} (depth={depth})"

    r_icon = _kind_icon(resolved["kind"])
    lines = [
        f"  Impact {direction} from {resolved['name']} (depth={depth})",
        f"  {r_icon} {resolved['name']}  [{resolved['kind']}]",
        "",
    ]

    by_tier: dict[str, list[dict]] = {}
    for r in results:
        tier = _classify_tier(r["kind"])
        by_tier.setdefault(tier, []).append(r)

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
    lines.append(f"  -- {len(results)} nodes affected")

    return "\n".join(lines)


@mcp.tool()
def neighbours(
    node: Annotated[str, Field(description="Node name or qname pattern to inspect.")],
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

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Tier 2 — Activation & Context
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def activate(
    seeds: Annotated[str, Field(description="Comma-separated node names or qname patterns to seed activation from.")],
    top_k: Annotated[int, Field(description="Number of top results to return. Default 20.", default=20, ge=1, le=100)] = 20,
) -> str:
    """Spreading activation from seed nodes — finds the most relevant nodes in the graph relative to your seeds. Uses Personalized PageRank with domain-tuned edge weights. Returns ranked results by relevance score."""
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

    scores = g.pygraph.activate(seed_ids, top_k)

    lines = [
        f"  Activation from: {', '.join(seed_names)}",
        f"  Top {len(scores)} results:",
        "",
    ]

    for nid, score in scores:
        node = g.nodes.get(nid)
        if not node:
            continue
        icon = _kind_icon(node["kind"])
        conf = _confidence_icon(node.get("confidence", "medium"))
        lines.append(f"    {score:.4f}  {icon} {conf} {node['name']}  [{node['kind']}]  {node['qname']}")

    return "\n".join(lines)


@mcp.tool()
def find(
    query: Annotated[str, Field(description="Node name or qname pattern to search for. Supports partial matching.")],
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

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Tier 3 — Health & Admin
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def graph_view(
    node: Annotated[str, Field(description="Node name or qname to render as a tree. Leave blank for full overview.", default="")] = "",
    depth: Annotated[int, Field(description="Tree depth. Default 2.", default=2, ge=1, le=5)] = 2,
) -> str:
    """Visual ASCII graph. With node: tree of children and connections. Without: full overview with counts."""
    g = get_graph()

    if node:
        return _render_node_tree(g, node, depth)
    return _render_overview(g)


@mcp.tool()
def reload() -> str:
    """Re-generate the graph from source. Call after code changes."""
    global _graph
    _graph = None
    g = get_graph()
    return (
        f"Reloaded: {g.pygraph.node_count()} nodes, {g.pygraph.edge_count()} edges, "
        f"{g.pygraph.cross_edge_count()} cross-stack, {len(g.flows)} flows"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Rendering helpers
# ─────────────────────────────────────────────────────────────────────────────

_ENTRY_KINDS = {"route", "grpc_service", "queue_consumer", "graphql_resolver",
                "ws_handler", "event_handler", "cli_command"}
_SERVICE_KINDS = {"module", "package"}
_HANDLER_KINDS = {"function", "method", "class", "struct", "interface", "enum"}
_DATA_KINDS = {"endpoint", "grpc_client", "queue_producer", "graphql_operation",
               "ws_client", "event_emitter", "cli_invocation"}


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
        help="Path to the target repository",
    )
    args = parser.parse_args()

    global REPO_PATH
    REPO_PATH = args.repo
    os.environ["REPO_GRAPH_REPO"] = args.repo
    mcp.run()


if __name__ == "__main__":
    main()
