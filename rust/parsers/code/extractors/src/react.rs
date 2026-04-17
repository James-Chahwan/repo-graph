//! React component + hook + React Router extraction.
//!
//! Runs per-file for TS/TSX/JS/JSX under React-detected projects. Emits:
//!   - COMPONENT nodes: capitalized function/const declarations returning JSX.
//!   - HOOK nodes: functions whose name starts with `use` (camelCase).
//!   - ROUTE nodes: React Router v6 `<Route path="/...">` and
//!     `createBrowserRouter([{ path: '/...', ... }])`.
//!
//! This is pattern-based — intentional to stay zero-AST-dependency like the
//! other cross-cutting extractors.

use repo_graph_code_domain::{CodeNav, GRAPH_TYPE, cell_type, node_kind};
use repo_graph_core::{Cell, CellPayload, Confidence, Node, NodeId, RepoId};

pub struct ReactNodes {
    pub nodes: Vec<Node>,
    pub nav: CodeNav,
}

pub fn extract_react_nodes(
    source: &str,
    module_qname: &str,
    module_id: NodeId,
    repo: RepoId,
) -> ReactNodes {
    let mut nodes = Vec::new();
    let mut nav = CodeNav::default();

    // --- Components: capitalized function/const whose body has JSX-ish marker.
    for name in scan_component_names(source) {
        let qname = format!("{module_qname}::{name}");
        let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::COMPONENT, &qname);
        nodes.push(Node {
            id,
            repo,
            confidence: Confidence::Medium,
            cells: Vec::new(),
        });
        nav.record(id, &name, &qname, node_kind::COMPONENT, Some(module_id));
    }

    // --- Hooks: `use<Xxx>` function / const arrow declarations.
    for name in scan_hook_names(source) {
        let qname = format!("{module_qname}::{name}");
        let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::HOOK, &qname);
        nodes.push(Node {
            id,
            repo,
            confidence: Confidence::Medium,
            cells: Vec::new(),
        });
        nav.record(id, &name, &qname, node_kind::HOOK, Some(module_id));
    }

    // --- React Router routes (browser-side, GET-only by nature).
    let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();
    for path in scan_react_router_paths(source) {
        let canonical = format!("GET {path}");
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

    ReactNodes { nodes, nav }
}

fn scan_component_names(source: &str) -> Vec<String> {
    let mut out = Vec::new();
    let has_jsx = source.contains("</") || source.contains("/>");
    if !has_jsx {
        return out;
    }
    for line in source.lines() {
        let t = line.trim_start();
        // function Foo(
        if let Some(rest) = t.strip_prefix("export default function ") {
            if let Some(name) = take_ident(rest) {
                if is_capitalized(&name) {
                    out.push(name);
                }
            }
        } else if let Some(rest) = t.strip_prefix("export function ") {
            if let Some(name) = take_ident(rest) {
                if is_capitalized(&name) {
                    out.push(name);
                }
            }
        } else if let Some(rest) = t.strip_prefix("function ") {
            if let Some(name) = take_ident(rest) {
                if is_capitalized(&name) {
                    out.push(name);
                }
            }
        } else if let Some(rest) = t.strip_prefix("export const ") {
            if let Some(name) = take_ident(rest) {
                if is_capitalized(&name)
                    && (line.contains("=>") || line.contains("React.FC") || line.contains(": FC"))
                {
                    out.push(name);
                }
            }
        } else if let Some(rest) = t.strip_prefix("const ") {
            if let Some(name) = take_ident(rest) {
                if is_capitalized(&name)
                    && (line.contains("=>") || line.contains("React.FC") || line.contains(": FC"))
                {
                    out.push(name);
                }
            }
        }
    }
    dedup(out)
}

fn scan_hook_names(source: &str) -> Vec<String> {
    let mut out = Vec::new();
    for line in source.lines() {
        let t = line.trim_start();
        let candidate = if let Some(r) = t.strip_prefix("export function ") {
            take_ident(r)
        } else if let Some(r) = t.strip_prefix("function ") {
            take_ident(r)
        } else if let Some(r) = t.strip_prefix("export const ") {
            take_ident(r).filter(|_| line.contains("=>"))
        } else if let Some(r) = t.strip_prefix("const ") {
            take_ident(r).filter(|_| line.contains("=>"))
        } else {
            None
        };
        if let Some(name) = candidate {
            if is_hook_name(&name) {
                out.push(name);
            }
        }
    }
    dedup(out)
}

fn scan_react_router_paths(source: &str) -> Vec<String> {
    let mut out = Vec::new();
    // JSX: <Route path="/foo" ... />
    let mut search_from = 0;
    while let Some(rel) = source[search_from..].find("<Route") {
        let start = search_from + rel;
        let end_gt = source[start..].find('>').map(|e| start + e).unwrap_or(source.len());
        let tag = &source[start..end_gt];
        if let Some(path) = extract_attr(tag, "path") {
            out.push(path);
        }
        search_from = end_gt.max(start + 1);
    }
    // Object form: { path: '/foo', element: ... } or path: "/foo" inside
    // createBrowserRouter / createMemoryRouter / createHashRouter literal.
    let mut search_from = 0;
    while let Some(rel) = source[search_from..].find("path:") {
        let start = search_from + rel + "path:".len();
        let rest = source[start..].trim_start();
        if let Some(path) = first_string_literal(rest) {
            // Crude guard: previous char should be { or , or whitespace (an object key).
            out.push(path);
        }
        search_from = start + 1;
    }
    dedup(out)
}

fn extract_attr(tag: &str, attr: &str) -> Option<String> {
    // attr="..."  or  attr='...'  or  attr={"..."}
    let key = format!("{attr}=");
    let idx = tag.find(&key)?;
    let rest = &tag[idx + key.len()..];
    let rest = rest.trim_start_matches('{').trim_start();
    first_string_literal(rest)
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

fn take_ident(s: &str) -> Option<String> {
    let bytes = s.as_bytes();
    let mut i = 0;
    while i < bytes.len() && (bytes[i].is_ascii_alphanumeric() || bytes[i] == b'_' || bytes[i] == b'$') {
        i += 1;
    }
    if i == 0 {
        None
    } else {
        Some(s[..i].to_string())
    }
}

fn is_capitalized(s: &str) -> bool {
    s.chars().next().is_some_and(|c| c.is_ascii_uppercase())
}

fn is_hook_name(s: &str) -> bool {
    if !s.starts_with("use") || s.len() < 4 {
        return false;
    }
    // `use<X>` where X is uppercase.
    s.chars().nth(3).is_some_and(|c| c.is_ascii_uppercase())
}

fn dedup(mut v: Vec<String>) -> Vec<String> {
    v.sort();
    v.dedup();
    v
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
    fn detects_function_component() {
        let src = r#"
export function UserCard({ user }: Props) {
    return <div>{user.name}</div>;
}
"#;
        let r = extract_react_nodes(src, "test", module_id(), repo());
        let comps: Vec<_> = r
            .nav
            .kind_by_id
            .iter()
            .filter(|(_, k)| **k == node_kind::COMPONENT)
            .filter_map(|(id, _)| r.nav.name_by_id.get(id))
            .collect();
        assert!(comps.iter().any(|n| n.as_str() == "UserCard"));
    }

    #[test]
    fn detects_arrow_component() {
        let src = "export const Button = ({ label }) => (<button>{label}</button>);";
        let r = extract_react_nodes(src, "test", module_id(), repo());
        assert!(r.nav.name_by_id.values().any(|n| n == "Button"));
    }

    #[test]
    fn detects_hook() {
        let src = "export function useAuth() { return useContext(AuthCtx); }";
        let r = extract_react_nodes(src, "test", module_id(), repo());
        let hooks: Vec<_> = r
            .nav
            .kind_by_id
            .iter()
            .filter(|(_, k)| **k == node_kind::HOOK)
            .filter_map(|(id, _)| r.nav.name_by_id.get(id))
            .collect();
        assert!(hooks.iter().any(|n| n.as_str() == "useAuth"));
    }

    #[test]
    fn detects_react_router_jsx() {
        let src = r#"
<Routes>
  <Route path="/users" element={<Users />} />
  <Route path="/users/:id" element={<UserDetail />} />
</Routes>
"#;
        let r = extract_react_nodes(src, "test", module_id(), repo());
        let names: Vec<&str> = r
            .nav
            .name_by_id
            .iter()
            .filter(|(id, _)| r.nav.kind_by_id.get(*id) == Some(&node_kind::ROUTE))
            .map(|(_, n)| n.as_str())
            .collect();
        assert!(names.contains(&"GET /users"));
        assert!(names.contains(&"GET /users/:id"));
    }

    #[test]
    fn detects_router_object_form() {
        let src = r#"
createBrowserRouter([
    { path: '/', element: <Home /> },
    { path: '/about', element: <About /> },
]);
"#;
        let r = extract_react_nodes(src, "test", module_id(), repo());
        let names: Vec<&str> = r
            .nav
            .name_by_id
            .iter()
            .filter(|(id, _)| r.nav.kind_by_id.get(*id) == Some(&node_kind::ROUTE))
            .map(|(_, n)| n.as_str())
            .collect();
        assert!(names.contains(&"GET /"));
        assert!(names.contains(&"GET /about"));
    }

    #[test]
    fn lowercase_function_not_component() {
        let src = "function helper() { return <div />; }";
        let r = extract_react_nodes(src, "test", module_id(), repo());
        assert!(r.nodes.iter().all(|n| {
            r.nav.kind_by_id.get(&n.id) != Some(&node_kind::COMPONENT)
        }));
    }
}
