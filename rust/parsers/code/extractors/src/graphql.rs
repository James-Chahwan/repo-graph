use repo_graph_code_domain::{CodeNav, GRAPH_TYPE, node_kind};
use repo_graph_core::{Confidence, Node, NodeId, RepoId};

pub struct GraphqlNodes {
    pub nodes: Vec<Node>,
    pub nav: CodeNav,
}

const OPERATION_PATTERNS: &[&str] = &[
    "useQuery(",
    "useMutation(",
    "useSubscription(",
    "useLazyQuery(",
    "client.query(",
    "client.mutate(",
    "client.subscribe(",
    "graphql-request",
    "request(",
];

const RESOLVER_PATTERNS: &[&str] = &[
    "@Query(",
    "@Mutation(",
    "@Subscription(",
    "@Resolver(",
    "@ResolveField(",
    "type Query {",
    "type Mutation {",
    "type Subscription {",
    "@strawberry.type",
    "@strawberry.mutation",
    "ObjectType):",
    "graphene.ObjectType",
];

pub fn extract_graphql_operation_nodes(
    source: &str,
    module_id: NodeId,
    repo: RepoId,
) -> GraphqlNodes {
    let mut nodes = Vec::new();
    let mut nav = CodeNav::default();
    let mut seen = std::collections::HashSet::new();

    for line in source.lines() {
        let trimmed = line.trim();
        for &pattern in OPERATION_PATTERNS {
            if trimmed.contains(pattern) {
                let op_name = extract_gql_operation_name(source, trimmed)
                    .unwrap_or_else(|| pattern.trim_end_matches('(').to_string());
                if seen.insert(op_name.clone()) {
                    let qname = format!("graphql_op:{op_name}");
                    let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::GRAPHQL_OPERATION, &qname);
                    nodes.push(Node {
                        id,
                        repo,
                        confidence: Confidence::Medium,
                        cells: vec![],
                    });
                    nav.record(id, &op_name, &qname, node_kind::GRAPHQL_OPERATION, Some(module_id));
                }
                break;
            }
        }
    }

    for name in extract_gql_template_operations(source) {
        if seen.insert(name.clone()) {
            let qname = format!("graphql_op:{name}");
            let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::GRAPHQL_OPERATION, &qname);
            nodes.push(Node {
                id,
                repo,
                confidence: Confidence::Strong,
                cells: vec![],
            });
            nav.record(id, &name, &qname, node_kind::GRAPHQL_OPERATION, Some(module_id));
        }
    }

    GraphqlNodes { nodes, nav }
}

pub fn extract_graphql_resolver_nodes(
    source: &str,
    module_id: NodeId,
    repo: RepoId,
) -> GraphqlNodes {
    let mut nodes = Vec::new();
    let mut nav = CodeNav::default();
    let mut seen = std::collections::HashSet::new();

    for &pattern in RESOLVER_PATTERNS {
        if source.contains(pattern) {
            let resolver_name = pattern
                .trim_start_matches('@')
                .trim_end_matches('(')
                .trim_end_matches(" {")
                .trim_end_matches("):")
                .replace("type ", "")
                .replace("graphene.", "");
            if seen.insert(resolver_name.clone()) {
                let qname = format!("graphql_resolver:{resolver_name}");
                let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::GRAPHQL_RESOLVER, &qname);
                nodes.push(Node {
                    id,
                    repo,
                    confidence: Confidence::Medium,
                    cells: vec![],
                });
                nav.record(id, &resolver_name, &qname, node_kind::GRAPHQL_RESOLVER, Some(module_id));
            }
        }
    }

    GraphqlNodes { nodes, nav }
}

fn extract_gql_operation_name(source: &str, _line: &str) -> Option<String> {
    for tag in ["gql`", "gql(`", "gql(\"", "graphql(`", "graphql(\""] {
        if let Some(idx) = source.find(tag) {
            let after = &source[idx + tag.len()..];
            return extract_operation_from_body(after);
        }
    }
    None
}

fn extract_gql_template_operations(source: &str) -> Vec<String> {
    let mut ops = Vec::new();
    let mut search_from = 0;
    while let Some(idx) = source[search_from..].find("gql`") {
        let abs = search_from + idx + 4;
        if let Some(name) = extract_operation_from_body(&source[abs..]) {
            ops.push(name);
        }
        search_from = abs;
    }
    ops
}

fn extract_operation_from_body(body: &str) -> Option<String> {
    let trimmed = body.trim();
    for keyword in ["query ", "mutation ", "subscription "] {
        if let Some(rest) = trimmed.strip_prefix(keyword) {
            let name: String = rest
                .chars()
                .take_while(|c| c.is_alphanumeric() || *c == '_')
                .collect();
            if !name.is_empty() {
                return Some(name);
            }
        }
    }
    None
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
    fn detects_use_query() {
        let source = "const { data } = useQuery(GET_USERS);";
        let result = extract_graphql_operation_nodes(source, module_id(), repo());
        assert!(!result.nodes.is_empty());
    }

    #[test]
    fn extracts_gql_template_name() {
        let source = r#"const GET_USERS = gql`query GetUsers { users { id name } }`;"#;
        let result = extract_graphql_operation_nodes(source, module_id(), repo());
        assert!(result.nav.qname_by_id.values().any(|q| q == "graphql_op:GetUsers"));
    }

    #[test]
    fn detects_resolver_decorator() {
        let source = "@Query()\nasync users() { return []; }";
        let result = extract_graphql_resolver_nodes(source, module_id(), repo());
        assert!(!result.nodes.is_empty());
        assert!(result.nav.qname_by_id.values().any(|q| q.starts_with("graphql_resolver:")));
    }

    #[test]
    fn detects_schema_type() {
        let source = "type Query {\n  users: [User]\n}";
        let result = extract_graphql_resolver_nodes(source, module_id(), repo());
        assert!(result.nav.qname_by_id.values().any(|q| q == "graphql_resolver:Query"));
    }
}
