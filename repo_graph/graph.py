"""
Graph wrapper around PyGraph (Rust engine).

Parses nodes_json/edges_json from the Rust PyGraph into Python dicts,
builds adjacency lists, and provides BFS traversal for MCP tools.
"""

import json
from collections import defaultdict
from pathlib import Path

import repo_graph_py


# Kind / edge-category id -> name, pulled live from the engine's canonical decode
# tables (repo-graph-py >= 0.4.15) so the wrapper never drifts from glia's
# code-domain registry. Names are lowercased to match the wrapper's tier sets and
# icons (server.py). Unknown ids fall back to kind_NN / cat_NN at lookup time.
KIND_NAMES = {i: n.lower() for i, n in repo_graph_py.kind_names()}
CATEGORY_NAMES = {i: n.lower() for i, n in repo_graph_py.category_names()}

# Kinds that start a flow (anything that triggers code execution). Hand-kept: the
# decode tables give names, not entry/tier semantics. Mirrors glia code-domain ids
# — route, grpc_service, queue_consumer, graphql_resolver, ws_handler,
# event_handler, cli_command, cron_job.
ENTRY_KINDS = {5, 11, 13, 15, 17, 19, 21, 37}


class RustGraph:
    """Wraps PyGraph with adjacency lists and traversal."""

    def __init__(self, pygraph, repo_path: str):
        self.pygraph = pygraph
        self.repo_path = Path(repo_path)
        self.nodes: dict[int, dict] = {}
        self.adjacency_out: dict[int, list[tuple[int, str]]] = defaultdict(list)
        self.adjacency_in: dict[int, list[tuple[int, str]]] = defaultdict(list)
        self.flows: dict[str, list[dict]] = {}
        self._build_indices()
        self._build_flows()

    def _build_indices(self):
        for n in json.loads(self.pygraph.nodes_json()):
            self.nodes[n["id"]] = {
                "id": n["id"],
                "kind": KIND_NAMES.get(n["kind"], f"kind_{n['kind']}"),
                "kind_id": n["kind"],
                "name": n["name"],
                "qname": n["qname"],
                "confidence": n["confidence"],
                # Source span (repo-graph-py >= 0.4.16, GR-1). None for synthetic
                # / cross-stack nodes that have no file location.
                "path": n.get("path"),
                "start_line": n.get("start_line"),
                "end_line": n.get("end_line"),
            }
        for e in json.loads(self.pygraph.edges_json()):
            cat = CATEGORY_NAMES.get(e["category"], f"cat_{e['category']}")
            self.adjacency_out[e["from"]].append((e["to"], cat))
            self.adjacency_in[e["to"]].append((e["from"], cat))

    def _build_flows(self):
        for node in self.nodes.values():
            if node["kind_id"] not in ENTRY_KINDS:
                continue
            path = self.downstream(node["id"], depth=6)
            if len(path) < 2:
                continue
            key = node["name"].lower().replace(" ", "_")
            self.flows[key] = [node] + path

    # -- Traversal --

    def downstream(self, node_id: int, depth: int = 3) -> list[dict]:
        return self._traverse(node_id, depth, "out")

    def upstream(self, node_id: int, depth: int = 3) -> list[dict]:
        return self._traverse(node_id, depth, "in")

    def _traverse(self, start: int, depth: int, direction: str) -> list[dict]:
        adj = self.adjacency_out if direction == "out" else self.adjacency_in
        visited: set[int] = set()
        result = []
        queue = [(start, 0)]
        while queue:
            node_id, d = queue.pop(0)
            if node_id in visited or d > depth:
                continue
            visited.add(node_id)
            node = self.nodes.get(node_id)
            if node and node_id != start:
                result.append({**node, "depth": d})
            if d < depth:
                for nid, _ in adj.get(node_id, []):
                    if nid not in visited:
                        queue.append((nid, d + 1))
        return result

    def shortest_path(self, from_id: int, to_id: int) -> list[dict] | None:
        if from_id not in self.nodes or to_id not in self.nodes:
            return None
        visited = {from_id}
        queue = [(from_id, [from_id])]
        while queue:
            current, path = queue.pop(0)
            if current == to_id:
                return [self.nodes[nid] for nid in path]
            nbrs: set[int] = set()
            for nid, _ in self.adjacency_out.get(current, []):
                nbrs.add(nid)
            for nid, _ in self.adjacency_in.get(current, []):
                nbrs.add(nid)
            for nid in nbrs:
                if nid not in visited:
                    visited.add(nid)
                    queue.append((nid, path + [nid]))
        return None

    # -- Lookups --

    def find_node(self, query: str) -> dict | None:
        nid = self.pygraph.find_node(query)
        if nid is not None:
            return self.nodes.get(nid)
        ids = self.pygraph.find_nodes_by_qname(query)
        if ids:
            return self.nodes.get(ids[0])
        q = query.lower()
        for node in self.nodes.values():
            if q in node["name"].lower() or q in node["qname"].lower():
                return node
        return None

    def find_nodes(self, query: str) -> list[dict]:
        ids = self.pygraph.find_nodes_by_qname(query)
        return [self.nodes[nid] for nid in ids if nid in self.nodes]

    # Liveness / dead-code is now the engine's: blast_radius records carry a
    # `live` flag from `entrypoint_reachable` (correct once INJECTS/dynamic edges
    # exist). The wrapper no longer re-derives it. See dev-notes reverse-handoff §5.

    def nodes_for_feature(self, feature: str) -> list[dict]:
        slug = feature.lower().replace("-", "_").replace(" ", "_")
        if slug in self.flows:
            return self.flows[slug]
        for key, nodes in self.flows.items():
            if slug in key or key in slug:
                return nodes
        results = self.find_nodes(feature)
        if results:
            return self.downstream(results[0]["id"], depth=6)
        return []
