use repo_graph_code_domain::{CodeNav, GRAPH_TYPE, node_kind};
use repo_graph_core::{Confidence, Node, NodeId, RepoId};

pub struct WsNodes {
    pub nodes: Vec<Node>,
    pub nav: CodeNav,
}

const HANDLER_PATTERNS: &[&str] = &[
    "ws.on(\"connection\"",
    "ws.on('connection'",
    "@WebSocketGateway",
    "WebSocketServer",
    "websocket.Upgrader",
    "gorilla/websocket",
    "channel \"",
    "channel '",
    "socket \"",
    "Phoenix.Channel",
    "ActionCable",
    "ws.handleUpgrade",
];

const CLIENT_PATTERNS: &[&str] = &[
    "new WebSocket(",
    "useWebSocket(",
    "io(",
    "io.connect(",
    "socket.io-client",
    "ws.connect(",
    "WebSocketSubject(",
    "connectWebSocket(",
];

pub fn extract_ws_handler_nodes(
    source: &str,
    module_id: NodeId,
    repo: RepoId,
) -> WsNodes {
    let mut nodes = Vec::new();
    let mut nav = CodeNav::default();
    let mut seen = std::collections::HashSet::new();

    for &pattern in HANDLER_PATTERNS {
        if source.contains(pattern) {
            let name = extract_ws_name(source, pattern).unwrap_or_else(|| "ws".to_string());
            if seen.insert(name.clone()) {
                let qname = format!("ws:{name}");
                let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::WS_HANDLER, &qname);
                nodes.push(Node {
                    id,
                    repo,
                    confidence: Confidence::Medium,
                    cells: vec![],
                });
                nav.record(id, &name, &qname, node_kind::WS_HANDLER, Some(module_id));
            }
        }
    }

    WsNodes { nodes, nav }
}

pub fn extract_ws_client_nodes(
    source: &str,
    module_id: NodeId,
    repo: RepoId,
) -> WsNodes {
    let mut nodes = Vec::new();
    let mut nav = CodeNav::default();
    let mut seen = std::collections::HashSet::new();

    for &pattern in CLIENT_PATTERNS {
        if source.contains(pattern) {
            let name = extract_ws_url(source, pattern).unwrap_or_else(|| "ws".to_string());
            if seen.insert(name.clone()) {
                let qname = format!("ws_client:{name}");
                let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::WS_CLIENT, &qname);
                nodes.push(Node {
                    id,
                    repo,
                    confidence: Confidence::Medium,
                    cells: vec![],
                });
                nav.record(id, &name, &qname, node_kind::WS_CLIENT, Some(module_id));
            }
        }
    }

    WsNodes { nodes, nav }
}

fn extract_ws_name(source: &str, pattern: &str) -> Option<String> {
    let idx = source.find(pattern)?;
    let after = &source[idx + pattern.len()..];
    extract_string_arg(after).or_else(|| {
        if pattern.contains("Gateway") || pattern.contains("Channel") || pattern.contains("Cable") {
            Some("default".to_string())
        } else {
            None
        }
    })
}

fn extract_ws_url(source: &str, pattern: &str) -> Option<String> {
    let idx = source.find(pattern)?;
    let after = &source[idx + pattern.len()..];
    extract_string_arg(after)
}

fn extract_string_arg(s: &str) -> Option<String> {
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
    if lit.is_empty() || lit.len() > 256 {
        return None;
    }
    Some(normalise_ws_path(lit))
}

fn normalise_ws_path(url: &str) -> String {
    if let Some(path) = url.strip_prefix("ws://").or_else(|| url.strip_prefix("wss://"))
        && let Some(slash) = path.find('/')
    {
        return path[slash..].to_string();
    }
    url.to_string()
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
    fn detects_ws_handler() {
        let source = "ws.on('connection', (socket) => { socket.send('hi'); });";
        let result = extract_ws_handler_nodes(source, module_id(), repo());
        assert!(!result.nodes.is_empty());
    }

    #[test]
    fn detects_ws_gateway() {
        let source = "@WebSocketGateway()\nexport class ChatGateway {}";
        let result = extract_ws_handler_nodes(source, module_id(), repo());
        assert!(!result.nodes.is_empty());
    }

    #[test]
    fn detects_ws_client() {
        let source = "const ws = new WebSocket('ws://localhost:8080/chat');";
        let result = extract_ws_client_nodes(source, module_id(), repo());
        assert!(!result.nodes.is_empty());
        assert!(result.nav.qname_by_id.values().any(|q| q.contains("/chat")));
    }
}
