#!/usr/bin/env python3
"""Call a repo-graph tool and print its output — the demo's right-pane engine.

Usage: DEMO_REPO=/path rg.py <tool> [args...]
Loads the cached .gmap (fast) so each call is sub-second after a warm-up.
"""
import os
import sys

os.environ.setdefault("REPO_GRAPH_REPO", os.environ.get("DEMO_REPO", os.getcwd()))
import repo_graph.server as s  # noqa: E402

tool, *args = sys.argv[1:]
print(getattr(s, tool)(*args))
