"""
repo-graph MCP server.

Structural navigation, context budgeting, and codebase health over any codebase,
powered by the Rust glia engine (glia-py) via PyO3.

Six tools, each a natural verb backed by an engine primitive:
    orient   — overview + full/scoped map + coverage blind-spots (status/dense_text/graph_view/coverage)
    find     — any text → ranked located nodes (find/locate/activate → resolve)
    impact   — blast radius: ranked, live-filtered, self-explaining (impact/neighbours → blast_radius)
    trace    — feature flow or A→B path across the stack (flow/trace → cross_stack_trace)
    read     — exact source for one or more nodes (batch)
    refresh  — (re)build the graph (generate/reload)

Usage:
    repo-graph --repo /path/to/your/repo
"""

import os
import re
import sys
import json
import shutil
import hashlib
import tempfile
import threading
import subprocess
from collections import Counter
from typing import Annotated

from pydantic import Field
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

import glia_py

from .graph import RustGraph, ENTRY_KIND_NAMES
from .gitexclude import ensure_cache_excluded

REPO_PATH = os.environ.get("REPO_GRAPH_REPO", os.getcwd())

mcp = MCPServer(
    "repo-graph",
    instructions=(
        "Structural map of this codebase (entities, relationships, cross-stack flows) via MCP. "
        "Use it BEFORE grepping for any structural question. Six tools: `orient` to get the lay "
        "of the land (counts, entry points, and where the graph is blind), `find` to turn any text "
        "— a symbol, keyword, stacktrace, failing test, or diff — into the ranked nodes that matter, "
        "`impact` for blast radius (what a change affects/depends on — ranked, located, dead code "
        "flagged ⊘), `trace` for a feature end-to-end or a path between two nodes, and `read` for a "
        "node's exact source. `refresh` rebuilds after big refactors. If these tools aren't loaded, "
        "search your tool list for them instead of grepping. A trivial single-file lookup? Just grep."
    ),
)

_graph: RustGraph | None = None

# Serializes graph rebuilds so the background watcher and a manual `refresh` (or a
# concurrent tool call's cold build) can't race on the `_graph` global.
_rebuild_lock = threading.Lock()


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


def _exclude_cache(target: str) -> None:
    """Keep the graph layout out of `git status` (local `info/exclude`; skipped
    if the user commits it). Never raises.

    Redundant for the default dir since glia 0.5.0 — `.glia/graph/` ships its own
    `.gitignore` (`*`) — but kept for a layout the engine didn't place there."""
    ensure_cache_excluded(glia_py.default_gmap_dir(target))


def _build_graph(target: str, incremental: bool = True) -> RustGraph:
    """Generate `target`'s graph, persist the `.gmap` cache, install it as live.

    `incremental` (default True) reuses the per-file parse cache at
    `<repo>/.glia/graph/parse_cache.bin` so unchanged files skip tree-sitter
    re-parsing; `incremental=False` forces a full reparse. Shared by `get_graph`
    (cold regen), the watcher, and `refresh`.

    Since glia 0.5.0 `generate` is a pure build that writes no layout, so the
    explicit `save_to_default` here is the only thing keeping the next cold start
    fast.
    """
    global _graph, REPO_PATH
    with _rebuild_lock:
        pg = glia_py.generate(target, incremental=incremental)
        try:
            pg.save_to_default(target)
        except Exception:
            # Best-effort: read-only fs / perms shouldn't break the live graph.
            pass
        _exclude_cache(target)
        REPO_PATH = target
        _graph = RustGraph(pg, target)
        return _graph


def _watch_rebuild() -> None:
    """Watcher callback: incrementally rebuild the graph after source edits.
    Logs to stderr (safe for the MCP stdio channel); never raises."""
    try:
        g = _build_graph(REPO_PATH, incremental=True)
        print(f"[watch] rebuilt: {g.pygraph.node_count()} nodes", file=sys.stderr)
    except Exception as e:
        print(f"[watch] rebuild failed: {e}", file=sys.stderr)


def get_graph() -> RustGraph:
    """Return the in-memory graph, lazy-loading on first access.

    Since glia 0.5.0 `load_from_gmap` self-heals: given the repo path it rebuilds
    a stale, old-format or missing layout itself and writes it back, so there's no
    `is_stale` pre-check here any more. A `ValueError` means it couldn't — fall
    back to a full build.
    """
    global _graph, REPO_PATH
    if _graph is not None:
        return _graph

    REPO_PATH = _resolve_repo(REPO_PATH)

    try:
        pg = glia_py.load_from_gmap(glia_py.default_gmap_dir(REPO_PATH), REPO_PATH)
        _exclude_cache(REPO_PATH)
        _graph = RustGraph(pg, REPO_PATH)
        return _graph
    except (ValueError, OSError, RuntimeError):
        return _build_graph(REPO_PATH)


def _truncate(text: str, budget: int, what: str = "output") -> str:
    """Cap `text` at `budget` chars (line-aligned) with a marker. budget <= 0 = no cap."""
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


def _rows(val) -> list:
    """Rows out of an engine answer. Since glia 0.5.0 the primitives return native
    dicts and lists, not JSON strings: a `{results, absence}` envelope yields its
    results, a bare list yields itself. Anything else → []."""
    if isinstance(val, dict):
        return list(val.get("results") or [])
    if isinstance(val, list):
        return val
    return []


def _render_absence(absence: dict | None, fallback: str) -> str:
    """The engine's own account of an empty answer (LD.8a): the reason, its
    FACT/HEURISTIC tier, and what to try instead — better than the wrapper
    guessing why nothing matched."""
    if not isinstance(absence, dict):
        return fallback
    reason = absence.get("reason", "no_match")
    tier = absence.get("tier", "")
    note = absence.get("note") or fallback
    lines = [f"  No answer ({reason}{', ' + tier if tier else ''}): {note}"]

    mechs = absence.get("mechanisms") or []
    if mechs:
        lines.append("    looked over: " + ", ".join(str(m) for m in mechs[:8]))
    for sug in (absence.get("suggestions") or [])[:5]:
        lines.append(f"    try: {sug}")
    # `caveats` are coverage rows, not strings — where extraction is partial for
    # the mechanism that came up empty. Rendered like orient's blind spots.
    caveats = absence.get("caveats") or []
    if caveats:
        lines.append("    blind spots (grep to confirm):")
        for c in caveats[:5]:
            if isinstance(c, dict):
                cat = c.get("edge_category", "?")
                lang = c.get("language", "*")
                found = c.get("edges_found")
                zero = "  [0 found]" if found == 0 else ""
                verify = f" — verify: {c['verify']}" if c.get("verify") else ""
                lines.append(f"      ⚠ {cat} ({lang}){zero}: {c.get('note', '')}{verify}")
            else:
                lines.append(f"      ⚠ {c}")

    searched = absence.get("nodes_searched")
    if searched is not None:
        tail = f"    searched {searched} nodes"
        if absence.get("unparsed_files"):
            tail += f"; {absence['unparsed_files']} file(s) failed to parse — grep those"
        lines.append(tail)
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# orient — overview + map + coverage blind-spots
#   (subsumes: status, dense_text, graph_view)
# ─────────────────────────────────────────────────────────────────────────────


# Cap the full dense_text dump so a large monorepo can't blow past MCP-client
# tool-result limits (e.g. Claude Desktop's 25k tokens). Override with
# REPO_GRAPH_DENSE_MAX_CHARS (0 = uncapped) for clients with bigger budgets.
try:
    DENSE_TEXT_MAX_CHARS = int(os.environ.get("REPO_GRAPH_DENSE_MAX_CHARS", "50000"))
except ValueError:
    DENSE_TEXT_MAX_CHARS = 50_000


@mcp.tool(annotations=ToolAnnotations(title="Orient", read_only_hint=True))
def orient(
    seed: Annotated[str, Field(description="Optional node/qname to scope the map around (its activated neighbourhood). Blank = repo overview.", default="")] = "",
    full: Annotated[bool, Field(description="With no seed: return the whole-repo dense structural map instead of the counts overview. Ignored when seed is given.", default=False)] = False,
    budget: Annotated[int, Field(description="Max chars in the result. 0 = default cap (~50k for the full map, uncapped otherwise).", default=0, ge=0)] = 0,
) -> str:
    """Get the lay of the land — ALWAYS the first call on a codebase. With no arguments: a counts + entry-points overview plus a `blind spots` note flagging which (language, edge-kind) extractions are partial so you know where to fall back to grep. With `seed=<node>`: the dense structural map scoped to that node's neighbourhood. With `full=true`: the whole-repo dense map (the full context dump). Orient first, then `find` to jump to nodes, `impact` for blast radius, `trace` for flows."""
    g = get_graph()

    if seed:
        records, absence = g.find_records(seed, 1)
        resolved = g.nodes.get(records[0]["id"]) if records else None
        if not resolved:
            return _render_absence(
                absence, f"Seed node not found: '{seed}'. Try `find` with a keyword.")
        scores = g.pygraph.activate([resolved["id"]], 50)
        node_ids = [nid for nid, _ in scores] or [resolved["id"]]
        text = g.pygraph.dense_text_subset(node_ids)
        return _truncate(text, budget, "scoped map")

    if full:
        return _truncate(g.pygraph.dense_text(), budget or DENSE_TEXT_MAX_CHARS, "dense map")

    return _render_overview(g)


# ─────────────────────────────────────────────────────────────────────────────
# find — any text → ranked located nodes
#   (subsumes: find, locate, activate)
# ─────────────────────────────────────────────────────────────────────────────


def _looks_like_signal(text: str) -> bool:
    """Heuristic: does `text` look like a failure signal (stacktrace / failing-test
    id / diff) rather than a bare symbol or keyword? Signals get engine `resolve`;
    plain names get keyword lookup first."""
    if "\n" in text:
        return True
    t = text.strip()
    if "::" in t or t.startswith("@@") or t.startswith("diff --git"):
        return True
    # `path/to/file.py:123` or `File "...", line N`
    if re.search(r"\.\w{1,4}[:\s\"]", t) and re.search(r"\bline\b|:\d", t):
        return True
    return False


def _render_located(header: str, records: list[dict], g: RustGraph, budget: int) -> str:
    """Render engine-located records ({qname,name,kind,score?,file,line,live?}) as
    a ranked, path-anchored list."""
    lines = [header, ""]
    for r in records:
        kind = _record_kind(g, r)
        icon = _kind_icon(kind)
        score = r.get("score")
        score_s = f"{score:.4f}  " if isinstance(score, (int, float)) else ""
        lines.append(
            f"    {score_s}{icon} {r.get('name', '?')}  [{kind}]  {r.get('qname', '')}"
            f"{_eloc(r)}{_elive(r)}"
        )
    return _truncate("\n".join(lines), budget, "find")


@mcp.tool(annotations=ToolAnnotations(title="Find Nodes", read_only_hint=True))
def find(
    query: Annotated[str, Field(description="What to locate: a symbol/keyword (e.g. `User`, `checkout`), OR a failure signal — paste a raw stacktrace, a failing-test id (path::test), or a unified diff / changed-file list.")],
    expand: Annotated[bool, Field(description="Return the relevant neighbourhood (Personalized-PageRank ranked) around the matches, not just the matches themselves. Use to discover what surrounds a seed.", default=False)] = False,
    kind: Annotated[str, Field(description="Force the signal type: 'symbol', 'stacktrace', 'test', 'diff', or 'auto' (sniff the shape).", default="auto")] = "auto",
    top_k: Annotated[int, Field(description="Max results. Default 20.", default=20, ge=1, le=100)] = 20,
    budget: Annotated[int, Field(description="Max chars in the result. 0 = no cap.", default=0, ge=0)] = 0,
) -> str:
    """Turn any text into the ranked nodes that matter — the on-ramp to the graph. A symbol or keyword returns matching nodes; a pasted stacktrace / failing-test id / diff is resolved to the code it implicates and ranked by relevance. Set `expand=true` to fan out to the surrounding neighbourhood (spreading activation). Every row carries `path:line`, so `read` the top hits directly — no grep."""
    g = get_graph()
    q = query.strip()
    if not q:
        return "Empty query."

    seed_ids: list[int] = []
    header: str

    absence: dict | None = None

    use_signal = kind not in ("symbol",) and (kind != "auto" or _looks_like_signal(q))
    if use_signal:
        # Failure signal → engine resolve (stacktrace/test/diff → located ranked nodes).
        sig_kind = kind if kind in ("stacktrace", "test", "diff") else "auto"
        try:
            env = g.pygraph.resolve(q, sig_kind, top_k)
        except (ValueError, RuntimeError):
            env = None
        recs = _rows(env)
        absence = env.get("absence") if isinstance(env, dict) else None
        if recs:
            seed_ids = [r["id"] for r in recs if "id" in r]
            if not expand:
                return _render_located(
                    f"  Resolved {len(recs)} node(s) from signal:", recs, g, budget)
        # else fall through to keyword lookup

    if not seed_ids:
        # Keyword / symbol lookup — the engine's ranked `find` (LD.3b). Its rows
        # already carry file/line/live and the match tier, so they render as-is.
        recs, find_absence = g.find_records(q, top_k)
        if not recs:
            return _render_absence(
                find_absence or absence,
                f"No nodes matched '{query}'. If this was a stacktrace/diff, none of its "
                f"frames mapped to a node — try `orient` or a keyword.")
        seed_ids = [r["id"] for r in recs if "id" in r]
        if not expand:
            return _render_located(
                f"  {len(recs)} node(s) matching '{query}':", recs, g, budget)

    # expand=True → PPR-ranked neighbourhood around the seeds.
    scores = g.pygraph.activate(seed_ids, top_k)
    recs = []
    for nid, sc in scores:
        node = g.nodes.get(nid)
        if node:
            rec = _node_record(g, node)
            rec["score"] = sc
            recs.append(rec)
    return _render_located(
        f"  {len(recs)} node(s) relevant to '{query}' (expanded):", recs, g, budget)


# ─────────────────────────────────────────────────────────────────────────────
# impact — blast radius (ranked, live-filtered, self-explaining)
#   (subsumes: impact, neighbours)
# ─────────────────────────────────────────────────────────────────────────────


# Old direction vocabulary → engine's. downstream=what it affects=forward;
# upstream=what it depends on=backward.
_DIRECTION_ALIAS = {"downstream": "forward", "upstream": "backward",
                    "forward": "forward", "backward": "backward", "both": "both"}


@mcp.tool(annotations=ToolAnnotations(title="Impact / Blast Radius", read_only_hint=True))
def impact(
    nodes: Annotated[str, Field(description="One or more node names/qnames, comma-separated. A diff touching N symbols is one call.")],
    direction: Annotated[str, Field(description="'forward' (what it affects), 'backward' (what it depends on / who uses it), or 'both'. (Aliases: downstream=forward, upstream=backward.)", default="both")] = "both",
    depth: Annotated[int, Field(description="How many hops to fan out. Default 4.", default=4, ge=1, le=10)] = 4,
    live_only: Annotated[bool, Field(description="Drop nodes not reachable from any entry point (likely-dead code). Default False = show all, marking dead ones ⊘.", default=False)] = False,
    top_k: Annotated[int, Field(description="Cap the ranked result. 0 = no cap.", default=0, ge=0, le=200)] = 0,
    budget: Annotated[int, Field(description="Max chars in the result. 0 = no cap.", default=0, ge=0)] = 0,
) -> str:
    """Blast radius in one call: fan out from one or more nodes to everything they affect (forward) or depend on / are used by (backward), returned as a complete, deduped, Personalized-PageRank-ranked, located closure. Each row carries `path:line`, the edge `via` reason it's in scope, and a `⊘` when the engine finds it unreachable from any entry point (likely dead). Structural import/containment fan-out is excluded — no noise. Depth-1 in both directions is a node's immediate neighbours. Pass several comma-separated nodes to assess a whole diff at once."""
    g = get_graph()
    dir_engine = _DIRECTION_ALIAS.get(direction.lower().strip(), "both")

    names = [n.strip() for n in nodes.split(",") if n.strip()]
    if not names:
        return f"No nodes found for: '{nodes}'"

    # One walk, one PPR, many seeds (LD.5). The engine resolves the raw names
    # itself — misses come back in `unresolved`, not as a wrapper lookup failure.
    try:
        env = g.pygraph.blast_radius(names, dir_engine, depth, None, live_only)
    except Exception as e:
        return f"Blast-radius failed for '{nodes}': {e}"

    affected = _rows(env)
    seeds = env.get("seeds") or [] if isinstance(env, dict) else []
    unresolved = env.get("unresolved") or [] if isinstance(env, dict) else []
    resolved_qnames = [s.get("qname", s.get("query", "?")) for s in seeds]
    seed_label = (", ".join(resolved_qnames[:4]) + (" …" if len(resolved_qnames) > 4 else "")
                  or ", ".join(names[:4]))

    if not affected:
        scope = "live " if live_only else ""
        out = _render_absence(
            env.get("absence") if isinstance(env, dict) else None,
            f"No {scope}{dir_engine} nodes found from {seed_label} (depth={depth}).")
        # An empty radius still has to report which of the names never resolved —
        # with a whole diff's worth of seeds that's the actionable half.
        if unresolved:
            out += f"\n    unresolved seed(s): {', '.join(str(u) for u in unresolved)}"
        return out

    if top_k:
        affected = affected[:top_k]

    lines = [f"  Impact ({dir_engine}) from {seed_label} — depth {depth}", ""]
    for r in affected:
        kind = _record_kind(g, r)
        icon = _kind_icon(kind)
        score = r.get("score")
        score_s = f"{score:.3f}  " if isinstance(score, (int, float)) else ""
        via = f"  via {r['reason']}" if r.get("reason") else ""
        d = r.get("depth")
        depth_s = f"  ·{d}" if isinstance(d, int) else ""
        lines.append(
            f"    {score_s}{icon} {r.get('name', '?')}  [{kind}]{_eloc(r)}{_elive(r)}{via}{depth_s}")

    dead = sum(1 for r in affected if r.get("live") is False)
    lines.append("")
    for sd in seeds:
        linked = sd.get("linked_seeds") or []
        if linked:
            lines.append(f"  seed {sd.get('qname', '?')} also links: "
                         + ", ".join(str(x) for x in linked[:5]))
    if unresolved:
        lines.append(f"  unresolved seed(s): {', '.join(str(u) for u in unresolved)}")
    note = f"  -- {len(affected)} nodes in blast radius"
    if dead and not live_only:
        note += (f"  ({dead} marked ⊘ are not reachable from a known entry point — likely dead, "
                 f"or an entry kind the engine doesn't yet recognise; re-run with live_only=true to drop them)")
    lines.append(note)

    return _truncate("\n".join(lines), budget, "impact")


# ─────────────────────────────────────────────────────────────────────────────
# trace — feature flow, or path between two nodes
#   (subsumes: flow, trace)
# ─────────────────────────────────────────────────────────────────────────────


_MECH_ICON = {"CALLS": "→", "HTTP_CALLS": "⇒", "HANDLED_BY": "⇒", "QUEUE_FLOWS": "⇥",
              "EVENT_FLOWS": "↯", "INJECTS": "⊕", "ACCESSES_DATA": "⊟", "TESTS": "✓"}


@mcp.tool(annotations=ToolAnnotations(title="Trace", read_only_hint=True))
def trace(
    from_node: Annotated[str, Field(description="A feature/keyword to trace end-to-end (one arg), OR the start node when tracing a path to `to_node`.")],
    to_node: Annotated[str, Field(description="Optional target node. Given → shortest path from_node→to_node. Blank → trace `from_node` as a feature across the stack.", default="")] = "",
    depth: Annotated[int, Field(description="Max hops for the cross-stack feature trace. Default 6.", default=6, ge=1, le=12)] = 6,
    budget: Annotated[int, Field(description="Max chars in the result. 0 = no cap.", default=0, ge=0)] = 0,
) -> str:
    """Follow the code across boundaries. One argument: trace a feature end-to-end — the ordered path from entry through the stack, each hop labelled with its mechanism (call / HTTP / queue / event / data), crossing service boundaries (frontend→backend). Two arguments: the shortest path between two specific nodes, hop by hop. This is where the graph beats reading many files — it knows the cross-stack links grep can't see."""
    g = get_graph()

    if to_node.strip():
        return _trace_path(g, from_node, to_node, budget)

    # Feature trace via the engine's cross-stack tracer. It raises when the
    # feature resolves to no node — treat that as "no cross-stack path" and fall
    # through to the flow fallback below.
    feature = from_node.strip()
    try:
        env = g.pygraph.cross_stack_trace(feature, depth)
    except (ValueError, RuntimeError):
        env = None
    hops = (env.get("hops") or []) if isinstance(env, dict) else []
    if hops:
        return _truncate(_render_trace(feature, env, hops), budget, "trace")

    # Fall back to the wrapper's flow layering (entry-point keyword → downstream).
    flow_nodes = g.nodes_for_feature(feature.lower())
    if not flow_nodes:
        available = ", ".join(sorted(g.flows.keys())[:30])
        return _render_absence(
            env.get("absence") if isinstance(env, dict) else None,
            f"No trace found for '{feature}'. It matched no cross-stack path and no entry "
            f"point. Available entry points: {available}")
    return _truncate(_render_nodes_layered(feature, flow_nodes[:30], g), budget, "trace")


def _render_hop(h: dict, indent: str = "    ") -> str:
    """One `from -> [mechanism] to` hop, located and boundary-marked."""
    mech = h.get("mechanism", "")
    arrow = _MECH_ICON.get(mech, "→")
    xs = ""
    if h.get("cross_repo"):
        xs = "  ⧉ cross-repo"
    elif h.get("cross_service"):
        xs = "  ⧉ cross-service"
    to_kind = str(h.get("to_kind", "")).lower()
    loc = _eloc({"file": h.get("to_file"), "line": h.get("to_line")})
    live = _elive({"live": h.get("to_live")})
    return (f"{indent}{h.get('from_qname', '?')}\n"
            f"{indent}  {arrow} [{mech}] {h.get('to_qname', '?')}  [{to_kind}]{loc}{live}{xs}")


def _seed_label(val) -> str:
    """`seed` / `target` are located node records, not strings."""
    if isinstance(val, dict):
        return str(val.get("qname") or val.get("name") or "?")
    return str(val or "")


def _render_trace(feature: str, env: dict, hops: list[dict]) -> str:
    """Render an engine cross-stack trace.

    `paths` is the answer whenever the engine produced one — ranked distinct
    routes, and with `to=` set it's the actual A→B path. `hops` is the whole
    explored set, so it's only the fallback when there are no paths."""
    head = f"  Trace: {feature}"
    seed = _seed_label(env.get("seed"))
    if seed and seed != feature:
        head += f"  (seed {seed})"
    target = _seed_label(env.get("target"))
    if target:
        head += f"  → {target}"
    resolved_by = env.get("resolved_by") or ""
    if resolved_by:
        head += f"  [resolved by {resolved_by}]"

    paths = env.get("paths") or []
    lines = [head, ""]
    if paths:
        for pth in paths:
            p_hops = pth.get("hops") or []
            lines.append(f"  path {pth.get('rank', '?')}  ({len(p_hops)} hops)")
            for h in p_hops:
                lines.append(_render_hop(h, "      "))
            lines.append("")
        if env.get("truncated"):
            lines.append(f"  -- more paths exist; showing the top {len(paths)} by rank")
    else:
        lines[0] = f"{head}  ({len(hops)} hops)"
        for h in hops:
            lines.append(_render_hop(h))
    return "\n".join(lines).rstrip()


def _trace_path(g: RustGraph, from_node: str, to_node: str, budget: int) -> str:
    """Path between two named nodes. The engine's `to=` mode first — it ranks
    real mechanism-labelled paths across the stack — with the structural
    shortest path as the fallback."""
    frm = g.find_node(from_node)
    to = g.find_node(to_node)
    if not frm:
        return f"Node not found: '{from_node}'"
    if not to:
        return f"Node not found: '{to_node}'"

    try:
        env = g.pygraph.cross_stack_trace(frm["qname"], 12, to["qname"], 10)
    except (ValueError, RuntimeError):
        env = None
    if isinstance(env, dict) and (env.get("hops") or env.get("paths")):
        return _truncate(
            _render_trace(f"{frm['name']} -> {to['name']}", env, env.get("hops") or []),
            budget, "trace")

    path = g.shortest_path(frm["id"], to["id"])
    if path is None:
        return _render_absence(
            env.get("absence") if isinstance(env, dict) else None,
            f"No path between {frm['name']} and {to['name']}")

    lines = [f"  Trace: {frm['name']} -> {to['name']} ({len(path)} hops)", ""]
    prev_tier = None
    for i, node in enumerate(path):
        icon = _kind_icon(_effective_kind(node))
        tier = _classify_tier(node)
        conf = _confidence_icon(node.get("confidence", "medium"))
        if tier != prev_tier:
            if prev_tier is not None:
                lines.append("      |")
                lines.append("      v")
            lines.append(f"  [{tier}]")
            prev_tier = tier
        arrow = "  -> " if i > 0 else "     "
        lines.append(f"  {arrow}{icon} {conf} {node['name']}  "
                     f"[{_effective_kind(node)}]{_loc(node)}{_elive(node)}")
    return _truncate("\n".join(lines), budget, "trace")


# ─────────────────────────────────────────────────────────────────────────────
# read — exact source for one or more nodes (batch)
# ─────────────────────────────────────────────────────────────────────────────


# node_cells (glia-py) — structured facets beyond the source span. `read`
# surfaces the high-value ones: HTTP method, cross-stack callers (ENDPOINT_HIT),
# covering tests (TEST), and semantic cells (intent/decision/constraint/failure).
try:
    _CELL_TYPE_NAMES = {i: n for i, n in glia_py.cell_type_names()}
except Exception:
    _CELL_TYPE_NAMES = {}

# Friendly names for the cells worth showing under a read. The ids come from the
# engine's own `cell_type_names()` table (never hand-kept) — this map only
# renames them and picks which ones surface. A cell the engine adds shows up
# under its own table name as soon as it's listed in _READ_CELL_TYPES.
_CELL_LABEL_OVERRIDES = {
    "ROUTE_METHOD": "method", "ENDPOINT_HIT": "called by (cross-stack)",
    "TEST": "tested by", "INTENT": "intent", "DECISION": "decision",
    "CONSTRAINT": "constraint", "FAIL": "failure mode", "ATTN": "attention",
    "IMPORTS": "imports", "CONV": "notes", "COVERAGE": "test coverage",
    "ENTRYPOINT": "declared entry point", "DOC_TAGS": "doc tags",
    "SCHEMA_FIELDS": "fields", "ACCESS_MODE": "access",
}
_READ_CELL_TYPES = set(_CELL_LABEL_OVERRIDES)

# VECTOR is a Bytes payload — `node_cells` returns "" for it, so never show it.
_SKIP_CELL_TYPES = {"VECTOR"}

_READ_CELL_LABELS = {
    tid: _CELL_LABEL_OVERRIDES.get(name, name.lower().replace("_", " "))
    for tid, name in _CELL_TYPE_NAMES.items()
    if name in _READ_CELL_TYPES and name not in _SKIP_CELL_TYPES
}


def _cell_text(name: str, content: str) -> str:
    """Flatten a cell payload for the `context:` footer.

    Several payloads became JSON objects/arrays in glia 0.5.0 — rendering the raw
    JSON would just get truncated mid-object, so pull the fields that carry the
    meaning."""
    raw = str(content).strip()
    if not raw or raw in ("[]", "{}"):
        return ""
    if raw[0] not in "[{":
        return " ".join(raw.split())
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return " ".join(raw.split())

    if name == "TEST" and isinstance(data, dict):
        tests = [t.get("test", "?") for t in (data.get("tests") or [])]
        total = data.get("total", len(tests))
        return f"{total}: " + ", ".join(tests[:6]) if tests else ""
    if name == "COVERAGE" and isinstance(data, dict):
        hit, total = data.get("hit"), data.get("lines")
        src = data.get("source", "")
        if hit is not None and total:
            return f"{hit}/{total} lines ({100 * hit // total}%){f' via {src}' if src else ''}"
    if name == "ENTRYPOINT" and isinstance(data, dict):
        return " ".join(str(data.get(k)) for k in ("decl", "pattern", "source")
                        if data.get(k))
    if name in ("DECISION", "CONSTRAINT", "FAIL") and isinstance(data, list):
        out = []
        for e in data[:3]:
            if not isinstance(e, dict):
                continue
            # FAIL: `message`/`role` are the readable pair; title/text for the rest.
            head = e.get("title") or e.get("message") or ""
            body = e.get("text") or e.get("role") or ""
            out.append(" — ".join(x for x in (head, body) if x) or json.dumps(e))
        return " | ".join(out)
    if isinstance(data, list):
        return ", ".join(
            x if isinstance(x, str) else json.dumps(x) for x in data[:8])
    if isinstance(data, dict):
        return " ".join(f"{k}={v}" for k, v in list(data.items())[:6])
    return " ".join(raw.split())


def _node_context(g: RustGraph, node_id: int, per_cell: int = 400) -> str:
    """High-value `node_cells` facets shown under a read — method, cross-stack
    callers, covering tests, semantic cells. '' when the node has none."""
    try:
        cells = g.pygraph.node_cells(node_id)
    except Exception:
        return ""
    rows = []
    for tid, content in cells:
        label = _READ_CELL_LABELS.get(tid)
        if not label:
            continue
        text = _cell_text(_CELL_TYPE_NAMES.get(tid, ""), content)
        if not text:
            continue
        if len(text) > per_cell:
            text = text[:per_cell] + " …"
        rows.append(f"    · {label}: {text}")
    return ("\n  context:\n" + "\n".join(rows)) if rows else ""


def _governing_docs_note(g: RustGraph, qname: str) -> str:
    """Doc sections that DOCUMENT this symbol (engine `governing_docs`) — 'the
    rules for X'. '' when nothing governs it or the repo has no ingested docs."""
    try:
        recs = _rows(g.pygraph.governing_docs(qname))
    except Exception:
        return ""
    if not recs:
        return ""
    rows = [f"    · {r.get('name') or r.get('qname', '?')}{_eloc(r)}" for r in recs[:5]]
    return "\n  governed by (docs):\n" + "\n".join(rows)


def _read_one(g: RustGraph, node: str, context_lines: int) -> str:
    """Source block for a single node, or a one-line reason it can't be read."""
    resolved = g.find_node(node)
    if not resolved:
        return f"Node not found: '{node}'"

    ctx = _node_context(g, resolved["id"]) + _governing_docs_note(g, resolved["qname"])
    path = resolved.get("path")
    start = resolved.get("start_line")
    end = resolved.get("end_line") or start
    if not path or not start:
        # No source span (a synthetic / cross-stack node — route, endpoint, data
        # entity). Still surface its structural cells (method, callers, tests).
        head = f"  {resolved['qname']}  [{_effective_kind(resolved)}]  (no source span)"
        return head + ctx if ctx else (
            f"{resolved['name']} has no source span (synthetic or cross-stack node) "
            f"— nothing to read.")

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
        f"  {resolved['qname']}  [{_effective_kind(resolved)}]\n"
        f"  {path}:{start}-{end}\n"
    )
    return f"{header}\n```\n{snippet}\n```" + ctx


@mcp.tool(annotations=ToolAnnotations(title="Read Source", read_only_hint=True))
def read(
    node: Annotated[str, Field(description="Node name or qname to read. Comma-separate several (e.g. the top-ranked nodes from `find`/`impact`) to slice them all in one call.")],
    context_lines: Annotated[int, Field(description="Lines of padding above and below the node's span. Default 0.", default=0, ge=0, le=200)] = 0,
    budget: Annotated[int, Field(description="Max chars in the result (shared across all nodes when several are given). 0 = no cap.", default=0, ge=0)] = 0,
) -> str:
    """Return the source code for one or more nodes, sliced from their files by the graph's line spans. Use after `find`/`impact` to read the exact code without grepping — comma-separate several node names to read the whole ranked set in a single call. Each node is a code block headed by its qname and `path:start-end`, plus a `context:` footer with structural facts the source alone doesn't show: HTTP method, cross-stack callers, covering tests, and intent/decision/constraint cells when present."""
    g = get_graph()
    names = [s.strip() for s in node.split(",") if s.strip()]
    if not names:
        return "No node given."
    blocks = [_read_one(g, name, context_lines) for name in names]
    return _truncate("\n\n".join(blocks), budget, "source")


# ─────────────────────────────────────────────────────────────────────────────
# refresh — (re)build the graph
#   (subsumes: generate, reload)
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool(annotations=ToolAnnotations(title="Refresh Graph", read_only_hint=False, open_world_hint=True))
def refresh(
    repo_path: Annotated[str, Field(description="Path or git URL to (re)scan. Blank = the repo the server is serving. A different path/URL retargets the server at it.", default="")] = "",
    full: Annotated[bool, Field(description="Force a full reparse instead of reusing the per-file parse cache. Default False (incremental — only changed files re-parse, so this is cheap after edits).", default=False)] = False,
) -> str:
    """(Re)build the structural graph with tree-sitter AST parsing across 20 languages, running the cross-stack resolvers (HTTP, gRPC, GraphQL, WebSocket, queues, events, CLI). Incremental by default — only changed files re-parse — so it's cheap to call after edits; set `full=true` to force a clean reparse. Accepts a local path or a git URL (cloned on demand). Call after a major refactor; routine edits are picked up automatically by the file watcher."""
    try:
        target = _resolve_repo(repo_path or REPO_PATH)
        g = _build_graph(target, incremental=not full)
    except Exception as e:
        return f"Refresh failed: {e}"

    pg = g.pygraph
    kind_counts: dict[str, int] = Counter(n["kind"] for n in g.nodes.values())
    type_summary = ", ".join(f"{count} {k}" for k, count in kind_counts.most_common(8))
    return (
        f"{'Rebuilt' if not full else 'Rebuilt (full reparse)'}: {pg.node_count()} nodes, "
        f"{pg.edge_count()} edges, {pg.cross_edge_count()} cross-stack edges, "
        f"{len(g.flows)} entry points\n"
        f"Kinds: {type_summary}\n"
        f"Engine: glia-py {glia_py.version()}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Rendering helpers
# ─────────────────────────────────────────────────────────────────────────────

# Straight from the engine's entry table (glia 0.5.0 / LD.6) — the same set
# liveness seeds from, so the wrapper can't drift from it the way the old
# hand-kept literal did (it was missing grpc_server, rpc_procedure, component).
_ENTRY_KINDS = ENTRY_KIND_NAMES
_SERVICE_KINDS = {"module", "package"}
_HANDLER_KINDS = {"function", "method", "class", "struct", "interface", "enum",
                  "component", "hook", "service", "directive", "pipe", "guard",
                  "composable", "attribute"}
_DATA_KINDS = {"endpoint", "grpc_client", "queue_producer", "graphql_operation",
               "ws_client", "event_emitter", "cli_invocation",
               "database", "cache", "blob_store", "search_index", "email_service",
               "data_entity", "config_key", "infra_resource", "package_dep"}


def _record_kind(g: RustGraph, rec: dict) -> str:
    """Display kind for an ENGINE answer record.

    The records carry `kind` but not `roles`, so a declared component or service
    would render as the bare CLASS/FUNCTION it is now. Look the node up by id to
    recover its role — the label that actually means something."""
    node = g.nodes.get(rec.get("id"))
    if node is not None and node.get("roles"):
        return _effective_kind(node)
    return str(rec.get("kind", "?")).lower()


def _effective_kind(node: dict) -> str:
    """What a node *acts as*, for tiering and icons.

    Since glia 0.5.0 a component / service / hook / directive / pipe / guard /
    composable with a declaration twin is a plain CLASS or FUNCTION carrying a
    ROLE cell, surfaced as `roles`. The role is the meaningful label, so it wins
    over the bare kind; the role vocabulary is the same words the kinds used."""
    roles = node.get("roles") or []
    if roles:
        return str(roles[0]).lower()
    return str(node.get("kind", "?")).lower()


def _classify_tier(node: dict) -> str:
    """Tier a node dict. `entry` is the engine's own flag (it also honours
    entrypoints declared in `.glia/overlay.toml`), so it decides first."""
    if node.get("entry"):
        return "ENTRY"
    kind = _effective_kind(node)
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


def _loc(node: dict) -> str:
    """`  path:start-end` suffix for a WRAPPER node dict (blank if no span)."""
    path = node.get("path")
    if not path:
        return ""
    start = node.get("start_line")
    if not start:
        return f"  {path}"
    end = node.get("end_line") or start
    span = f"{start}-{end}" if end and end != start else f"{start}"
    return f"  {path}:{span}"


def _eloc(rec: dict) -> str:
    """`  file:line` suffix for an ENGINE record (blast_radius/resolve/find/trace
    carry `file`/`line` from the engine's own locator — no wrapper path-guessing).

    Every answer record's `line` is 1-based since glia 0.5.0 (LD.1), matching
    `nodes_json` spans, so the test is explicitly `is not None` — the old
    truthiness test silently dropped a legitimate line."""
    f = rec.get("file")
    if not f:
        return ""
    line = rec.get("line")
    return f"  {f}:{line}" if line is not None else f"  {f}"


def _elive(rec: dict) -> str:
    """` ⊘` when the engine flags a record not reachable from an entry point.

    Liveness is the engine's `entrypoint_reachable` (only present on records that
    carry it, e.g. blast_radius). Absent `live` key → no marker (unknown, not dead)."""
    return " ⊘" if rec.get("live") is False else ""


def _node_record(g: RustGraph, node: dict) -> dict:
    """Project a wrapper node dict into the engine-record shape the located/impact
    renderers consume (so keyword hits render like resolve/blast_radius rows)."""
    return {
        "id": node["id"],
        "qname": node.get("qname", ""),
        "name": node.get("name", "?"),
        "kind": _effective_kind(node),
        "file": node.get("path"),
        "line": node.get("start_line"),
        "live": node.get("live"),
    }


def _coverage_note(g: RustGraph) -> str:
    """Compact blind-spot footer from the engine's `coverage()` — where extraction
    is partial for the languages actually in this repo, so the agent falls back to
    grep deliberately (P2). '' when the engine build predates coverage."""
    try:
        recs = _rows(g.pygraph.coverage())
    except Exception:
        return ""
    if not recs:
        return ""
    lines = ["", "  Blind spots (verify these with grep — the graph may under-link them):"]
    for r in recs[:8]:
        lang = r.get("language", "*")
        cat = r.get("edge_category", "?")
        found = r.get("edges_found")
        zero = "  [0 found]" if found == 0 else ""
        note = r.get("note", "")
        lines.append(f"    ⚠ {cat} ({lang}){zero}: {note}")
    return "\n".join(lines)


def _render_overview(g: RustGraph) -> str:
    kind_counts = Counter(n["kind"] for n in g.nodes.values())
    conf_counts = Counter(n["confidence"] for n in g.nodes.values())

    lines = [
        "  repo-graph",
        "  " + "=" * 40,
        "",
        f"  {g.pygraph.node_count()} nodes, {g.pygraph.edge_count()} edges, "
        f"{g.pygraph.cross_edge_count()} cross-stack",
        f"  Engine: glia-py {glia_py.version()} (Rust + tree-sitter)",
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
            flow = g.flows[f]
            entry = flow.get("entry") or {}
            kind = str(entry.get("kind", "?")).lower()
            icon = _kind_icon(kind)
            xs = "  ⧉ cross-service" if flow.get("cross_service") else ""
            reach = flow.get("reach")
            reach_s = f"  ·{reach} reached" if isinstance(reach, int) else ""
            lines.append(f"    {icon} {f}  [{kind}]{reach_s}{xs}")
        if len(flow_list) > 20:
            lines.append(f"    ... and {len(flow_list) - 20} more")

    cov = _coverage_note(g)
    if cov:
        lines.append(cov)

    lines.append("")
    lines.append("  Next: `find <symbol|stacktrace|diff>` to jump to nodes, `impact <node>` for "
                 "blast radius, `trace <feature>` for flows, `orient <node>` / `orient full=true` "
                 "for the map.")

    return "\n".join(lines)


def _render_nodes_layered(feature: str, nodes: list[dict], g: RustGraph) -> str:
    tiers: dict[str, list[dict]] = {"ENTRY": [], "SERVICE": [], "HANDLER": [], "DATA": []}
    for node in nodes:
        tiers[_classify_tier(node)].append(node)

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
            icon = _kind_icon(_effective_kind(node))
            conf = _confidence_icon(node.get("confidence", "medium"))
            lines.append(f"    {icon} {conf} {node['name']}  "
                         f"[{_effective_kind(node)}]{_loc(node)}{_elive(node)}")
        if len(items) > 10:
            lines.append(f"    ... and {len(items) - 10} more")
        rendered_any = True

    lines.append("")
    lines.append(f"  -- {len(nodes)} nodes in flow")
    return "\n".join(lines)


def main():
    import argparse

    # `repo-graph install` / `repo-graph uninstall` (also via `uvx mcp-repo-graph
    # install`) route to the installer before the server's own arg parsing. Any
    # other invocation starts the MCP server as normal.
    argv = sys.argv[1:]
    if argv and argv[0] in ("install", "uninstall"):
        from .installer import main as installer_main
        raise SystemExit(installer_main(argv))

    parser = argparse.ArgumentParser(description="repo-graph MCP server")
    parser.add_argument(
        "--repo",
        default=os.environ.get("REPO_GRAPH_REPO", os.getcwd()),
        help="Path to the target repository, or a git URL to clone and map",
    )
    args = parser.parse_args()

    global REPO_PATH
    # Resolve a git URL to a local clone once at startup, so every tool sees a real
    # directory — not just the lazy get_graph path.
    REPO_PATH = _resolve_repo(args.repo)
    os.environ["REPO_GRAPH_REPO"] = REPO_PATH

    # Live freshness: watch the repo and incrementally rebuild on edits, unless
    # disabled (REPO_GRAPH_WATCH=0) or watchdog isn't installed.
    if os.environ.get("REPO_GRAPH_WATCH", "1") != "0":
        from .watcher import start_watcher
        if start_watcher(REPO_PATH, _watch_rebuild) is not None:
            print(f"[watch] watching {REPO_PATH} for changes", file=sys.stderr)

    mcp.run()


if __name__ == "__main__":
    main()
