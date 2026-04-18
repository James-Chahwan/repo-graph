---
name: Data sources analyzer
description: Cross-cutting analyzer added 2026-04-15 that emits `data_source` nodes for DB/cache/queue/blob/search/email clients across all languages.
type: project
originSessionId: 0e62cb6a-08b1-4aa8-869a-5e18a4072869
---
**What it is:** `repo_graph/analyzers/data_sources.py` — a supplementary analyzer (detect() always True) that runs alongside language analyzers.

**Coverage (40+ patterns):**
- `db`: postgres, mysql, sqlite, mssql, mongodb, dynamodb, cassandra, couchbase, neo4j, influxdb, clickhouse, generic-sql (ORMs)
- `cache`: redis, memcached
- `queue`: kafka, rabbitmq, sqs, sns, nats, gcp-pubsub, celery, sidekiq, bullmq
- `blob`: s3, gcs, azure-blob, minio
- `search`: elasticsearch, algolia, meilisearch, typesense
- `email`: sendgrid, ses, smtp, mailgun, postmark, resend

**Architecture decisions (non-obvious):**
1. **Cross-cutting over per-language.** Instead of editing all 20 language analyzers to emit data_source nodes, one analyzer scans all source files. Keeps pattern table DRY.
2. **`file::<rel>` synthetic edges.** The analyzer doesn't know about per-language module IDs. It emits edges with `from_id=f"file::{file_rel}"`, and `generator.py:_resolve_file_edges` rewires to the best module/package node. Same pattern as existing `_link_endpoints_to_routes`.
3. **Import-line filter.** Patterns match only on lines passing `_IMPORT_LINE` regex (import/from/use/require/include/Go-paren-imports/Clojure-require/etc.). Without this, `data_sources.py` itself matched every pattern (self-match via its own regex literals) — verified by running on repo-graph before the fix (37 false positives → 0).
4. **Resolver walks up dir tree.** `_resolve_file_edges` tries: exact file node → dir's module-level nodes → parent dir → ... → root → any node on file. Needed because Go `go_package` nodes have directory-level file_paths, not per-file.

**Why:** User asked "do we also handle data sources? like queues, dbs, file system etc". Flow tracing was missing "what writes to Redis / reads from Postgres" queries — the common question when debugging production issues.

**How to apply:** Any new data-source detection should go into `_PATTERNS` in `data_sources.py` (not per-language analyzer). Keep patterns anchored to distinctive package names (`kafkajs`, `ioredis`, `@aws-sdk/client-s3`) rather than generic words — false-positive risk is high otherwise.

**Known Go import forms handled:** bare `"path"`, aliased `alias "path"`, blank `_ "path"`, dot `. "path"`. The aliased form was initially missed (caught by quokka-stack test — NATS was imported as `nats "github.com/nats-io/nats.go"`).

**Quokka-stack validation (2026-04-15):** detected db/mongodb, queue/nats, blob/s3, email/resend. Matched go.mod exactly. 7 deduped edges from go_package/go_module nodes.
