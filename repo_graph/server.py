"""
repo-graph MCP server.

Structural navigation, context budgeting, and codebase health tools.
Reads from .ai/repo-graph/ in the target repository.

Usage:
    repo-graph --repo /path/to/your/repo
"""

import os
from typing import Annotated

from pydantic import Field
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .analyzers import get_file_analyzer
from .graph import RepoGraph

REPO_PATH = os.environ.get("REPO_GRAPH_REPO", os.getcwd())

mcp = FastMCP(
    "repo-graph",
    instructions=(
        "Structural map of this codebase — entities, relationships, and feature flows. "
        "BEFORE grepping or reading files, call `status` to orient, then `flow` or `impact` "
        "to find exactly which files matter. This avoids wasting context on exploration. "
        "Use for: finding feature flows, tracing paths between components, impact analysis, "
        "context cost estimation, file hotspots, and split planning. "
        "Works with any language/framework."
    ),
)

_graph: RepoGraph | None = None


def get_graph() -> RepoGraph:
    global _graph
    if _graph is None:
        _graph = RepoGraph(REPO_PATH)
    return _graph


# ─────────────────────────────────────────────────────────────────────────────
# Tier 0 — Generation
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def generate(
    repo_path: Annotated[str, Field(description="Absolute path to the repository to scan. Defaults to the repo the server was started with.", default="")] = "",
) -> str:
    """Writes to .ai/repo-graph/. Scan the codebase and (re)build the structural graph. Auto-detects languages and frameworks. Creates nodes.json, edges.json, flows/*.yaml, and state.md. Call on first use, after major refactors, or when graph data feels stale. Returns a summary of detected node types, edge counts, and available flows."""
    from .generator import generate as run_generate

    target = repo_path or REPO_PATH
    target_path = Path(target)

    if not target_path.is_dir():
        return f"Not a directory: {target}"

    try:
        nodes, edges, flows = run_generate(target_path)
    except Exception as e:
        return f"Generation failed: {e}"

    # Reload the in-memory graph
    global _graph
    _graph = None
    g = get_graph()

    # Summarize what was detected
    node_types: dict[str, int] = {}
    for node in nodes:
        t = node["type"]
        node_types[t] = node_types.get(t, 0) + 1

    type_summary = ", ".join(f"{count} {t}" for t, count in sorted(node_types.items()))

    return (
        f"Generated repo graph: {len(nodes)} nodes, {len(edges)} edges, "
        f"{len(flows)} flows\n"
        f"Node types: {type_summary}\n"
        f"Flows: {', '.join(sorted(flows.keys())) if flows else '(none)'}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tier 1 — Navigation
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def status() -> str:
    """Read-only. Repo overview showing detected languages, node/edge counts, available feature flows, and a visual graph summary. Call this first to orient before using other tools. Returns state.md content plus an ASCII overview of the graph structure. No parameters needed."""
    g = get_graph()
    state_path = g.graph_dir / "state.md"
    parts = []
    if state_path.exists():
        parts.append(state_path.read_text())
    else:
        parts.append(f"No state.md found at {state_path}. Run `generate` tool first.")
        return parts[0]

    # Append visual overview
    parts.append("")
    parts.append(_render_overview(g))
    return "\n".join(parts)


_CONFIDENCE_RANK = {"weak": 0, "medium": 1, "strong": 2}


@mcp.tool()
def flow(
    feature: Annotated[str, Field(description="Feature name or keyword to match against available flows. Case-insensitive, supports partial matching. Example: 'login', 'users', 'checkout'.")],
    kind: Annotated[str, Field(description="Optional kind filter: http, page, cli, grpc, queue. Restricts matches to flows tagged with this entrypoint type. Leave blank to match any kind.", default="")] = "",
    min_confidence: Annotated[str, Field(description="Minimum trust tier: weak, medium, strong. Hides flows scored below this tier (e.g. medium hides weak). Default weak = no filter.", default="weak")] = "weak",
) -> str:
    """Read-only. End-to-end flow for a feature: entry point through service layer to data store, rendered as layered tiers (ENTRY -> SERVICE -> HANDLER -> DATA). Call after `status` to drill into a specific feature. Returns an ASCII tier diagram with file paths and line counts. Lists available flows if no match found."""
    g = get_graph()
    feature_lower = feature.lower().strip()
    kind_filter = kind.lower().strip() or None
    min_rank = _CONFIDENCE_RANK.get(min_confidence.lower().strip(), 0)

    def _key_ok(key: str) -> bool:
        if kind_filter and g.flow_kinds.get(key, "http") != kind_filter:
            return False
        conf = g.flow_confidence.get(key, "medium")
        return _CONFIDENCE_RANK.get(conf, 1) >= min_rank

    # Find the matching flow — prefer exact match, then shortest containing key
    flow_yaml = None
    flow_key = feature_lower
    if feature_lower in g.flows and _key_ok(feature_lower):
        flow_yaml = g.flows[feature_lower]
    else:
        candidates = []
        for key, content in g.flows.items():
            if not _key_ok(key):
                continue
            if feature_lower in key or key in feature_lower:
                candidates.append((key, content))
        if candidates:
            # Prefer the shortest key (most specific match)
            best_key, best_content = min(candidates, key=lambda x: len(x[0]))
            flow_yaml = best_content
            flow_key = best_key

    if flow_yaml is None:
        available_keys = [k for k in g.flows.keys() if _key_ok(k)]
        available = ", ".join(
            f"[{g.flow_kinds.get(k, 'http')}/{g.flow_confidence.get(k, 'medium')}] {k}"
            for k in sorted(available_keys)
        )
        filters = []
        if kind_filter:
            filters.append(f"kind={kind_filter}")
        if min_rank > 0:
            filters.append(f"min_confidence={min_confidence}")
        suffix = f" ({', '.join(filters)})" if filters else ""
        return f"No flow found for '{feature}'{suffix}. Available flows: {available}"

    return _render_flow_layered(flow_key, flow_yaml, g)


@mcp.tool()
def trace(
    from_node: Annotated[str, Field(description="Starting node ID or name. Accepts exact IDs (e.g. 'pkg_auth') or fuzzy name matches (e.g. 'auth').")],
    to_node: Annotated[str, Field(description="Target node ID or name. Accepts exact IDs or fuzzy name matches.")],
) -> str:
    """Read-only. Shortest path between two nodes in the graph, showing each hop with tier transitions (ENTRY -> SERVICE -> HANDLER -> DATA). Call when you need to understand how two components are connected. Returns the path as an ASCII diagram with file paths and line counts per node."""
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

    lines = [f"  Trace: {from_resolved['id']} -> {to_resolved['id']} ({len(path)} hops)", ""]

    prev_tier = None
    for i, node in enumerate(path):
        icon = _type_icon(node["type"])
        tier = _classify_tier(node["type"], node.get("name", ""))
        fp = node.get("file_path", "")
        lc = g.file_line_count(fp) if fp else 0
        size_str = f" ({lc}L)" if lc else ""

        # Show tier transition
        if tier != prev_tier:
            if prev_tier is not None:
                lines.append("      |")
                lines.append("      v")
            lines.append(f"  [{tier}]")
            prev_tier = tier

        arrow = "  -> " if i > 0 else "     "
        lines.append(f"  {arrow}{icon} {node.get('name', node['id'])}  {fp}{size_str}")

    return "\n".join(lines)


@mcp.tool()
def impact(
    node: Annotated[str, Field(description="Node ID or name to analyze. Accepts exact IDs (e.g. 'func_handleLogin') or fuzzy name matches (e.g. 'handleLogin').")],
    direction: Annotated[str, Field(description="'downstream' to see what this node affects, 'upstream' to see what it depends on.", default="downstream")] = "downstream",
    depth: Annotated[int, Field(description="How many hops to traverse. Higher values find more distant dependencies. Default 3.", default=3, ge=1, le=10)] = 3,
    include_tests: Annotated[bool, Field(description="If true, also surface test files that import the node (via `tests` edges). Useful before refactoring to see what tests need updating.", default=False)] = False,
) -> str:
    """Read-only. Blast radius analysis: fan out from a node to see everything it affects (downstream) or depends on (upstream), grouped by architectural tier. Call before modifying a component to understand the change's reach. Returns affected node count, file count, and a tier-grouped list of impacted components."""
    g = get_graph()
    resolved = g.find_node(node)
    if not resolved:
        return f"Node not found: '{node}'"

    if direction == "upstream":
        results = g.upstream(resolved["id"], depth)
    else:
        results = g.downstream(resolved["id"], depth)

    affected_tests: list[dict] = []
    if include_tests:
        seen_test_ids: set[str] = set()
        candidate_ids = {resolved["id"]} | {r["id"] for r in results}
        for cid in candidate_ids:
            for upstream_id, etype in g.adjacency_in.get(cid, []):
                if etype != "tests":
                    continue
                if upstream_id in seen_test_ids:
                    continue
                seen_test_ids.add(upstream_id)
                tn = g.nodes.get(upstream_id)
                if tn:
                    affected_tests.append(tn)

    if not results:
        return f"No {direction} nodes found from {resolved['id']} (depth={depth})"

    r_icon = _type_icon(resolved["type"])
    lines = [
        f"  Impact {direction} from {resolved['id']} (depth={depth})",
        f"  {r_icon} {resolved.get('name', resolved['id'])}  [{resolved['type']}]",
        "",
    ]

    # Group by tier
    by_tier: dict[str, list[dict]] = {}
    for r in results:
        tier = _classify_tier(r["type"], r.get("name", ""))
        by_tier.setdefault(tier, []).append(r)

    tier_order = ["ENTRY", "SERVICE", "HANDLER", "DATA"]
    total_files: set[str] = set()

    for tier_name in tier_order:
        items = by_tier.get(tier_name, [])
        if not items:
            continue
        lines.append(f"  [{tier_name}] ({len(items)} affected)")
        for n in items[:15]:
            icon = _type_icon(n["type"])
            fp = n.get("file_path", "")
            if fp:
                total_files.add(fp)
            lines.append(f"    {icon} {n.get('name', n['id'])}  {fp}")
        if len(items) > 15:
            lines.append(f"    ... and {len(items) - 15} more")

    lines.append("")
    lines.append(f"  -- {len(results)} nodes affected across {len(total_files)} files")
    if total_files:
        lines.append("")
        lines.append("  These files cover the blast radius — read them before searching further.")

    if include_tests:
        if affected_tests:
            lines.append("")
            lines.append(f"  [TESTS] ({len(affected_tests)} affected)")
            for t in affected_tests[:20]:
                lines.append(f"    ⌬ {t.get('name', t['id'])}  {t.get('file_path', '')}")
            if len(affected_tests) > 20:
                lines.append(f"    ... and {len(affected_tests) - 20} more")
        else:
            lines.append("")
            lines.append("  [TESTS] none found")

    return "\n".join(lines)


@mcp.tool()
def neighbours(
    node: Annotated[str, Field(description="Node ID or name to inspect. Accepts exact IDs or fuzzy name matches.")],
) -> str:
    """Read-only. All direct connections to and from a node, one hop in each direction, showing edge types (imports, calls, defines, etc.). Call to understand a single component's immediate dependencies and dependents. Returns outbound and inbound connections as an ASCII tree."""
    g = get_graph()
    resolved = g.find_node(node)
    if not resolved:
        return f"Node not found: '{node}'"

    n = g.neighbours(resolved["id"])
    r_icon = _type_icon(resolved["type"])
    lines = [
        f"  {r_icon} {resolved.get('name', resolved['id'])}",
        f"  |   [{resolved['type']}] {resolved.get('file_path', '')}",
    ]

    if n["outbound"]:
        lines.append("  |")
        lines.append(f"  +-->> Outbound ({len(n['outbound'])}):")
        for entry in n["outbound"][:20]:
            nn = entry["node"]
            icon = _type_icon(nn.get("type", "?"))
            lines.append(f"  |     {icon} {nn.get('name', nn.get('id', '?'))} --({entry['edge']})")
        if len(n["outbound"]) > 20:
            lines.append(f"  |     ... and {len(n['outbound']) - 20} more")

    if n["inbound"]:
        lines.append("  |")
        lines.append(f"  +--<< Inbound ({len(n['inbound'])}):")
        for entry in n["inbound"][:20]:
            nn = entry["node"]
            icon = _type_icon(nn.get("type", "?"))
            lines.append(f"        {icon} {nn.get('name', nn.get('id', '?'))} --({entry['edge']})")
        if len(n["inbound"]) > 20:
            lines.append(f"        ... and {len(n['inbound']) - 20} more")

    if not n["outbound"] and not n["inbound"]:
        lines.append("  (isolated node -- no connections)")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Tier 2 — Budgeting
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def cost(
    feature: Annotated[str, Field(description="Feature name or keyword matching a flow. Case-insensitive, supports partial matching. Example: 'auth', 'payments'.")],
) -> str:
    """Read-only. Total context cost in lines for a feature's flow, with per-file breakdown. Call before starting work to know if the feature fits in context. Returns total line count, file count, and a bar chart of per-file sizes sorted largest first."""
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
def hotspots(
    threshold: Annotated[int, Field(description="Minimum file size in lines to include. Files below this are ignored. Default 300.", default=300, ge=50)] = 300,
) -> str:
    """Read-only. Files ranked by size multiplied by connection count, identifying the biggest maintenance risks. High-coupling large files waste the most context. Call to find which files need splitting or refactoring first. Returns files sorted by risk score with severity labels (CRITICAL/WARNING)."""
    g = get_graph()

    by_file: dict[str, dict] = {}
    for node in g.nodes.values():
        fp = node.get("file_path", "")
        if not fp or fp.endswith("/"):
            continue

        if fp not in by_file:
            line_count = g.file_line_count(fp)
            if line_count < threshold:
                continue
            by_file[fp] = {
                "file_path": fp,
                "lines": line_count,
                "coupling": 0,
                "node_ids": [],
            }

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

    lines = [f"Hotspots (files > {threshold} lines, ranked by size x coupling):\n"]
    for r in results[:20]:
        severity = "CRITICAL" if r["lines"] > 800 and r["coupling"] > 3 else "WARNING"
        lines.append(
            f"  [{severity}] {r['file_path']}\n"
            f"           {r['lines']} lines, {r['coupling']} connections, "
            f"score={r['score']}"
        )

    return "\n".join(lines)


@mcp.tool()
def minimal_read(
    feature: Annotated[str, Field(description="Feature name or keyword matching a flow. Case-insensitive, supports partial matching. Example: 'auth', 'checkout'.")],
    sub_task: Annotated[str, Field(description="Optional keywords to filter the file set further. Space-separated. Example: 'validation middleware'. Omit to get all files for the feature.", default="")] = "",
) -> str:
    """Read-only. Smallest set of files needed for a task, ranked by relevance. Filters by sub_task keywords if given, otherwise returns the full feature file set. Call before reading code to know exactly which files to open. Returns file paths with line counts, sorted largest first."""
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
def bloat_report(
    file_path: Annotated[str, Field(description="Relative path to the file to analyze, from the repo root. Example: 'src/server.py', 'internal/handler.go'.")],
) -> str:
    """Read-only. Internal structure of a single file: functions/methods ranked by size, class counts, and injected services. Call on files flagged by `hotspots` to understand what's inside before splitting. Returns a structured breakdown of the file's contents with line counts per function."""
    g = get_graph()
    full_path = g.repo_path / file_path

    if not full_path.exists():
        return f"File not found: {file_path}"

    analyzer = get_file_analyzer(g.repo_path, full_path)
    if analyzer is None:
        return f"No analyzer available for: {file_path}"

    analysis = analyzer.analyze_file(full_path)
    if analysis is None:
        return f"Could not analyze: {file_path}"

    report = analyzer.format_bloat_report(analysis)
    if report is None:
        return f"Could not format report for: {file_path}"

    return report


@mcp.tool()
def split_plan(
    file_path: Annotated[str, Field(description="Relative path to the file to analyze, from the repo root. Example: 'src/server.py', 'internal/handler.go'.")],
) -> str:
    """Read-only. Concrete split suggestions for an oversized file, grouped by responsibility and cohesion. Works with any supported language. Call after `bloat_report` to get actionable refactoring guidance. Returns suggested new files with the functions/classes that belong in each."""
    g = get_graph()
    full_path = g.repo_path / file_path

    if not full_path.exists():
        return f"File not found: {file_path}"

    analyzer = get_file_analyzer(g.repo_path, full_path)
    if analyzer is None:
        return f"No analyzer available for: {file_path}"

    analysis = analyzer.analyze_file(full_path)
    if analysis is None:
        return f"Could not analyze: {file_path}"

    splits = analyzer.suggest_splits(full_path, analysis)
    if not splits:
        return f"No split suggestions for {file_path} — too few functions or too small."

    report = analyzer.format_split_plan(file_path, analysis, splits)
    if report is None:
        return f"Could not format split plan for: {file_path}"

    return report


@mcp.tool()
def graph_view(
    feature: Annotated[str, Field(description="Feature name to render as a layered flow diagram. Mutually exclusive with 'node'. Example: 'auth', 'checkout'.", default="")] = "",
    node: Annotated[str, Field(description="Node ID or name to render as a tree with children, connections, and flows. Mutually exclusive with 'feature'. Example: 'pkg_auth'.", default="")] = "",
    depth: Annotated[int, Field(description="Tree depth for node view. Higher values show more nested children. Default 2.", default=2, ge=1, le=5)] = 2,
) -> str:
    """Read-only. Visual ASCII graph map with three modes. With feature: layered flow diagram (ENTRY -> SERVICE -> HANDLER -> DATA). With node: tree of children, connections, and flows. Without args: full graph overview with node/edge type counts. Call to visualize structure before diving into code."""
    g = get_graph()

    if feature:
        return _render_feature_tree(g, feature, depth)
    elif node:
        return _render_node_tree(g, node, depth)
    else:
        return _render_overview(g)


_ENTRY_TYPES = {"route", "ng_page", "react_component", "react_module", "page", "entry_point"}
_SERVICE_TYPES = {"ng_service", "ng_guard", "react_context", "react_hook",
                  "go_package", "py_module", "rs_module", "ts_module",
                  "java_package", "cs_namespace", "rb_module", "php_namespace"}
_HANDLER_TYPES = {"go_function", "py_function", "rs_function", "ts_function",
                  "py_class", "java_class", "cs_class", "rb_class", "php_class",
                  "swift_class", "cpp_class", "ts_class", "handler"}
_DATA_TYPES = {"api_call", "model", "db", "store", "repository"}


def _classify_tier(node_type: str, node_name: str = "") -> str:
    """Classify a node into a visual tier."""
    if node_type in _ENTRY_TYPES:
        return "ENTRY"
    if node_type in _SERVICE_TYPES:
        return "SERVICE"
    if node_type in _HANDLER_TYPES:
        return "HANDLER"
    if node_type in _DATA_TYPES:
        return "DATA"
    # Heuristic fallback
    nl = node_name.lower()
    if "service" in nl or "provider" in nl:
        return "SERVICE"
    if "handler" in nl or "controller" in nl:
        return "HANDLER"
    if "model" in nl or "repo" in nl or "store" in nl or "api" in nl:
        return "DATA"
    return "HANDLER"


def _render_feature_tree(g: RepoGraph, feature: str, depth: int) -> str:
    """Render a feature flow as a layered tier view."""
    feature_lower = feature.lower().strip()

    # Check if there's a flow for this feature (try exact, then substring)
    flow_content = None
    feature_key = feature_lower
    # Exact match first, then shortest substring match
    if feature_lower in g.flows:
        flow_content = g.flows[feature_lower]
        feature_key = feature_lower
    else:
        candidates = []
        for key, content in g.flows.items():
            if feature_lower in key or key in feature_lower:
                candidates.append((key, content))
        if candidates:
            feature_key, flow_content = min(candidates, key=lambda x: len(x[0]))

    if flow_content:
        return _render_flow_layered(feature_key, flow_content, g)

    # Fall back to nodes_for_feature traversal
    nodes = g.nodes_for_feature(feature)
    if not nodes:
        return f"No feature '{feature}' found. Use `status` to see available flows."

    return _render_nodes_layered(feature, nodes[:30], g)


def _render_flow_layered(name: str, flow_yaml: str, g: RepoGraph) -> str:
    """Parse a flow YAML and render as layered tiers."""
    import re

    step_pattern = re.compile(r"\{id:\s*([^,}]+),\s*type:\s*([^,}]+)(?:,\s*edge:\s*([^}]+))?\}")
    steps = step_pattern.findall(flow_yaml)

    if not steps:
        return f"  Flow: {name}\n  (empty flow)"

    # Classify each step into a tier
    tiers: dict[str, list[tuple[str, str, str, str]]] = {
        "ENTRY": [], "SERVICE": [], "HANDLER": [], "DATA": [],
    }
    unique_files: set[str] = set()
    total_lines = 0

    for node_id, node_type, edge_type in steps:
        node_id = node_id.strip()
        node_type = node_type.strip()
        edge_type = edge_type.strip() if edge_type else ""
        node = g.nodes.get(node_id, {})
        display_name = node.get("name", node_id)
        file_path = node.get("file_path", "")
        tier = _classify_tier(node_type, display_name)
        tiers[tier].append((node_id, node_type, display_name, file_path))
        if file_path and file_path not in unique_files:
            unique_files.add(file_path)
            total_lines += g.file_line_count(file_path)

    lines = [f"  Flow: {name}", "  " + "=" * (len(name) + 6), ""]

    tier_order = ["ENTRY", "SERVICE", "HANDLER", "DATA"]
    tier_icons = {"ENTRY": ">>", "SERVICE": "<>", "HANDLER": "[]", "DATA": "()"}
    rendered_any = False

    for tier_name in tier_order:
        items = tiers[tier_name]
        if not items:
            continue

        if rendered_any:
            lines.append("      |")
            lines.append("      v")

        lines.append(f"  {tier_icons[tier_name]} {tier_name}")
        lines.append("  " + "-" * 40)

        shown = items[:10]
        for node_id, node_type, display_name, file_path in shown:
            icon = _type_icon(node_type)
            fp_str = f"  {file_path}" if file_path else ""
            lines.append(f"    {icon} {display_name}{fp_str}")
        if len(items) > 10:
            lines.append(f"    ... and {len(items) - 10} more")

        rendered_any = True

    lines.append("")
    lines.append(f"  -- {len(steps)} nodes, {len(unique_files)} files, ~{total_lines} lines")
    if unique_files:
        lines.append("")
        lines.append("  Start with these files — they cover this feature's flow.")
    return "\n".join(lines)


def _render_nodes_layered(feature: str, nodes: list[dict], g: RepoGraph) -> str:
    """Render traversal nodes grouped by tier (fallback when no flow YAML)."""
    tiers: dict[str, list[dict]] = {
        "ENTRY": [], "SERVICE": [], "HANDLER": [], "DATA": [],
    }

    for node in nodes:
        tier = _classify_tier(node["type"], node.get("name", ""))
        tiers[tier].append(node)

    lines = [f"  Feature: {feature}", "  " + "=" * (len(feature) + 10), ""]

    tier_order = ["ENTRY", "SERVICE", "HANDLER", "DATA"]
    tier_icons = {"ENTRY": ">>", "SERVICE": "<>", "HANDLER": "[]", "DATA": "()"}
    rendered_any = False

    for tier_name in tier_order:
        items = tiers[tier_name]
        if not items:
            continue

        if rendered_any:
            lines.append("      |")
            lines.append("      v")

        lines.append(f"  {tier_icons[tier_name]} {tier_name}")
        lines.append("  " + "-" * 40)

        for node in items[:10]:
            icon = _type_icon(node["type"])
            fp = node.get("file_path", "")
            fp_str = f"  {fp}" if fp else ""
            lines.append(f"    {icon} {node.get('name', node['id'])}{fp_str}")
        if len(items) > 10:
            lines.append(f"    ... and {len(items) - 10} more")

        rendered_any = True

    return "\n".join(lines)


def _render_node_tree(g: RepoGraph, query: str, depth: int) -> str:
    """Render a node with features, children, connections, and used-by."""
    resolved = g.find_node(query)
    if not resolved:
        return f"Node not found: '{query}'"

    node_id = resolved["id"]
    icon = _type_icon(resolved["type"])
    fp = resolved.get("file_path", "")
    lc = g.file_line_count(fp) if fp else 0
    size_str = f"  ({lc} lines)" if lc else ""

    lines = [
        f"  {icon} {resolved.get('name', node_id)}",
        f"  |   [{resolved['type']}] {fp}{size_str}",
    ]

    # Which flows reference this node?
    member_flows = []
    for flow_name, flow_yaml in g.flows.items():
        if node_id in flow_yaml:
            member_flows.append(flow_name)
    if member_flows:
        lines.append("  |")
        lines.append("  +-- Flows:")
        for fname in member_flows[:10]:
            k = g.flow_kinds.get(fname, "http")
            c = g.flow_confidence.get(fname, "medium")
            lines.append(f"  |     * [{k}] {_confidence_icon(c)} {fname}")
        if len(member_flows) > 10:
            lines.append(f"  |     ... and {len(member_flows) - 10} more")

    # Split outbound into children vs connections
    _CHILD_EDGES = {"defines", "contains", "exports"}
    out_edges = g.adjacency_out.get(node_id, [])
    in_edges = g.adjacency_in.get(node_id, [])

    children = [(tid, et) for tid, et in out_edges if et in _CHILD_EDGES]
    connections = [(tid, et) for tid, et in out_edges if et not in _CHILD_EDGES]

    if children:
        lines.append("  |")
        lines.append("  +-- Children:")
        for i, (target_id, edge_type) in enumerate(children[:20]):
            target = g.nodes.get(target_id, {"id": target_id, "type": "?", "name": target_id})
            t_icon = _type_icon(target.get("type", "?"))
            prefix = "  |     " if i < len(children[:20]) - 1 or connections or in_edges else "        "
            t_fp = target.get("file_path", "")
            t_lc = g.file_line_count(t_fp) if t_fp else 0
            sz = f" ({t_lc}L)" if t_lc else ""
            lines.append(f"{prefix}{t_icon} {target.get('name', target_id)} [{target.get('type', '?')}]{sz}")

            # Show sub-children at depth > 1
            if depth > 1:
                sub_children = [(sid, se) for sid, se in g.adjacency_out.get(target_id, []) if se in _CHILD_EDGES]
                for j, (sub_id, _) in enumerate(sub_children[:5]):
                    sub = g.nodes.get(sub_id, {"name": sub_id, "type": "?"})
                    sub_icon = _type_icon(sub.get("type", "?"))
                    lines.append(f"{prefix}  {sub_icon} {sub.get('name', sub_id)}")
                if len(sub_children) > 5:
                    lines.append(f"{prefix}  ... +{len(sub_children) - 5}")

        if len(children) > 20:
            lines.append(f"  |     ... and {len(children) - 20} more")

    if connections:
        lines.append("  |")
        lines.append("  +-->> Connects to:")
        for i, (target_id, edge_type) in enumerate(connections[:15]):
            target = g.nodes.get(target_id, {"id": target_id, "type": "?", "name": target_id})
            t_icon = _type_icon(target.get("type", "?"))
            lines.append(f"  |     {t_icon} {target.get('name', target_id)} --({edge_type})")
        if len(connections) > 15:
            lines.append(f"  |     ... and {len(connections) - 15} more")

    if in_edges:
        lines.append("  |")
        lines.append("  +--<< Used by:")
        for i, (source_id, edge_type) in enumerate(in_edges[:15]):
            source = g.nodes.get(source_id, {"id": source_id, "type": "?", "name": source_id})
            s_icon = _type_icon(source.get("type", "?"))
            lines.append(f"        {s_icon} {source.get('name', source_id)} --({edge_type})")
        if len(in_edges) > 15:
            lines.append(f"        ... and {len(in_edges) - 15} more")

    return "\n".join(lines)


def _render_overview(g: RepoGraph) -> str:
    """Render a high-level overview of the graph structure."""
    from collections import Counter

    type_counts = Counter(n["type"] for n in g.nodes.values())
    edge_counts = Counter(e["type"] for e in g.edges)

    lines = [
        "  repo-graph",
        "  " + "=" * 40,
        "",
        f"  {len(g.nodes)} nodes, {len(g.edges)} edges, {len(g.flows)} flows",
        "",
        "  Node types:",
    ]

    for ntype, count in type_counts.most_common(15):
        bar = "█" * min(count // 5, 30) or "▏"
        lines.append(f"    {count:>5} {bar:30s} {ntype}")

    if edge_counts:
        lines.append("")
        lines.append("  Edge types:")
        for etype, count in edge_counts.most_common(10):
            lines.append(f"    {count:>5} {etype}")

    if g.flows:
        lines.append("")
        flow_list = sorted(g.flows.keys())
        kind_counts = Counter(g.flow_kinds.get(k, "http") for k in flow_list)
        conf_counts = Counter(g.flow_confidence.get(k, "medium") for k in flow_list)
        kind_summary = ", ".join(f"{c} {k}" for k, c in kind_counts.most_common())
        conf_summary = ", ".join(f"{c} {k}" for k, c in conf_counts.most_common())
        lines.append(f"  Flows ({len(flow_list)} — {kind_summary}; trust: {conf_summary}):")
        for f in flow_list[:20]:
            k = g.flow_kinds.get(f, "http")
            c = g.flow_confidence.get(f, "medium")
            icon = _confidence_icon(c)
            lines.append(f"    ◆ [{k}] {icon} {f}")
        if len(flow_list) > 20:
            lines.append(f"    ... and {len(flow_list) - 20} more")

    return "\n".join(lines)


def _confidence_icon(confidence: str) -> str:
    """Visual tier marker: weak=⚠, medium=·, strong=●."""
    return {"weak": "⚠", "medium": "·", "strong": "●"}.get(confidence, "·")


def _type_icon(node_type: str) -> str:
    """Map node types to compact visual icons."""
    icons = {
        "route": "⟁",
        "go_module": "◈",
        "go_package": "◇",
        "go_function": "ƒ",
        "rs_crate": "◈",
        "rs_module": "◇",
        "rs_struct": "□",
        "rs_trait": "◊",
        "rs_function": "ƒ",
        "ts_module": "◇",
        "ts_class": "□",
        "ts_function": "ƒ",
        "react_project": "◈",
        "react_module": "◇",
        "react_component": "⬡",
        "react_hook": "⚓",
        "react_context": "◎",
        "ng_page": "⬡",
        "ng_service": "⚙",
        "ng_guard": "⛨",
        "ng_shared": "◇",
        "py_package": "◈",
        "py_module": "◇",
        "py_class": "□",
        "py_function": "ƒ",
        "java_project": "◈",
        "java_package": "◇",
        "java_class": "□",
        "cs_project": "◈",
        "cs_namespace": "◇",
        "cs_class": "□",
        "rb_project": "◈",
        "rb_file": "◇",
        "rb_class": "□",
        "rb_module": "◇",
        "php_project": "◈",
        "php_namespace": "◇",
        "php_class": "□",
        "php_interface": "◊",
        "swift_project": "◈",
        "swift_file": "◇",
        "swift_class": "□",
        "swift_struct": "□",
        "swift_protocol": "◊",
        "cpp_project": "◈",
        "cpp_source": "◇",
        "cpp_header": "◇",
        "cpp_class": "□",
        "cpp_struct": "□",
        "api_call": "↗",
    }
    return icons.get(node_type, "●")


@mcp.tool()
def reload() -> str:
    """Read-only. Reload graph data from disk into memory. Call after running `generate` or after external changes to .ai/repo-graph/ files. No parameters needed. Returns updated node, edge, and flow counts."""
    global _graph
    _graph = None
    g = get_graph()
    return f"Reloaded: {len(g.nodes)} nodes, {len(g.edges)} edges, {len(g.flows)} flows"


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
