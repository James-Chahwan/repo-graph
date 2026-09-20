"""
Graph wrapper around PyGraph (the glia Rust engine).

Holds the node index the renderers need (spans, kinds, roles, liveness) and
forwards every traversal and lookup to the engine. Since glia 0.5.0 the engine
owns find, BFS, shortest-path and entry flows, so this file keeps no adjacency
copy of its own — it is an index and a set of thin forwarders.
"""

import json
from functools import cached_property
from pathlib import Path

import glia_py


# Kind / edge-category id -> name, pulled live from the engine's canonical decode
# tables so the wrapper never drifts from glia's code-domain registry. Names are
# lowercased to match the wrapper's tier sets and icons (server.py). Unknown ids
# fall back to kind_NN / cat_NN at lookup time.
KIND_NAMES = {i: n.lower() for i, n in glia_py.kind_names()}
CATEGORY_NAMES = {i: n.lower() for i, n in glia_py.category_names()}

# Kinds that start a flow, straight from the engine's entry table (`entry_kinds`,
# glia 0.5.0 / LD.6) — the same set liveness seeds from. Never hand-kept: the old
# literal set drifted and was missing GRPC_SERVER, RPC_PROCEDURE and COMPONENT.
ENTRY_KINDS = {i for i, _ in glia_py.entry_kinds()}
ENTRY_KIND_NAMES = {n.lower() for _, n in glia_py.entry_kinds()}


class RustGraph:
    """Node index over PyGraph; traversal and lookup forward to the engine."""

    def __init__(self, pygraph, repo_path: str):
        self.pygraph = pygraph
        self.repo_path = Path(repo_path)
        self.nodes: dict[int, dict] = {}
        self._build_indices()

    def _build_indices(self):
        for n in json.loads(self.pygraph.nodes_json()):
            self.nodes[n["id"]] = {
                "id": n["id"],
                "kind": KIND_NAMES.get(n["kind"], f"kind_{n['kind']}"),
                "kind_id": n["kind"],
                "name": n["name"],
                "qname": n["qname"],
                "confidence": n["confidence"],
                # Source span. None for synthetic / cross-stack nodes.
                "path": n.get("path"),
                "start_line": n.get("start_line"),
                "end_line": n.get("end_line"),
                # glia 0.5.0: the engine's own semantics. `roles` tiers a node
                # (a component/service/hook is now a CLASS/FUNCTION carrying a
                # ROLE cell), `entry` marks an entry point, `live` marks
                # entry-point reachability.
                "roles": n.get("roles") or [],
                "entry": n.get("entry", False),
                "live": n.get("live"),
            }

    # -- Entry flows (engine `entry_flows`, LD.4b) --

    @cached_property
    def entry_flows(self) -> list[dict]:
        """Every entry point's forward flow, from the engine. Lazy: a server that
        only ever answers `find` / `read` never pays for it."""
        try:
            return self.pygraph.entry_flows(6)
        except Exception:
            return []

    @cached_property
    def flows(self) -> dict[str, dict]:
        """`key -> flow` view of `entry_flows`, for name lookup and counts.
        Duplicate keys (the same route in two services) collapse, as before."""
        return {f["key"]: f for f in self.entry_flows if f.get("key")}

    def _flow_nodes(self, flow: dict) -> list[dict]:
        """A flow rendered as node dicts: its entry, then each hop's target.
        Hops carry qname/kind/file/line but no id, so targets are projected
        rather than looked up."""
        entry = flow.get("entry") or {}
        out = [self.nodes.get(entry.get("id")) or {
            "id": entry.get("id"),
            "name": entry.get("name", "?"),
            "qname": entry.get("qname", ""),
            "kind": str(entry.get("kind", "?")).lower(),
            "confidence": "medium",
            "path": entry.get("file"),
            "start_line": entry.get("line"),
            "end_line": None,
            "roles": [], "entry": True, "live": None,
        }]
        for h in flow.get("hops") or []:
            qn = h.get("to_qname", "")
            out.append({
                "id": None,
                "name": qn.split("::")[-1] or qn or "?",
                "qname": qn,
                "kind": str(h.get("to_kind", "?")).lower(),
                "confidence": "medium",
                "path": h.get("to_file"),
                "start_line": h.get("to_line"),
                "end_line": None,
                "roles": [], "entry": False, "live": h.get("to_live"),
            })
        return out

    # -- Traversal (engine `bfs` / `predecessors` / `shortest_path`, LD.3c) --

    def downstream(self, node_id: int, depth: int = 3) -> list[dict]:
        try:
            reached = self.pygraph.bfs(node_id, "out", None, depth)
        except Exception:
            return []
        out = []
        for nid, d, _cat, _parent in reached:
            node = self.nodes.get(nid)
            if node:
                out.append({**node, "depth": d})
        return out

    def upstream(self, node_id: int, depth: int = 3) -> list[dict]:
        try:
            reached = self.pygraph.predecessors(node_id, None, depth)
        except Exception:
            return []
        return [self.nodes[nid] for nid in reached if nid in self.nodes]

    def shortest_path(self, from_id: int, to_id: int) -> list[dict] | None:
        """Shortest path as node dicts, or None when `to_id` isn't reached.
        The engine returns `[(id, category id that entered it)]`."""
        if from_id not in self.nodes or to_id not in self.nodes:
            return None
        try:
            steps = self.pygraph.shortest_path(from_id, to_id, "both", None, 12)
        except Exception:
            return None
        if not steps:
            return None
        out = []
        for nid, cat in steps:
            node = self.nodes.get(nid)
            if node:
                out.append({**node, "via": CATEGORY_NAMES.get(cat) if cat is not None else None})
        return out or None

    # -- Lookups (engine `find`, LD.3b — it replaced find_node/find_nodes_by_qname) --

    def find_records(self, query: str, top_k: int = 20) -> tuple[list[dict], dict | None]:
        """Engine `find` envelope: `(results, absence)`. Results are the engine's
        own located, ranked rows (`match` tier, `live`, `file`, `line`)."""
        try:
            env = self.pygraph.find(query, top_k)
        except Exception:
            return [], None
        if not isinstance(env, dict):
            return [], None
        return list(env.get("results") or []), env.get("absence")

    def find_node(self, query: str) -> dict | None:
        """The single best node for `query`, as a wrapper node dict (so callers
        keep the full span the engine rows don't carry)."""
        results, _ = self.find_records(query, 1)
        if not results:
            return None
        return self.nodes.get(results[0].get("id"))

    def find_nodes(self, query: str, top_k: int = 20) -> list[dict]:
        results, _ = self.find_records(query, top_k)
        return [self.nodes[r["id"]] for r in results
                if r.get("id") in self.nodes]

    # Liveness / dead-code is the engine's: answer records carry `live` from
    # `entrypoint_reachable`, and `nodes_json` carries it per node. The wrapper
    # never re-derives it.

    def nodes_for_feature(self, feature: str) -> list[dict]:
        """Best-effort flow layering for a feature name — the fallback when the
        engine's cross-stack trace finds no path."""
        slug = feature.lower().replace("-", "_").replace(" ", "_")
        flow = self.flows.get(slug)
        if flow is None:
            for key, f in self.flows.items():
                if slug in key or key in slug:
                    flow = f
                    break
        if flow is not None:
            return self._flow_nodes(flow)
        results = self.find_nodes(feature, 1)
        if results:
            return self.downstream(results[0]["id"], depth=6)
        return []
