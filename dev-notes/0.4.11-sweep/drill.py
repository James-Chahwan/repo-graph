"""Drill into specialty node counts per repo — which analyzers produced WHICH node kinds?"""
import json
from pathlib import Path

KIND = {5:"ROUTE", 9:"ENDPOINT", 11:"GRPC_SVC", 12:"GRPC_CLI",
        13:"Q_CONS", 14:"Q_PROD", 15:"GQL_RES", 16:"GQL_OP",
        17:"WS_HAND", 18:"WS_CLI", 19:"EVT_HAND", 20:"EVT_EMIT",
        21:"CLI_CMD", 22:"CLI_INV"}

records = []
for line in (Path(__file__).parent / "results.jsonl").read_text().splitlines():
    if line.strip():
        records.append(json.loads(line))

print(f"{'repo':<45s} " + " ".join(f"{v:>7s}" for v in KIND.values()))
print("-" * 160)

SPECIAL = set(KIND.keys())
rows = []
for r in records:
    if not r.get("ok"): continue
    kd = {int(k): v for k, v in r.get("kind_dist", {}).items()}
    hits = {k: kd.get(k, 0) for k in SPECIAL}
    if sum(hits.values()) > 0:
        rows.append((r["repo_spec"], hits))

rows.sort(key=lambda x: -sum(x[1].values()))
for spec, hits in rows:
    print(f"{spec:<45s} " + " ".join(f"{hits[k]:>7d}" for k in KIND))

print(f"\nRepos with any specialty kind: {len(rows)}/{sum(1 for r in records if r.get('ok'))}")

# Aggregate per kind
print("\n=== total per specialty kind ===")
agg = {k: 0 for k in KIND}
for _, hits in rows:
    for k, v in hits.items():
        agg[k] += v
for k, v in agg.items():
    print(f"  {KIND[k]:<10s} {v:>6d}")

# Which repos had no specialty but should have?
expected = {
    "celery/celery": "Q_CONS",
    "sidekiq/sidekiq": "Q_CONS",
    "taskforcesh/bullmq": "Q_CONS",
    "oban-bg/oban": "Q_CONS",
    "grpc/grpc-go": "GRPC_SVC",
    "etcd-io/etcd": "GRPC_SVC",
    "tikv/tikv": "GRPC_SVC",
    "temporalio/temporal": "GRPC_SVC",
    "pingcap/tidb": "GRPC_SVC",
    "graphql/graphql-js": "GQL_RES",
    "apollographql/apollo-server": "GQL_RES",
    "dgraph-io/dgraph": "GQL_RES",
    "rmosolgo/graphql-ruby": "GQL_RES",
    "socketio/socket.io": "WS_HAND",
    "centrifugal/centrifugo": "WS_HAND",
    "spf13/cobra": "CLI_CMD",
    "clap-rs/clap": "CLI_CMD",
    "pallets/click": "CLI_CMD",
    "urfave/cli": "CLI_CMD",
    "tj/commander.js": "CLI_CMD",
}
print("\n=== expected specialty node MISSES ===")
for repo, want in expected.items():
    want_id = {v: k for k, v in KIND.items()}[want]
    r = next((x for x in records if x.get("repo_spec") == repo and x.get("ok")), None)
    if not r:
        print(f"  {repo:<35s} (no record or failed)")
        continue
    kd = {int(k): v for k, v in r.get("kind_dist", {}).items()}
    got = kd.get(want_id, 0)
    status = "OK" if got > 0 else "MISS"
    print(f"  [{status}] {repo:<35s} expected {want}, got {got}  (total nodes={r.get('node_count')})")
