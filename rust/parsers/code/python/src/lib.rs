//! repo-graph-parser-python — tree-sitter Python → `repo_graph_core` types.
//!
//! Single-file scan: emit Module/Class/Function/Method nodes with Code/Doc/
//! Position cells, intra-file `defines` and `calls` edges. Cross-file refs
//! (imports, bare-name or attribute calls that bind to another module) are
//! recorded as `ImportStmt` / `CallSite` for the graph crate's cross-file
//! resolver.
//!
//! All code-domain primitives (constants, `FileParse`, `CodeNav`,
//! `ImportStmt`, `CallSite`, `ParseError`) live in `repo-graph-code-domain`
//! and are re-exported from this crate for convenience.

use std::collections::HashMap;

use repo_graph_core::{Cell, CellPayload, Confidence, Edge, Node, NodeId, RepoId};
use tree_sitter::{Node as TsNode, Parser};

pub use repo_graph_code_domain::{
    CallQualifier, CallSite, CodeNav, FileParse, GRAPH_TYPE, ImportStmt, ImportTarget, ParseError,
    cell_type, edge_category, node_kind,
};

/// Parse one Python source file.
///
/// `module_qname` is the dotted module path in `::` form (`myapp::users`).
/// `file_rel_path` is the repo-relative path stored in position cells.
pub fn parse_file(
    source: &str,
    file_rel_path: &str,
    module_qname: &str,
    repo: RepoId,
) -> Result<FileParse, ParseError> {
    let mut parser = Parser::new();
    let lang: tree_sitter::Language = tree_sitter_python::LANGUAGE.into();
    parser
        .set_language(&lang)
        .map_err(|e| ParseError::LanguageInit(e.to_string()))?;
    let tree = parser.parse(source, None).ok_or(ParseError::NoTree)?;
    let src = source.as_bytes();

    let mut acc = Acc::default();
    let root = tree.root_node();

    let module_id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::MODULE, module_qname);
    acc.nodes.push(Node {
        id: module_id,
        repo,
        confidence: Confidence::Strong,
        cells: build_cells(&root, src, file_rel_path),
    });
    let module_simple = module_qname.rsplit("::").next().unwrap_or(module_qname);
    acc.nav
        .record(module_id, module_simple, module_qname, node_kind::MODULE, None);

    let mut cursor = root.walk();
    for child in root.named_children(&mut cursor) {
        match child.kind() {
            "class_definition" => {
                visit_class(child, src, file_rel_path, module_qname, module_id, repo, &mut acc);
            }
            "function_definition" => {
                visit_function(
                    child, src, file_rel_path, module_qname, module_id, None, repo, &mut acc,
                    &[],
                );
            }
            "decorated_definition" => {
                visit_decorated_top(
                    child, src, file_rel_path, module_qname, module_id, repo, &mut acc,
                );
            }
            "import_statement" => collect_import(child, src, module_qname, &mut acc),
            "import_from_statement" => collect_import_from(child, src, module_qname, &mut acc),
            "expression_statement" => {
                // Top-level calls — record them with module as source.
                collect_calls_in(child, src, module_id, None, &mut acc);
                // Django-style path('/x', view) registrations in urls.py scan.
                scan_django_routes(child, src, repo, &mut acc);
            }
            "assignment" => {
                // urlpatterns = [ path(...), re_path(...) ] lives here too.
                scan_django_routes(child, src, repo, &mut acc);
            }
            _ => {}
        }
    }

    resolve_intra_file(acc, repo)
}

/// Unwrap a top-level `decorated_definition` into its inner def + decorator
/// list, then dispatch. v0.4.11a R-python — needed so Flask/FastAPI handlers
/// (which are always decorated) emit both their function node and the
/// associated Route nodes.
fn visit_decorated_top(
    n: TsNode,
    src: &[u8],
    file_rel: &str,
    module_qname: &str,
    module_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    let (decos, inner) = split_decorated(n);
    let Some(inner) = inner else { return };
    match inner.kind() {
        "function_definition" => {
            visit_function(
                inner, src, file_rel, module_qname, module_id, None, repo, acc, &decos,
            );
        }
        "class_definition" => {
            // Class decorators are rare route surface in Py frameworks; skip
            // route extraction here but still visit so nodes/methods emit.
            visit_class(inner, src, file_rel, module_qname, module_id, repo, acc);
        }
        _ => {}
    }
}

fn split_decorated<'a>(n: TsNode<'a>) -> (Vec<TsNode<'a>>, Option<TsNode<'a>>) {
    let mut decos = Vec::new();
    let mut inner = None;
    let mut cursor = n.walk();
    for c in n.named_children(&mut cursor) {
        match c.kind() {
            "decorator" => decos.push(c),
            "function_definition" | "class_definition" => inner = Some(c),
            _ => {}
        }
    }
    (decos, inner)
}

// ============================================================================
// Internal accumulator
// ============================================================================

#[derive(Default)]
struct Acc {
    nodes: Vec<Node>,
    edges: Vec<Edge>,
    imports: Vec<ImportStmt>,
    unresolved: Vec<UnresolvedCall>,
    /// module-level functions: bare name → node id
    module_functions: HashMap<String, NodeId>,
    /// class methods: (class id, method name) → method node id
    class_methods: HashMap<(NodeId, String), NodeId>,
    nav: CodeNav,
}

struct UnresolvedCall {
    from: NodeId,
    enclosing_class: Option<NodeId>,
    qualifier: CallQualifier,
}

// ============================================================================
// Visitors
// ============================================================================

fn visit_class(
    n: TsNode,
    src: &[u8],
    file_rel: &str,
    module_qname: &str,
    module_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    let Some(name) = child_text(n, "name", src) else {
        return;
    };
    let class_qname = format!("{module_qname}::{name}");
    let class_id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::CLASS, &class_qname);
    acc.nodes.push(Node {
        id: class_id,
        repo,
        confidence: Confidence::Strong,
        cells: build_cells(&n, src, file_rel),
    });
    acc.edges.push(Edge {
        from: module_id,
        to: class_id,
        category: edge_category::DEFINES,
        confidence: Confidence::Strong,
    });
    acc.nav
        .record(class_id, name, &class_qname, node_kind::CLASS, Some(module_id));

    let Some(body) = n.child_by_field_name("body") else {
        return;
    };
    let mut cursor = body.walk();
    for member in body.named_children(&mut cursor) {
        match member.kind() {
            "function_definition" => {
                visit_method(member, src, file_rel, &class_qname, class_id, repo, acc, &[]);
            }
            "decorated_definition" => {
                let (decos, inner) = split_decorated(member);
                if let Some(inner) = inner
                    && inner.kind() == "function_definition"
                {
                    visit_method(inner, src, file_rel, &class_qname, class_id, repo, acc, &decos);
                }
            }
            _ => {}
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn visit_method(
    n: TsNode,
    src: &[u8],
    file_rel: &str,
    class_qname: &str,
    class_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
    decorators: &[TsNode],
) {
    let Some(name) = child_text(n, "name", src) else {
        return;
    };
    let method_qname = format!("{class_qname}::{name}");
    let method_id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::METHOD, &method_qname);
    acc.nodes.push(Node {
        id: method_id,
        repo,
        confidence: Confidence::Strong,
        cells: build_cells(&n, src, file_rel),
    });
    acc.edges.push(Edge {
        from: class_id,
        to: method_id,
        category: edge_category::DEFINES,
        confidence: Confidence::Strong,
    });
    acc.class_methods
        .insert((class_id, name.to_string()), method_id);
    acc.nav
        .record(method_id, name, &method_qname, node_kind::METHOD, Some(class_id));

    for deco in decorators {
        check_route_decorator(*deco, src, method_id, repo, acc);
    }

    if let Some(body) = n.child_by_field_name("body") {
        collect_calls_in(body, src, method_id, Some(class_id), acc);
    }
}

#[allow(clippy::too_many_arguments)]
fn visit_function(
    n: TsNode,
    src: &[u8],
    file_rel: &str,
    module_qname: &str,
    module_id: NodeId,
    parent_func_id: Option<NodeId>,
    repo: RepoId,
    acc: &mut Acc,
    decorators: &[TsNode],
) {
    let Some(name) = child_text(n, "name", src) else {
        return;
    };
    let func_qname = format!("{module_qname}::{name}");
    let func_id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::FUNCTION, &func_qname);
    acc.nodes.push(Node {
        id: func_id,
        repo,
        confidence: Confidence::Strong,
        cells: build_cells(&n, src, file_rel),
    });
    let parent = parent_func_id.unwrap_or(module_id);
    acc.edges.push(Edge {
        from: parent,
        to: func_id,
        category: edge_category::DEFINES,
        confidence: Confidence::Strong,
    });
    // Only top-level functions go in the module symbol table — nested ones
    // aren't reachable by bare name from module scope.
    if parent_func_id.is_none() {
        acc.module_functions
            .insert(name.to_string(), func_id);
    }
    acc.nav
        .record(func_id, name, &func_qname, node_kind::FUNCTION, Some(parent));

    for deco in decorators {
        check_route_decorator(*deco, src, func_id, repo, acc);
    }

    if let Some(body) = n.child_by_field_name("body") {
        collect_calls_in(body, src, func_id, None, acc);
        // Nested defs inside the body — visited recursively.
        let mut cursor = body.walk();
        for member in body.named_children(&mut cursor) {
            match member.kind() {
                "function_definition" => visit_function(
                    member, src, file_rel, &func_qname, module_id, Some(func_id), repo, acc, &[],
                ),
                "decorated_definition" => {
                    let (decos, inner) = split_decorated(member);
                    if let Some(inner) = inner
                        && inner.kind() == "function_definition"
                    {
                        visit_function(
                            inner, src, file_rel, &func_qname, module_id, Some(func_id), repo,
                            acc, &decos,
                        );
                    }
                }
                _ => {}
            }
        }
    }
}

// ============================================================================
// Imports
// ============================================================================

fn collect_import(n: TsNode, src: &[u8], from_module: &str, acc: &mut Acc) {
    // `import a, b.c as d` — children are dotted_name or aliased_import.
    let mut cursor = n.walk();
    for child in n.named_children(&mut cursor) {
        match child.kind() {
            "dotted_name" => {
                let path = text(child, src).to_string();
                acc.imports.push(ImportStmt {
                    from_module: from_module.to_string(),
                    target: ImportTarget::Module { path, alias: None },
                });
            }
            "aliased_import" => {
                let Some(name_n) = child.child_by_field_name("name") else {
                    continue;
                };
                let Some(alias_n) = child.child_by_field_name("alias") else {
                    continue;
                };
                acc.imports.push(ImportStmt {
                    from_module: from_module.to_string(),
                    target: ImportTarget::Module {
                        path: text(name_n, src).to_string(),
                        alias: Some(text(alias_n, src).to_string()),
                    },
                });
            }
            _ => {}
        }
    }
}

fn collect_import_from(n: TsNode, src: &[u8], from_module: &str, acc: &mut Acc) {
    // Fields: module_name (dotted_name | relative_import) + name children.
    let (module, level) = match n.child_by_field_name("module_name") {
        Some(m) if m.kind() == "dotted_name" => (text(m, src).to_string(), 0),
        Some(m) if m.kind() == "relative_import" => parse_relative_import(m, src),
        Some(_) | None => (String::new(), 0),
    };

    // Imported names are the `name` field (can be multi). Walk named children
    // after the module_name and treat dotted_name / aliased_import as items.
    let mut cursor = n.walk();
    let mut saw_module = false;
    for child in n.named_children(&mut cursor) {
        if !saw_module {
            // Skip the module_name / relative_import slot.
            if matches!(child.kind(), "dotted_name" | "relative_import")
                && n.child_by_field_name("module_name").map(|m| m.id()) == Some(child.id())
            {
                saw_module = true;
                continue;
            }
        }
        match child.kind() {
            "dotted_name" => {
                acc.imports.push(ImportStmt {
                    from_module: from_module.to_string(),
                    target: ImportTarget::Symbol {
                        module: module.clone(),
                        name: text(child, src).to_string(),
                        alias: None,
                        level,
                    },
                });
            }
            "aliased_import" => {
                let Some(name_n) = child.child_by_field_name("name") else {
                    continue;
                };
                let alias = child
                    .child_by_field_name("alias")
                    .map(|a| text(a, src).to_string());
                acc.imports.push(ImportStmt {
                    from_module: from_module.to_string(),
                    target: ImportTarget::Symbol {
                        module: module.clone(),
                        name: text(name_n, src).to_string(),
                        alias,
                        level,
                    },
                });
            }
            _ => {}
        }
    }
}

fn parse_relative_import(n: TsNode, src: &[u8]) -> (String, u32) {
    // `.` * level + optional dotted_name.
    let raw = text(n, src);
    let level = raw.chars().take_while(|c| *c == '.').count() as u32;
    let module = raw.trim_start_matches('.').to_string();
    (module, level)
}

// ============================================================================
// Call collection
// ============================================================================

fn collect_calls_in(
    n: TsNode,
    src: &[u8],
    from: NodeId,
    enclosing_class: Option<NodeId>,
    acc: &mut Acc,
) {
    let mut stack = vec![n];
    while let Some(node) = stack.pop() {
        let kind = node.kind();
        // Don't descend into nested function/class bodies — they have their
        // own from-node and are walked separately.
        if matches!(kind, "function_definition" | "class_definition") {
            continue;
        }
        if kind == "call"
            && let Some(q) = extract_call_qualifier(node, src)
        {
            acc.unresolved.push(UnresolvedCall {
                from,
                enclosing_class,
                qualifier: q,
            });
        }
        let mut cursor = node.walk();
        for child in node.named_children(&mut cursor) {
            stack.push(child);
        }
    }
}

fn extract_call_qualifier(call: TsNode, src: &[u8]) -> Option<CallQualifier> {
    let func = call.child_by_field_name("function")?;
    match func.kind() {
        "identifier" => Some(CallQualifier::Bare(text(func, src).to_string())),
        "attribute" => {
            let object = func.child_by_field_name("object")?;
            let attr = func.child_by_field_name("attribute")?;
            let name = text(attr, src).to_string();
            if object.kind() == "identifier" {
                let base = text(object, src).to_string();
                if base == "self" {
                    Some(CallQualifier::SelfMethod(name))
                } else {
                    Some(CallQualifier::Attribute { base, name })
                }
            } else {
                // Chained / complex receivers — keep the raw text.
                Some(CallQualifier::ComplexReceiver {
                    receiver: text(object, src).to_string(),
                    name,
                })
            }
        }
        _ => None,
    }
}

// ============================================================================
// Intra-file resolution
// ============================================================================

fn resolve_intra_file(mut acc: Acc, _repo: RepoId) -> Result<FileParse, ParseError> {
    let mut out = FileParse {
        nodes: std::mem::take(&mut acc.nodes),
        edges: std::mem::take(&mut acc.edges),
        imports: std::mem::take(&mut acc.imports),
        calls: Vec::new(),
        refs: Vec::new(),
        nav: std::mem::take(&mut acc.nav),
    };
    for uc in acc.unresolved {
        let resolved: Option<NodeId> = match &uc.qualifier {
            CallQualifier::Bare(name) => acc.module_functions.get(name).copied(),
            CallQualifier::SelfMethod(name) => uc
                .enclosing_class
                .and_then(|cid| acc.class_methods.get(&(cid, name.clone())).copied()),
            _ => None,
        };
        match resolved {
            Some(to) => out.edges.push(Edge {
                from: uc.from,
                to,
                category: edge_category::CALLS,
                confidence: Confidence::Strong,
            }),
            None => out.calls.push(CallSite {
                from: uc.from,
                qualifier: uc.qualifier,
            }),
        }
    }
    Ok(out)
}

// ============================================================================
// Cell building
// ============================================================================

fn build_cells(n: &TsNode, src: &[u8], file_rel: &str) -> Vec<Cell> {
    let code = Cell {
        kind: cell_type::CODE,
        payload: CellPayload::Text(slice(n, src).to_string()),
    };
    let pos = Cell {
        kind: cell_type::POSITION,
        payload: CellPayload::Json(position_json(n, file_rel)),
    };
    let mut cells = vec![code, pos];
    if let Some(doc) = extract_docstring(n, src) {
        cells.push(Cell {
            kind: cell_type::DOC,
            payload: CellPayload::Text(doc),
        });
    }
    cells
}

fn position_json(n: &TsNode, file_rel: &str) -> String {
    let start = n.start_position();
    let end = n.end_position();
    format!(
        "{{\"file\":\"{}\",\"start_line\":{},\"end_line\":{}}}",
        file_rel.replace('\\', "\\\\").replace('"', "\\\""),
        start.row,
        end.row
    )
}

/// Returns the module/class/function docstring if present.
fn extract_docstring(n: &TsNode, src: &[u8]) -> Option<String> {
    let body = match n.kind() {
        "module" => *n,
        _ => n.child_by_field_name("body")?,
    };
    let mut cursor = body.walk();
    let first = body.named_children(&mut cursor).next()?;
    if first.kind() != "expression_statement" {
        return None;
    }
    let mut inner_cursor = first.walk();
    let string_node = first.named_children(&mut inner_cursor).next()?;
    if string_node.kind() != "string" {
        return None;
    }
    let raw = text(string_node, src);
    Some(strip_string_quotes(raw))
}

fn strip_string_quotes(s: &str) -> String {
    const PREFIXES: [char; 8] = ['r', 'R', 'b', 'B', 'u', 'U', 'f', 'F'];
    let t = s.trim_start_matches(PREFIXES);
    let stripped = if t.len() >= 6
        && ((t.starts_with("\"\"\"") && t.ends_with("\"\"\""))
            || (t.starts_with("'''") && t.ends_with("'''")))
    {
        &t[3..t.len() - 3]
    } else if t.len() >= 2
        && ((t.starts_with('"') && t.ends_with('"'))
            || (t.starts_with('\'') && t.ends_with('\'')))
    {
        &t[1..t.len() - 1]
    } else {
        t
    };
    stripped.to_string()
}

// ============================================================================
// Route extraction — Flask / FastAPI / Django (v0.4.11a R-python)
// ============================================================================
//
// Flask / FastAPI use decorators on function/method handlers:
//   @app.route('/path', methods=['GET','POST'])   (Flask)
//   @app.get('/path')                              (Flask 2+, FastAPI)
//   @router.post('/path')                          (FastAPI)
//   @blueprint.route('/path')                      (Flask)
//
// Django uses `path('/url', view)` / `re_path(...)` inside a `urlpatterns`
// list in `urls.py`. Method defaults to ANY because Django method dispatch
// happens inside the view function, not the URL declaration.

fn check_route_decorator(
    deco: TsNode,
    src: &[u8],
    handler_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    // Decorator text starts with '@'. Its `.call` form gives us the function
    // expression + argument list.
    let raw = text(deco, src);
    let body = raw.trim_start_matches('@').trim();
    let Some(paren) = body.find('(') else {
        return;
    };
    let head = &body[..paren];
    // Verb is the trailing attribute: `app.get` → "get"; `app.route` → "route".
    let verb = head.rsplit('.').next().unwrap_or("").to_ascii_lowercase();
    let Some(methods) = route_methods_for(&verb, &body[paren..]) else {
        return;
    };
    let args = &body[paren + 1..];
    let Some(path) = first_string_literal(args) else {
        return;
    };
    for m in methods {
        emit_route(m, &path, handler_id, repo, acc);
    }
}

/// Returns the HTTP methods a Python decorator maps to, or None if not a
/// route decorator. The inputs are the trailing attribute (`get`, `route`,
/// `websocket`…) and the full arg-list slice starting at `(`.
fn route_methods_for(verb: &str, args: &str) -> Option<Vec<&'static str>> {
    match verb {
        "get" => Some(vec!["GET"]),
        "post" => Some(vec!["POST"]),
        "put" => Some(vec!["PUT"]),
        "delete" => Some(vec!["DELETE"]),
        "patch" => Some(vec!["PATCH"]),
        "head" => Some(vec!["HEAD"]),
        "options" => Some(vec!["OPTIONS"]),
        "route" => Some(flask_route_methods(args)),
        _ => None,
    }
}

/// Extract the `methods=[...]` kwarg from a Flask-style `@app.route(...)`.
/// Defaults to `["GET"]` when absent.
fn flask_route_methods(args: &str) -> Vec<&'static str> {
    let Some(idx) = args.find("methods") else {
        return vec!["GET"];
    };
    let rest = &args[idx + "methods".len()..];
    let Some(lb) = rest.find('[') else {
        return vec!["GET"];
    };
    let Some(rb) = rest[lb..].find(']') else {
        return vec!["GET"];
    };
    let list = &rest[lb + 1..lb + rb];
    let mut out = Vec::new();
    for part in list.split(',') {
        let t = part.trim().trim_matches('\'').trim_matches('"').trim();
        let verb = match t.to_ascii_uppercase().as_str() {
            "GET" => "GET",
            "POST" => "POST",
            "PUT" => "PUT",
            "DELETE" => "DELETE",
            "PATCH" => "PATCH",
            "HEAD" => "HEAD",
            "OPTIONS" => "OPTIONS",
            _ => continue,
        };
        out.push(verb);
    }
    if out.is_empty() {
        out.push("GET");
    }
    out
}

/// Django `urls.py` scan — finds `path('/url', view)` / `re_path(r'/url', …)`
/// / `url(r'/url', …)` calls inside the node and emits one Route per path.
/// Method is ANY because Django views dispatch internally.
fn scan_django_routes(root: TsNode, src: &[u8], repo: RepoId, acc: &mut Acc) {
    let mut stack = vec![root];
    while let Some(n) = stack.pop() {
        if n.kind() == "call"
            && let Some(func) = n.child_by_field_name("function")
        {
            let name = text(func, src);
            let is_django =
                matches!(name, "path" | "re_path" | "url") || name.ends_with(".path");
            if is_django
                && let Some(args) = n.child_by_field_name("arguments")
            {
                let arg_text = text(args, src);
                if let Some(path) = first_string_literal(&arg_text[1..]) {
                    emit_route_no_handler("ANY", &path, repo, acc);
                }
            }
        }
        let mut cursor = n.walk();
        for c in n.named_children(&mut cursor) {
            stack.push(c);
        }
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

fn emit_route_no_handler(method: &str, path: &str, repo: RepoId, acc: &mut Acc) {
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

fn first_string_literal(s: &str) -> Option<String> {
    let bytes = s.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        let b = bytes[i];
        if b == b'\'' || b == b'"' {
            let quote = b;
            // Skip leading r/b/u/f string prefixes captured earlier — s has
            // already been sliced past the `(`, so we can match the opener.
            let mut j = i + 1;
            while j < bytes.len() && bytes[j] != quote {
                if bytes[j] == b'\\' {
                    j += 2;
                    continue;
                }
                j += 1;
            }
            if j >= bytes.len() {
                return None;
            }
            let lit = std::str::from_utf8(&bytes[i + 1..j]).ok()?.to_string();
            if lit.is_empty() || lit.len() > 256 {
                return None;
            }
            return Some(lit);
        }
        // Skip common prefix chars before a quote (r''/b""/rb'' — up to 2
        // char prefix). If `b` is alphanumeric or '_' we just keep walking.
        i += 1;
    }
    None
}

// ============================================================================
// Tree-sitter helpers
// ============================================================================

fn slice<'a>(n: &TsNode, src: &'a [u8]) -> &'a str {
    std::str::from_utf8(&src[n.byte_range()]).unwrap_or("")
}

fn text<'a>(n: TsNode, src: &'a [u8]) -> &'a str {
    slice(&n, src)
}

fn child_text<'a>(n: TsNode, field: &str, src: &'a [u8]) -> Option<&'a str> {
    n.child_by_field_name(field).map(|c| text(c, src))
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use repo_graph_core::EdgeCategoryId;

    fn repo() -> RepoId {
        RepoId::from_canonical("test://py_smoke")
    }

    fn has_edge(parse: &FileParse, from: NodeId, to: NodeId, cat: EdgeCategoryId) -> bool {
        parse
            .edges
            .iter()
            .any(|e| e.from == from && e.to == to && e.category == cat)
    }

    #[test]
    fn parses_helpers_module_with_two_functions() {
        let src = "def hash_password(password):\n    return _inner(password)\n\n\ndef _inner(p):\n    return p.encode()\n";
        let parse = parse_file(src, "myapp/helpers.py", "myapp::helpers", repo()).unwrap();

        let module_id = NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::MODULE, "myapp::helpers");
        let hash_id = NodeId::from_parts(
            GRAPH_TYPE,
            repo(),
            node_kind::FUNCTION,
            "myapp::helpers::hash_password",
        );
        let inner_id = NodeId::from_parts(
            GRAPH_TYPE,
            repo(),
            node_kind::FUNCTION,
            "myapp::helpers::_inner",
        );

        assert!(parse.nodes.iter().any(|n| n.id == module_id));
        assert!(parse.nodes.iter().any(|n| n.id == hash_id));
        assert!(parse.nodes.iter().any(|n| n.id == inner_id));

        assert!(has_edge(&parse, module_id, hash_id, edge_category::DEFINES));
        assert!(has_edge(&parse, module_id, inner_id, edge_category::DEFINES));

        // Intra-file bare call: hash_password → _inner
        assert!(
            has_edge(&parse, hash_id, inner_id, edge_category::CALLS),
            "expected intra-file bare call to resolve, got calls edges: {:?}",
            parse
                .edges
                .iter()
                .filter(|e| e.category == edge_category::CALLS)
                .collect::<Vec<_>>()
        );
    }

    #[test]
    fn parses_users_class_with_self_call() {
        let src = "from .helpers import hash_password\n\n\nclass User:\n    def login(self, password):\n        return hash_password(password)\n\n    def save(self):\n        self.login(\"x\")\n";
        let parse = parse_file(src, "myapp/users.py", "myapp::users", repo()).unwrap();

        let class_id = NodeId::from_parts(
            GRAPH_TYPE,
            repo(),
            node_kind::CLASS,
            "myapp::users::User",
        );
        let login_id = NodeId::from_parts(
            GRAPH_TYPE,
            repo(),
            node_kind::METHOD,
            "myapp::users::User::login",
        );
        let save_id = NodeId::from_parts(
            GRAPH_TYPE,
            repo(),
            node_kind::METHOD,
            "myapp::users::User::save",
        );

        assert!(parse.nodes.iter().any(|n| n.id == class_id));
        assert!(parse.nodes.iter().any(|n| n.id == login_id));
        assert!(parse.nodes.iter().any(|n| n.id == save_id));

        assert!(has_edge(&parse, class_id, login_id, edge_category::DEFINES));
        assert!(has_edge(&parse, class_id, save_id, edge_category::DEFINES));

        // self.login() inside save — intra-class self call resolves.
        assert!(
            has_edge(&parse, save_id, login_id, edge_category::CALLS),
            "expected self.login call to resolve to User::login"
        );

        // hash_password(...) inside login — cross-file, stays unresolved.
        assert!(
            parse
                .calls
                .iter()
                .any(|c| c.from == login_id
                    && matches!(&c.qualifier, CallQualifier::Bare(n) if n == "hash_password")),
            "expected hash_password call to be unresolved, got: {:?}",
            parse.calls
        );

        // Relative import record.
        assert!(parse.imports.iter().any(|i| matches!(
            &i.target,
            ImportTarget::Symbol { module, name, level, .. }
                if module == "helpers" && name == "hash_password" && *level == 1
        )));
    }

    #[test]
    fn parses_auth_with_absolute_and_submodule_imports() {
        let src = "from myapp.users import User\nfrom myapp import helpers\n\n\ndef do_login():\n    u = User()\n    u.login(\"x\")\n    helpers.hash_password(\"x\")\n";
        let parse = parse_file(src, "myapp/auth.py", "myapp::auth", repo()).unwrap();

        let do_login_id = NodeId::from_parts(
            GRAPH_TYPE,
            repo(),
            node_kind::FUNCTION,
            "myapp::auth::do_login",
        );
        assert!(parse.nodes.iter().any(|n| n.id == do_login_id));

        // Two import records.
        assert!(parse.imports.iter().any(|i| matches!(
            &i.target,
            ImportTarget::Symbol { module, name, level, .. }
                if module == "myapp.users" && name == "User" && *level == 0
        )));
        assert!(parse.imports.iter().any(|i| matches!(
            &i.target,
            ImportTarget::Symbol { module, name, level, .. }
                if module == "myapp" && name == "helpers" && *level == 0
        )));

        // Three call sites, all cross-file at the v0.4.2 layer.
        let mut quals: Vec<&CallQualifier> = parse
            .calls
            .iter()
            .filter(|c| c.from == do_login_id)
            .map(|c| &c.qualifier)
            .collect();
        quals.sort_by_key(|q| format!("{q:?}"));
        assert_eq!(quals.len(), 3, "unexpected call sites: {quals:?}");
        // User() — bare call (constructor)
        assert!(quals.iter().any(|q| matches!(q, CallQualifier::Bare(n) if n == "User")));
        // u.login("x") — Attribute. v0.4.3 disambiguates "u is a local var → drop"
        // from "helpers is an imported name → resolve" using the import table.
        assert!(quals.iter().any(
            |q| matches!(q, CallQualifier::Attribute { base, name } if base == "u" && name == "login")
        ));
        // helpers.hash_password("x") — Attribute
        assert!(quals.iter().any(
            |q| matches!(q, CallQualifier::Attribute { base, name } if base == "helpers" && name == "hash_password")
        ));
    }

    #[test]
    fn module_node_has_code_and_position_cells() {
        let src = "def f(): pass\n";
        let parse = parse_file(src, "foo.py", "foo", repo()).unwrap();
        let module_id = NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::MODULE, "foo");
        let m = parse.nodes.iter().find(|n| n.id == module_id).unwrap();
        assert!(m.cells.iter().any(|c| c.kind == cell_type::CODE));
        assert!(m.cells.iter().any(|c| c.kind == cell_type::POSITION));
    }

    #[test]
    fn docstring_becomes_doc_cell() {
        let src = "\"\"\"hello world\"\"\"\n\ndef f():\n    \"\"\"inner doc\"\"\"\n    return 1\n";
        let parse = parse_file(src, "foo.py", "foo", repo()).unwrap();
        let module_id = NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::MODULE, "foo");
        let func_id = NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::FUNCTION, "foo::f");
        let m = parse.nodes.iter().find(|n| n.id == module_id).unwrap();
        let f = parse.nodes.iter().find(|n| n.id == func_id).unwrap();
        assert!(
            m.cells.iter().any(|c| c.kind == cell_type::DOC
                && matches!(&c.payload, CellPayload::Text(t) if t == "hello world")),
            "module doc cell missing"
        );
        assert!(
            f.cells.iter().any(|c| c.kind == cell_type::DOC
                && matches!(&c.payload, CellPayload::Text(t) if t == "inner doc")),
            "function doc cell missing"
        );
    }

    #[test]
    fn syntax_error_produces_partial_graph() {
        // tree-sitter recovers — we still get the valid top-level def.
        let src = "def ok(): pass\n\nthis is !!! not valid python\n";
        let parse = parse_file(src, "broken.py", "broken", repo()).unwrap();
        let ok_id = NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::FUNCTION, "broken::ok");
        assert!(parse.nodes.iter().any(|n| n.id == ok_id));
    }

    // ----- v0.4.11a R-python: route extraction -----

    fn route_id(method: &str, path: &str) -> NodeId {
        NodeId::from_parts(
            GRAPH_TYPE,
            repo(),
            node_kind::ROUTE,
            &format!("{method} {path}"),
        )
    }

    #[test]
    fn flask_app_get_decorator_emits_route() {
        let src = "from flask import Flask\napp = Flask(__name__)\n\n@app.get('/users')\ndef list_users():\n    return []\n";
        let parse = parse_file(src, "app.py", "app", repo()).unwrap();
        let handler = NodeId::from_parts(
            GRAPH_TYPE,
            repo(),
            node_kind::FUNCTION,
            "app::list_users",
        );
        let rid = route_id("GET", "/users");
        assert!(parse.nodes.iter().any(|n| n.id == rid), "missing Route");
        assert!(parse.nodes.iter().any(|n| n.id == handler));
        assert!(
            has_edge(&parse, rid, handler, edge_category::HANDLED_BY),
            "missing HANDLED_BY edge"
        );
    }

    #[test]
    fn flask_route_with_methods_kwarg_emits_multiple() {
        let src = "from flask import Flask\napp = Flask(__name__)\n\n@app.route('/users', methods=['GET','POST'])\ndef users():\n    return []\n";
        let parse = parse_file(src, "app.py", "app", repo()).unwrap();
        assert!(parse.nodes.iter().any(|n| n.id == route_id("GET", "/users")));
        assert!(parse.nodes.iter().any(|n| n.id == route_id("POST", "/users")));
    }

    #[test]
    fn flask_route_without_methods_defaults_to_get() {
        let src = "@app.route('/ping')\ndef ping():\n    return 'pong'\n";
        let parse = parse_file(src, "app.py", "app", repo()).unwrap();
        assert!(parse.nodes.iter().any(|n| n.id == route_id("GET", "/ping")));
    }

    #[test]
    fn fastapi_router_post_decorator_emits_route() {
        let src = "from fastapi import APIRouter\nrouter = APIRouter()\n\n@router.post('/items')\nasync def create_item(item: dict):\n    return item\n";
        let parse = parse_file(src, "routes.py", "routes", repo()).unwrap();
        let handler = NodeId::from_parts(
            GRAPH_TYPE,
            repo(),
            node_kind::FUNCTION,
            "routes::create_item",
        );
        let rid = route_id("POST", "/items");
        assert!(parse.nodes.iter().any(|n| n.id == rid));
        assert!(has_edge(&parse, rid, handler, edge_category::HANDLED_BY));
    }

    #[test]
    fn django_path_call_emits_route_without_handler() {
        let src = "from django.urls import path, re_path\nfrom . import views\n\nurlpatterns = [\n    path('users/', views.user_list),\n    re_path(r'^admin/', views.admin),\n]\n";
        let parse = parse_file(src, "urls.py", "urls", repo()).unwrap();
        assert!(parse.nodes.iter().any(|n| n.id == route_id("ANY", "users/")));
        assert!(parse.nodes.iter().any(|n| n.id == route_id("ANY", "^admin/")));
    }

    #[test]
    fn class_method_decorator_emits_route() {
        let src = "class Api:\n    @staticmethod\n    @app.get('/ok')\n    def ok():\n        return 'ok'\n";
        let parse = parse_file(src, "api.py", "api", repo()).unwrap();
        let handler = NodeId::from_parts(
            GRAPH_TYPE,
            repo(),
            node_kind::METHOD,
            "api::Api::ok",
        );
        let rid = route_id("GET", "/ok");
        assert!(parse.nodes.iter().any(|n| n.id == handler), "method missing");
        assert!(parse.nodes.iter().any(|n| n.id == rid), "route missing");
        assert!(has_edge(&parse, rid, handler, edge_category::HANDLED_BY));
    }

    #[test]
    fn non_route_decorator_is_ignored() {
        let src = "@functools.lru_cache(maxsize=128)\ndef compute(x):\n    return x\n";
        let parse = parse_file(src, "m.py", "m", repo()).unwrap();
        let has_any_route = parse
            .nodes
            .iter()
            .any(|n| matches!(parse.nav.kind_by_id.get(&n.id).copied(), Some(k) if k == node_kind::ROUTE));
        assert!(!has_any_route, "non-route decorator shouldn't emit a Route");
    }
}
