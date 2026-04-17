//! Vue component/composable + Vue Router extraction.
//!
//! Pattern-based. Runs per-file on TS under Vue-detected projects. Emits:
//!   - COMPONENT: one per `.vue` file (name from basename) + `defineComponent({...})`.
//!   - COMPOSABLE: `export function useX` / `export const useX = (...) =>`.
//!   - ROUTE: `{ path: '/x', component: X }` → GET /x (Vue Router shape).

use repo_graph_code_domain::{CodeNav, GRAPH_TYPE, cell_type, node_kind};
use repo_graph_core::{Cell, CellPayload, Confidence, Node, NodeId, RepoId};

pub struct VueNodes {
    pub nodes: Vec<Node>,
    pub nav: CodeNav,
}

pub fn extract_vue_nodes(
    source: &str,
    path: &str,
    module_qname: &str,
    module_id: NodeId,
    repo: RepoId,
) -> VueNodes {
    let mut nodes = Vec::new();
    let mut nav = CodeNav::default();

    // --- Component: one per .vue file, keyed by basename.
    if path.ends_with(".vue") {
        if let Some(name) = vue_component_name_from_path(path) {
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
    }
    // `defineComponent` usage (in any .ts / .vue <script> content).
    for name in scan_define_component_names(source) {
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

    // --- Composables: `useX` function/const declarations.
    for name in scan_composable_names(source) {
        let qname = format!("{module_qname}::{name}");
        let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::COMPOSABLE, &qname);
        nodes.push(Node {
            id,
            repo,
            confidence: Confidence::Medium,
            cells: Vec::new(),
        });
        nav.record(id, &name, &qname, node_kind::COMPOSABLE, Some(module_id));
    }

    // --- Vue Router routes: `{ path: '/x', component: X }`.
    let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();
    for path_str in scan_router_paths(source) {
        let normalized = if path_str.starts_with('/') {
            path_str
        } else {
            format!("/{path_str}")
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

    VueNodes { nodes, nav }
}

fn vue_component_name_from_path(path: &str) -> Option<String> {
    let norm = path.replace('\\', "/");
    let filename = norm.rsplit('/').next()?;
    let stem = filename.strip_suffix(".vue")?;
    if stem.is_empty() {
        None
    } else {
        Some(stem.to_string())
    }
}

fn scan_define_component_names(source: &str) -> Vec<String> {
    let mut out = Vec::new();
    for line in source.lines() {
        let t = line.trim_start();
        // `export default defineComponent({...})` → emit component named after
        // file basename — skip here since we already emit from path.
        // Pattern of interest: `const X = defineComponent({...})` or
        // `export const X = defineComponent(`
        if let Some(rest) = t.strip_prefix("export const ") {
            if let Some(name) = take_ident(rest) {
                if line.contains("defineComponent(") {
                    out.push(name);
                }
            }
        } else if let Some(rest) = t.strip_prefix("const ") {
            if let Some(name) = take_ident(rest) {
                if line.contains("defineComponent(") {
                    out.push(name);
                }
            }
        }
    }
    dedup(out)
}

fn scan_composable_names(source: &str) -> Vec<String> {
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
            if is_composable_name(&name) {
                out.push(name);
            }
        }
    }
    dedup(out)
}

fn scan_router_paths(source: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut search_from = 0;
    while let Some(rel) = source[search_from..].find("path:") {
        let start = search_from + rel + "path:".len();
        let rest = source[start..].trim_start();
        if let Some(path) = first_string_literal(rest) {
            out.push(path);
        }
        search_from = start + 1;
    }
    dedup(out)
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

fn is_composable_name(s: &str) -> bool {
    if !s.starts_with("use") || s.len() < 4 {
        return false;
    }
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
    fn component_from_vue_path() {
        let r = extract_vue_nodes("", "src/components/UserCard.vue", "test", module_id(), repo());
        let names: Vec<&str> = r
            .nav
            .kind_by_id
            .iter()
            .filter(|(_, k)| **k == node_kind::COMPONENT)
            .filter_map(|(id, _)| r.nav.name_by_id.get(id).map(|s| s.as_str()))
            .collect();
        assert!(names.contains(&"UserCard"));
    }

    #[test]
    fn composable_detected() {
        let src = "export function useAuth() { return {} }";
        let r = extract_vue_nodes(src, "src/composables/useAuth.ts", "test", module_id(), repo());
        let names: Vec<&str> = r
            .nav
            .kind_by_id
            .iter()
            .filter(|(_, k)| **k == node_kind::COMPOSABLE)
            .filter_map(|(id, _)| r.nav.name_by_id.get(id).map(|s| s.as_str()))
            .collect();
        assert!(names.contains(&"useAuth"));
    }

    #[test]
    fn router_routes() {
        let src = r#"
const routes = [
    { path: '/', component: Home },
    { path: '/users', component: Users },
    { path: '/users/:id', component: UserDetail },
];
createRouter({ history: createWebHistory(), routes });
"#;
        let r = extract_vue_nodes(src, "src/router.ts", "test", module_id(), repo());
        let names: Vec<&str> = r
            .nav
            .name_by_id
            .iter()
            .filter(|(id, _)| r.nav.kind_by_id.get(*id) == Some(&node_kind::ROUTE))
            .map(|(_, n)| n.as_str())
            .collect();
        assert!(names.contains(&"GET /"));
        assert!(names.contains(&"GET /users"));
        assert!(names.contains(&"GET /users/:id"));
    }

    #[test]
    fn define_component_const() {
        let src = "export const UserCard = defineComponent({ props: {} });";
        let r = extract_vue_nodes(src, "src/UserCard.ts", "test", module_id(), repo());
        let names: Vec<&str> = r
            .nav
            .kind_by_id
            .iter()
            .filter(|(_, k)| **k == node_kind::COMPONENT)
            .filter_map(|(id, _)| r.nav.name_by_id.get(id).map(|s| s.as_str()))
            .collect();
        assert!(names.contains(&"UserCard"));
    }
}
