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
    let lang: tree_sitter::Language = tree_sitter_clojure_orchard::LANGUAGE.into();
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
        visit_form(child, src, file_rel, parent_qname, parent_id, repo, acc);
    }
}

fn visit_form(
    node: TsNode,
    src: &[u8],
    file_rel: &str,
    parent_qname: &str,
    parent_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    if node.kind() != "list_lit" {
        return;
    }
    let Some(head) = first_symbol(node, src) else {
        return;
    };

    match head {
        "ns" => collect_ns(node, src, parent_qname, acc),
        "def" | "defn" | "defn-" | "defmacro" => {
            visit_defn(node, src, file_rel, parent_qname, parent_id, repo, acc);
        }
        "defprotocol" => {
            visit_defprotocol(node, src, file_rel, parent_qname, parent_id, repo, acc);
        }
        "defrecord" | "deftype" => {
            visit_defrecord(node, src, file_rel, parent_qname, parent_id, repo, acc);
        }
        "require" => collect_require(node, src, parent_qname, acc),
        _ => {}
    }
}

fn first_symbol<'a>(list: TsNode<'a>, src: &'a [u8]) -> Option<&'a str> {
    let mut cursor = list.walk();
    for child in list.named_children(&mut cursor) {
        if child.kind() == "sym_lit" {
            return Some(text_of(child, src));
        }
    }
    None
}

fn second_symbol<'a>(list: TsNode<'a>, src: &'a [u8]) -> Option<&'a str> {
    let mut cursor = list.walk();
    let mut seen_first = false;
    for child in list.named_children(&mut cursor) {
        if child.kind() == "sym_lit" {
            if seen_first {
                return Some(text_of(child, src));
            }
            seen_first = true;
        }
    }
    None
}

fn visit_defn(
    node: TsNode,
    src: &[u8],
    file_rel: &str,
    parent_qname: &str,
    parent_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    let Some(name) = second_symbol(node, src) else {
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
        .record(id, name, &qname, node_kind::FUNCTION, Some(parent_id));

    collect_calls_in(node, src, id, acc);
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
    let Some(name) = second_symbol(node, src) else {
        return;
    };
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

    let mut cursor = node.walk();
    for child in node.named_children(&mut cursor) {
        if child.kind() == "list_lit"
            && let Some(method_name) = first_symbol(child, src)
        {
            let mq = format!("{qname}::{method_name}");
            let mid = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::METHOD, &mq);
            acc.nodes.push(Node {
                id: mid,
                repo,
                confidence: Confidence::Strong,
                cells: entity_cells(&child, src, file_rel),
            });
            acc.edges.push(Edge {
                from: id,
                to: mid,
                category: edge_category::DEFINES,
                confidence: Confidence::Strong,
            });
            acc.nav
                .record(mid, method_name, &mq, node_kind::METHOD, Some(id));
        }
    }
}

fn visit_defrecord(
    node: TsNode,
    src: &[u8],
    file_rel: &str,
    parent_qname: &str,
    parent_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    let Some(name) = second_symbol(node, src) else {
        return;
    };
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

fn collect_ns(node: TsNode, src: &[u8], from_module: &str, acc: &mut Acc) {
    let mut cursor = node.walk();
    for child in node.named_children(&mut cursor) {
        if child.kind() == "list_lit"
            && first_symbol(child, src) == Some(":require")
        {
            collect_require(child, src, from_module, acc);
        }
        if child.kind() == "kwd_lit" && text_of(child, src) == ":require" {
            let mut c2 = node.walk();
            let children: Vec<_> = node.named_children(&mut c2).collect();
            for ch in &children {
                if ch.kind() == "vec_lit" {
                    let req_text = extract_require_from_vec(*ch, src);
                    if !req_text.is_empty() {
                        acc.imports.push(ImportStmt {
                            from_module: from_module.to_string(),
                            target: ImportTarget::Module {
                                path: req_text,
                                alias: None,
                            },
                        });
                    }
                }
            }
        }
    }
}

fn extract_require_from_vec<'a>(vec_node: TsNode<'a>, src: &'a [u8]) -> String {
    let mut cursor = vec_node.walk();
    for child in vec_node.named_children(&mut cursor) {
        if child.kind() == "sym_lit" {
            return text_of(child, src).to_string();
        }
    }
    String::new()
}

fn collect_require(node: TsNode, src: &[u8], from_module: &str, acc: &mut Acc) {
    let mut cursor = node.walk();
    for child in node.named_children(&mut cursor) {
        if child.kind() == "vec_lit" {
            let req = extract_require_from_vec(child, src);
            if !req.is_empty() {
                acc.imports.push(ImportStmt {
                    from_module: from_module.to_string(),
                    target: ImportTarget::Module {
                        path: req,
                        alias: None,
                    },
                });
            }
        }
        if child.kind() == "sym_lit" && text_of(child, src) != "require" {
            let sym = text_of(child, src);
            acc.imports.push(ImportStmt {
                from_module: from_module.to_string(),
                target: ImportTarget::Module {
                    path: sym.to_string(),
                    alias: None,
                },
            });
        }
    }
}

fn collect_calls_in(node: TsNode, src: &[u8], from: NodeId, acc: &mut Acc) {
    let mut stack = vec![node];
    while let Some(n) = stack.pop() {
        if n.kind() == "list_lit"
            && let Some(head) = first_symbol(n, src)
            && !matches!(head, "def" | "defn" | "defn-" | "defmacro" | "let" | "if" | "when" | "do" | "fn" | "loop" | "cond" | "case" | "ns" | "require" | "defprotocol" | "defrecord" | "deftype")
        {
            if head.contains('/') {
                let parts: Vec<&str> = head.splitn(2, '/').collect();
                acc.calls.push(CallSite {
                    from,
                    qualifier: CallQualifier::Attribute {
                        base: parts[0].to_string(),
                        name: parts[1].to_string(),
                    },
                });
            } else if let Some(stripped) = head.strip_prefix('.') {
                acc.calls.push(CallSite {
                    from,
                    qualifier: CallQualifier::SelfMethod(stripped.to_string()),
                });
            } else {
                acc.calls.push(CallSite {
                    from,
                    qualifier: CallQualifier::Bare(head.to_string()),
                });
            }
        }
        let mut cursor = n.walk();
        for child in n.named_children(&mut cursor) {
            if child.kind() != "list_lit" || first_symbol(child, src).is_none_or(|s| !matches!(s, "defn" | "defn-" | "fn" | "defmacro")) {
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
    fn defns_and_protocol() {
        let source = r#"
(defprotocol Greeter
  (greet [this name]))

(defn hello [name]
  (str "Hello " name))

(defn- internal-fn []
  (println "private"))
"#;
        let fp = parse_file(source, "src/greeter.clj", "src::greeter", repo()).unwrap();
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::INTERFACE).count(), 1);
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::FUNCTION).count(), 2);
    }

    #[test]
    fn defrecord() {
        let source = r#"
(defrecord User [name email])
"#;
        let fp = parse_file(source, "src/user.clj", "src::user", repo()).unwrap();
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::STRUCT).count(), 1);
    }

    #[test]
    fn calls_detected() {
        let source = r#"
(defn process [x]
  (validate x)
  (db/save x))
"#;
        let fp = parse_file(source, "src/proc.clj", "src::proc", repo()).unwrap();
        assert!(fp.calls.iter().any(|c| matches!(&c.qualifier, CallQualifier::Bare(n) if n == "validate")));
        assert!(fp.calls.iter().any(|c| matches!(&c.qualifier, CallQualifier::Attribute { base, name } if base == "db" && name == "save")));
    }
}
