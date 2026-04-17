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
    let lang: tree_sitter::Language = tree_sitter_solidity::LANGUAGE.into();
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
            "import_directive" => collect_import(child, src, parent_qname, acc),
            "contract_declaration" => {
                visit_contract(child, src, file_rel, parent_qname, parent_id, repo, node_kind::CLASS, acc);
            }
            "interface_declaration" => {
                visit_contract(child, src, file_rel, parent_qname, parent_id, repo, node_kind::INTERFACE, acc);
            }
            "library_declaration" => {
                visit_contract(child, src, file_rel, parent_qname, parent_id, repo, node_kind::PACKAGE, acc);
            }
            "enum_declaration" => {
                visit_enum(child, src, file_rel, parent_qname, parent_id, repo, acc);
            }
            "struct_declaration" => {
                visit_struct_decl(child, src, file_rel, parent_qname, parent_id, repo, acc);
            }
            _ => {}
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn visit_contract(
    node: TsNode,
    src: &[u8],
    file_rel: &str,
    parent_qname: &str,
    parent_id: NodeId,
    repo: RepoId,
    kind: repo_graph_core::NodeKindId,
    acc: &mut Acc,
) {
    let Some(name_node) = node.child_by_field_name("name") else {
        return;
    };
    let name = text_of(name_node, src);
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
        let mut c = body.walk();
        for child in body.named_children(&mut c) {
            match child.kind() {
                "function_definition" => {
                    visit_function(child, src, file_rel, &qname, id, repo, acc);
                }
                "event_definition" => {
                    visit_event(child, src, file_rel, &qname, id, repo, acc);
                }
                "enum_declaration" => {
                    visit_enum(child, src, file_rel, &qname, id, repo, acc);
                }
                "struct_declaration" => {
                    visit_struct_decl(child, src, file_rel, &qname, id, repo, acc);
                }
                _ => {}
            }
        }
    }
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
}

fn visit_event(
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

fn visit_struct_decl(
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
    let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::STRUCT, &qname);

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
        .record(id, name, &qname, node_kind::STRUCT, Some(parent_id));
}

fn collect_import(node: TsNode, src: &[u8], from_module: &str, acc: &mut Acc) {
    let text = text_of(node, src).trim().to_string();
    let path = text
        .trim_start_matches("import ")
        .trim_end_matches(';')
        .trim()
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
        if n.kind() == "call_expression"
            && let Some(func) = n.child_by_field_name("function")
        {
            let qualifier = classify_call(func, src);
            acc.calls.push(CallSite { from, qualifier });
        }
        let mut cursor = n.walk();
        for child in n.named_children(&mut cursor) {
            if !matches!(child.kind(), "function_definition") {
                stack.push(child);
            }
        }
    }
}

fn classify_call(func_node: TsNode, src: &[u8]) -> CallQualifier {
    match func_node.kind() {
        "identifier" => CallQualifier::Bare(text_of(func_node, src).to_string()),
        "member_expression" => {
            let obj = func_node
                .child_by_field_name("object")
                .map(|n| text_of(n, src))
                .unwrap_or("");
            let prop = func_node
                .child_by_field_name("property")
                .map(|n| text_of(n, src))
                .unwrap_or("");
            CallQualifier::Attribute {
                base: obj.to_string(),
                name: prop.to_string(),
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
    fn contract_and_functions() {
        let source = r#"
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract Token {
    function transfer(address to, uint256 amount) public returns (bool) {
        return true;
    }

    event Transfer(address indexed from, address indexed to, uint256 value);
}
"#;
        let fp = parse_file(source, "contracts/Token.sol", "contracts::Token", repo()).unwrap();
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::CLASS).count(), 1);
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::METHOD).count(), 1);
    }

    #[test]
    fn interface_and_library() {
        let source = r#"
interface IERC20 {
    function totalSupply() external view returns (uint256);
}

library SafeMath {
    function add(uint256 a, uint256 b) internal pure returns (uint256) {
        return a + b;
    }
}
"#;
        let fp = parse_file(source, "contracts/Lib.sol", "contracts::Lib", repo()).unwrap();
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::INTERFACE).count(), 1);
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::PACKAGE).count(), 1);
    }

    #[test]
    fn imports() {
        let source = r#"
import "./IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
"#;
        let fp = parse_file(source, "contracts/Token.sol", "contracts::Token", repo()).unwrap();
        assert_eq!(fp.imports.len(), 2);
    }
}
