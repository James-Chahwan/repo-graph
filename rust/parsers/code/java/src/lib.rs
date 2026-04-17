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
    let lang: tree_sitter::Language = tree_sitter_java::LANGUAGE.into();
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

    let mut cursor = root.walk();
    for child in root.named_children(&mut cursor) {
        match child.kind() {
            "import_declaration" => collect_import(child, src, module_qname, &mut acc),
            "class_declaration" | "interface_declaration" | "enum_declaration"
            | "record_declaration" => {
                visit_type_decl(child, src, file_rel_path, module_qname, module_id, repo, &mut acc);
            }
            _ => {}
        }
    }

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

fn visit_type_decl(
    node: TsNode,
    src: &[u8],
    file_rel: &str,
    module_qname: &str,
    parent_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    let Some(name_node) = node.child_by_field_name("name") else {
        return;
    };
    let name = text_of(name_node, src);
    let kind = match node.kind() {
        "class_declaration" | "record_declaration" => node_kind::CLASS,
        "interface_declaration" => node_kind::INTERFACE,
        "enum_declaration" => node_kind::ENUM,
        _ => return,
    };
    let qname = format!("{module_qname}::{name}");
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

    // Walk body for methods + nested types.
    let Some(body) = node.child_by_field_name("body") else {
        return;
    };
    let mut cursor = body.walk();
    for child in body.named_children(&mut cursor) {
        match child.kind() {
            "method_declaration" | "constructor_declaration" => {
                visit_method(child, src, file_rel, &qname, id, repo, acc);
            }
            "class_declaration" | "interface_declaration" | "enum_declaration"
            | "record_declaration" => {
                visit_type_decl(child, src, file_rel, &qname, id, repo, acc);
            }
            _ => {}
        }
    }

    // Check for Spring/JAX-RS route annotations on the class.
    check_route_annotations(node, src, file_rel, id, repo, acc);
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

    // Check for route annotations on the method.
    check_route_annotations(node, src, file_rel, id, repo, acc);
}

fn check_route_annotations(
    node: TsNode,
    src: &[u8],
    _file_rel: &str,
    handler_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    // Walk siblings/markers before this node looking for annotations.
    // In Java tree-sitter, annotations are modifiers on the declaration.
    let text = text_of(node, src);

    // Spring: @GetMapping("/path"), @PostMapping, @RequestMapping
    let spring_patterns = [
        ("@GetMapping", "GET"),
        ("@PostMapping", "POST"),
        ("@PutMapping", "PUT"),
        ("@DeleteMapping", "DELETE"),
        ("@PatchMapping", "PATCH"),
    ];
    for (prefix, method) in &spring_patterns {
        if let Some(pos) = text.find(prefix)
            && let Some(path) = extract_annotation_string(&text[pos..])
        {
            emit_route(method, &path, handler_id, repo, acc);
        }
    }
    // @RequestMapping with method param
    if let Some(pos) = text.find("@RequestMapping")
        && let Some(path) = extract_annotation_string(&text[pos..])
    {
        emit_route("ANY", &path, handler_id, repo, acc);
    }
    // JAX-RS: @Path("/path") + @GET/@POST
    if let Some(pos) = text.find("@Path")
        && let Some(path) = extract_annotation_string(&text[pos..])
    {
        let method = if text.contains("@GET") {
            "GET"
        } else if text.contains("@POST") {
            "POST"
        } else if text.contains("@PUT") {
            "PUT"
        } else if text.contains("@DELETE") {
            "DELETE"
        } else {
            "ANY"
        };
        emit_route(method, &path, handler_id, repo, acc);
    }
}

fn emit_route(method: &str, path: &str, handler_id: NodeId, repo: RepoId, acc: &mut Acc) {
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

fn extract_annotation_string(text: &str) -> Option<String> {
    let paren = text.find('(')?;
    let rest = &text[paren + 1..];
    // Find first quoted string: "..." or value = "..."
    let quote_start = rest.find('"')?;
    let after = &rest[quote_start + 1..];
    let quote_end = after.find('"')?;
    Some(after[..quote_end].to_string())
}

fn collect_import(node: TsNode, src: &[u8], from_module: &str, acc: &mut Acc) {
    // `import com.foo.bar.Baz;` or `import static com.foo.bar.Baz.method;`
    let text = text_of(node, src).trim().to_string();
    let path = text
        .trim_start_matches("import ")
        .trim_start_matches("static ")
        .trim_end_matches(';')
        .trim();

    if path.ends_with(".*") {
        // Wildcard import — module import
        let module_path = path.trim_end_matches(".*").replace('.', "::");
        acc.imports.push(ImportStmt {
            from_module: from_module.to_string(),
            target: ImportTarget::Module {
                path: module_path,
                alias: None,
            },
        });
    } else if let Some(last_dot) = path.rfind('.') {
        let module_part = &path[..last_dot];
        let name = &path[last_dot + 1..];
        acc.imports.push(ImportStmt {
            from_module: from_module.to_string(),
            target: ImportTarget::Symbol {
                module: module_part.replace('.', "::"),
                name: name.to_string(),
                alias: None,
                level: 0,
            },
        });
    }
}

fn collect_calls_in(node: TsNode, src: &[u8], from: NodeId, acc: &mut Acc) {
    let mut stack = vec![node];
    while let Some(n) = stack.pop() {
        if n.kind() == "method_invocation" {
            let qualifier = classify_method_invocation(n, src);
            acc.calls.push(CallSite { from, qualifier });
        }
        let mut cursor = n.walk();
        for child in n.named_children(&mut cursor) {
            if !matches!(
                child.kind(),
                "class_declaration"
                    | "lambda_expression"
                    | "method_declaration"
                    | "anonymous_class_body"
            ) {
                stack.push(child);
            }
        }
    }
}

fn classify_method_invocation(node: TsNode, src: &[u8]) -> CallQualifier {
    let name = node
        .child_by_field_name("name")
        .map(|n| text_of(n, src))
        .unwrap_or("");
    if let Some(obj) = node.child_by_field_name("object") {
        let obj_text = text_of(obj, src);
        if obj_text == "this" {
            CallQualifier::SelfMethod(name.to_string())
        } else if obj.kind() == "identifier" {
            CallQualifier::Attribute {
                base: obj_text.to_string(),
                name: name.to_string(),
            }
        } else {
            CallQualifier::ComplexReceiver {
                receiver: obj_text.to_string(),
                name: name.to_string(),
            }
        }
    } else {
        CallQualifier::Bare(name.to_string())
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
        let source = r#"
package com.example;

public class UserService {
    public User getUser(String id) {
        return db.find(id);
    }

    private void validate(User u) {}
}
"#;
        let fp = parse_file(source, "src/main/java/UserService.java", "com::example", repo()).unwrap();
        let names: Vec<&str> = fp.nav.name_by_id.values().map(|s| s.as_str()).collect();
        assert!(names.contains(&"UserService"));
        assert!(names.contains(&"getUser"));
        assert!(names.contains(&"validate"));
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::CLASS).count(), 1);
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::METHOD).count(), 2);
    }

    #[test]
    fn interfaces_and_enums() {
        let source = r#"
package com.example;

public interface Drawable {
    void draw();
}

public enum Color {
    RED, GREEN, BLUE;
}
"#;
        let fp = parse_file(source, "src/main/java/Types.java", "com::example", repo()).unwrap();
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::INTERFACE).count(), 1);
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::ENUM).count(), 1);
    }

    #[test]
    fn imports() {
        let source = r#"
package com.example;

import com.example.models.User;
import java.util.*;
import static org.junit.Assert.assertEquals;
"#;
        let fp = parse_file(source, "src/main/java/App.java", "com::example", repo()).unwrap();
        assert_eq!(fp.imports.len(), 3);
    }

    #[test]
    fn spring_routes() {
        let source = r#"
package com.example;

public class UserController {
    @GetMapping("/users")
    public List<User> list() { return null; }

    @PostMapping("/users")
    public User create() { return null; }
}
"#;
        let fp = parse_file(source, "src/main/java/UserController.java", "com::example", repo()).unwrap();
        let routes: Vec<_> = fp
            .nav
            .kind_by_id
            .iter()
            .filter(|(_, k)| **k == node_kind::ROUTE)
            .filter_map(|(id, _)| fp.nav.name_by_id.get(id).map(|s| s.as_str()))
            .collect();
        assert!(routes.contains(&"GET /users"));
        assert!(routes.contains(&"POST /users"));
    }

    #[test]
    fn this_calls() {
        let source = r#"
package com.example;

public class Service {
    public void handle() {
        this.validate();
        helper.process();
    }
    private void validate() {}
}
"#;
        let fp = parse_file(source, "src/main/java/Service.java", "com::example", repo()).unwrap();
        let self_calls: Vec<_> = fp
            .calls
            .iter()
            .filter(|c| matches!(&c.qualifier, CallQualifier::SelfMethod(_)))
            .collect();
        assert_eq!(self_calls.len(), 1);
        let attr_calls: Vec<_> = fp
            .calls
            .iter()
            .filter(|c| matches!(&c.qualifier, CallQualifier::Attribute { .. }))
            .collect();
        assert_eq!(attr_calls.len(), 1);
    }
}
