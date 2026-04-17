use repo_graph_code_domain::{CodeNav, edge_category, node_kind, GRAPH_TYPE};
use repo_graph_core::{Confidence, Node, NodeId, RepoId};
use repo_graph_graph::*;

fn repo_a() -> RepoId {
    RepoId::from_canonical("test://resolver/a")
}
fn repo_b() -> RepoId {
    RepoId::from_canonical("test://resolver/b")
}

fn make_graph(repo: RepoId, nodes: Vec<Node>, nav: CodeNav) -> RepoGraph {
    RepoGraph {
        repo,
        nodes,
        edges: vec![],
        nav,
        symbols: Default::default(),
        unresolved_calls: vec![],
        unresolved_refs: vec![],
    }
}

fn make_node(repo: RepoId, kind: repo_graph_core::NodeKindId, qname: &str, confidence: Confidence) -> (Node, NodeId) {
    let id = NodeId::from_parts(GRAPH_TYPE, repo, kind, qname);
    let node = Node {
        id,
        repo,
        confidence,
        cells: vec![],
    };
    (node, id)
}

fn record(nav: &mut CodeNav, id: NodeId, name: &str, qname: &str, kind: repo_graph_core::NodeKindId) {
    nav.record(id, name, qname, kind, None);
}

// ============================================================================
// GrpcStackResolver
// ============================================================================

#[test]
fn grpc_resolver_links_client_to_service() {
    let mut nav_a = CodeNav::default();
    let (svc_node, svc_id) = make_node(repo_a(), node_kind::GRPC_SERVICE, "grpc:UserService", Confidence::Strong);
    record(&mut nav_a, svc_id, "UserService", "grpc:UserService", node_kind::GRPC_SERVICE);
    let ga = make_graph(repo_a(), vec![svc_node], nav_a);

    let mut nav_b = CodeNav::default();
    let (client_node, client_id) = make_node(repo_b(), node_kind::GRPC_CLIENT, "grpc_client:UserService", Confidence::Medium);
    record(&mut nav_b, client_id, "UserService", "grpc_client:UserService", node_kind::GRPC_CLIENT);
    let gb = make_graph(repo_b(), vec![client_node], nav_b);

    let mut merged = MergedGraph::new(vec![ga, gb]);
    GrpcStackResolver.resolve(&mut merged);

    let grpc_edges: Vec<_> = merged.cross_edges.iter().filter(|e| e.category == edge_category::GRPC_CALLS).collect();
    assert_eq!(grpc_edges.len(), 1);
    assert_eq!(grpc_edges[0].from, client_id);
    assert_eq!(grpc_edges[0].to, svc_id);
    assert_eq!(grpc_edges[0].confidence, Confidence::Medium);
}

#[test]
fn grpc_resolver_method_level_matches_service() {
    let mut nav_a = CodeNav::default();
    let (svc_node, svc_id) = make_node(repo_a(), node_kind::GRPC_SERVICE, "grpc:OrderService", Confidence::Strong);
    record(&mut nav_a, svc_id, "OrderService", "grpc:OrderService", node_kind::GRPC_SERVICE);
    let ga = make_graph(repo_a(), vec![svc_node], nav_a);

    let mut nav_b = CodeNav::default();
    let (client_node, client_id) = make_node(repo_b(), node_kind::GRPC_CLIENT, "grpc_client:OrderService.PlaceOrder", Confidence::Medium);
    record(&mut nav_b, client_id, "OrderService", "grpc_client:OrderService.PlaceOrder", node_kind::GRPC_CLIENT);
    let gb = make_graph(repo_b(), vec![client_node], nav_b);

    let mut merged = MergedGraph::new(vec![ga, gb]);
    GrpcStackResolver.resolve(&mut merged);

    assert_eq!(merged.cross_edges.len(), 1);
}

// ============================================================================
// QueueStackResolver
// ============================================================================

#[test]
fn queue_resolver_links_producer_to_consumer() {
    let mut nav_a = CodeNav::default();
    let (consumer_node, consumer_id) = make_node(repo_a(), node_kind::QUEUE_CONSUMER, "queue_consumer:emails", Confidence::Medium);
    record(&mut nav_a, consumer_id, "emails", "queue_consumer:emails", node_kind::QUEUE_CONSUMER);
    let ga = make_graph(repo_a(), vec![consumer_node], nav_a);

    let mut nav_b = CodeNav::default();
    let (producer_node, producer_id) = make_node(repo_b(), node_kind::QUEUE_PRODUCER, "queue_producer:emails", Confidence::Medium);
    record(&mut nav_b, producer_id, "emails", "queue_producer:emails", node_kind::QUEUE_PRODUCER);
    let gb = make_graph(repo_b(), vec![producer_node], nav_b);

    let mut merged = MergedGraph::new(vec![ga, gb]);
    QueueStackResolver.resolve(&mut merged);

    let queue_edges: Vec<_> = merged.cross_edges.iter().filter(|e| e.category == edge_category::QUEUE_FLOWS).collect();
    assert_eq!(queue_edges.len(), 1);
    assert_eq!(queue_edges[0].from, producer_id);
    assert_eq!(queue_edges[0].to, consumer_id);
}

#[test]
fn queue_resolver_no_match_on_different_topics() {
    let mut nav_a = CodeNav::default();
    let (consumer_node, consumer_id) = make_node(repo_a(), node_kind::QUEUE_CONSUMER, "queue_consumer:emails", Confidence::Medium);
    record(&mut nav_a, consumer_id, "emails", "queue_consumer:emails", node_kind::QUEUE_CONSUMER);
    let ga = make_graph(repo_a(), vec![consumer_node], nav_a);

    let mut nav_b = CodeNav::default();
    let (producer_node, producer_id) = make_node(repo_b(), node_kind::QUEUE_PRODUCER, "queue_producer:orders", Confidence::Medium);
    record(&mut nav_b, producer_id, "orders", "queue_producer:orders", node_kind::QUEUE_PRODUCER);
    let gb = make_graph(repo_b(), vec![producer_node], nav_b);

    let mut merged = MergedGraph::new(vec![ga, gb]);
    QueueStackResolver.resolve(&mut merged);

    assert!(merged.cross_edges.is_empty());
}

// ============================================================================
// GraphQLStackResolver
// ============================================================================

#[test]
fn graphql_resolver_links_operation_to_resolver() {
    let mut nav_a = CodeNav::default();
    let (resolver_node, resolver_id) = make_node(repo_a(), node_kind::GRAPHQL_RESOLVER, "graphql_resolver:Mutation", Confidence::Strong);
    record(&mut nav_a, resolver_id, "Mutation", "graphql_resolver:Mutation", node_kind::GRAPHQL_RESOLVER);
    let ga = make_graph(repo_a(), vec![resolver_node], nav_a);

    let mut nav_b = CodeNav::default();
    let (op_node, op_id) = make_node(repo_b(), node_kind::GRAPHQL_OPERATION, "graphql_op:CreateUserMutation", Confidence::Medium);
    record(&mut nav_b, op_id, "CreateUserMutation", "graphql_op:CreateUserMutation", node_kind::GRAPHQL_OPERATION);
    let gb = make_graph(repo_b(), vec![op_node], nav_b);

    let mut merged = MergedGraph::new(vec![ga, gb]);
    GraphQLStackResolver.resolve(&mut merged);

    let gql_edges: Vec<_> = merged.cross_edges.iter().filter(|e| e.category == edge_category::GRAPHQL_CALLS).collect();
    assert_eq!(gql_edges.len(), 1);
    assert_eq!(gql_edges[0].from, op_id);
    assert_eq!(gql_edges[0].to, resolver_id);
}

// ============================================================================
// WebSocketStackResolver
// ============================================================================

#[test]
fn ws_resolver_links_client_to_handler() {
    let mut nav_a = CodeNav::default();
    let (handler_node, handler_id) = make_node(repo_a(), node_kind::WS_HANDLER, "ws:/chat", Confidence::Strong);
    record(&mut nav_a, handler_id, "chat", "ws:/chat", node_kind::WS_HANDLER);
    let ga = make_graph(repo_a(), vec![handler_node], nav_a);

    let mut nav_b = CodeNav::default();
    let (client_node, client_id) = make_node(repo_b(), node_kind::WS_CLIENT, "ws_client:/chat", Confidence::Medium);
    record(&mut nav_b, client_id, "chat", "ws_client:/chat", node_kind::WS_CLIENT);
    let gb = make_graph(repo_b(), vec![client_node], nav_b);

    let mut merged = MergedGraph::new(vec![ga, gb]);
    WebSocketStackResolver.resolve(&mut merged);

    let ws_edges: Vec<_> = merged.cross_edges.iter().filter(|e| e.category == edge_category::WS_CONNECTS).collect();
    assert_eq!(ws_edges.len(), 1);
    assert_eq!(ws_edges[0].from, client_id);
    assert_eq!(ws_edges[0].to, handler_id);
}

// ============================================================================
// EventBusResolver
// ============================================================================

#[test]
fn event_resolver_links_emitter_to_handler() {
    let mut nav_a = CodeNav::default();
    let (handler_node, handler_id) = make_node(repo_a(), node_kind::EVENT_HANDLER, "event_handle:user.created", Confidence::Weak);
    record(&mut nav_a, handler_id, "user.created", "event_handle:user.created", node_kind::EVENT_HANDLER);
    let ga = make_graph(repo_a(), vec![handler_node], nav_a);

    let mut nav_b = CodeNav::default();
    let (emitter_node, emitter_id) = make_node(repo_b(), node_kind::EVENT_EMITTER, "event_emit:user.created", Confidence::Weak);
    record(&mut nav_b, emitter_id, "user.created", "event_emit:user.created", node_kind::EVENT_EMITTER);
    let gb = make_graph(repo_b(), vec![emitter_node], nav_b);

    let mut merged = MergedGraph::new(vec![ga, gb]);
    EventBusResolver.resolve(&mut merged);

    let event_edges: Vec<_> = merged.cross_edges.iter().filter(|e| e.category == edge_category::EVENT_FLOWS).collect();
    assert_eq!(event_edges.len(), 1);
    assert_eq!(event_edges[0].from, emitter_id);
    assert_eq!(event_edges[0].to, handler_id);
    assert_eq!(event_edges[0].confidence, Confidence::Weak);
}

// ============================================================================
// CliInvocationResolver
// ============================================================================

#[test]
fn cli_resolver_links_invocation_to_command() {
    let mut nav_a = CodeNav::default();
    let (cmd_node, cmd_id) = make_node(repo_a(), node_kind::CLI_COMMAND, "cli:migrate", Confidence::Strong);
    record(&mut nav_a, cmd_id, "migrate", "cli:migrate", node_kind::CLI_COMMAND);
    let ga = make_graph(repo_a(), vec![cmd_node], nav_a);

    let mut nav_b = CodeNav::default();
    let (inv_node, inv_id) = make_node(repo_b(), node_kind::CLI_INVOCATION, "cli_invoke:migrate", Confidence::Medium);
    record(&mut nav_b, inv_id, "migrate", "cli_invoke:migrate", node_kind::CLI_INVOCATION);
    let gb = make_graph(repo_b(), vec![inv_node], nav_b);

    let mut merged = MergedGraph::new(vec![ga, gb]);
    CliInvocationResolver.resolve(&mut merged);

    let cli_edges: Vec<_> = merged.cross_edges.iter().filter(|e| e.category == edge_category::CLI_INVOKES).collect();
    assert_eq!(cli_edges.len(), 1);
    assert_eq!(cli_edges[0].from, inv_id);
    assert_eq!(cli_edges[0].to, cmd_id);
}

// ============================================================================
// All resolvers run together without interference
// ============================================================================

#[test]
fn all_resolvers_compose_cleanly() {
    let mut nav_a = CodeNav::default();
    let (svc_node, svc_id) = make_node(repo_a(), node_kind::GRPC_SERVICE, "grpc:Auth", Confidence::Strong);
    record(&mut nav_a, svc_id, "Auth", "grpc:Auth", node_kind::GRPC_SERVICE);
    let (consumer_node, consumer_id) = make_node(repo_a(), node_kind::QUEUE_CONSUMER, "queue_consumer:jobs", Confidence::Medium);
    record(&mut nav_a, consumer_id, "jobs", "queue_consumer:jobs", node_kind::QUEUE_CONSUMER);
    let (cmd_node, cmd_id) = make_node(repo_a(), node_kind::CLI_COMMAND, "cli:seed", Confidence::Strong);
    record(&mut nav_a, cmd_id, "seed", "cli:seed", node_kind::CLI_COMMAND);
    let ga = make_graph(repo_a(), vec![svc_node, consumer_node, cmd_node], nav_a);

    let mut nav_b = CodeNav::default();
    let (client_node, _) = make_node(repo_b(), node_kind::GRPC_CLIENT, "grpc_client:Auth", Confidence::Medium);
    record(&mut nav_b, client_node.id, "Auth", "grpc_client:Auth", node_kind::GRPC_CLIENT);
    let (producer_node, _) = make_node(repo_b(), node_kind::QUEUE_PRODUCER, "queue_producer:jobs", Confidence::Medium);
    record(&mut nav_b, producer_node.id, "jobs", "queue_producer:jobs", node_kind::QUEUE_PRODUCER);
    let (inv_node, _) = make_node(repo_b(), node_kind::CLI_INVOCATION, "cli_invoke:seed", Confidence::Medium);
    record(&mut nav_b, inv_node.id, "seed", "cli_invoke:seed", node_kind::CLI_INVOCATION);
    let gb = make_graph(repo_b(), vec![client_node, producer_node, inv_node], nav_b);

    let mut merged = MergedGraph::new(vec![ga, gb]);
    merged.run(&GrpcStackResolver);
    merged.run(&QueueStackResolver);
    merged.run(&CliInvocationResolver);

    assert_eq!(merged.cross_edges.len(), 3);
    assert!(merged.cross_edges.iter().any(|e| e.category == edge_category::GRPC_CALLS));
    assert!(merged.cross_edges.iter().any(|e| e.category == edge_category::QUEUE_FLOWS));
    assert!(merged.cross_edges.iter().any(|e| e.category == edge_category::CLI_INVOKES));
}
