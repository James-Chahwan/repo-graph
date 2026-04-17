use std::collections::HashMap;

use repo_graph_core::{Cell, CellPayload, Confidence, Edge, Node, NodeId, RepoId};
use tree_sitter::{Node as TsNode, Parser};

pub use repo_graph_code_domain::{
    CallQualifier, CallSite, CodeNav, FileParse, GRAPH_TYPE, ImportStmt, ImportTarget, ParseError,
    UnresolvedRef, cell_type, edge_category, node_kind,
};

pub fn parse_file(
    source: &str,
    file_rel_path: &str,
    module_qname: &str,
    repo: RepoId,
) -> Result<FileParse, ParseError> {
    let mut parser = Parser::new();
    let lang: tree_sitter::Language = tree_sitter_rust::LANGUAGE.into();
    parser
        .set_language(&lang)
        .map_err(|e| ParseError::LanguageInit(e.to_string()))?;
    let tree = parser.parse(source, None).ok_or(ParseError::NoTree)?;
    let src = source.as_bytes();
    let root = tree.root_node();

    let mut acc = Acc::default();

    let module_id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::MODULE, module_qname);
    acc.nodes.push(Node {
        id: module_id,
        repo,
        confidence: Confidence::Strong,
        cells: file_cells(&root, src, file_rel_path),
    });
    let module_simple = module_qname.rsplit("::").next().unwrap_or(module_qname);
    acc.nav
        .record(module_id, module_simple, module_qname, node_kind::MODULE, None);

    // First pass: collect type names → NodeId for impl block resolution.
    let mut type_ids: HashMap<String, NodeId> = HashMap::new();
    let mut cursor = root.walk();
    for child in root.named_children(&mut cursor) {
        match child.kind() {
            "struct_item" | "enum_item" | "trait_item" => {
                if let Some(name) = child.child_by_field_name("name") {
                    let name_str = text_of(name, src);
                    let kind = match child.kind() {
                        "struct_item" => node_kind::STRUCT,
                        "enum_item" => node_kind::ENUM,
                        "trait_item" => node_kind::INTERFACE,
                        _ => unreachable!(),
                    };
                    let qname = format!("{module_qname}::{name_str}");
                    let id = NodeId::from_parts(GRAPH_TYPE, repo, kind, &qname);
                    type_ids.insert(name_str.to_string(), id);

                    acc.nodes.push(Node {
                        id,
                        repo,
                        confidence: Confidence::Strong,
                        cells: entity_cells(&child, src, file_rel_path),
                    });
                    acc.edges.push(Edge {
                        from: module_id,
                        to: id,
                        category: edge_category::DEFINES,
                        confidence: Confidence::Strong,
                    });
                    acc.nav.record(id, name_str, &qname, kind, Some(module_id));
                }
            }
            _ => {}
        }
    }

    // Second pass: functions, impl blocks, use statements.
    let mut cursor = root.walk();
    for child in root.named_children(&mut cursor) {
        match child.kind() {
            "function_item" => {
                visit_function(child, src, file_rel_path, module_qname, module_id, repo, &mut acc);
            }
            "impl_item" => {
                visit_impl(
                    child, src, file_rel_path, module_qname, module_id, repo, &type_ids, &mut acc,
                );
            }
            "use_declaration" => {
                collect_use(child, src, module_qname, &mut acc);
            }
            "attribute_item" => {
                visit_route_attr(child, src, file_rel_path, module_id, repo, &mut acc);
            }
            _ => {}
        }
    }

    scan_axum_routes(source, repo, &mut acc);

    Ok(FileParse {
        nodes: acc.nodes,
        edges: acc.edges,
        imports: acc.imports,
        calls: acc.calls,
        refs: acc.refs,
        nav: acc.nav,
    })
}

#[derive(Default)]
struct Acc {
    nodes: Vec<Node>,
    edges: Vec<Edge>,
    imports: Vec<ImportStmt>,
    calls: Vec<CallSite>,
    refs: Vec<UnresolvedRef>,
    nav: CodeNav,
}

fn visit_function(
    node: TsNode,
    src: &[u8],
    file_rel: &str,
    module_qname: &str,
    module_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    let Some(name_node) = node.child_by_field_name("name") else {
        return;
    };
    let name = text_of(name_node, src);
    let qname = format!("{module_qname}::{name}");
    let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::FUNCTION, &qname);

    acc.nodes.push(Node {
        id,
        repo,
        confidence: Confidence::Strong,
        cells: entity_cells(&node, src, file_rel),
    });
    acc.edges.push(Edge {
        from: module_id,
        to: id,
        category: edge_category::DEFINES,
        confidence: Confidence::Strong,
    });
    acc.nav
        .record(id, name, &qname, node_kind::FUNCTION, Some(module_id));

    if let Some(body) = node.child_by_field_name("body") {
        collect_calls_in(body, src, id, acc);
    }
}

#[allow(clippy::too_many_arguments)]
fn visit_impl(
    node: TsNode,
    src: &[u8],
    file_rel: &str,
    module_qname: &str,
    module_id: NodeId,
    repo: RepoId,
    type_ids: &HashMap<String, NodeId>,
    acc: &mut Acc,
) {
    // `impl Foo { ... }` or `impl Trait for Foo { ... }`
    // Find the target type name — it's the `type` field.
    let Some(type_node) = node.child_by_field_name("type") else {
        return;
    };
    let type_name = text_of(type_node, src);
    // Strip generic parameters: `Foo<T>` → `Foo`
    let base_name = type_name.split('<').next().unwrap_or(type_name);
    let parent_id = type_ids.get(base_name).copied().unwrap_or(module_id);

    let Some(body) = node.child_by_field_name("body") else {
        return;
    };
    let mut cursor = body.walk();
    for child in body.named_children(&mut cursor) {
        if child.kind() == "function_item" {
            let Some(name_node) = child.child_by_field_name("name") else {
                continue;
            };
            let name = text_of(name_node, src);
            let qname = format!("{module_qname}::{base_name}::{name}");
            let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::METHOD, &qname);

            acc.nodes.push(Node {
                id,
                repo,
                confidence: Confidence::Strong,
                cells: entity_cells(&child, src, file_rel),
            });
            acc.edges.push(Edge {
                from: parent_id,
                to: id,
                category: edge_category::DEFINES,
                confidence: Confidence::Strong,
            });
            acc.nav
                .record(id, name, &qname, node_kind::METHOD, Some(parent_id));

            if let Some(fn_body) = child.child_by_field_name("body") {
                collect_calls_in(fn_body, src, id, acc);
            }
        }
    }
}

fn collect_use(node: TsNode, src: &[u8], from_module: &str, acc: &mut Acc) {
    // `use crate::foo::bar;` or `use crate::foo::{bar, baz};` or `use super::foo;`
    let text = text_of(node, src);
    let trimmed = text.trim_start_matches("use ").trim_end_matches(';').trim();

    if trimmed.starts_with("crate::") {
        let path = trimmed.trim_start_matches("crate::");
        if let Some(brace_pos) = path.find('{') {
            // `crate::foo::{bar, baz}` — multiple symbol imports
            let base = path[..brace_pos].trim_end_matches("::");
            let names_part = &path[brace_pos + 1..].trim_end_matches('}');
            for name in names_part.split(',') {
                let name = name.trim();
                if name == "self" || name.is_empty() {
                    continue;
                }
                let (actual_name, alias) = if let Some((n, a)) = name.split_once(" as ") {
                    (n.trim(), Some(a.trim().to_string()))
                } else {
                    (name, None)
                };
                acc.imports.push(ImportStmt {
                    from_module: from_module.to_string(),
                    target: ImportTarget::Symbol {
                        module: base.to_string(),
                        name: actual_name.to_string(),
                        alias,
                        level: 0,
                    },
                });
            }
        } else if let Some((module, name)) = path.rsplit_once("::") {
            // `crate::foo::bar` — single symbol import
            let (actual_name, alias) = if let Some((n, a)) = name.split_once(" as ") {
                (n.trim(), Some(a.trim().to_string()))
            } else {
                (name, None)
            };
            acc.imports.push(ImportStmt {
                from_module: from_module.to_string(),
                target: ImportTarget::Symbol {
                    module: module.to_string(),
                    name: actual_name.to_string(),
                    alias,
                    level: 0,
                },
            });
        } else {
            // `crate::foo` — module import
            acc.imports.push(ImportStmt {
                from_module: from_module.to_string(),
                target: ImportTarget::Module {
                    path: path.to_string(),
                    alias: None,
                },
            });
        }
    } else if trimmed.starts_with("super::") {
        let path = trimmed.trim_start_matches("super::");
        if let Some((module, name)) = path.rsplit_once("::") {
            acc.imports.push(ImportStmt {
                from_module: from_module.to_string(),
                target: ImportTarget::Symbol {
                    module: format!("super::{module}"),
                    name: name.to_string(),
                    alias: None,
                    level: 1,
                },
            });
        } else {
            acc.imports.push(ImportStmt {
                from_module: from_module.to_string(),
                target: ImportTarget::Module {
                    path: format!("super::{path}"),
                    alias: None,
                },
            });
        }
    }
    // External crate imports (std::, etc.) — skip, won't resolve internally.
}

fn visit_route_attr(
    node: TsNode,
    src: &[u8],
    _file_rel: &str,
    module_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    let text = text_of(node, src);
    // Actix/Rocket: #[get("/path")] or #[post("/path")]
    let methods = ["get", "post", "put", "delete", "patch", "head", "options"];
    for method in &methods {
        let prefix = format!("#[{method}(\"");
        if let Some(rest) = text.strip_prefix(&prefix)
            && let Some(end) = rest.find('"')
        {
            let path = &rest[..end];
            let method_upper = method.to_uppercase();
            let route_name = format!("{method_upper} {path}");
            let route_id =
                NodeId::from_parts(GRAPH_TYPE, repo, node_kind::ROUTE, &route_name);
            acc.nodes.push(Node {
                id: route_id,
                repo,
                confidence: Confidence::Strong,
                cells: vec![Cell {
                    kind: cell_type::ROUTE_METHOD,
                    payload: CellPayload::Text(method_upper.clone()),
                }],
            });
            acc.edges.push(Edge {
                from: route_id,
                to: module_id,
                category: edge_category::HANDLED_BY,
                confidence: Confidence::Strong,
            });
            acc.nav.record(
                route_id,
                &route_name,
                &route_name,
                node_kind::ROUTE,
                None,
            );
        }
    }
}

fn scan_axum_routes(source: &str, repo: RepoId, acc: &mut Acc) {
    // Axum: Router::new().route("/path", get(handler).post(handler2))
    //                    .route("/users/:id", get(get_user))
    let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();
    let needle = ".route(";
    let mut search_from = 0;
    let bytes = source.as_bytes();
    while let Some(rel) = source[search_from..].find(needle) {
        let start = search_from + rel + needle.len();
        let Some(path_end) = source[start..].find('"') else {
            search_from = start;
            continue;
        };
        let q_start = start + path_end + 1;
        let mut j = q_start;
        while j < bytes.len() && bytes[j] != b'"' {
            if bytes[j] == b'\\' && j + 1 < bytes.len() {
                j += 2;
            } else {
                j += 1;
            }
        }
        if j >= bytes.len() {
            break;
        }
        let path = &source[q_start..j];
        let Some(call_end) = find_matching_paren(&source[start..]) else {
            search_from = j + 1;
            continue;
        };
        let args_text = &source[start..start + call_end];
        for method in ["get", "post", "put", "patch", "delete", "head", "options"] {
            let pat = format!("{method}(");
            if contains_method_call(args_text, &pat) {
                let mu = method.to_ascii_uppercase();
                let route_name = format!("{mu} {path}");
                if seen.insert(route_name.clone()) {
                    emit_axum_route(&mu, path, repo, acc);
                }
            }
        }
        search_from = start + call_end + 1;
    }
}

fn find_matching_paren(s: &str) -> Option<usize> {
    let bytes = s.as_bytes();
    let mut depth = 1usize;
    let mut i = 0;
    while i < bytes.len() {
        match bytes[i] {
            b'(' => depth += 1,
            b')' => {
                depth -= 1;
                if depth == 0 {
                    return Some(i);
                }
            }
            b'"' => {
                i += 1;
                while i < bytes.len() && bytes[i] != b'"' {
                    if bytes[i] == b'\\' && i + 1 < bytes.len() {
                        i += 2;
                    } else {
                        i += 1;
                    }
                }
            }
            _ => {}
        }
        i += 1;
    }
    None
}

fn contains_method_call(hay: &str, pat: &str) -> bool {
    // Match `pat` with a preceding non-word char (so `get(` matches, but not `target(`).
    let bytes = hay.as_bytes();
    let pat_bytes = pat.as_bytes();
    let mut i = 0;
    while i + pat_bytes.len() <= bytes.len() {
        if &bytes[i..i + pat_bytes.len()] == pat_bytes {
            let prev_ok = i == 0 || {
                let p = bytes[i - 1];
                !(p.is_ascii_alphanumeric() || p == b'_')
            };
            if prev_ok {
                return true;
            }
        }
        i += 1;
    }
    false
}

fn emit_axum_route(method: &str, path: &str, repo: RepoId, acc: &mut Acc) {
    let route_name = format!("{method} {path}");
    let route_id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::ROUTE, &route_name);
    acc.nodes.push(Node {
        id: route_id,
        repo,
        confidence: Confidence::Medium,
        cells: vec![Cell {
            kind: cell_type::ROUTE_METHOD,
            payload: CellPayload::Text(method.to_string()),
        }],
    });
    acc.nav
        .record(route_id, &route_name, &route_name, node_kind::ROUTE, None);
}

fn collect_calls_in(node: TsNode, src: &[u8], from: NodeId, acc: &mut Acc) {
    let mut stack = vec![node];
    while let Some(n) = stack.pop() {
        if n.kind() == "call_expression"
            && let Some(func) = n.child_by_field_name("function")
        {
            let qualifier = classify_call(func, src);
            acc.calls.push(CallSite { from, qualifier });
        }
        // Don't recurse into nested function items (closures are ok).
        let mut cursor = n.walk();
        for child in n.named_children(&mut cursor) {
            if child.kind() != "function_item" {
                stack.push(child);
            }
        }
    }
}

fn classify_call(func_node: TsNode, src: &[u8]) -> CallQualifier {
    match func_node.kind() {
        "identifier" => CallQualifier::Bare(text_of(func_node, src).to_string()),
        "field_expression" => {
            let obj = func_node
                .child_by_field_name("value")
                .map(|n| text_of(n, src))
                .unwrap_or("");
            let field = func_node
                .child_by_field_name("field")
                .map(|n| text_of(n, src))
                .unwrap_or("");
            if obj == "self" {
                CallQualifier::SelfMethod(field.to_string())
            } else if func_node
                .child_by_field_name("value")
                .is_some_and(|v| v.kind() == "identifier")
            {
                CallQualifier::Attribute {
                    base: obj.to_string(),
                    name: field.to_string(),
                }
            } else {
                CallQualifier::ComplexReceiver {
                    receiver: obj.to_string(),
                    name: field.to_string(),
                }
            }
        }
        "scoped_identifier" => {
            let path = func_node
                .child_by_field_name("path")
                .map(|n| text_of(n, src))
                .unwrap_or("");
            let name = func_node
                .child_by_field_name("name")
                .map(|n| text_of(n, src))
                .unwrap_or("");
            CallQualifier::Attribute {
                base: path.to_string(),
                name: name.to_string(),
            }
        }
        _ => CallQualifier::ComplexReceiver {
            receiver: text_of(func_node, src).to_string(),
            name: String::new(),
        },
    }
}

// ============================================================================
// Helpers
// ============================================================================

fn text_of<'a>(node: TsNode<'a>, src: &'a [u8]) -> &'a str {
    node.utf8_text(src).unwrap_or("")
}

fn file_cells(root: &TsNode, src: &[u8], file_rel: &str) -> Vec<Cell> {
    vec![
        Cell {
            kind: cell_type::CODE,
            payload: CellPayload::Text(text_of(*root, src).to_string()),
        },
        Cell {
            kind: cell_type::POSITION,
            payload: CellPayload::Text(format!(
                "{}:{}-{}",
                file_rel,
                root.start_position().row + 1,
                root.end_position().row + 1,
            )),
        },
    ]
}

fn entity_cells(node: &TsNode, src: &[u8], file_rel: &str) -> Vec<Cell> {
    vec![
        Cell {
            kind: cell_type::CODE,
            payload: CellPayload::Text(text_of(*node, src).to_string()),
        },
        Cell {
            kind: cell_type::POSITION,
            payload: CellPayload::Text(format!(
                "{}:{}-{}",
                file_rel,
                node.start_position().row + 1,
                node.end_position().row + 1,
            )),
        },
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    fn repo() -> RepoId {
        RepoId(1)
    }

    #[test]
    fn structs_and_functions() {
        let source = r#"
pub struct User {
    name: String,
}

pub fn create_user(name: &str) -> User {
    User { name: name.to_string() }
}
"#;
        let fp = parse_file(source, "src/models.rs", "myapp::models", repo()).unwrap();
        let names: Vec<&str> = fp.nav.name_by_id.values().map(|s| s.as_str()).collect();
        assert!(names.contains(&"models"));
        assert!(names.contains(&"User"));
        assert!(names.contains(&"create_user"));
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::STRUCT).count(), 1);
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::FUNCTION).count(), 1);
    }

    #[test]
    fn impl_methods() {
        let source = r#"
struct Foo;

impl Foo {
    pub fn bar(&self) -> i32 { 42 }
    fn baz(&mut self) {}
}
"#;
        let fp = parse_file(source, "src/foo.rs", "myapp::foo", repo()).unwrap();
        let methods: Vec<&str> = fp
            .nav
            .kind_by_id
            .iter()
            .filter(|(_, k)| **k == node_kind::METHOD)
            .filter_map(|(id, _)| fp.nav.name_by_id.get(id).map(|s| s.as_str()))
            .collect();
        assert!(methods.contains(&"bar"));
        assert!(methods.contains(&"baz"));
        assert_eq!(methods.len(), 2);
    }

    #[test]
    fn enums_and_traits() {
        let source = r#"
pub enum Color {
    Red,
    Green,
    Blue,
}

pub trait Drawable {
    fn draw(&self);
}
"#;
        let fp = parse_file(source, "src/lib.rs", "myapp", repo()).unwrap();
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::ENUM).count(), 1);
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::INTERFACE).count(), 1);
    }

    #[test]
    fn use_imports() {
        let source = r#"
use crate::models::User;
use crate::db;
use crate::auth::{login, logout};
use std::io::Read;
"#;
        let fp = parse_file(source, "src/main.rs", "myapp", repo()).unwrap();
        // std import is skipped (external)
        assert_eq!(fp.imports.len(), 4); // User, db, login, logout
    }

    #[test]
    fn self_method_calls() {
        let source = r#"
struct Server;

impl Server {
    fn handle(&self) {
        self.validate();
        self.respond();
    }
    fn validate(&self) {}
    fn respond(&self) {}
}
"#;
        let fp = parse_file(source, "src/server.rs", "myapp::server", repo()).unwrap();
        let self_calls: Vec<_> = fp
            .calls
            .iter()
            .filter(|c| matches!(&c.qualifier, CallQualifier::SelfMethod(_)))
            .collect();
        assert_eq!(self_calls.len(), 2);
    }

    #[test]
    fn axum_routes_basic() {
        let source = r#"
async fn list_users() {}
async fn create_user() {}
async fn get_user() {}

fn app() -> Router {
    Router::new()
        .route("/users", get(list_users).post(create_user))
        .route("/users/:id", get(get_user))
}
"#;
        let fp = parse_file(source, "src/main.rs", "myapp", repo()).unwrap();
        let route_names: Vec<&str> = fp
            .nav
            .name_by_id
            .iter()
            .filter(|(id, _)| fp.nav.kind_by_id.get(*id) == Some(&node_kind::ROUTE))
            .map(|(_, n)| n.as_str())
            .collect();
        assert!(route_names.contains(&"GET /users"));
        assert!(route_names.contains(&"POST /users"));
        assert!(route_names.contains(&"GET /users/:id"));
    }
}
