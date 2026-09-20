#!/usr/bin/env python3
"""Call a repo-graph tool and print its output — the demo's right-pane engine.

Usage: DEMO_REPO=/path rg.py <tool> [positional...] [key=value...]

Loads the cached .gmap (fast) so each call is sub-second after a warm-up. The
`key=value` form exists because the 0.5.0 tools take typed keyword arguments
(`expand=true`, `kind=stacktrace`, `depth=3`) and argv is all strings.
"""
import os
import sys

os.environ.setdefault("REPO_GRAPH_REPO", os.environ.get("DEMO_REPO", os.getcwd()))
import repo_graph.server as s  # noqa: E402


def coerce(v: str):
    """argv is strings; the tools take bool/int. Everything else stays a string."""
    low = v.lower()
    if low in ("true", "false"):
        return low == "true"
    if v.lstrip("-").isdigit():
        return int(v)
    return v


tool, *rest = sys.argv[1:]
args, kwargs = [], {}
for a in rest:
    # only split on '=' when the left side looks like an identifier, so a query
    # containing '=' is still passed through intact
    key, sep, val = a.partition("=")
    if sep and key.isidentifier():
        kwargs[key] = coerce(val)
    else:
        args.append(a)

print(getattr(s, tool)(*args, **kwargs))
