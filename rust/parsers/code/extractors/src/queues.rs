use repo_graph_core::NodeId;

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
    for (pattern, framework) in PATTERNS {
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

const PATTERNS: &[(&str, QueueFramework)] = &[
    ("@celery.task", QueueFramework::Celery),
    ("@shared_task", QueueFramework::Celery),
    ("@dramatiq.actor", QueueFramework::Dramatiq),
    ("new Worker(", QueueFramework::BullMQ),
    ("new Queue(", QueueFramework::BullMQ),
    ("BullModule", QueueFramework::BullMQ),
    ("include Sidekiq::Worker", QueueFramework::Sidekiq),
    ("include Sidekiq::Job", QueueFramework::Sidekiq),
    ("use Oban.Worker", QueueFramework::Oban),
    ("use Oban.Pro.Worker", QueueFramework::Oban),
    ("nats.connect", QueueFramework::Nats),
    ("nc.subscribe", QueueFramework::Nats),
    ("amqp.connect", QueueFramework::RabbitMQ),
    ("channel.consume", QueueFramework::RabbitMQ),
    ("KafkaConsumer", QueueFramework::Kafka),
    ("consumer.subscribe", QueueFramework::Kafka),
];

#[cfg(test)]
mod tests {
    use super::*;
    use repo_graph_code_domain::{GRAPH_TYPE, node_kind};
    use repo_graph_core::RepoId;

    #[test]
    fn detects_celery() {
        let id = NodeId::from_parts(GRAPH_TYPE, RepoId(1), node_kind::MODULE, "test");
        let refs = extract_queue_consumers("@celery.task\ndef process():", id);
        assert!(refs.iter().any(|r| r.framework == QueueFramework::Celery));
    }

    #[test]
    fn detects_bullmq() {
        let id = NodeId::from_parts(GRAPH_TYPE, RepoId(1), node_kind::MODULE, "test");
        let refs = extract_queue_consumers("const worker = new Worker('queue', handler);", id);
        assert!(refs.iter().any(|r| r.framework == QueueFramework::BullMQ));
    }

    #[test]
    fn detects_sidekiq() {
        let id = NodeId::from_parts(GRAPH_TYPE, RepoId(1), node_kind::MODULE, "test");
        let refs = extract_queue_consumers("include Sidekiq::Worker", id);
        assert!(refs.iter().any(|r| r.framework == QueueFramework::Sidekiq));
    }
}
