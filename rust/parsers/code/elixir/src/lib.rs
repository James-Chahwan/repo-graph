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
    let lang: tree_sitter::Language = tree_sitter_elixir::LANGUAGE.into();
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
        visit_node(child, src, file_rel, parent_qname, parent_id, repo, acc);
    }
}

fn visit_node(
    node: TsNode,
    src: &[u8],
    file_rel: &str,
    parent_qname: &str,
    parent_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    if node.kind() != "call" {
        return;
    }
    let target = node.child_by_field_name("target").map(|n| text_of(n, src));
    let Some(target_name) = target else { return };

    match target_name {
        "defmodule" => visit_defmodule(node, src, file_rel, parent_qname, parent_id, repo, acc),
        "def" | "defp" => visit_def(node, src, file_rel, parent_qname, parent_id, repo, acc),
        "defprotocol" => visit_defprotocol(node, src, file_rel, parent_qname, parent_id, repo, acc),
        "defstruct" => visit_defstruct(node, src, file_rel, parent_qname, parent_id, repo, acc),
        "import" | "alias" | "use" => collect_import(node, src, parent_qname, acc),
        _ => {}
    }
}

fn find_args(node: TsNode) -> Option<TsNode> {
    let mut c = node.walk();
    node.named_children(&mut c).find(|ch| ch.kind() == "arguments")
}

fn visit_defmodule(
    node: TsNode,
    src: &[u8],
    file_rel: &str,
    parent_qname: &str,
    parent_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    let Some(args) = find_args(node) else {
        return;
    };
    let name = first_arg_text(args, src);
    if name.is_empty() {
        return;
    }
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
        .record(id, &name, &qname, node_kind::PACKAGE, Some(parent_id));

    let mut cursor = node.walk();
    for child in node.named_children(&mut cursor) {
        if child.kind() == "do_block" {
            let mut c2 = child.walk();
            for gc in child.named_children(&mut c2) {
                visit_node(gc, src, file_rel, &qname, id, repo, acc);
            }
        }
    }
}

fn visit_def(
    node: TsNode,
    src: &[u8],
    file_rel: &str,
    parent_qname: &str,
    parent_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    let Some(args) = find_args(node) else {
        return;
    };
    let name = extract_def_name(args, src);
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

    let mut cursor = node.walk();
    for child in node.named_children(&mut cursor) {
        if child.kind() == "do_block" {
            collect_calls_in(child, src, id, acc);
        }
    }
}

fn visit_defprotocol(
    node: TsNode,
    src: &[u8],
    file_rel: &str,
    parent_qname: &str,
    parent_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    let Some(args) = find_args(node) else {
        return;
    };
    let name = first_arg_text(args, src);
    if name.is_empty() {
        return;
    }
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
        .record(id, &name, &qname, node_kind::INTERFACE, Some(parent_id));
}

fn visit_defstruct(
    node: TsNode,
    src: &[u8],
    file_rel: &str,
    parent_qname: &str,
    parent_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    let qname = format!("{parent_qname}::__struct__");
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
        .record(id, "__struct__", &qname, node_kind::STRUCT, Some(parent_id));
}

fn collect_import(node: TsNode, src: &[u8], from_module: &str, acc: &mut Acc) {
    let Some(args) = find_args(node) else {
        return;
    };
    let path = first_arg_text(args, src);
    if !path.is_empty() {
        acc.imports.push(ImportStmt {
            from_module: from_module.to_string(),
            target: ImportTarget::Module {
                path,
                alias: None,
            },
        });
    }
}

fn first_arg_text(args: TsNode, src: &[u8]) -> String {
    let mut cursor = args.walk();
    for child in args.named_children(&mut cursor) {
        match child.kind() {
            "alias" | "identifier" | "atom" => {
                return text_of(child, src).trim().to_string();
            }
            _ => {
                let text = text_of(child, src).trim().to_string();
                if !text.is_empty() {
                    return text;
                }
            }
        }
    }
    String::new()
}

fn extract_def_name(args: TsNode, src: &[u8]) -> String {
    let mut cursor = args.walk();
    for child in args.named_children(&mut cursor) {
        match child.kind() {
            "identifier" => return text_of(child, src).to_string(),
            "call" => {
                if let Some(target) = child.child_by_field_name("target") {
                    return text_of(target, src).to_string();
                }
            }
            _ => {}
        }
    }
    String::new()
}

fn collect_calls_in(node: TsNode, src: &[u8], from: NodeId, acc: &mut Acc) {
    let mut stack = vec![node];
    while let Some(n) = stack.pop() {
        if n.kind() == "call"
            && let Some(target) = n.child_by_field_name("target")
        {
            match target.kind() {
                "identifier" => {
                    let name = text_of(target, src);
                    if !matches!(name, "def" | "defp" | "defmodule" | "defprotocol" | "defstruct" | "import" | "alias" | "use" | "if" | "case" | "cond" | "do" | "end") {
                        acc.calls.push(CallSite {
                            from,
                            qualifier: CallQualifier::Bare(name.to_string()),
                        });
                    }
                }
                "dot" => {
                    let text = text_of(target, src);
                    if let Some(pos) = text.rfind('.') {
                        acc.calls.push(CallSite {
                            from,
                            qualifier: CallQualifier::Attribute {
                                base: text[..pos].to_string(),
                                name: text[pos + 1..].to_string(),
                            },
                        });
                    }
                }
                _ => {}
            }
        }
        let mut cursor = n.walk();
        for child in n.named_children(&mut cursor) {
            if !matches!(child.kind(), "anonymous_function") {
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
    fn module_and_functions() {
        let source = r#"
defmodule MyApp.Users do
  def get_user(id) do
    Repo.get(User, id)
  end

  defp validate(user) do
    :ok
  end
end
"#;
        let fp = parse_file(source, "lib/users.ex", "lib::users", repo()).unwrap();
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::PACKAGE).count(), 1);
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::FUNCTION).count(), 2);
    }

    #[test]
    fn imports() {
        let source = r#"
defmodule MyApp.Web do
  import Plug.Conn
  alias MyApp.Repo
  use Phoenix.Controller
end
"#;
        let fp = parse_file(source, "lib/web.ex", "lib::web", repo()).unwrap();
        assert_eq!(fp.imports.len(), 3);
    }

    #[test]
    fn calls_detected() {
        let source = r#"
defmodule MyApp.Service do
  def run(data) do
    validate(data)
    Repo.insert(data)
  end
end
"#;
        let fp = parse_file(source, "lib/service.ex", "lib::service", repo()).unwrap();
        assert!(fp.calls.iter().any(|c| matches!(&c.qualifier, CallQualifier::Bare(n) if n == "validate")));
        assert!(fp.calls.iter().any(|c| matches!(&c.qualifier, CallQualifier::Attribute { base, name } if base == "Repo" && name == "insert")));
    }
}
