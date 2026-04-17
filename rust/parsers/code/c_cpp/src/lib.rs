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
    is_cpp: bool,
    repo: RepoId,
) -> Result<FileParse, ParseError> {
    let mut parser = Parser::new();
    let lang: tree_sitter::Language = if is_cpp {
        tree_sitter_cpp::LANGUAGE.into()
    } else {
        tree_sitter_c::LANGUAGE.into()
    };
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
            "preproc_include" => collect_include(child, src, parent_qname, acc),
            "function_definition" => {
                visit_function(child, src, file_rel, parent_qname, parent_id, repo, acc);
            }
            "struct_specifier" | "class_specifier" => {
                visit_type(child, src, file_rel, parent_qname, parent_id, repo, acc);
            }
            "enum_specifier" => {
                visit_enum(child, src, file_rel, parent_qname, parent_id, repo, acc);
            }
            "namespace_definition" => {
                visit_namespace(child, src, file_rel, parent_qname, parent_id, repo, acc);
            }
            "declaration" => {
                // C++ forward declarations with inline class bodies
                let mut c2 = child.walk();
                for gc in child.named_children(&mut c2) {
                    if gc.kind() == "struct_specifier" || gc.kind() == "class_specifier" {
                        visit_type(gc, src, file_rel, parent_qname, parent_id, repo, acc);
                    }
                }
            }
            _ => {}
        }
    }
}

fn visit_namespace(
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
    let ns_id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::PACKAGE, &qname);

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
        .record(ns_id, name, &qname, node_kind::PACKAGE, Some(parent_id));

    if let Some(body) = node.child_by_field_name("body") {
        visit_children(body, src, file_rel, &qname, ns_id, repo, acc);
    }
}

fn visit_type(
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
    let kind = if node.kind() == "class_specifier" {
        node_kind::CLASS
    } else {
        node_kind::STRUCT
    };
    let qname = format!("{parent_qname}::{name}");
    let id = NodeId::from_parts(GRAPH_TYPE, repo, kind, &qname);

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
    acc.nav.record(id, name, &qname, kind, Some(parent_id));

    if let Some(body) = node.child_by_field_name("body") {
        let mut cursor = body.walk();
        for child in body.named_children(&mut cursor) {
            if child.kind() == "function_definition" {
                visit_method(child, src, file_rel, &qname, id, repo, acc);
            }
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
    let Some(declarator) = node.child_by_field_name("declarator") else {
        return;
    };
    let name = extract_func_name(declarator, src);
    if name.is_empty() {
        return;
    }
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
    let Some(declarator) = node.child_by_field_name("declarator") else {
        return;
    };
    let name = extract_func_name(declarator, src);
    if name.is_empty() {
        return;
    }
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

    if let Some(body) = node.child_by_field_name("body") {
        collect_calls_in(body, src, id, acc);
    }
}

fn extract_func_name(declarator: TsNode, src: &[u8]) -> String {
    // Walk down through function_declarator → pointer_declarator → etc. to find identifier
    let mut node = declarator;
    loop {
        if let Some(decl) = node.child_by_field_name("declarator") {
            node = decl;
        } else if matches!(
            node.kind(),
            "identifier" | "field_identifier" | "qualified_identifier" | "destructor_name"
        ) {
            return text_of(node, src).to_string();
        } else {
            return text_of(node, src).split('(').next().unwrap_or("").trim().to_string();
        }
    }
}

fn collect_include(node: TsNode, src: &[u8], from_module: &str, acc: &mut Acc) {
    // #include "local.h" — local includes only
    let Some(path_node) = node.child_by_field_name("path") else {
        return;
    };
    let path = text_of(path_node, src);
    if path.starts_with('"') {
        let cleaned = path.trim_matches('"');
        acc.imports.push(ImportStmt {
            from_module: from_module.to_string(),
            target: ImportTarget::Module {
                path: cleaned.to_string(),
                alias: None,
            },
        });
    }
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
        let mut cursor = n.walk();
        for child in n.named_children(&mut cursor) {
            if !matches!(child.kind(), "function_definition" | "lambda_expression") {
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
                .child_by_field_name("argument")
                .map(|n| text_of(n, src))
                .unwrap_or("");
            let field = func_node
                .child_by_field_name("field")
                .map(|n| text_of(n, src))
                .unwrap_or("");
            if obj == "this" {
                CallQualifier::SelfMethod(field.to_string())
            } else {
                CallQualifier::Attribute {
                    base: obj.to_string(),
                    name: field.to_string(),
                }
            }
        }
        "qualified_identifier" => {
            let text = text_of(func_node, src);
            if let Some(pos) = text.rfind("::") {
                CallQualifier::Attribute {
                    base: text[..pos].to_string(),
                    name: text[pos + 2..].to_string(),
                }
            } else {
                CallQualifier::Bare(text.to_string())
            }
        }
        _ => CallQualifier::ComplexReceiver {
            receiver: text_of(func_node, src).to_string(),
            name: String::new(),
        },
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
    fn structs_and_functions_c() {
        let source = r#"
#include "header.h"

struct Point {
    int x;
    int y;
};

int add(int a, int b) {
    return a + b;
}
"#;
        let fp = parse_file(source, "src/math.c", "src::math", false, repo()).unwrap();
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::STRUCT).count(), 1);
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::FUNCTION).count(), 1);
        assert_eq!(fp.imports.len(), 1);
    }

    #[test]
    fn classes_and_methods_cpp() {
        let source = r#"
class UserService {
public:
    void getUser(int id) {
        this->validate(id);
    }
    void validate(int id) {}
};
"#;
        let fp = parse_file(source, "src/service.cpp", "src::service", true, repo()).unwrap();
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::CLASS).count(), 1);
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::METHOD).count(), 2);
    }

    #[test]
    fn namespaces() {
        let source = r#"
namespace app {
    struct Config {};
    void init() {}
}
"#;
        let fp = parse_file(source, "src/app.cpp", "src::app", true, repo()).unwrap();
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::PACKAGE).count(), 1);
    }
}
