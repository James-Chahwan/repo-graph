use repo_graph_code_domain::{CodeNav, GRAPH_TYPE, node_kind};
use repo_graph_core::{Confidence, Node, NodeId, RepoId};

pub struct QueueConsumer {
    pub from: NodeId,
    pub framework: QueueFramework,
    pub identifier: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum QueueFramework {
    Celery,
    Dramatiq,
    BullMQ,
    Sidekiq,
    Oban,
    Nats,
    RabbitMQ,
    Kafka,
}

pub fn extract_queue_consumers(source: &str, from: NodeId) -> Vec<QueueConsumer> {
    let mut consumers = Vec::new();
    for (pattern, framework) in CONSUMER_PATTERNS {
        if source.contains(pattern) {
            consumers.push(QueueConsumer {
                from,
                framework: framework.clone(),
                identifier: pattern.to_string(),
            });
        }
    }
    consumers
}

const CONSUMER_PATTERNS: &[(&str, QueueFramework)] = &[
    ("@celery.task", QueueFramework::Celery),
    ("@shared_task", QueueFramework::Celery),
    ("@dramatiq.actor", QueueFramework::Dramatiq),
    ("new Worker(", QueueFramework::BullMQ),
    ("BullModule", QueueFramework::BullMQ),
    ("include Sidekiq::Worker", QueueFramework::Sidekiq),
    ("include Sidekiq::Job", QueueFramework::Sidekiq),
    ("use Oban.Worker", QueueFramework::Oban),
    ("use Oban.Pro.Worker", QueueFramework::Oban),
    ("nc.subscribe", QueueFramework::Nats),
    ("channel.consume", QueueFramework::RabbitMQ),
    ("KafkaConsumer", QueueFramework::Kafka),
    ("consumer.subscribe", QueueFramework::Kafka),
];

const PRODUCER_PATTERNS: &[(&str, QueueFramework)] = &[
    (".delay(", QueueFramework::Celery),
    (".apply_async(", QueueFramework::Celery),
    (".send(", QueueFramework::Dramatiq),
    ("queue.add(", QueueFramework::BullMQ),
    ("new Queue(", QueueFramework::BullMQ),
    ("perform_async", QueueFramework::Sidekiq),
    ("perform_in", QueueFramework::Sidekiq),
    ("Oban.insert", QueueFramework::Oban),
    ("nc.publish", QueueFramework::Nats),
    ("channel.publish", QueueFramework::RabbitMQ),
    ("channel.basic_publish", QueueFramework::RabbitMQ),
    ("producer.send", QueueFramework::Kafka),
    ("producer.produce", QueueFramework::Kafka),
];

pub struct QueueNodes {
    pub nodes: Vec<Node>,
    pub nav: CodeNav,
}

pub fn extract_queue_consumer_nodes(
    source: &str,
    module_id: NodeId,
    repo: RepoId,
) -> QueueNodes {
    let mut nodes = Vec::new();
    let mut nav = CodeNav::default();
    let mut seen = std::collections::HashSet::new();

    for (pattern, framework) in CONSUMER_PATTERNS {
        if source.contains(pattern) {
            let topic = extract_topic_near(source, pattern).unwrap_or_else(|| framework_tag(framework));
            let key = format!("{topic}:{framework:?}");
            if seen.insert(key) {
                let qname = format!("queue_consumer:{topic}");
                let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::QUEUE_CONSUMER, &qname);
                nodes.push(Node {
                    id,
                    repo,
                    confidence: Confidence::Medium,
                    cells: vec![],
                });
                nav.record(id, &topic, &qname, node_kind::QUEUE_CONSUMER, Some(module_id));
            }
        }
    }

    QueueNodes { nodes, nav }
}

pub fn extract_queue_producer_nodes(
    source: &str,
    module_id: NodeId,
    repo: RepoId,
) -> QueueNodes {
    let mut nodes = Vec::new();
    let mut nav = CodeNav::default();
    let mut seen = std::collections::HashSet::new();

    for (pattern, framework) in PRODUCER_PATTERNS {
        if source.contains(pattern) {
            let topic = extract_topic_near(source, pattern).unwrap_or_else(|| framework_tag(framework));
            let key = format!("{topic}:{framework:?}");
            if seen.insert(key) {
                let qname = format!("queue_producer:{topic}");
                let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::QUEUE_PRODUCER, &qname);
                nodes.push(Node {
                    id,
                    repo,
                    confidence: Confidence::Medium,
                    cells: vec![],
                });
                nav.record(id, &topic, &qname, node_kind::QUEUE_PRODUCER, Some(module_id));
            }
        }
    }

    QueueNodes { nodes, nav }
}

fn framework_tag(f: &QueueFramework) -> String {
    format!("{f:?}").to_lowercase()
}

fn extract_topic_near(source: &str, pattern: &str) -> Option<String> {
    let idx = source.find(pattern)?;
    let after = &source[idx + pattern.len()..];
    extract_first_string_literal(after)
}

fn extract_first_string_literal(s: &str) -> Option<String> {
    let trimmed = s.trim_start();
    let (quote, rest) = if let Some(rest) = trimmed.strip_prefix('\'') {
        ('\'', rest)
    } else if let Some(rest) = trimmed.strip_prefix('"') {
        ('"', rest)
    } else {
        return None;
    };
    let end = rest.find(quote)?;
    let lit = &rest[..end];
    if lit.is_empty() || lit.len() > 128 {
        return None;
    }
    Some(lit.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn repo() -> RepoId {
        RepoId(1)
    }

    fn module_id() -> NodeId {
        NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::MODULE, "test")
    }

    #[test]
    fn detects_celery() {
        let id = NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::MODULE, "test");
        let refs = extract_queue_consumers("@celery.task\ndef process():", id);
        assert!(refs.iter().any(|r| r.framework == QueueFramework::Celery));
    }

    #[test]
    fn detects_bullmq() {
        let id = NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::MODULE, "test");
        let refs = extract_queue_consumers("const worker = new Worker('queue', handler);", id);
        assert!(refs.iter().any(|r| r.framework == QueueFramework::BullMQ));
    }

    #[test]
    fn detects_sidekiq() {
        let id = NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::MODULE, "test");
        let refs = extract_queue_consumers("include Sidekiq::Worker", id);
        assert!(refs.iter().any(|r| r.framework == QueueFramework::Sidekiq));
    }

    #[test]
    fn consumer_nodes_with_topic() {
        let source = "const worker = new Worker('emails', handler);";
        let result = extract_queue_consumer_nodes(source, module_id(), repo());
        assert_eq!(result.nodes.len(), 1);
        let qname = result.nav.qname_by_id.values().next().unwrap();
        assert_eq!(qname, "queue_consumer:emails");
    }

    #[test]
    fn producer_nodes() {
        let source = "send_email.delay('hello')";
        let result = extract_queue_producer_nodes(source, module_id(), repo());
        assert_eq!(result.nodes.len(), 1);
        assert_eq!(result.nav.kind_by_id[&result.nodes[0].id], node_kind::QUEUE_PRODUCER);
    }

    #[test]
    fn kafka_producer_and_consumer() {
        let consumer = "const c = new KafkaConsumer();\nc.subscribe('user-events')";
        let cr = extract_queue_consumer_nodes(consumer, module_id(), repo());
        assert!(!cr.nodes.is_empty());

        let producer = "producer.send({ topic: 'user-events' })";
        let pr = extract_queue_producer_nodes(producer, module_id(), repo());
        assert!(!pr.nodes.is_empty());
    }
}
