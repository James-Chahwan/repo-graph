//! Angular component/service/directive/pipe/guard/module + Angular Router extraction.
//!
//! Pattern-based, runs per-file on TS under Angular-detected projects. Emits:
//!   - COMPONENT: class with `@Component({...})` decorator.
//!   - SERVICE: class with `@Injectable({...})` decorator.
//!   - DIRECTIVE: class with `@Directive({...})` decorator.
//!   - PIPE: class with `@Pipe({...})` decorator.
//!   - GUARD: classes ending in `Guard` (CanActivate/CanDeactivate patterns).
//!   - ROUTE: `{ path: 'users', component: UsersComponent }` entries (GET).

use repo_graph_code_domain::{CodeNav, GRAPH_TYPE, cell_type, node_kind};
use repo_graph_core::{Cell, CellPayload, Confidence, Node, NodeId, NodeKindId, RepoId};

pub struct AngularNodes {
    pub nodes: Vec<Node>,
    pub nav: CodeNav,
}

pub fn extract_angular_nodes(
    source: &str,
    module_qname: &str,
    module_id: NodeId,
    repo: RepoId,
) -> AngularNodes {
    let mut nodes = Vec::new();
    let mut nav = CodeNav::default();

    for (name, kind) in scan_decorated_classes(source) {
        let qname = format!("{module_qname}::{name}");
        let id = NodeId::from_parts(GRAPH_TYPE, repo, kind, &qname);
        nodes.push(Node {
            id,
            repo,
            confidence: Confidence::Medium,
            cells: Vec::new(),
        });
        nav.record(id, &name, &qname, kind, Some(module_id));
    }

    let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();
    for path in scan_angular_router_paths(source) {
        let normalized = if path.starts_with('/') {
            path
        } else {
            format!("/{path}")
        };
        let canonical = format!("GET {normalized}");
        if !seen.insert(canonical.clone()) {
            continue;
        }
        let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::ROUTE, &canonical);
        nodes.push(Node {
            id,
            repo,
            confidence: Confidence::Medium,
            cells: vec![Cell {
                kind: cell_type::ROUTE_METHOD,
                payload: CellPayload::Text("GET".to_string()),
            }],
        });
        nav.record(id, &canonical, &canonical, node_kind::ROUTE, None);
    }

    AngularNodes { nodes, nav }
}

fn scan_decorated_classes(source: &str) -> Vec<(String, NodeKindId)> {
    let mut out: Vec<(String, NodeKindId)> = Vec::new();
    let lines: Vec<&str> = source.lines().collect();
    let mut pending: Option<NodeKindId> = None;
    for line in &lines {
        let t = line.trim_start();
        if t.starts_with("@Component(") {
            pending = Some(node_kind::COMPONENT);
            continue;
        }
        if t.starts_with("@Injectable(") {
            pending = Some(node_kind::SERVICE);
            continue;
        }
        if t.starts_with("@Directive(") {
            pending = Some(node_kind::DIRECTIVE);
            continue;
        }
        if t.starts_with("@Pipe(") {
            pending = Some(node_kind::PIPE);
            continue;
        }
        if let Some(kind) = pending {
            if let Some(name) = extract_class_name(t) {
                out.push((name, kind));
                pending = None;
                continue;
            }
            // still in between decorator and class — swallow blank/comment lines
            if t.is_empty() || t.starts_with("//") || t.starts_with("/*") || t.starts_with("*") {
                continue;
            }
            // Decorator didn't immediately precede class — keep pending alive only
            // across trivial lines; if we hit a non-trivial non-class line, drop it.
            if !t.starts_with('@') {
                pending = None;
            }
        }
    }
    // Convention-based: classes ending in `Guard` without a matching @ decorator
    // get GUARD kind.
    for line in &lines {
        let t = line.trim_start();
        if let Some(name) = extract_class_name(t) {
            if name.ends_with("Guard") && !out.iter().any(|(n, _)| n == &name) {
                out.push((name, node_kind::GUARD));
            }
        }
    }
    out.sort_by(|a, b| a.0.cmp(&b.0).then(a.1.0.cmp(&b.1.0)));
    out.dedup();
    out
}

fn extract_class_name(line: &str) -> Option<String> {
    let trimmed = line.trim_start_matches("export ").trim_start_matches("default ");
    let rest = trimmed.strip_prefix("class ")?;
    let name_end = rest
        .find(|c: char| !(c.is_ascii_alphanumeric() || c == '_' || c == '$'))
        .unwrap_or(rest.len());
    if name_end == 0 {
        None
    } else {
        Some(rest[..name_end].to_string())
    }
}

fn scan_angular_router_paths(source: &str) -> Vec<String> {
    let mut out = Vec::new();
    // Angular Router routes: `{ path: 'users', component: UsersComponent }`.
    let mut search_from = 0;
    while let Some(rel) = source[search_from..].find("path:") {
        let start = search_from + rel + "path:".len();
        let rest = source[start..].trim_start();
        if let Some(path) = first_string_literal(rest) {
            out.push(path);
        }
        search_from = start + 1;
    }
    // Also RouterModule.forRoot([...]) + forChild([...]).
    out.sort();
    out.dedup();
    out
}

fn first_string_literal(s: &str) -> Option<String> {
    let bytes = s.as_bytes();
    if bytes.is_empty() {
        return None;
    }
    let delim = match bytes[0] {
        b'"' => b'"',
        b'\'' => b'\'',
        b'`' => b'`',
        _ => return None,
    };
    let mut j = 1;
    while j < bytes.len() && bytes[j] != delim {
        if bytes[j] == b'\\' && j + 1 < bytes.len() {
            j += 2;
        } else {
            j += 1;
        }
    }
    if j < bytes.len() {
        Some(s[1..j].to_string())
    } else {
        None
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
    fn detects_component_service_directive_pipe() {
        let src = r#"
@Component({ selector: 'app-user' })
export class UserComponent {}

@Injectable({ providedIn: 'root' })
export class UserService {}

@Directive({ selector: '[appHi]' })
export class HiDirective {}

@Pipe({ name: 'upper' })
export class UpperPipe {}
"#;
        let r = extract_angular_nodes(src, "test", module_id(), repo());
        let get = |kind: NodeKindId| -> Vec<&str> {
            r.nav
                .kind_by_id
                .iter()
                .filter(|(_, k)| **k == kind)
                .filter_map(|(id, _)| r.nav.name_by_id.get(id).map(|s| s.as_str()))
                .collect()
        };
        assert!(get(node_kind::COMPONENT).contains(&"UserComponent"));
        assert!(get(node_kind::SERVICE).contains(&"UserService"));
        assert!(get(node_kind::DIRECTIVE).contains(&"HiDirective"));
        assert!(get(node_kind::PIPE).contains(&"UpperPipe"));
    }

    #[test]
    fn detects_guard() {
        let src = "export class AuthGuard { canActivate() { return true; } }";
        let r = extract_angular_nodes(src, "test", module_id(), repo());
        let guards: Vec<&str> = r
            .nav
            .kind_by_id
            .iter()
            .filter(|(_, k)| **k == node_kind::GUARD)
            .filter_map(|(id, _)| r.nav.name_by_id.get(id).map(|s| s.as_str()))
            .collect();
        assert!(guards.contains(&"AuthGuard"));
    }

    #[test]
    fn detects_routes() {
        let src = r#"
const routes: Routes = [
    { path: '', component: HomeComponent },
    { path: 'users', component: UsersComponent },
    { path: 'users/:id', component: UserDetailComponent },
];
RouterModule.forRoot(routes);
"#;
        let r = extract_angular_nodes(src, "test", module_id(), repo());
        let names: Vec<&str> = r
            .nav
            .name_by_id
            .iter()
            .filter(|(id, _)| r.nav.kind_by_id.get(*id) == Some(&node_kind::ROUTE))
            .map(|(_, n)| n.as_str())
            .collect();
        assert!(names.contains(&"GET /users"));
        assert!(names.contains(&"GET /users/:id"));
        assert!(names.contains(&"GET /"));
    }
}
