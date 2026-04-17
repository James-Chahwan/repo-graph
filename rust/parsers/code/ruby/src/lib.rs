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
    let lang: tree_sitter::Language = tree_sitter_ruby::LANGUAGE.into();
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

    visit_body(root, src, file_rel_path, module_qname, module_id, repo, &mut acc);

    if is_rails_routes_file(file_rel_path) {
        scan_rails_routes(root, src, repo, &mut acc);
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

fn visit_body(
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
            "class" => visit_class(child, src, file_rel, parent_qname, parent_id, repo, acc),
            "module" => visit_module(child, src, file_rel, parent_qname, parent_id, repo, acc),
            "method" | "singleton_method" => {
                visit_method(child, src, file_rel, parent_qname, parent_id, repo, acc);
            }
            "call" => {
                collect_require(child, src, parent_qname, acc);
                collect_call(child, src, parent_id, acc);
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
        visit_body(body, src, file_rel, &qname, id, repo, acc);
    }
}

fn visit_module(
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

    if let Some(body) = node.child_by_field_name("body") {
        visit_body(body, src, file_rel, &qname, id, repo, acc);
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
}

fn collect_require(node: TsNode, src: &[u8], from_module: &str, acc: &mut Acc) {
    let method_name = node
        .child_by_field_name("method")
        .map(|n| text_of(n, src))
        .unwrap_or("");
    if method_name != "require" && method_name != "require_relative" {
        return;
    }
    let Some(args) = node.child_by_field_name("arguments") else {
        return;
    };
    let mut cursor = args.walk();
    for arg in args.named_children(&mut cursor) {
        if arg.kind() == "string" {
            let raw = text_of(arg, src);
            let path = raw.trim_matches(|c| c == '\'' || c == '"');
            acc.imports.push(ImportStmt {
                from_module: from_module.to_string(),
                target: ImportTarget::Module {
                    path: path.to_string(),
                    alias: None,
                },
            });
        }
    }
}

fn collect_call(node: TsNode, src: &[u8], from: NodeId, acc: &mut Acc) {
    let method_name = node
        .child_by_field_name("method")
        .map(|n| text_of(n, src))
        .unwrap_or("");
    if method_name.is_empty() {
        return;
    }
    if let Some(recv) = node.child_by_field_name("receiver") {
        let recv_text = text_of(recv, src);
        if recv_text == "self" {
            acc.calls.push(CallSite {
                from,
                qualifier: CallQualifier::SelfMethod(method_name.to_string()),
            });
        } else if recv.kind() == "identifier" || recv.kind() == "constant" {
            acc.calls.push(CallSite {
                from,
                qualifier: CallQualifier::Attribute {
                    base: recv_text.to_string(),
                    name: method_name.to_string(),
                },
            });
        }
    } else {
        acc.calls.push(CallSite {
            from,
            qualifier: CallQualifier::Bare(method_name.to_string()),
        });
    }
}

fn collect_calls_in(node: TsNode, src: &[u8], from: NodeId, acc: &mut Acc) {
    let mut stack = vec![node];
    while let Some(n) = stack.pop() {
        if n.kind() == "call" {
            collect_call(n, src, from, acc);
        }
        let mut cursor = n.walk();
        for child in n.named_children(&mut cursor) {
            if !matches!(child.kind(), "method" | "singleton_method" | "class" | "module") {
                stack.push(child);
            }
        }
    }
}

fn text_of<'a>(node: TsNode<'a>, src: &'a [u8]) -> &'a str {
    node.utf8_text(src).unwrap_or("")
}

// ============================================================================
// Rails route extraction (v0.4.11a R-ruby)
// ============================================================================
//
// Gated to `config/routes.rb` (or any file named routes.rb) to avoid
// false-positives on arbitrary `get`/`post` method calls elsewhere in the
// codebase. Inside the Rails router DSL we match:
//
//   get/post/put/patch/delete/match '/path'[, to: 'ctrl#act']
//   root 'ctrl#index'
//   resources :users      → emits ANY /users
//   resource :profile     → emits ANY /profile
//
// Routes are emitted in shape B — `<METHOD> <path>` qname + Text
// ROUTE_METHOD cell — the resolver compat shape that HttpStackResolver
// accepts uniformly across parser-java/csharp/php/rust/python/ruby.

fn is_rails_routes_file(rel_path: &str) -> bool {
    rel_path.ends_with("routes.rb") || rel_path.ends_with("/routes.rb")
}

fn scan_rails_routes(root: TsNode, src: &[u8], repo: RepoId, acc: &mut Acc) {
    let mut stack = vec![root];
    while let Some(n) = stack.pop() {
        if n.kind() == "call" {
            try_emit_rails_route(n, src, repo, acc);
        }
        let mut cursor = n.walk();
        for c in n.named_children(&mut cursor) {
            stack.push(c);
        }
    }
}

fn try_emit_rails_route(call: TsNode, src: &[u8], repo: RepoId, acc: &mut Acc) {
    let method = call
        .child_by_field_name("method")
        .map(|n| text_of(n, src))
        .unwrap_or("");
    let Some(args) = call.child_by_field_name("arguments") else {
        return;
    };
    let verb = match method {
        "get" => Some("GET"),
        "post" => Some("POST"),
        "put" => Some("PUT"),
        "patch" => Some("PATCH"),
        "delete" => Some("DELETE"),
        "match" => Some("ANY"),
        "root" => Some("GET"),
        "resources" | "resource" => None,
        _ => return,
    };

    // First argument is either a string path or a :symbol (for resources).
    let mut cursor = args.walk();
    let first = args.named_children(&mut cursor).next();
    let Some(first) = first else { return };
    let first_txt = text_of(first, src);

    match method {
        "resources" | "resource" => {
            let name = first_txt.trim_start_matches(':').trim();
            if name.is_empty() {
                return;
            }
            let path = format!("/{name}");
            emit_rails_route("ANY", &path, repo, acc);
        }
        "root" => {
            emit_rails_route("GET", "/", repo, acc);
        }
        _ => {
            let Some(verb) = verb else { return };
            let path = match first.kind() {
                "string" => first_txt.trim_matches(|c| c == '\'' || c == '"').to_string(),
                _ => return,
            };
            if path.is_empty() {
                return;
            }
            emit_rails_route(verb, &path, repo, acc);
        }
    }
}

fn emit_rails_route(method: &str, path: &str, repo: RepoId, acc: &mut Acc) {
    let path = if path.starts_with('/') {
        path.to_string()
    } else {
        format!("/{path}")
    };
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
    fn classes_and_methods() {
        let source = r#"
class User
  def initialize(name)
    @name = name
  end

  def greet
    "Hello #{@name}"
  end
end
"#;
        let fp = parse_file(source, "app/models/user.rb", "app::models::user", repo()).unwrap();
        let names: Vec<&str> = fp.nav.name_by_id.values().map(|s| s.as_str()).collect();
        assert!(names.contains(&"User"));
        assert!(names.contains(&"initialize"));
        assert!(names.contains(&"greet"));
    }

    #[test]
    fn modules() {
        let source = r#"
module Auth
  class Token
    def verify; end
  end
end
"#;
        let fp = parse_file(source, "lib/auth.rb", "lib::auth", repo()).unwrap();
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::PACKAGE).count(), 1);
        assert_eq!(fp.nav.kind_by_id.values().filter(|k| **k == node_kind::CLASS).count(), 1);
    }

    #[test]
    fn require_imports() {
        let source = r#"
require 'json'
require_relative '../helpers/auth'
"#;
        let fp = parse_file(source, "app/service.rb", "app::service", repo()).unwrap();
        assert_eq!(fp.imports.len(), 2);
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
    fn rails_verb_routes_emit() {
        let source = r#"
Rails.application.routes.draw do
  get '/users', to: 'users#index'
  post '/users', to: 'users#create'
  put '/users/:id', to: 'users#update'
  delete '/users/:id', to: 'users#destroy'
end
"#;
        let fp = parse_file(source, "config/routes.rb", "config::routes", repo()).unwrap();
        assert!(fp.nodes.iter().any(|n| n.id == route_id("GET", "/users")));
        assert!(fp.nodes.iter().any(|n| n.id == route_id("POST", "/users")));
        assert!(fp.nodes.iter().any(|n| n.id == route_id("PUT", "/users/:id")));
        assert!(fp.nodes.iter().any(|n| n.id == route_id("DELETE", "/users/:id")));
    }

    #[test]
    fn rails_resources_and_root_emit() {
        let source = r#"
Rails.application.routes.draw do
  resources :posts
  resource :profile
  root 'home#index'
end
"#;
        let fp = parse_file(source, "config/routes.rb", "config::routes", repo()).unwrap();
        assert!(fp.nodes.iter().any(|n| n.id == route_id("ANY", "/posts")));
        assert!(fp.nodes.iter().any(|n| n.id == route_id("ANY", "/profile")));
        assert!(fp.nodes.iter().any(|n| n.id == route_id("GET", "/")));
    }

    #[test]
    fn routes_not_extracted_outside_routes_file() {
        // `get` used as hash accessor / method name elsewhere shouldn't emit routes.
        let source = r#"
class UsersController
  def get(key)
    @cache.get(key)
  end
end
"#;
        let fp = parse_file(source, "app/controllers/users.rb", "app::controllers::users", repo())
            .unwrap();
        let has_route = fp
            .nav
            .kind_by_id
            .values()
            .any(|k| *k == node_kind::ROUTE);
        assert!(!has_route, "non-routes.rb file should not emit ROUTE nodes");
    }
}
