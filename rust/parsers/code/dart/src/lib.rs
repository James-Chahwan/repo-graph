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
}
