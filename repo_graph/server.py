"""
repo-graph MCP server.

Structural navigation, context budgeting, and codebase health tools.
Reads from .ai/repo-graph/ in the target repository.

Usage:
    repo-graph --repo /path/to/your/repo
"""

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .graph import RepoGraph
from .analyzer import (
    analyze_go_file,
    analyze_ts_component,
    analyze_scss_file,
    suggest_splits,
)

REPO_PATH = os.environ.get("REPO_GRAPH_REPO", os.getcwd())

mcp = FastMCP(
    "repo-graph",
    instructions=(
        "Codebase structural navigation, context budgeting, and health analysis. "
        "Use for: finding feature flows, impact analysis, context cost estimation, "
        "file hotspots, and split planning. Complements semantic search tools."
    ),
)

_graph: RepoGraph | None = None


def get_graph() -> RepoGraph:
    global _graph
    if _graph is None:
        _graph = RepoGraph(REPO_PATH)
    return _graph


# ─────────────────────────────────────────────────────────────────────────────
# Tier 1 — Navigation
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def status() -> str:
    """Repo overview: git state, feature coverage, available flows. Cheap orientation."""
    g = get_graph()
    state_path = g.graph_dir / "state.md"
    if state_path.exists():
        return state_path.read_text()
    return f"No state.md found at {state_path}. Run `repo-graph-generate` first."


@mcp.tool()
def flow(feature: str) -> str:
    """
    Get the full end-to-end flow for a feature.
    Shows: page → service → route → handler → repo → DB collection.
    """
    g = get_graph()
    feature_key = feature.lower().replace(" ", "-").replace("_", "-")

    if feature_key in g.flows:
        return g.flows[feature_key]

    # Try fuzzy match
    for key, content in g.flows.items():
        if feature_key in key:
            return content

    available = ", ".join(sorted(g.flows.keys()))
    return f"No flow found for '{feature}'. Available flows: {available}"


@mcp.tool()
def trace(from_node: str, to_node: str) -> str:
    """
    Find the shortest path between two nodes in the graph.
    Accepts node IDs (e.g. 'handler_auth') or fuzzy names (e.g. 'auth controller').
    """
    g = get_graph()

    from_resolved = g.find_node(from_node)
    to_resolved = g.find_node(to_node)

    if not from_resolved:
        return f"Node not found: '{from_node}'"
    if not to_resolved:
        return f"Node not found: '{to_node}'"

    path = g.shortest_path(from_resolved["id"], to_resolved["id"])
    if path is None:
        return f"No path between {from_resolved['id']} and {to_resolved['id']}"

    lines = [f"Path: {from_resolved['id']} → {to_resolved['id']} ({len(path)} hops)\n"]
    for i, node in enumerate(path):
        prefix = "  → " if i > 0 else "    "
        fp = node.get("file_path", "")
        line_count = g.file_line_count(fp) if fp else 0
        size_str = f" ({line_count} lines)" if line_count else ""
        lines.append(f"{prefix}{node['id']} [{node['type']}] {fp}{size_str}")

    return "\n".join(lines)


@mcp.tool()
def impact(node: str, direction: str = "downstream", depth: int = 3) -> str:
    """
    Fan out from a node to see what it affects (downstream) or depends on (upstream).
    Use to assess blast radius before making changes.
    """
    g = get_graph()
    resolved = g.find_node(node)
    if not resolved:
        return f"Node not found: '{node}'"

    if direction == "upstream":
        results = g.upstream(resolved["id"], depth)
    else:
        results = g.downstream(resolved["id"], depth)

    if not results:
        return f"No {direction} nodes found from {resolved['id']} (depth={depth})"

    # Group by depth
    by_depth: dict[int, list[dict]] = {}
    for r in results:
        d = r["depth"]
        by_depth.setdefault(d, []).append(r)

    lines = [f"Impact {direction} from {resolved['id']} (depth={depth}):\n"]
    for d in sorted(by_depth.keys()):
        lines.append(f"  Depth {d}:")
        for n in by_depth[d]:
            fp = n.get("file_path", "")
            lines.append(f"    {n['id']} [{n['type']}] {fp}")

    return "\n".join(lines)


@mcp.tool()
def neighbours(node: str) -> str:
    """Direct connections to/from a node — one hop in each direction."""
    g = get_graph()
    resolved = g.find_node(node)
    if not resolved:
        return f"Node not found: '{node}'"

    n = g.neighbours(resolved["id"])
    lines = [f"Neighbours of {resolved['id']}:\n"]

    if n["outbound"]:
        lines.append("  Outbound (this → ...):")
        for entry in n["outbound"]:
            nn = entry["node"]
            lines.append(f"    → {nn.get('id', '?')} [{nn.get('type', '?')}] via {entry['edge']}")

    if n["inbound"]:
        lines.append("  Inbound (... → this):")
        for entry in n["inbound"]:
            nn = entry["node"]
            lines.append(f"    ← {nn.get('id', '?')} [{nn.get('type', '?')}] via {entry['edge']}")

    if not n["outbound"] and not n["inbound"]:
        lines.append("  (isolated node — no connections)")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Tier 2 — Budgeting
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def cost(feature: str) -> str:
    """
    Total context cost (lines) for a feature's flow.
    Shows each file and its line count, plus the total.
    Use before starting work to know if you can hold the feature in context.
    """
    g = get_graph()
    nodes = g.nodes_for_feature(feature)

    if not nodes:
        return f"No nodes found for feature '{feature}'"

    sized = g.file_sizes_for_nodes(nodes)
    sized.sort(key=lambda n: n.get("lines", 0), reverse=True)

    total = sum(n.get("lines", 0) for n in sized)

    lines = [f"Context cost for '{feature}': {total} lines across {len(sized)} files\n"]
    for n in sized:
        lc = n.get("lines", 0)
        bar = "█" * (lc // 50)
        lines.append(f"  {lc:>5} {bar:40s} {n.get('file_path', '?')}")

    return "\n".join(lines)


@mcp.tool()
def hotspots(threshold: int = 300) -> str:
    """
    Files over threshold lines, ranked by size × connection count.
    High-coupling big files are the worst context hogs.
    """
    g = get_graph()

    # Aggregate by file_path — multiple nodes can share a file (e.g. routes in one controller)
    by_file: dict[str, dict] = {}
    for node in g.nodes.values():
        fp = node.get("file_path", "")
        if not fp or fp.endswith("/"):
            continue

        if fp not in by_file:
            line_count = g.file_line_count(fp)
            if line_count < threshold:
                continue
            by_file[fp] = {"file_path": fp, "lines": line_count, "coupling": 0, "node_ids": []}

        if fp in by_file:
            entry = by_file[fp]
            out_count = len(g.adjacency_out.get(node["id"], []))
            in_count = len(g.adjacency_in.get(node["id"], []))
            entry["coupling"] += out_count + in_count
            entry["node_ids"].append(node["id"])

    results = []
    for entry in by_file.values():
        entry["score"] = entry["lines"] * max(entry["coupling"], 1)
        results.append(entry)

    results.sort(key=lambda r: r["score"], reverse=True)

    if not results:
        return f"No files over {threshold} lines found in the graph."

    lines = [f"Hotspots (files > {threshold} lines, ranked by size × coupling):\n"]
    for r in results[:20]:
        severity = "CRITICAL" if r["lines"] > 800 and r["coupling"] > 3 else "WARNING"
        lines.append(
            f"  [{severity}] {r['file_path']}\n"
            f"           {r['lines']} lines, {r['coupling']} connections, "
            f"score={r['score']}"
        )

    return "\n".join(lines)


@mcp.tool()
def minimal_read(feature: str, sub_task: str = "") -> str:
    """
    Suggest the minimum set of files to read for a task within a feature.
    If sub_task is given, filters to nodes whose names/IDs match keywords.
    Without sub_task, returns the full feature file set ranked by relevance.
    """
    g = get_graph()
    nodes = g.nodes_for_feature(feature)

    if not nodes:
        return f"No nodes found for feature '{feature}'"

    if sub_task:
        keywords = sub_task.lower().split()
        scored = []
        for n in nodes:
            text = f"{n.get('id', '')} {n.get('name', '')} {n.get('type', '')}".lower()
            hits = sum(1 for kw in keywords if kw in text)
            if hits > 0:
                scored.append((hits, n))
        scored.sort(key=lambda x: x[0], reverse=True)
        nodes = [n for _, n in scored]

    sized = g.file_sizes_for_nodes(nodes)
    sized.sort(key=lambda n: n.get("lines", 0), reverse=True)

    total = sum(n.get("lines", 0) for n in sized)
    label = f"'{feature}' > '{sub_task}'" if sub_task else f"'{feature}'"

    lines = [f"Minimal read set for {label}: {total} lines across {len(sized)} files\n"]
    for n in sized:
        lines.append(f"  {n.get('lines', 0):>5} lines  {n.get('file_path', '?')}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Tier 3 — Health
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def bloat_report(file_path: str) -> str:
    """
    Analyze a file's internal structure: functions/methods, sizes, injected services.
    Works with .go, .ts, and .scss files. Use to understand what's inside before splitting.
    """
    g = get_graph()
    full_path = g.repo_path / file_path

    if not full_path.exists():
        return f"File not found: {file_path}"

    if file_path.endswith(".go"):
        analysis = analyze_go_file(full_path)
        lines = [
            f"Bloat report: {analysis['file']} ({analysis['total_lines']} lines, "
            f"{analysis['function_count']} functions)\n"
        ]
        lines.append("Functions (largest first):")
        for fn in analysis["functions"][:15]:
            bar = "█" * (fn["lines"] // 5)
            lines.append(f"  {fn['lines']:>4} lines  {bar:30s}  {fn['name']} (L{fn['start']}-{fn['end']})")
        return "\n".join(lines)

    elif file_path.endswith(".ts"):
        analysis = analyze_ts_component(full_path)
        lines = [
            f"Bloat report: {analysis['file']} ({analysis['total_lines']} lines, "
            f"{analysis['service_count']} services, {analysis['method_count']} methods)\n"
        ]
        if analysis["services_injected"]:
            lines.append("Injected services:")
            for s in analysis["services_injected"]:
                lines.append(f"  {s['field']}: {s['type']}")

        lines.append("\nMethods (largest first):")
        for m in analysis["methods"][:15]:
            bar = "█" * (m["approx_lines"] // 3)
            lines.append(f"  ~{m['approx_lines']:>3} lines  {bar:30s}  {m['name']} (L{m['line']})")
        return "\n".join(lines)

    elif file_path.endswith(".scss"):
        analysis = analyze_scss_file(full_path)
        lines = [
            f"Bloat report: {analysis['file']} ({analysis['total_lines']} lines, "
            f"{analysis['block_count']} top-level blocks)\n"
        ]
        lines.append("SCSS blocks (largest first):")
        for b in analysis["blocks"][:15]:
            bar = "█" * (b["lines"] // 10)
            lines.append(f"  {b['lines']:>4} lines  {bar:30s}  {b['selector']} (L{b['start']}-{b['end']})")
        return "\n".join(lines)

    return f"Unsupported file type: {file_path}. Supports .go, .ts, .scss"


@mcp.tool()
def split_plan(file_path: str) -> str:
    """
    Propose concrete splits for a large file based on internal cohesion.
    For .ts components: clusters methods by service affinity.
    For .go controllers: groups functions by repo usage.
    """
    g = get_graph()
    full_path = g.repo_path / file_path

    if not full_path.exists():
        return f"File not found: {file_path}"

    component_name = full_path.stem.replace(".component", "").replace("_controller", "")

    if file_path.endswith(".ts"):
        ts = analyze_ts_component(full_path)

        # Also check for companion SCSS
        scss_path = full_path.with_suffix("").with_suffix(".component.scss")
        scss = None
        if scss_path.exists():
            scss = analyze_scss_file(scss_path)

        clusters = suggest_splits(component_name, ts, scss)
        if not clusters:
            return f"No split suggestions for {file_path} — too few methods or services."

        lines = [f"Split plan for {file_path} ({ts['total_lines']} lines):\n"]

        if scss:
            lines.append(f"Companion SCSS: {scss['file']} ({scss['total_lines']} lines)\n")

        for i, cluster in enumerate(clusters, 1):
            lines.append(f"  {i}. {cluster['suggested_name']} (~{cluster['approx_lines']} lines)")
            if cluster["related_services"]:
                lines.append(f"     Services: {', '.join(cluster['related_services'])}")
            lines.append(f"     Methods: {', '.join(cluster['methods'][:10])}")
            if len(cluster["methods"]) > 10:
                lines.append(f"     ... and {len(cluster['methods']) - 10} more")

        # Context savings estimate
        largest = max(c["approx_lines"] for c in clusters) if clusters else ts["total_lines"]
        lines.append(f"\n  Context savings: {ts['total_lines']} → max ~{largest} per task touch")
        return "\n".join(lines)

    elif file_path.endswith(".go"):
        go = analyze_go_file(full_path)
        lines = [f"Split plan for {file_path} ({go['total_lines']} lines, {go['function_count']} functions):\n"]

        # Group functions by prefix patterns
        groups: dict[str, list[dict]] = {}
        for fn in go["functions"]:
            name = fn["name"]
            # Heuristic: group by verb prefix or domain keyword
            prefix = "other"
            for keyword in ["OAuth", "Google", "Register", "Login", "Refresh",
                           "Password", "Reset", "Forgot", "2FA", "Verify",
                           "Unsubscribe", "Handle", "Create", "Update", "Delete",
                           "List", "Get", "Find", "Search", "Sync", "Send",
                           "ensure", "run", "seed"]:
                if keyword.lower() in name.lower():
                    prefix = keyword.lower()
                    break
            groups.setdefault(prefix, []).append(fn)

        # Merge small groups
        merged: dict[str, list[dict]] = {}
        small = []
        for prefix, fns in groups.items():
            total = sum(f["lines"] for f in fns)
            if total < 80:
                small.extend(fns)
            else:
                merged[prefix] = fns

        if small:
            merged["misc"] = small

        for i, (prefix, fns) in enumerate(merged.items(), 1):
            total = sum(f["lines"] for f in fns)
            fn_names = [f["name"] for f in fns]
            lines.append(f"  {i}. {component_name}_{prefix}.go (~{total} lines)")
            lines.append(f"     Functions: {', '.join(fn_names[:8])}")
            if len(fn_names) > 8:
                lines.append(f"     ... and {len(fn_names) - 8} more")

        return "\n".join(lines)

    return f"Unsupported file type for split planning: {file_path}"


@mcp.tool()
def reload() -> str:
    """Reload graph data from disk after a regeneration."""
    global _graph
    _graph = None
    g = get_graph()
    return f"Reloaded: {len(g.nodes)} nodes, {len(g.edges)} edges, {len(g.flows)} flows"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="repo-graph MCP server")
    parser.add_argument("--repo", default=os.environ.get("REPO_GRAPH_REPO", os.getcwd()),
                        help="Path to the target repository")
    args = parser.parse_args()

    os.environ["REPO_GRAPH_REPO"] = args.repo
    mcp.run()


if __name__ == "__main__":
    main()
