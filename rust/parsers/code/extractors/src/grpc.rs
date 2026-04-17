use repo_graph_core::NodeId;

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

#[cfg(test)]
mod tests {
    use super::*;
    use repo_graph_code_domain::{GRAPH_TYPE, node_kind};
    use repo_graph_core::RepoId;

    #[test]
    fn parses_proto_service() {
        let source = r#"
service UserService {
  rpc GetUser (GetUserRequest) returns (User);
  rpc ListUsers (ListUsersRequest) returns (ListUsersResponse);
}
"#;
        let id = NodeId::from_parts(GRAPH_TYPE, RepoId(1), node_kind::MODULE, "test");
        let services = extract_grpc_from_proto(source, id);
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
        let id = NodeId::from_parts(GRAPH_TYPE, RepoId(1), node_kind::MODULE, "test");
        let services = extract_grpc_from_proto(source, id);
        assert_eq!(services.len(), 2);
    }
}
