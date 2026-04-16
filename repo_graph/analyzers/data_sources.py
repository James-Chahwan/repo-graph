"""
Cross-language data source detector.

Scans all source files for imports/SDK usages that indicate external data
sources (databases, caches, queues, object stores, search, email) and emits
`data_source` nodes + `uses` edges from the file's module.

Edges are emitted with a synthetic `file::<rel>` source; generator.py rewires
these to the best-matching module/package node in the final graph.

Patterns prefer distinctive package names (e.g. `ioredis`, `kafkajs`,
`@aws-sdk/client-s3`) over generic keywords to minimise false positives.
"""

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


# (regex, ds_type, ds_name)
_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # ---- Relational / SQL -------------------------------------------------
    (re.compile(r"""(?:from|import)\s+['"]?pg['"]?(?:\s|$|;|\.)"""), "db", "postgres"),
    (re.compile(r"""['"]pg['"]|['"]postgres['"]"""), "db", "postgres"),
    (re.compile(r"\bpsycopg2?\b|\bpg8000\b|\basyncpg\b"), "db", "postgres"),
    (re.compile(r"github\.com/lib/pq|github\.com/jackc/pgx|tokio[-_]postgres"), "db", "postgres"),
    (re.compile(r"\bmysql2?\b|\bpymysql\b|mysql-connector|go-sql-driver/mysql"), "db", "mysql"),
    (re.compile(r"\bsqlite3\b|better-sqlite3|mattn/go-sqlite3|\bsqlx::sqlite\b"), "db", "sqlite"),
    (re.compile(r"['\"]mssql['\"]|System\.Data\.SqlClient|Microsoft\.Data\.SqlClient"), "db", "mssql"),
    # ORMs / DB toolkits — generic SQL
    (re.compile(r"\bsqlalchemy\b|\btortoise-orm\b|\bpeewee\b"), "db", "sql"),
    (re.compile(r"@prisma/client|drizzle-orm|['\"]typeorm['\"]|['\"]sequelize['\"]|['\"]knex['\"]|['\"]kysely['\"]|['\"]mikro-orm['\"]"), "db", "sql"),
    (re.compile(r"gorm\.io|go-gorm|jinzhu/gorm|\bent/schema\b"), "db", "sql"),
    (re.compile(r"\bdiesel\b|\bsqlx\b|\bsea[-_]orm\b"), "db", "sql"),
    (re.compile(r"ActiveRecord::|ApplicationRecord|class\s+\w+\s*<\s*ActiveRecord::Base"), "db", "sql"),
    (re.compile(r"use\s+Ecto\b|Ecto\.(?:Repo|Changeset|Query|Schema)"), "db", "sql"),
    (re.compile(r"next\.jdbc|honeysql|\bkorma\b"), "db", "sql"),
    (re.compile(r"org\.hibernate|javax\.persistence|jakarta\.persistence|\bslick\.jdbc\b|\bdoobie\b"), "db", "sql"),
    (re.compile(r"Microsoft\.EntityFrameworkCore|\bDbContext\b"), "db", "sql"),
    (re.compile(r"use\s+Doctrine\\|Doctrine\\ORM|Laravel\\Eloquent|Illuminate\\Database"), "db", "sql"),
    # Django ORM
    (re.compile(r"from\s+django\.db|models\.Model\b"), "db", "sql"),

    # ---- NoSQL document/key-value ----------------------------------------
    (re.compile(r"\bpymongo\b|\bmongoose\b|['\"]mongodb['\"]|mongo-go-driver|mongo-driver|go\.mongodb\.org|MongoDB\.Driver|mongo::Client"), "db", "mongodb"),
    (re.compile(r"@aws-sdk/client-dynamodb|\bdynamodb\b|boto3.*dynamodb|DynamoDB", re.IGNORECASE), "db", "dynamodb"),
    (re.compile(r"cassandra-driver|\bgocql\b|\bscylladb\b"), "db", "cassandra"),
    (re.compile(r"\bcouchbase\b|\bcouchdb\b"), "db", "couchbase"),
    (re.compile(r"\bneo4j\b|py2neo|neo4j-driver"), "db", "neo4j"),
    (re.compile(r"\binfluxdb\b|influxdb-client"), "db", "influxdb"),
    (re.compile(r"\bclickhouse\b|clickhouse-driver|clickhouse-connect"), "db", "clickhouse"),

    # ---- Cache ------------------------------------------------------------
    (re.compile(r"['\"]ioredis['\"]|['\"]redis['\"]|import\s+redis\b|from\s+redis\b|go-redis/redis|\bRedix\b|StackExchange\.Redis|\bJedis\b|\bLettuce\b|\bcarmine\b|\bredix\b"), "cache", "redis"),
    (re.compile(r"\bpymemcache\b|\bmemcached\b|\bmemjs\b|gomemcache"), "cache", "memcached"),

    # ---- Queues / streams -------------------------------------------------
    (re.compile(r"\bkafkajs\b|\bkafka-python\b|\bKafkaEx\b|\bsegmentio/kafka-go\b|spring-kafka|\bconfluent_kafka\b|\bBroadway\.Kafka\b"), "queue", "kafka"),
    (re.compile(r"\bamqplib\b|\bpika\b|streadway/amqp|\bbunny\b|\brabbitmq\b|rabbitmq-client"), "queue", "rabbitmq"),
    (re.compile(r"@aws-sdk/client-sqs|aws-sdk-go-v2/service/sqs|boto3.*sqs|\bSQSClient\b"), "queue", "sqs"),
    (re.compile(r"@aws-sdk/client-sns|aws-sdk-go-v2/service/sns|boto3.*sns|\bSNSClient\b"), "queue", "sns"),
    (re.compile(r"['\"]nats['\"]|nats\.go|['\"]@nats-io/"), "queue", "nats"),
    (re.compile(r"@google-cloud/pubsub|google-cloud-pubsub"), "queue", "gcp-pubsub"),
    (re.compile(r"\bcelery\b|import\s+celery"), "queue", "celery"),
    (re.compile(r"\bsidekiq\b"), "queue", "sidekiq"),
    (re.compile(r"['\"]bullmq['\"]|['\"]bull['\"]"), "queue", "bull"),

    # ---- Object storage ---------------------------------------------------
    (re.compile(r"@aws-sdk/client-s3|aws-sdk-go-v2/service/s3|boto3.*s3|\bS3Client\b|Amazon\.S3|aws-sdk/s3|Fog::Storage"), "blob", "s3"),
    (re.compile(r"google-cloud-storage|@google-cloud/storage"), "blob", "gcs"),
    (re.compile(r"azure-storage-blob|@azure/storage-blob|Azure\.Storage\.Blobs"), "blob", "azure-blob"),
    (re.compile(r"\bminio\b|minio-py|minio-go"), "blob", "minio"),

    # ---- Search -----------------------------------------------------------
    (re.compile(r"@elastic/elasticsearch|olivere/elastic|\belasticsearch\b|opensearch-py|@opensearch-project/opensearch"), "search", "elasticsearch"),
    (re.compile(r"\balgoliasearch\b|algolia-search"), "search", "algolia"),
    (re.compile(r"\bmeilisearch\b"), "search", "meilisearch"),
    (re.compile(r"\btypesense\b"), "search", "typesense"),

    # ---- Email ------------------------------------------------------------
    (re.compile(r"@sendgrid/mail|\bsendgrid\b"), "email", "sendgrid"),
    (re.compile(r"@aws-sdk/client-ses|aws-sdk-go-v2/service/ses|boto3.*ses|\bSESClient\b"), "email", "ses"),
    (re.compile(r"\bnodemailer\b|\bsmtplib\b|net/smtp"), "email", "smtp"),
    (re.compile(r"\bmailgun\b|mailgun-js|mailgun\.py"), "email", "mailgun"),
    (re.compile(r"\bpostmark\b|postmark-py"), "email", "postmark"),
    (re.compile(r"\bresend\b"), "email", "resend"),
]

_SCAN_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".go", ".rs", ".rb", ".php", ".java", ".kt",
    ".scala", ".sc", ".clj", ".cljs", ".cljc",
    ".cs", ".swift", ".ex", ".exs", ".dart",
    ".c", ".cc", ".cpp", ".h", ".hpp",
    ".vue",
}

# Identifies lines that look like imports/requires/uses across languages.
# Patterns are applied line-by-line so a file's body (e.g. regex literals)
# can't trigger false matches.
_IMPORT_LINE = re.compile(
    r"""(?:
        ^\s*(?:import|from|use|using|alias|package|gem|include|@import)\b   # py/ts/rust/scala/kotlin/ruby/php/c/scss
      | ^\s*\#include\b                                                       # c/cpp
      | \brequire(?:_relative|_tree)?\s*[\(\'\"]                              # ruby/js
      | \bimport\s*\(                                                         # js dynamic
      | ^\s*"[\w./\-@:]+"\s*$                                                 # go bare import line
      | ^\s*[\w.]+\s+"[\w./\-@:]+"\s*$                                        # go aliased import (alias "path")
      | ^\s*_\s+"[\w./\-@:]+"\s*$                                             # go blank import (_ "path")
      | ^\s*\.\s+"[\w./\-@:]+"\s*$                                            # go dot import (. "path")
      | \(:require\b                                                          # clojure
      | ^\s*:require\b                                                        # clojure inside ns
    )""",
    re.VERBOSE,
)


class DataSourceAnalyzer(LanguageAnalyzer):

    @staticmethod
    def detect(index) -> bool:
        return True  # Supplementary — always runs

    def scan(self) -> AnalysisResult:
        nodes: list[Node] = []
        edges: list[Edge] = []
        seen_nodes: set[str] = set()
        first_file_for: dict[str, str] = {}

        for path in self.index.files_with_ext(_SCAN_SUFFIXES):
            # Skip tests — they often import data clients for setup
            parts_lower = [p.lower() for p in path.parts]
            if any(p in ("test", "tests", "__tests__", "spec", "specs") for p in parts_lower):
                continue
            if path.name.startswith("test_") or path.name.endswith(("_test.go", "_test.py", ".test.ts", ".test.js", ".spec.ts", ".spec.js")):
                continue

            content = read_safe(path)
            if not content:
                continue

            # Keep only lines that look like imports/requires/uses. This avoids
            # matching regex pattern literals, string constants, or comments.
            import_lines = "\n".join(
                line for line in content.splitlines() if _IMPORT_LINE.search(line)
            )
            if not import_lines:
                continue

            file_rel = rel_path(self.repo_root, path)
            found: set[tuple[str, str]] = set()
            for pattern, ds_type, ds_name in _PATTERNS:
                if pattern.search(import_lines):
                    found.add((ds_type, ds_name))

            for ds_type, ds_name in found:
                ds_id = f"data_source_{ds_type}_{ds_name}"
                if ds_id not in seen_nodes:
                    seen_nodes.add(ds_id)
                    first_file_for[ds_id] = file_rel
                    nodes.append(Node(
                        id=ds_id, type="data_source",
                        name=f"{ds_type}/{ds_name}", file_path=file_rel,
                    ))
                edges.append(Edge(
                    from_id=f"file::{file_rel}", to_id=ds_id, type="uses",
                ))

        return AnalysisResult(
            nodes=nodes, edges=edges,
            state_sections=self._state(nodes),
        )

    def _state(self, nodes: list[Node]) -> dict[str, str]:
        ds = [n for n in nodes if n.type == "data_source"]
        if not ds:
            return {}
        by_type: dict[str, list[str]] = {}
        for n in ds:
            kind, name = n.name.split("/", 1)
            by_type.setdefault(kind, []).append(name)
        lines = []
        for kind in sorted(by_type):
            names = ", ".join(sorted(set(by_type[kind])))
            lines.append(f"- **{kind}**: {names}")
        return {"Data Sources": "\n".join(lines) + "\n"}
