"""
Graph data loader and traversal engine.

Reads nodes.json, edges.json, and flows/*.yaml from a target repo's
.ai/repo-graph/ directory. Builds adjacency lists for fast traversal.
"""

import json
import os
from collections import defaultdict
from pathlib import Path


class RepoGraph:
    """Loaded graph of a codebase — nodes, edges, adjacency, flows."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.graph_dir = self.repo_path / ".ai" / "repo-graph"
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.adjacency_out: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self.adjacency_in: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self.flows: dict[str, str] = {}
        self._load()

    def _load(self):
        nodes_path = self.graph_dir / "nodes.json"
        edges_path = self.graph_dir / "edges.json"
        flows_dir = self.graph_dir / "flows"

        if nodes_path.exists():
            raw_nodes = json.loads(nodes_path.read_text())
            for node in raw_nodes:
                self.nodes[node["id"]] = node

        if edges_path.exists():
            self.edges = json.loads(edges_path.read_text())
            for edge in self.edges:
                self.adjacency_out[edge["from"]].append((edge["to"], edge["type"]))
                self.adjacency_in[edge["to"]].append((edge["from"], edge["type"]))

        if flows_dir.exists():
            for flow_file in sorted(flows_dir.glob("*.yaml")):
                self.flows[flow_file.stem] = flow_file.read_text()

    def reload(self):
        """Re-read graph data from disk (e.g. after a regeneration)."""
        self.nodes.clear()
        self.edges.clear()
        self.adjacency_out.clear()
        self.adjacency_in.clear()
        self.flows.clear()
        self._load()

    # -- Traversal --

    def downstream(self, node_id: str, depth: int = 3) -> list[dict]:
        """Fan out from a node following outbound edges, up to depth hops."""
        return self._traverse(node_id, depth, direction="out")

    def upstream(self, node_id: str, depth: int = 3) -> list[dict]:
        """Fan in to a node following inbound edges, up to depth hops."""
        return self._traverse(node_id, depth, direction="in")

    def _traverse(self, start: str, depth: int, direction: str) -> list[dict]:
        adj = self.adjacency_out if direction == "out" else self.adjacency_in
        visited = set()
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
                for neighbour_id, edge_type in adj.get(node_id, []):
                    if neighbour_id not in visited:
                        queue.append((neighbour_id, d + 1))

        return result

    def shortest_path(self, from_id: str, to_id: str) -> list[dict] | None:
        """BFS shortest path between two nodes (undirected)."""
        if from_id not in self.nodes or to_id not in self.nodes:
            return None

        visited = {from_id}
        queue = [(from_id, [from_id])]

        while queue:
            current, path = queue.pop(0)
            if current == to_id:
                return [self.nodes[nid] for nid in path]

            # Check both directions for path finding
            neighbours = set()
            for nid, _ in self.adjacency_out.get(current, []):
                neighbours.add(nid)
            for nid, _ in self.adjacency_in.get(current, []):
                neighbours.add(nid)

            for nid in neighbours:
                if nid not in visited:
                    visited.add(nid)
                    queue.append((nid, path + [nid]))

        return None

    # -- Lookups --

    def nodes_for_feature(self, feature: str) -> list[dict]:
        """All nodes reachable from a feature's entry point."""
        slug = feature.lower().replace("-", "_").replace(" ", "_")

        # Try common ID patterns for feature entry points
        for prefix in ("ng_page_", "fe_page_", "page_", "module_", "entry_", ""):
            candidate = f"{prefix}{slug}"
            if candidate in self.nodes:
                return self.downstream(candidate, depth=10)

        # Fuzzy fallback — match on node name or id
        page_types = {"ng_page", "fe_page", "frontend_page", "page", "module", "entry_point"}
        for node_id, node in self.nodes.items():
            if slug in node_id.lower() and node["type"] in page_types:
                return self.downstream(node_id, depth=10)

        return []

    def nodes_by_type(self, node_type: str) -> list[dict]:
        """All nodes of a given type."""
        return [n for n in self.nodes.values() if n["type"] == node_type]

    def find_node(self, query: str) -> dict | None:
        """Find a node by exact ID or fuzzy name match."""
        if query in self.nodes:
            return self.nodes[query]
        q = query.lower()
        for node in self.nodes.values():
            if q in node["id"].lower() or q in node.get("name", "").lower():
                return node
        return None

    def neighbours(self, node_id: str) -> dict:
        """Direct neighbours in both directions."""
        out = [
            {"node": self.nodes.get(nid, {"id": nid}), "edge": etype}
            for nid, etype in self.adjacency_out.get(node_id, [])
        ]
        inc = [
            {"node": self.nodes.get(nid, {"id": nid}), "edge": etype}
            for nid, etype in self.adjacency_in.get(node_id, [])
        ]
        return {"outbound": out, "inbound": inc}

    # -- File sizes --

    def file_line_count(self, file_path: str) -> int:
        """Count lines in a file relative to repo root."""
        full_path = self.repo_path / file_path
        if not full_path.is_file():
            return 0
        try:
            return sum(1 for _ in full_path.open(encoding="utf-8", errors="ignore"))
        except OSError:
            return 0

    def file_sizes_for_nodes(self, nodes: list[dict]) -> list[dict]:
        """Attach line counts to a list of nodes."""
        seen_paths = set()
        result = []
        for node in nodes:
            fp = node.get("file_path", "")
            if not fp or fp in seen_paths:
                continue
            seen_paths.add(fp)
            lines = self.file_line_count(fp)
            result.append({**node, "lines": lines})
        return result
