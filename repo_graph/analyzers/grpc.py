"""
gRPC entrypoint analyzer.

Cross-cutting analyzer that parses `.proto` files to emit:
  - `grpc_service` nodes   (one per `service Foo { ... }` block)
  - `grpc_method` nodes    (one per `rpc Name(Req) returns (Resp);`)
  - `contains` edges       (service → method)
  - `handled_by` edges     (method → file anchor of the .proto file)

Flow kind `grpc` is applied automatically by the generator's auto-flow
pass (treats `grpc_method` as an entrypoint type).

Detection signal: any `.proto` file in the repo.
"""

from __future__ import annotations

import re
from pathlib import Path

from .base import (
    AnalysisResult,
    Edge,
    LanguageAnalyzer,
    Node,
    read_safe,
    rel_path,
)


_SERVICE_RE = re.compile(r"service\s+(\w+)\s*\{([^}]*)\}", re.DOTALL)
_RPC_RE = re.compile(
    r"rpc\s+(\w+)\s*\(\s*(?:stream\s+)?[\w.]+\s*\)\s*returns\s*\(\s*(?:stream\s+)?[\w.]+\s*\)",
)


def _svc_id(service: str, file_rel: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", file_rel).strip("_")
    return f"grpc_svc_{service}__{slug}"


def _method_id(service_id: str, method: str) -> str:
    return f"{service_id}__{method}"


class GrpcAnalyzer(LanguageAnalyzer):
    """Cross-cutting gRPC analyzer — runs whenever .proto files exist."""

    @staticmethod
    def detect(index) -> bool:
        return bool(index.files_with_ext(".proto"))

    def scan(self) -> AnalysisResult:
        nodes: list[Node] = []
        edges: list[Edge] = []
        seen: set[str] = set()

        for proto in self.index.files_with_ext(".proto"):
            content = read_safe(proto)
            if not content:
                continue
            file_rel = rel_path(self.repo_root, proto)
            for sm in _SERVICE_RE.finditer(content):
                svc_name = sm.group(1)
                body = sm.group(2)
                sid = _svc_id(svc_name, file_rel)
                if sid in seen:
                    continue
                seen.add(sid)
                nodes.append(Node(
                    id=sid, type="grpc_service",
                    name=svc_name, file_path=file_rel,
                ))
                for rm in _RPC_RE.finditer(body):
                    mname = rm.group(1)
                    mid = _method_id(sid, mname)
                    if mid in seen:
                        continue
                    seen.add(mid)
                    nodes.append(Node(
                        id=mid, type="grpc_method",
                        name=f"{svc_name}.{mname}", file_path=file_rel,
                    ))
                    edges.append(Edge(from_id=sid, to_id=mid, type="contains"))
                    edges.append(Edge(
                        from_id=mid, to_id=f"file::{file_rel}",
                        type="handled_by",
                    ))

        state = self._state(nodes)
        return AnalysisResult(nodes=nodes, edges=edges, state_sections=state)

    def _state(self, nodes: list[Node]) -> dict[str, str]:
        svcs = [n for n in nodes if n.type == "grpc_service"]
        methods = [n for n in nodes if n.type == "grpc_method"]
        if not svcs and not methods:
            return {}
        return {
            "gRPC": f"{len(svcs)} services, {len(methods)} methods\n",
        }
