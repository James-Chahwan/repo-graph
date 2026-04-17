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
    let lang: tree_sitter::Language = tree_sitter_dart::LANGUAGE.into();
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

    visit_top(root, src, file_rel_path, module_qname, module_id, repo, &mut acc);
    scan_dart_routes(source, repo, &mut acc);

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

fn visit_top(
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
            "import_or_export" => collect_import(child, src, parent_qname, acc),
            "class_declaration" => {
                visit_class(child, src, file_rel, parent_qname, parent_id, repo, acc);
            }
            "enum_declaration" => {
                visit_enum(child, src, file_rel, parent_qname, parent_id, repo, acc);
            }
            "function_signature" | "function_definition" | "top_level_definition" => {
                visit_function(child, src, file_rel, parent_qname, parent_id, repo, acc);
            }
            _ => {}
        }
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
    let Some(name) = find_identifier(node, src) else {
        return;
    };
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
    acc.nav.record(id, &name, &qname, node_kind::CLASS, Some(parent_id));

    let mut c = node.walk();
    for child in node.named_children(&mut c) {
        if child.kind() == "class_body" {
            let mut c2 = child.walk();
            for member in child.named_children(&mut c2) {
                if member.kind() == "class_member" {
                    visit_class_member(member, src, file_rel, &qname, id, repo, acc);
                }
            }
        }
    }
}

fn visit_class_member(
    node: TsNode,
    src: &[u8],
    file_rel: &str,
    parent_qname: &str,
    parent_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    let mut c = node.walk();
    for child in node.named_children(&mut c) {
        if child.kind() == "method_signature"
            && let Some(name) = find_method_name(child, src)
        {
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
                .record(id, &name, &qname, node_kind::METHOD, Some(parent_id));
        }
        if child.kind() == "function_body"
            && let Some(method_id) = acc.nodes.last().map(|n| n.id)
        {
            collect_calls_in(child, src, method_id, acc);
        }
    }
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
    let Some(name_node) = node.child_by_field_name("name").or_else(|| {
        let mut c = node.walk();
        node.named_children(&mut c).find(|ch| ch.kind() == "identifier")
    }) else {
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
    let Some(name) = find_method_name(node, src) else {
        return;
    };
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
        .record(id, &name, &qname, node_kind::FUNCTION, Some(parent_id));
}

fn find_identifier<'a>(node: TsNode<'a>, src: &'a [u8]) -> Option<String> {
    let mut c = node.walk();
    for child in node.named_children(&mut c) {
        if child.kind() == "identifier" {
            return Some(text_of(child, src).to_string());
        }
    }
    None
}

fn find_method_name<'a>(node: TsNode<'a>, src: &'a [u8]) -> Option<String> {
    if let Some(name) = find_identifier(node, src) {
        return Some(name);
    }
    let mut c = node.walk();
    for child in node.named_children(&mut c) {
        if child.kind() == "function_signature" {
            return find_identifier(child, src);
        }
    }
    None
}

fn collect_import(node: TsNode, src: &[u8], from_module: &str, acc: &mut Acc) {
    let text = text_of(node, src).trim().to_string();
    if !text.starts_with("import") {
        return;
    }
    let path = text
        .trim_start_matches("import ")
        .trim_end_matches(';')
        .trim()
        .trim_matches('\'')
        .trim_matches('"');
    acc.imports.push(ImportStmt {
        from_module: from_module.to_string(),
        target: ImportTarget::Module {
            path: path.to_string(),
            alias: None,
        },
    });
}

fn collect_calls_in(node: TsNode, src: &[u8], from: NodeId, acc: &mut Acc) {
    let mut stack = vec![node];
    while let Some(n) = stack.pop() {
        match n.kind() {
            "selector_expression" => {
                if let Some(field) = n.child_by_field_name("field") {
                    let target = n.named_child(0).map(|c| text_of(c, src)).unwrap_or("");
                    let method = text_of(field, src);
                    if target == "this" {
                        acc.calls.push(CallSite {
                            from,
                            qualifier: CallQualifier::SelfMethod(method.to_string()),
                        });
                    } else if n.named_child(0).is_some_and(|c| c.kind() == "identifier") {
                        acc.calls.push(CallSite {
                            from,
                            qualifier: CallQualifier::Attribute {
                                base: target.to_string(),
                                name: method.to_string(),
                            },
                        });
                    }
                }
            }
            "identifier" => {
                if n.parent().is_some_and(|p| {
                    p.kind() == "arguments" || p.kind() == "argument_part"
                }) {
                    // skip — arguments, not calls
                } else if n.parent().is_some_and(|p| {
                    p.kind() == "selector_expression"
                }) {
                    // handled above
                }
            }
            _ => {}
        }
        let mut cursor = n.walk();
        for child in n.named_children(&mut cursor) {
            if !matches!(
                child.kind(),
                "function_expression" | "class_definition" | "function_definition"
            ) {
                stack.push(child);
            }
        }
    }
}

fn text_of<'a>(node: TsNode<'a>, src: &'a [u8]) -> &'a str {
    node.utf8_text(src).unwrap_or("")
}

// ============================================================================
// Dart route extraction (v0.4.11a R-dart)
// ============================================================================
//
// Two framework surfaces covered via text scan (robust to tree-sitter-dart's
// no-field-name quirk):
//
//   go_router navigation:  GoRoute(path: '/users', ...)  → ANY /users
//   shelf / shelf_router:  router.get('/users', handler) → GET /users
//                          ..post('/x', h)  (cascade)    → POST /x
//
// Shape B ROUTE nodes (METHOD <path> qname + Text ROUTE_METHOD cell).

fn scan_dart_routes(source: &str, repo: RepoId, acc: &mut Acc) {
    // Track emitted routes to dedup — a file may hit the same path twice
    // between the tree walk and the text scan.
    let mut seen = std::collections::HashSet::new();

    // go_router — look for `GoRoute(path:` token.
    let needle = "GoRoute(";
    let mut idx = 0;
    while let Some(pos) = source[idx..].find(needle) {
        let start = idx + pos + needle.len();
        if let Some(path) = extract_kwarg_string(&source[start..], "path") {
            emit_dart_route("ANY", &path, repo, acc, &mut seen);
        }
        idx = start;
    }

    // shelf-style `.get('/...' / .post('/...' / etc.
    for method in ["get", "post", "put", "patch", "delete", "head", "options"] {
        let needle = format!(".{method}(");
        let mut idx = 0;
        while let Some(pos) = source[idx..].find(&needle) {
            let after = &source[idx + pos + needle.len()..];
            if let Some(path) = first_string_literal_dart(after)
                && path.starts_with('/')
            {
                let verb = method.to_ascii_uppercase();
                emit_dart_route(&verb, &path, repo, acc, &mut seen);
            }
            idx += pos + needle.len();
        }
    }
}

fn extract_kwarg_string(s: &str, key: &str) -> Option<String> {
    // Looks for `path: '/x'` or `path: "/x"` allowing whitespace.
    let mut i = 0;
    while let Some(pos) = s[i..].find(key) {
        let start = i + pos + key.len();
        let rest = s[start..].trim_start();
        if let Some(after_colon) = rest.strip_prefix(':')
            && let Some(lit) = first_string_literal_dart(after_colon)
        {
            return Some(lit);
        }
        i = start;
    }
    None
}

fn first_string_literal_dart(s: &str) -> Option<String> {
    let trimmed = s.trim_start();
    let bytes = trimmed.as_bytes();
    if bytes.is_empty() {
        return None;
    }
    let quote = match bytes[0] {
        b'\'' | b'"' => bytes[0],
        _ => return None,
    };
    let rest = &trimmed[1..];
    let end = rest.find(quote as char)?;
    let lit = &rest[..end];
    if lit.is_empty() || lit.len() > 256 {
        return None;
    }
    Some(lit.to_string())
}

fn emit_dart_route(
    method: &str,
    path: &str,
    repo: RepoId,
    acc: &mut Acc,
    seen: &mut std::collections::HashSet<(String, String)>,
) {
    let key = (method.to_string(), path.to_string());
    if !seen.insert(key) {
        return;
    }
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
    fn class_and_enum() {
        let source = r#"
class User {
  String name;
  void greet() {
    print('Hello $name');
  }
}

enum Status { active, inactive }
"#;
        let fp = parse_file(source, "lib/user.dart", "lib::user", repo()).unwrap();
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::CLASS).count(), 1);
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::ENUM).count(), 1);
    }

    #[test]
    fn imports() {
        let source = r#"
import 'package:flutter/material.dart';
import 'dart:async';
"#;
        let fp = parse_file(source, "lib/main.dart", "lib::main", repo()).unwrap();
        assert_eq!(fp.imports.len(), 2);
    }

    #[test]
    fn top_level_function() {
        let source = r#"
void main() {
  runApp(MyApp());
}
"#;
        let fp = parse_file(source, "lib/main.dart", "lib::main", repo()).unwrap();
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::FUNCTION).count(), 1);
    }

    fn route_id(method: &str, path: &str) -> NodeId {
        NodeId::from_parts(
            GRAPH_TYPE,
            repo(),
            node_kind::ROUTE,
            &format!("{method} {path}"),
        )
    }

    #[test]
    fn go_router_routes_emit() {
        let source = r#"
final router = GoRouter(routes: [
  GoRoute(path: '/users', builder: (c, s) => UsersScreen()),
  GoRoute(path: '/users/:id', builder: (c, s) => UserDetail()),
]);
"#;
        let fp = parse_file(source, "lib/router.dart", "lib::router", repo()).unwrap();
        assert!(fp.nodes.iter().any(|n| n.id == route_id("ANY", "/users")));
        assert!(fp.nodes.iter().any(|n| n.id == route_id("ANY", "/users/:id")));
    }

    #[test]
    fn shelf_routes_emit() {
        let source = r#"
import 'package:shelf_router/shelf_router.dart';

final app = Router()
  ..get('/users', handleList)
  ..post('/users', handleCreate);
"#;
        let fp = parse_file(source, "bin/server.dart", "bin::server", repo()).unwrap();
        assert!(fp.nodes.iter().any(|n| n.id == route_id("GET", "/users")));
        assert!(fp.nodes.iter().any(|n| n.id == route_id("POST", "/users")));
    }
}
