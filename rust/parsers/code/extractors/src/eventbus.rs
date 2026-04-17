use repo_graph_code_domain::{CodeNav, GRAPH_TYPE, node_kind};
use repo_graph_core::{Confidence, Node, NodeId, RepoId};

pub struct EventNodes {
    pub nodes: Vec<Node>,
    pub nav: CodeNav,
}

const EMITTER_PATTERNS: &[(&str, bool)] = &[
    (".emit(", true),
    (".dispatch(", true),
    ("Subject.next(", true),
    ("EventBridge.putEvents", false),
    ("eventBridge.putEvents", false),
    ("publish(", true),
    (".trigger(", true),
    ("dispatchEvent(", true),
];

const HANDLER_PATTERNS: &[(&str, bool)] = &[
    (".on(", true),
    (".addEventListener(", true),
    (".subscribe(", true),
    ("@EventPattern(", true),
    ("@OnEvent(", true),
    ("handle_event", false),
    (".addListener(", true),
];

pub fn extract_event_emitter_nodes(
    source: &str,
    module_id: NodeId,
    repo: RepoId,
) -> EventNodes {
    let mut nodes = Vec::new();
    let mut nav = CodeNav::default();
    let mut seen = std::collections::HashSet::new();

    for &(pattern, extract_name) in EMITTER_PATTERNS {
        if !source.contains(pattern) {
            continue;
        }
        let event_name = if extract_name {
            extract_event_name(source, pattern)
        } else {
            None
        }
        .unwrap_or_else(|| pattern.trim_matches('.').trim_end_matches('(').to_string());

        if seen.insert(event_name.clone()) {
            let qname = format!("event_emit:{event_name}");
            let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::EVENT_EMITTER, &qname);
            nodes.push(Node {
                id,
                repo,
                confidence: Confidence::Weak,
                cells: vec![],
            });
            nav.record(id, &event_name, &qname, node_kind::EVENT_EMITTER, Some(module_id));
        }
    }

    EventNodes { nodes, nav }
}

pub fn extract_event_handler_nodes(
    source: &str,
    module_id: NodeId,
    repo: RepoId,
) -> EventNodes {
    let mut nodes = Vec::new();
    let mut nav = CodeNav::default();
    let mut seen = std::collections::HashSet::new();

    for &(pattern, extract_name) in HANDLER_PATTERNS {
        if !source.contains(pattern) {
            continue;
        }
        let event_name = if extract_name {
            extract_event_name(source, pattern)
        } else {
            None
        }
        .unwrap_or_else(|| pattern.trim_matches('.').trim_end_matches('(').to_string());

        if seen.insert(event_name.clone()) {
            let qname = format!("event_handle:{event_name}");
            let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::EVENT_HANDLER, &qname);
            nodes.push(Node {
                id,
                repo,
                confidence: Confidence::Weak,
                cells: vec![],
            });
            nav.record(id, &event_name, &qname, node_kind::EVENT_HANDLER, Some(module_id));
        }
    }

    EventNodes { nodes, nav }
}

fn extract_event_name(source: &str, pattern: &str) -> Option<String> {
    let idx = source.find(pattern)?;
    let after = &source[idx + pattern.len()..];
    let trimmed = after.trim_start();
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
    fn detects_emit() {
        let source = "emitter.emit('user.created', data);";
        let result = extract_event_emitter_nodes(source, module_id(), repo());
        assert!(!result.nodes.is_empty());
        assert!(result.nav.qname_by_id.values().any(|q| q == "event_emit:user.created"));
    }

    #[test]
    fn detects_handler() {
        let source = "emitter.on('user.created', handler);";
        let result = extract_event_handler_nodes(source, module_id(), repo());
        assert!(!result.nodes.is_empty());
        assert!(result.nav.qname_by_id.values().any(|q| q == "event_handle:user.created"));
    }

    #[test]
    fn detects_nest_event_pattern() {
        let source = "@EventPattern('order.placed')\nasync handleOrder(data) {}";
        let result = extract_event_handler_nodes(source, module_id(), repo());
        assert!(result.nav.qname_by_id.values().any(|q| q == "event_handle:order.placed"));
    }
}
