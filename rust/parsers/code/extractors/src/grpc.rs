use repo_graph_code_domain::{CodeNav, GRAPH_TYPE, node_kind};
use repo_graph_core::{Cell, CellPayload, Confidence, Node, NodeId, RepoId};

pub struct GrpcService {
    pub from: NodeId,
    pub service_name: String,
    pub methods: Vec<String>,
}

pub fn extract_grpc_from_proto(source: &str, from: NodeId) -> Vec<GrpcService> {
    let mut services = Vec::new();
    let mut current_service: Option<String> = None;
    let mut current_methods = Vec::new();

    for line in source.lines() {
        let trimmed = line.trim();
        if let Some(rest) = trimmed.strip_prefix("service ") {
            if let Some(current) = current_service.take() {
                services.push(GrpcService {
                    from,
                    service_name: current,
                    methods: std::mem::take(&mut current_methods),
                });
            }
            let name = rest.split('{').next().unwrap_or("").trim();
            if !name.is_empty() {
                current_service = Some(name.to_string());
            }
        } else if trimmed.starts_with("rpc ") {
            let rest = trimmed.strip_prefix("rpc ").unwrap_or("");
            let method = rest.split('(').next().unwrap_or("").trim();
            if !method.is_empty() {
                current_methods.push(method.to_string());
            }
        }
    }

    if let Some(current) = current_service {
        services.push(GrpcService {
            from,
            service_name: current,
            methods: current_methods,
        });
    }

    services
}

pub struct GrpcNodes {
    pub nodes: Vec<Node>,
    pub nav: CodeNav,
}

pub fn extract_grpc_service_nodes(source: &str, module_id: NodeId, repo: RepoId) -> GrpcNodes {
    let services = extract_grpc_from_proto(source, module_id);
    let mut nodes = Vec::new();
    let mut nav = CodeNav::default();

    for svc in &services {
        let qname = format!("grpc:{}", svc.service_name);
        let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::GRPC_SERVICE, &qname);
        nodes.push(Node {
            id,
            repo,
            confidence: Confidence::Strong,
            cells: vec![Cell {
                kind: repo_graph_code_domain::cell_type::INTENT,
                payload: CellPayload::Text(format!(
                    "gRPC service {} with {} methods",
                    svc.service_name,
                    svc.methods.len()
                )),
            }],
        });
        nav.record(id, &svc.service_name, &qname, node_kind::GRPC_SERVICE, Some(module_id));
    }

    GrpcNodes { nodes, nav }
}

const GRPC_CLIENT_PATTERNS: &[(&str, &str)] = &[
    ("NewClient(", ""),
    ("Client(", ""),
    ("Stub(", ""),
    ("ServiceClient(", ""),
];

pub fn extract_grpc_client_nodes(source: &str, module_id: NodeId, repo: RepoId) -> GrpcNodes {
    let mut nodes = Vec::new();
    let mut nav = CodeNav::default();
    let mut seen = std::collections::HashSet::new();

    for line in source.lines() {
        let trimmed = line.trim();
        for &(suffix, _) in GRPC_CLIENT_PATTERNS {
            if let Some(pos) = trimmed.find(suffix) {
                let before = &trimmed[..pos];
                let svc_name = extract_service_name_from_client(before);
                if !svc_name.is_empty() && seen.insert(svc_name.clone()) {
                    let qname = format!("grpc_client:{svc_name}");
                    let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::GRPC_CLIENT, &qname);
                    nodes.push(Node {
                        id,
                        repo,
                        confidence: Confidence::Medium,
                        cells: vec![],
                    });
                    nav.record(id, &svc_name, &qname, node_kind::GRPC_CLIENT, Some(module_id));
                }
            }
        }
    }

    GrpcNodes { nodes, nav }
}

fn extract_service_name_from_client(before: &str) -> String {
    let token = before
        .rsplit(|c: char| !c.is_alphanumeric() && c != '_')
        .next()
        .unwrap_or("");
    let name = token
        .strip_suffix("Service")
        .or_else(|| token.strip_suffix("Svc"))
        .unwrap_or(token);
    if name.len() >= 2 {
        name.to_string()
    } else {
        String::new()
    }
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
    fn parses_proto_service() {
        let source = r#"
service UserService {
  rpc GetUser (GetUserRequest) returns (User);
  rpc ListUsers (ListUsersRequest) returns (ListUsersResponse);
}
"#;
        let services = extract_grpc_from_proto(source, module_id());
        assert_eq!(services.len(), 1);
        assert_eq!(services[0].service_name, "UserService");
        assert_eq!(services[0].methods.len(), 2);
        assert_eq!(services[0].methods[0], "GetUser");
    }

    #[test]
    fn multiple_services() {
        let source = r#"
service Auth {
  rpc Login (LoginReq) returns (Token);
}

service Users {
  rpc Get (GetReq) returns (User);
}
"#;
        let services = extract_grpc_from_proto(source, module_id());
        assert_eq!(services.len(), 2);
    }

    #[test]
    fn service_nodes_from_proto() {
        let source = "service OrderService {\n  rpc Place (Req) returns (Resp);\n}";
        let result = extract_grpc_service_nodes(source, module_id(), repo());
        assert_eq!(result.nodes.len(), 1);
        assert_eq!(result.nav.kind_by_id[&result.nodes[0].id], node_kind::GRPC_SERVICE);
    }

    #[test]
    fn client_nodes_from_code() {
        let source = "conn := grpc.Dial(addr)\nclient := pb.NewOrderServiceClient(conn)";
        let result = extract_grpc_client_nodes(source, module_id(), repo());
        assert_eq!(result.nodes.len(), 1);
        assert_eq!(result.nav.kind_by_id[&result.nodes[0].id], node_kind::GRPC_CLIENT);
        let qname = result.nav.qname_by_id.values().next().unwrap();
        assert!(qname.starts_with("grpc_client:"));
    }
}
