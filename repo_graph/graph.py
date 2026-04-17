"""
Graph wrapper around PyGraph (Rust engine).

Parses nodes_json/edges_json from the Rust PyGraph into Python dicts,
builds adjacency lists, and provides BFS traversal for MCP tools.
"""

import json
from collections import defaultdict
from pathlib import Path


KIND_NAMES = {
    1: "module", 2: "class", 3: "function", 4: "method",
    5: "route", 6: "package", 7: "interface", 8: "struct",
    9: "endpoint", 10: "enum",
    11: "grpc_service", 12: "grpc_client", 13: "queue_consumer", 14: "queue_producer",
    15: "graphql_resolver", 16: "graphql_operation", 17: "ws_handler", 18: "ws_client",
    19: "event_handler", 20: "event_emitter", 21: "cli_command", 22: "cli_invocation",
}

CATEGORY_NAMES = {
    1: "defines", 2: "contains", 3: "imports", 4: "calls", 5: "uses",
    6: "documents", 7: "tests", 8: "injects",
    9: "handled_by", 10: "http_calls",
    11: "grpc_calls", 12: "queue_flows", 13: "graphql_calls", 14: "ws_connects",
    15: "event_flows", 16: "shares_schema", 17: "cli_invokes",
}

ENTRY_KINDS = {5, 11, 13, 15, 17, 19, 21}  # route, grpc_service, queue_consumer, graphql_resolver, ws_handler, event_handler, cli_command


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

    def neighbours(self, node_id: int) -> dict:
        out = [
            {"node": self.nodes.get(nid, {"id": nid, "kind": "?", "name": str(nid)}), "edge": cat}
            for nid, cat in self.adjacency_out.get(node_id, [])
        ]
        inc = [
            {"node": self.nodes.get(nid, {"id": nid, "kind": "?", "name": str(nid)}), "edge": cat}
            for nid, cat in self.adjacency_in.get(node_id, [])
        ]
        return {"outbound": out, "inbound": inc}

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

    # -- File sizes --

    def file_line_count(self, qname: str) -> int:
        parts = qname.replace("::", "/")
        candidates = [
            self.repo_path / f"{parts}.py",
            self.repo_path / f"{parts}.go",
            self.repo_path / f"{parts}.ts",
            self.repo_path / f"{parts}.tsx",
            self.repo_path / f"{parts}.rs",
        ]
        for p in candidates:
            if p.is_file():
                try:
                    return sum(1 for _ in p.open(encoding="utf-8", errors="ignore"))
                except OSError:
                    return 0
        return 0
