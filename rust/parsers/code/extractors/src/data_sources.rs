use repo_graph_core::NodeId;

pub struct DataSourceRef {
    pub from: NodeId,
    pub kind: DataSourceKind,
    pub identifier: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DataSourceKind {
    Database,
    Cache,
    Queue,
    BlobStore,
    Search,
    Email,
}

pub fn extract_data_sources(source: &str, from: NodeId) -> Vec<DataSourceRef> {
    let mut refs = Vec::new();
    for (pattern, kind) in PATTERNS {
        if source.contains(pattern) {
            refs.push(DataSourceRef {
                from,
                kind: kind.clone(),
                identifier: pattern.to_string(),
            });
        }
    }
    refs
}

const PATTERNS: &[(&str, DataSourceKind)] = &[
    ("pg.", DataSourceKind::Database),
    ("mysql.", DataSourceKind::Database),
    ("sqlite", DataSourceKind::Database),
    ("MongoClient", DataSourceKind::Database),
    ("mongoose.", DataSourceKind::Database),
    ("Prisma", DataSourceKind::Database),
    ("TypeORM", DataSourceKind::Database),
    ("Sequelize", DataSourceKind::Database),
    ("sqlalchemy", DataSourceKind::Database),
    ("diesel::", DataSourceKind::Database),
    ("sqlx::", DataSourceKind::Database),
    ("ActiveRecord", DataSourceKind::Database),
    ("Ecto.Repo", DataSourceKind::Database),
    ("Redis", DataSourceKind::Cache),
    ("redis.", DataSourceKind::Cache),
    ("Memcached", DataSourceKind::Cache),
    ("RabbitMQ", DataSourceKind::Queue),
    ("amqplib", DataSourceKind::Queue),
    ("kafka", DataSourceKind::Queue),
    ("SQS", DataSourceKind::Queue),
    ("S3Client", DataSourceKind::BlobStore),
    ("BlobServiceClient", DataSourceKind::BlobStore),
    ("upload", DataSourceKind::BlobStore),
    ("Elasticsearch", DataSourceKind::Search),
    ("OpenSearch", DataSourceKind::Search),
    ("Algolia", DataSourceKind::Search),
    ("Meilisearch", DataSourceKind::Search),
    ("SendGrid", DataSourceKind::Email),
    ("Mailgun", DataSourceKind::Email),
    ("nodemailer", DataSourceKind::Email),
    ("SMTP", DataSourceKind::Email),
];

#[cfg(test)]
mod tests {
    use super::*;
    use repo_graph_code_domain::{GRAPH_TYPE, node_kind};
    use repo_graph_core::RepoId;

    #[test]
    fn detects_database() {
        let id = NodeId::from_parts(GRAPH_TYPE, RepoId(1), node_kind::MODULE, "test");
        let refs = extract_data_sources("const db = new MongoClient(url);", id);
        assert_eq!(refs.len(), 1);
        assert_eq!(refs[0].kind, DataSourceKind::Database);
    }

    #[test]
    fn detects_multiple() {
        let id = NodeId::from_parts(GRAPH_TYPE, RepoId(1), node_kind::MODULE, "test");
        let source = "import Redis from 'redis';\nconst es = new Elasticsearch();";
        let refs = extract_data_sources(source, id);
        assert!(refs.iter().any(|r| r.kind == DataSourceKind::Cache));
        assert!(refs.iter().any(|r| r.kind == DataSourceKind::Search));
    }
}
