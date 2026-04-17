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
    let lang: tree_sitter::Language = tree_sitter_hcl::LANGUAGE.into();
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
            "block" => visit_block(child, src, file_rel, parent_qname, parent_id, repo, acc),
            "body" => {
                let mut c2 = child.walk();
                for gc in child.named_children(&mut c2) {
                    if gc.kind() == "block" {
                        visit_block(gc, src, file_rel, parent_qname, parent_id, repo, acc);
                    }
                }
            }
            _ => {}
        }
    }
}

fn visit_block(
    node: TsNode,
    src: &[u8],
    file_rel: &str,
    parent_qname: &str,
    parent_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    let labels = collect_labels(node, src);
    if labels.is_empty() {
        return;
    }

    let block_type = labels[0].as_str();
    match block_type {
        "resource" if labels.len() >= 3 => {
            let name = format!("{}.{}", labels[1], labels[2]);
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
                .record(id, &name, &qname, node_kind::STRUCT, Some(parent_id));
        }
        "module" if labels.len() >= 2 => {
            let name = &labels[1];
            let qname = format!("{parent_qname}::{name}");
            let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::PACKAGE, &qname);
            acc.nodes.push(Node {
                id,
                repo,
                confidence: Confidence::Strong,
                cells: entity_cells(&node, src, file_rel),
            });
            acc.edges.push(Edge {
                from: parent_id,
                to: id,
                category: edge_category::CONTAINS,
                confidence: Confidence::Strong,
            });
            acc.nav
                .record(id, name, &qname, node_kind::PACKAGE, Some(parent_id));

            if let Some(source_attr) = find_attribute(node, src, "source") {
                acc.imports.push(ImportStmt {
                    from_module: parent_qname.to_string(),
                    target: ImportTarget::Module {
                        path: source_attr,
                        alias: None,
                    },
                });
            }
        }
        "variable" if labels.len() >= 2 => {
            let name = format!("var.{}", labels[1]);
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
        "output" if labels.len() >= 2 => {
            let name = format!("output.{}", labels[1]);
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
        "data" if labels.len() >= 3 => {
            let name = format!("data.{}.{}", labels[1], labels[2]);
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
                .record(id, &name, &qname, node_kind::STRUCT, Some(parent_id));
        }
        _ => {}
    }
}

fn collect_labels(node: TsNode, src: &[u8]) -> Vec<String> {
    let mut labels = Vec::new();
    let mut cursor = node.walk();
    for child in node.named_children(&mut cursor) {
        match child.kind() {
            "identifier" => labels.push(text_of(child, src).to_string()),
            "string_lit" => {
                let mut c = child.walk();
                for gc in child.named_children(&mut c) {
                    if gc.kind() == "template_literal" {
                        labels.push(text_of(gc, src).to_string());
                        break;
                    }
                }
            }
            _ => {}
        }
    }
    labels
}

fn find_attribute(node: TsNode, src: &[u8], attr_name: &str) -> Option<String> {
    let mut cursor = node.walk();
    for child in node.named_children(&mut cursor) {
        if child.kind() == "body" {
            let mut c2 = child.walk();
            for gc in child.named_children(&mut c2) {
                if gc.kind() == "attribute" {
                    let key = gc.named_child(0).map(|n| text_of(n, src)).unwrap_or("");
                    if key == attr_name {
                        let val_text = gc.named_child(1).map(|n| text_of(n, src)).unwrap_or("");
                        return Some(val_text.trim_matches('"').to_string());
                    }
                }
            }
        }
    }
    None
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
    fn resources_and_variables() {
        let source = r#"
resource "aws_instance" "web" {
  ami           = "ami-12345"
  instance_type = "t2.micro"
}

variable "region" {
  default = "us-east-1"
}

output "instance_id" {
  value = aws_instance.web.id
}
"#;
        let fp = parse_file(source, "main.tf", "main", repo()).unwrap();
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::STRUCT).count(), 1);
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::FUNCTION).count(), 2);
    }

    #[test]
    fn modules_with_source() {
        let source = r#"
module "vpc" {
  source = "./modules/vpc"
}
"#;
        let fp = parse_file(source, "main.tf", "main", repo()).unwrap();
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::PACKAGE).count(), 1);
        assert_eq!(fp.imports.len(), 1);
    }

    #[test]
    fn data_source() {
        let source = r#"
data "aws_ami" "ubuntu" {
  most_recent = true
}
"#;
        let fp = parse_file(source, "data.tf", "data", repo()).unwrap();
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::STRUCT).count(), 1);
    }
}
