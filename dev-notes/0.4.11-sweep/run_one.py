"""Run generate() on one repo and print JSON result. Isolated per-repo so crashes don't kill the sweep."""
import json
import sys
import time
import traceback
from collections import Counter

import repo_graph_py


def main():
    repo = sys.argv[1]
    result = {"repo": repo}
    t0 = time.time()
    try:
        pg = repo_graph_py.generate(repo)
        nodes = json.loads(pg.nodes_json())
        edges = json.loads(pg.edges_json())
        result["ok"] = True
        result["elapsed_s"] = round(time.time() - t0, 3)
        result["node_count"] = pg.node_count()
        result["edge_count"] = pg.edge_count()
        result["cross_edge_count"] = pg.cross_edge_count()
        result["kind_dist"] = dict(Counter(n["kind"] for n in nodes))
        result["edge_cat_dist"] = dict(Counter(e["category"] for e in edges))
        result["confidence_dist"] = dict(Counter(n.get("confidence", "none") for n in nodes))
    except Exception as e:
        result["ok"] = False
        result["elapsed_s"] = round(time.time() - t0, 3)
        result["error"] = f"{type(e).__name__}: {e}"
        result["traceback"] = traceback.format_exc()[-2000:]
    print(json.dumps(result))


if __name__ == "__main__":
    main()
