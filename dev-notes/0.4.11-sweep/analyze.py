"""Read results.jsonl, produce summary + anomaly report."""
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

RESULTS = Path(__file__).parent / "results.jsonl"

# Kind IDs from rust/code-domain/src/lib.rs
KIND_NAMES = {
    1: "MODULE", 2: "CLASS", 3: "FUNCTION", 4: "METHOD",
    5: "ROUTE", 6: "PACKAGE", 7: "INTERFACE", 8: "STRUCT",
    9: "ENDPOINT", 10: "ENUM",
    11: "GRPC_SERVICE", 12: "GRPC_CLIENT",
    13: "QUEUE_CONSUMER", 14: "QUEUE_PRODUCER",
    15: "GRAPHQL_RESOLVER", 16: "GRAPHQL_OPERATION",
    17: "WS_HANDLER", 18: "WS_CLIENT",
    19: "EVENT_HANDLER", 20: "EVENT_EMITTER",
    21: "CLI_COMMAND", 22: "CLI_INVOCATION",
}
CAT_NAMES = {
    1: "DEFINES", 2: "CONTAINS", 3: "IMPORTS", 4: "CALLS", 5: "USES",
    6: "DOCUMENTS", 7: "TESTS", 8: "INJECTS", 9: "HANDLED_BY",
    10: "HTTP_CALLS", 11: "GRPC_CALLS", 12: "QUEUE_FLOWS",
    13: "GRAPHQL_CALLS", 14: "WS_CONNECTS", 15: "EVENT_FLOWS",
    16: "SHARES_SCHEMA", 17: "CLI_INVOKES",
}


def load():
    records = []
    for line in RESULTS.read_text().splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def summarize(records):
    total = len(records)
    ok = [r for r in records if r.get("ok")]
    clone_fail = [r for r in records if not r.get("ok") and r.get("phase") == "clone"]
    gen_fail = [r for r in records if not r.get("ok") and r.get("phase") != "clone"]

    print(f"=== SUMMARY ({total} repos) ===")
    print(f"  ok:         {len(ok)}")
    print(f"  clone fail: {len(clone_fail)}")
    print(f"  gen fail:   {len(gen_fail)}")
    print()

    if ok:
        nodes = [r["node_count"] for r in ok]
        edges = [r["edge_count"] for r in ok]
        cross = [r.get("cross_edge_count", 0) for r in ok]
        elapsed = [r["elapsed_s"] for r in ok]
        sizes = [r.get("size_mb", 0) for r in ok]
        print("=== DISTRIBUTIONS (ok repos) ===")
        for name, vals in [("nodes", nodes), ("edges", edges), ("cross_edges", cross),
                           ("elapsed_s", elapsed), ("size_mb", sizes)]:
            if vals:
                print(f"  {name:12s} min={min(vals):>8.1f}  median={statistics.median(vals):>8.1f}  "
                      f"p90={sorted(vals)[int(len(vals)*0.9)]:>8.1f}  max={max(vals):>8.1f}")
        print()

    # Anomalies
    print("=== ANOMALIES ===")

    # Empty graphs (likely detection fail)
    empty = [r for r in ok if r.get("node_count", 0) < 10]
    if empty:
        print(f"\n  Near-empty graphs (<10 nodes) — likely language detection miss:")
        for r in sorted(empty, key=lambda r: r["node_count"]):
            print(f"    {r['repo_spec']:45s}  nodes={r['node_count']} edges={r['edge_count']} size={r.get('size_mb')}MB")

    # No cross edges on likely-crossstack repos
    likely_crossstack = {"calcom/cal.com", "medusajs/medusa", "supabase/supabase",
                         "mattermost/mattermost", "chatwoot/chatwoot", "immich-app/immich",
                         "novuhq/novu", "outline/outline", "twentyhq/twenty", "metabase/metabase",
                         "firefly-iii/firefly-iii", "appwrite/appwrite", "saleor/saleor",
                         "strapi/strapi", "keystonejs/keystone"}
    no_cross = [r for r in ok if r["repo_spec"] in likely_crossstack and r.get("cross_edge_count", 0) == 0]
    if no_cross:
        print(f"\n  Fullstack repos with ZERO cross-stack edges (HttpStackResolver miss):")
        for r in no_cross:
            print(f"    {r['repo_spec']:45s}  nodes={r['node_count']} edges={r['edge_count']}")

    # Perf outliers
    slow = sorted([r for r in ok if r["elapsed_s"] > 30], key=lambda r: -r["elapsed_s"])
    if slow:
        print(f"\n  Slow repos (>30s):")
        for r in slow[:20]:
            print(f"    {r['repo_spec']:45s}  {r['elapsed_s']:>6.1f}s  size={r.get('size_mb')}MB  nodes={r['node_count']}")

    # Failures
    if gen_fail:
        print(f"\n  Generate failures:")
        for r in gen_fail:
            err = r.get("error", "")[:200]
            print(f"    {r['repo_spec']:45s}  {err}")
    if clone_fail:
        print(f"\n  Clone failures:")
        for r in clone_fail:
            err = r.get("error", "")[:200]
            print(f"    {r['repo_spec']:45s}  {err}")

    # Cross edges per fullstack repo (positive signal)
    print(f"\n=== CROSS-STACK HITS (HttpStackResolver + others) ===")
    cross_sorted = sorted([r for r in ok if r.get("cross_edge_count", 0) > 0],
                          key=lambda r: -r["cross_edge_count"])
    for r in cross_sorted[:30]:
        print(f"    {r['repo_spec']:45s}  cross={r['cross_edge_count']:>5d}  nodes={r['node_count']}")
    if not cross_sorted:
        print("    (none — suggests resolver miss or test set lacks crossstack)")

    # Confidence distribution across all
    print(f"\n=== CONFIDENCE (aggregate over all ok repos) ===")
    agg_conf = Counter()
    for r in ok:
        for c, n in r.get("confidence_dist", {}).items():
            agg_conf[c] += n
    total_nodes = sum(agg_conf.values())
    for c, n in agg_conf.most_common():
        pct = 100 * n / total_nodes if total_nodes else 0
        print(f"    {c:10s}  {n:>8d}  ({pct:.1f}%)")

    # Kind distribution
    print(f"\n=== NODE KIND DISTRIBUTION (aggregate) ===")
    agg_kind = Counter()
    for r in ok:
        for k, n in r.get("kind_dist", {}).items():
            agg_kind[int(k)] += n
    total_nodes = sum(agg_kind.values())
    for k, n in sorted(agg_kind.items()):
        name = KIND_NAMES.get(k, f"kind_{k}")
        pct = 100 * n / total_nodes if total_nodes else 0
        print(f"    {k:>3d} {name:15s}  {n:>8d}  ({pct:.1f}%)")

    # Edge category distribution
    print(f"\n=== EDGE CATEGORY DISTRIBUTION (aggregate) ===")
    agg_cat = Counter()
    for r in ok:
        for k, n in r.get("edge_cat_dist", {}).items():
            agg_cat[int(k)] += n
    total_edges = sum(agg_cat.values())
    for c, n in sorted(agg_cat.items()):
        name = CAT_NAMES.get(c, f"cat_{c}")
        pct = 100 * n / total_edges if total_edges else 0
        print(f"    {c:>3d} {name:15s}  {n:>8d}  ({pct:.1f}%)")


if __name__ == "__main__":
    summarize(load())
