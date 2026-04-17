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
    let lang: tree_sitter::Language = tree_sitter_php::LANGUAGE_PHP.into();
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

    visit_children(root, src, file_rel_path, module_qname, module_id, repo, &mut acc);

    scan_laravel_routes(source, module_id, repo, &mut acc);

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

fn visit_children(
    node: TsNode,
    src: &[u8],
    file_rel: &str,
    parent_qname: &str,
    parent_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    let mut cursor = node.walk();
    for child in node.named_children(&mut cursor) {
        match child.kind() {
            "namespace_definition" => {
                visit_namespace(child, src, file_rel, parent_qname, parent_id, repo, acc);
            }
            "class_declaration" => {
                visit_class(child, src, file_rel, parent_qname, parent_id, repo, acc);
            }
            "interface_declaration" => {
                visit_interface(child, src, file_rel, parent_qname, parent_id, repo, acc);
            }
            "enum_declaration" => {
                visit_enum(child, src, file_rel, parent_qname, parent_id, repo, acc);
            }
            "function_definition" => {
                visit_function(child, src, file_rel, parent_qname, parent_id, repo, acc);
            }
            "namespace_use_declaration" => collect_use(child, src, parent_qname, acc),
            _ => {}
        }
    }
}

fn visit_namespace(
    node: TsNode,
    src: &[u8],
    file_rel: &str,
    _parent_qname: &str,
    parent_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    let Some(name_node) = node.child_by_field_name("name") else {
        return;
    };
    let name = text_of(name_node, src);
    let qname = name.replace('\\', "::");
    let ns_id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::PACKAGE, &qname);
    let simple = qname.rsplit("::").next().unwrap_or(&qname);

    acc.nodes.push(Node {
        id: ns_id,
        repo,
        confidence: Confidence::Strong,
        cells: entity_cells(&node, src, file_rel),
    });
    acc.edges.push(Edge {
        from: parent_id,
        to: ns_id,
        category: edge_category::CONTAINS,
        confidence: Confidence::Strong,
    });
    acc.nav
        .record(ns_id, simple, &qname, node_kind::PACKAGE, Some(parent_id));

    if let Some(body) = node.child_by_field_name("body") {
        visit_children(body, src, file_rel, &qname, ns_id, repo, acc);
    }
}

fn visit_class(
    node: TsNode,
    src: &[u8],
    file_rel: &str,
    parent_qname: &str,
    parent_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    let Some(name_node) = node.child_by_field_name("name") else {
        return;
    };
    let name = text_of(name_node, src);
    let qname = format!("{parent_qname}::{name}");
    let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::CLASS, &qname);

    acc.nodes.push(Node {
        id,
        repo,
        confidence: Confidence::Strong,
        cells: entity_cells(&node, src, file_rel),
    });
    acc.edges.push(Edge {
        from: parent_id,
        to: id,
        category: edge_category::DEFINES,
        confidence: Confidence::Strong,
    });
    acc.nav.record(id, name, &qname, node_kind::CLASS, Some(parent_id));

    if let Some(body) = node.child_by_field_name("body") {
        let mut cursor = body.walk();
        for child in body.named_children(&mut cursor) {
            if child.kind() == "method_declaration" {
                visit_method(child, src, file_rel, &qname, id, repo, acc);
            }
        }
    }

    check_route_attrs(node, src, id, repo, acc);
}

fn visit_interface(
    node: TsNode,
    src: &[u8],
    file_rel: &str,
    parent_qname: &str,
    parent_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    let Some(name_node) = node.child_by_field_name("name") else {
        return;
    };
    let name = text_of(name_node, src);
    let qname = format!("{parent_qname}::{name}");
    let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::INTERFACE, &qname);

    acc.nodes.push(Node {
        id,
        repo,
        confidence: Confidence::Strong,
        cells: entity_cells(&node, src, file_rel),
    });
    acc.edges.push(Edge {
        from: parent_id,
        to: id,
        category: edge_category::DEFINES,
        confidence: Confidence::Strong,
    });
    acc.nav
        .record(id, name, &qname, node_kind::INTERFACE, Some(parent_id));
}

fn visit_enum(
    node: TsNode,
    src: &[u8],
    file_rel: &str,
    parent_qname: &str,
    parent_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    let Some(name_node) = node.child_by_field_name("name") else {
        return;
    };
    let name = text_of(name_node, src);
    let qname = format!("{parent_qname}::{name}");
    let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::ENUM, &qname);

    acc.nodes.push(Node {
        id,
        repo,
        confidence: Confidence::Strong,
        cells: entity_cells(&node, src, file_rel),
    });
    acc.edges.push(Edge {
        from: parent_id,
        to: id,
        category: edge_category::DEFINES,
        confidence: Confidence::Strong,
    });
    acc.nav
        .record(id, name, &qname, node_kind::ENUM, Some(parent_id));
}

fn visit_function(
    node: TsNode,
    src: &[u8],
    file_rel: &str,
    parent_qname: &str,
    parent_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    let Some(name_node) = node.child_by_field_name("name") else {
        return;
    };
    let name = text_of(name_node, src);
    let qname = format!("{parent_qname}::{name}");
    let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::FUNCTION, &qname);

    acc.nodes.push(Node {
        id,
        repo,
        confidence: Confidence::Strong,
        cells: entity_cells(&node, src, file_rel),
    });
    acc.edges.push(Edge {
        from: parent_id,
        to: id,
        category: edge_category::DEFINES,
        confidence: Confidence::Strong,
    });
    acc.nav
        .record(id, name, &qname, node_kind::FUNCTION, Some(parent_id));

    if let Some(body) = node.child_by_field_name("body") {
        collect_calls_in(body, src, id, acc);
    }
}

fn visit_method(
    node: TsNode,
    src: &[u8],
    file_rel: &str,
    parent_qname: &str,
    parent_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    let Some(name_node) = node.child_by_field_name("name") else {
        return;
    };
    let name = text_of(name_node, src);
    let qname = format!("{parent_qname}::{name}");
    let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::METHOD, &qname);

    acc.nodes.push(Node {
        id,
        repo,
        confidence: Confidence::Strong,
        cells: entity_cells(&node, src, file_rel),
    });
    acc.edges.push(Edge {
        from: parent_id,
        to: id,
        category: edge_category::DEFINES,
        confidence: Confidence::Strong,
    });
    acc.nav
        .record(id, name, &qname, node_kind::METHOD, Some(parent_id));

    if let Some(body) = node.child_by_field_name("body") {
        collect_calls_in(body, src, id, acc);
    }

    check_route_attrs(node, src, id, repo, acc);
}

fn check_route_attrs(node: TsNode, src: &[u8], handler_id: NodeId, repo: RepoId, acc: &mut Acc) {
    let text = text_of(node, src);
    // Walk every #[Route(...)] occurrence — a class or method may carry multiple.
    let mut search_from = 0;
    while let Some(rel) = text[search_from..].find("#[Route(") {
        let start = search_from + rel + 8;
        let Some((path, consumed)) = extract_first_string(&text[start..]) else {
            search_from = start;
            continue;
        };
        let attr_end = find_attr_end(&text[start..]).unwrap_or(text.len() - start);
        let attr_text = &text[start..start + attr_end];
        let methods = parse_methods_kwarg(attr_text);
        if methods.is_empty() {
            emit_route_strong("ANY", &path, handler_id, repo, acc);
        } else {
            for m in methods {
                emit_route_strong(&m, &path, handler_id, repo, acc);
            }
        }
        search_from = start + consumed.max(1);
    }
}

fn extract_first_string(s: &str) -> Option<(String, usize)> {
    let bytes = s.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        let c = bytes[i];
        if c == b'\'' || c == b'"' {
            let delim = c;
            let start = i + 1;
            let mut j = start;
            while j < bytes.len() && bytes[j] != delim {
                if bytes[j] == b'\\' && j + 1 < bytes.len() {
                    j += 2;
                } else {
                    j += 1;
                }
            }
            if j < bytes.len() {
                return Some((s[start..j].to_string(), j + 1));
            }
            return None;
        }
        i += 1;
    }
    None
}

fn find_attr_end(s: &str) -> Option<usize> {
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
            b'\'' | b'"' => {
                let delim = bytes[i];
                i += 1;
                while i < bytes.len() && bytes[i] != delim {
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

fn parse_methods_kwarg(attr_text: &str) -> Vec<String> {
    let Some(pos) = attr_text.find("methods:") else {
        return Vec::new();
    };
    let after = &attr_text[pos + 8..];
    let Some(open) = after.find('[') else {
        return Vec::new();
    };
    let Some(close) = after[open..].find(']') else {
        return Vec::new();
    };
    let inner = &after[open + 1..open + close];
    let mut out = Vec::new();
    let bytes = inner.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        let c = bytes[i];
        if c == b'\'' || c == b'"' {
            let delim = c;
            let start = i + 1;
            let mut j = start;
            while j < bytes.len() && bytes[j] != delim {
                j += 1;
            }
            if j < bytes.len() {
                let m = inner[start..j].to_ascii_uppercase();
                if !m.is_empty() {
                    out.push(m);
                }
                i = j + 1;
                continue;
            }
        }
        i += 1;
    }
    out
}

fn scan_laravel_routes(source: &str, module_id: NodeId, repo: RepoId, acc: &mut Acc) {
    let methods: &[(&str, &str)] = &[
        ("Route::get(", "GET"),
        ("Route::post(", "POST"),
        ("Route::put(", "PUT"),
        ("Route::patch(", "PATCH"),
        ("Route::delete(", "DELETE"),
        ("Route::options(", "OPTIONS"),
        ("Route::any(", "ANY"),
    ];
    for (needle, method) in methods {
        let mut search_from = 0;
        while let Some(rel) = source[search_from..].find(needle) {
            let start = search_from + rel + needle.len();
            if let Some((path, consumed)) = extract_first_string(&source[start..]) {
                emit_route_medium(method, &path, module_id, repo, acc);
                search_from = start + consumed.max(1);
            } else {
                search_from = start;
            }
        }
    }
    // Route::resource('/users', UserController::class) → REST 7
    let mut search_from = 0;
    while let Some(rel) = source[search_from..].find("Route::resource(") {
        let start = search_from + rel + "Route::resource(".len();
        if let Some((path, consumed)) = extract_first_string(&source[start..]) {
            for m in ["GET", "POST", "PUT", "PATCH", "DELETE"] {
                emit_route_medium(m, &path, module_id, repo, acc);
            }
            search_from = start + consumed.max(1);
        } else {
            search_from = start;
        }
    }
    // Route::apiResource → REST 5 (no create/edit)
    let mut search_from = 0;
    while let Some(rel) = source[search_from..].find("Route::apiResource(") {
        let start = search_from + rel + "Route::apiResource(".len();
        if let Some((path, consumed)) = extract_first_string(&source[start..]) {
            for m in ["GET", "POST", "PUT", "PATCH", "DELETE"] {
                emit_route_medium(m, &path, module_id, repo, acc);
            }
            search_from = start + consumed.max(1);
        } else {
            search_from = start;
        }
    }
}

fn emit_route_strong(method: &str, path: &str, handler_id: NodeId, repo: RepoId, acc: &mut Acc) {
    let route_name = format!("{method} {path}");
    let route_id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::ROUTE, &route_name);
    acc.nodes.push(Node {
        id: route_id,
        repo,
        confidence: Confidence::Strong,
        cells: vec![Cell {
            kind: cell_type::ROUTE_METHOD,
            payload: CellPayload::Text(method.to_string()),
        }],
    });
    acc.edges.push(Edge {
        from: route_id,
        to: handler_id,
        category: edge_category::HANDLED_BY,
        confidence: Confidence::Strong,
    });
    acc.nav
        .record(route_id, &route_name, &route_name, node_kind::ROUTE, None);
}

fn emit_route_medium(method: &str, path: &str, _module_id: NodeId, repo: RepoId, acc: &mut Acc) {
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

fn collect_use(node: TsNode, src: &[u8], from_module: &str, acc: &mut Acc) {
    let text = text_of(node, src).trim().to_string();
    let path = text
        .trim_start_matches("use ")
        .trim_end_matches(';')
        .trim();

    if let Some(last_bs) = path.rfind('\\') {
        let module_part = &path[..last_bs];
        let name = &path[last_bs + 1..];
        acc.imports.push(ImportStmt {
            from_module: from_module.to_string(),
            target: ImportTarget::Symbol {
                module: module_part.replace('\\', "::"),
                name: name.to_string(),
                alias: None,
                level: 0,
            },
        });
    } else {
        acc.imports.push(ImportStmt {
            from_module: from_module.to_string(),
            target: ImportTarget::Module {
                path: path.replace('\\', "::"),
                alias: None,
            },
        });
    }
}

fn collect_calls_in(node: TsNode, src: &[u8], from: NodeId, acc: &mut Acc) {
    let mut stack = vec![node];
    while let Some(n) = stack.pop() {
        match n.kind() {
            "function_call_expression" => {
                if let Some(func) = n.child_by_field_name("function") {
                    acc.calls.push(CallSite {
                        from,
                        qualifier: CallQualifier::Bare(text_of(func, src).to_string()),
                    });
                }
            }
            "member_call_expression" => {
                let obj = n
                    .child_by_field_name("object")
                    .map(|o| text_of(o, src))
                    .unwrap_or("");
                let name = n
                    .child_by_field_name("name")
                    .map(|o| text_of(o, src))
                    .unwrap_or("");
                if obj == "$this" {
                    acc.calls.push(CallSite {
                        from,
                        qualifier: CallQualifier::SelfMethod(name.to_string()),
                    });
                } else {
                    acc.calls.push(CallSite {
                        from,
                        qualifier: CallQualifier::Attribute {
                            base: obj.to_string(),
                            name: name.to_string(),
                        },
                    });
                }
            }
            "scoped_call_expression" => {
                let scope = n
                    .child_by_field_name("scope")
                    .map(|o| text_of(o, src))
                    .unwrap_or("");
                let name = n
                    .child_by_field_name("name")
                    .map(|o| text_of(o, src))
                    .unwrap_or("");
                acc.calls.push(CallSite {
                    from,
                    qualifier: CallQualifier::Attribute {
                        base: scope.to_string(),
                        name: name.to_string(),
                    },
                });
            }
            _ => {}
        }
        let mut cursor = n.walk();
        for child in n.named_children(&mut cursor) {
            if !matches!(
                child.kind(),
                "function_definition" | "class_declaration" | "anonymous_function_creation_expression"
            ) {
                stack.push(child);
            }
        }
    }
}

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
    fn classes_and_methods() {
        let source = r#"<?php
namespace App\Services;

class UserService {
    public function getUser(string $id): User {
        return $this->repo->find($id);
    }

    private function validate(User $u): void {}
}
"#;
        let fp = parse_file(source, "src/Services/UserService.php", "App::Services", repo()).unwrap();
        let names: Vec<&str> = fp.nav.name_by_id.values().map(|s| s.as_str()).collect();
        assert!(names.contains(&"UserService"));
        assert!(names.contains(&"getUser"));
        assert!(names.contains(&"validate"));
    }

    #[test]
    fn interfaces_and_enums() {
        let source = r#"<?php
namespace App;

interface Drawable {
    public function draw(): void;
}

enum Color {
    case Red;
    case Green;
}
"#;
        let fp = parse_file(source, "src/Types.php", "App", repo()).unwrap();
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::INTERFACE).count(), 1);
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::ENUM).count(), 1);
    }

    #[test]
    fn use_imports() {
        let source = r#"<?php
use App\Models\User;
use Illuminate\Http\Request;
"#;
        let fp = parse_file(source, "src/Controller.php", "App", repo()).unwrap();
        assert_eq!(fp.imports.len(), 2);
    }

    #[test]
    fn symfony_route_methods_list() {
        let source = r#"<?php
namespace App\Controller;

class UserController {
    #[Route('/users', methods: ['GET', 'POST'])]
    public function list() {}

    #[Route('/users/{id}', methods: ['PUT', 'DELETE'])]
    public function update() {}
}
"#;
        let fp = parse_file(source, "src/UserController.php", "App::Controller", repo()).unwrap();
        let route_names: Vec<&str> = fp
            .nav
            .name_by_id
            .iter()
            .filter(|(id, _)| fp.nav.kind_by_id.get(*id) == Some(&node_kind::ROUTE))
            .map(|(_, n)| n.as_str())
            .collect();
        assert!(route_names.contains(&"GET /users"));
        assert!(route_names.contains(&"POST /users"));
        assert!(route_names.contains(&"PUT /users/{id}"));
        assert!(route_names.contains(&"DELETE /users/{id}"));
    }

    #[test]
    fn symfony_route_no_methods_is_any() {
        let source = r#"<?php
class C {
    #[Route('/health')]
    public function health() {}
}
"#;
        let fp = parse_file(source, "src/C.php", "App", repo()).unwrap();
        let route_names: Vec<&str> = fp
            .nav
            .name_by_id
            .iter()
            .filter(|(id, _)| fp.nav.kind_by_id.get(*id) == Some(&node_kind::ROUTE))
            .map(|(_, n)| n.as_str())
            .collect();
        assert!(route_names.contains(&"ANY /health"));
    }

    #[test]
    fn laravel_route_facade() {
        let source = r#"<?php
Route::get('/users', [UserController::class, 'index']);
Route::post('/users', [UserController::class, 'store']);
Route::put('/users/{id}', [UserController::class, 'update']);
Route::delete('/users/{id}', [UserController::class, 'destroy']);
"#;
        let fp = parse_file(source, "routes/web.php", "routes::web", repo()).unwrap();
        let route_names: Vec<&str> = fp
            .nav
            .name_by_id
            .iter()
            .filter(|(id, _)| fp.nav.kind_by_id.get(*id) == Some(&node_kind::ROUTE))
            .map(|(_, n)| n.as_str())
            .collect();
        assert!(route_names.contains(&"GET /users"));
        assert!(route_names.contains(&"POST /users"));
        assert!(route_names.contains(&"PUT /users/{id}"));
        assert!(route_names.contains(&"DELETE /users/{id}"));
    }

    #[test]
    fn laravel_route_resource() {
        let source = r#"<?php
Route::resource('/photos', PhotoController::class);
"#;
        let fp = parse_file(source, "routes/web.php", "routes::web", repo()).unwrap();
        let route_names: Vec<&str> = fp
            .nav
            .name_by_id
            .iter()
            .filter(|(id, _)| fp.nav.kind_by_id.get(*id) == Some(&node_kind::ROUTE))
            .map(|(_, n)| n.as_str())
            .collect();
        assert!(route_names.iter().any(|n| n.starts_with("GET /photos")));
        assert!(route_names.iter().any(|n| n.starts_with("POST /photos")));
        assert!(route_names.iter().any(|n| n.starts_with("PUT /photos")));
        assert!(route_names.iter().any(|n| n.starts_with("DELETE /photos")));
    }

    #[test]
    fn this_calls() {
        let source = r#"<?php
class Service {
    public function handle(): void {
        $this->validate();
        $helper->process();
    }
    private function validate(): void {}
}
"#;
        let fp = parse_file(source, "src/Service.php", "App", repo()).unwrap();
        let self_calls: Vec<_> = fp
            .calls
            .iter()
            .filter(|c| matches!(&c.qualifier, CallQualifier::SelfMethod(_)))
            .collect();
        assert_eq!(self_calls.len(), 1);
    }
}
