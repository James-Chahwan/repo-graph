#!/usr/bin/env python3
"""MCP shim that serves repo-graph's real tools in one of two arms.

    ARM=full  pass the engine's answer through untouched
    ARM=bare  replace a structured absence with a flat "No results."

Everything else is identical: same engine, same graph, same ranking, same
`path:line` on every row. The only variable is what an *empty* answer looks
like, which is the thing being measured.
"""
import os
import re
import sys

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import repo_graph.server as rg  # noqa: E402

ARM = os.environ.get("ARM", "full")
mcp = MCPServer("repo-graph", instructions=rg.mcp.instructions)

#: what the wrapper printed before 0.5.0 gave absences a shape
_BARE = "No results."


def strip(text: str) -> str:
    """In the bare arm, collapse any structured absence to a flat empty answer."""
    if ARM != "bare" or not text:
        return text
    if text.lstrip().startswith("No answer ("):
        return _BARE
    # trace/orient fall back to prose that still explains itself; flatten those too
    if re.match(r"\s*No (trace|nodes|answer)", text):
        return _BARE
    return text


def _wrap(fn):
    def inner(*a, **k):
        return strip(fn(*a, **k))
    inner.__name__ = fn.__name__
    inner.__doc__ = fn.__doc__
    inner.__annotations__ = getattr(fn, "__annotations__", {})
    inner.__signature__ = __import__("inspect").signature(fn)
    return inner


for name, title, ro in [("orient", "Orient", True), ("find", "Find Nodes", True),
                        ("impact", "Impact / Blast Radius", True), ("trace", "Trace", True),
                        ("read", "Read Source", True), ("refresh", "Refresh Graph", False)]:
    mcp.tool(annotations=ToolAnnotations(title=title, read_only_hint=ro))(_wrap(getattr(rg, name)))

if __name__ == "__main__":
    print(f"[shim] ARM={ARM} repo={os.environ.get('REPO_GRAPH_REPO')}", file=sys.stderr)
    mcp.run()
