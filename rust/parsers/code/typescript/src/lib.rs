//! repo-graph-parser-typescript — tree-sitter TypeScript → `repo_graph_core` types.
//!
//! Single-file scan: emit Module/Class/Interface/Function/Method nodes with
//! Code/Position cells, intra-file `defines` and `calls` edges. Cross-file
//! refs (imports, calls that bind to another module) are recorded as
//! `ImportStmt` / `CallSite` for the graph crate's cross-file resolver.
//!
//! `export …` wrappers are unwrapped transparently — `export class Foo {}`
//! produces the same node shape as `class Foo {}`.
//!
//! `const foo = () => {...}` and `const foo = function(){...}` are treated as
//! top-level Function nodes identical to `function foo() {}`.
//!
//! All code-domain primitives live in `repo-graph-code-domain` and are
//! re-exported from this crate for convenience.

use std::collections::HashMap;

use repo_graph_core::{Cell, CellPayload, Confidence, Edge, Node, NodeId, RepoId};
use tree_sitter::{Node as TsNode, Parser};

pub use repo_graph_code_domain::{
    CallQualifier, CallSite, CodeNav, FileParse, GRAPH_TYPE, ImportStmt, ImportTarget, ParseError,
    cell_type, edge_category, node_kind,
};

/// Parse one TypeScript source file.
///
/// `module_qname` is the module path in `::` form (e.g. `src::users::service`).
/// `file_rel_path` is the repo-relative file path stored in position cells.
pub fn parse_file(
    source: &str,
    file_rel_path: &str,
    module_qname: &str,
    repo: RepoId,
) -> Result<FileParse, ParseError> {
    let mut parser = Parser::new();
    let lang: tree_sitter::Language = tree_sitter_typescript::LANGUAGE_TYPESCRIPT.into();
    parser
        .set_language(&lang)
        .map_err(|e| ParseError::LanguageInit(e.to_string()))?;
    let tree = parser.parse(source, None).ok_or(ParseError::NoTree)?;
    let src = source.as_bytes();

    let mut acc = Acc {
        file_rel: file_rel_path.to_string(),
        repo: Some(repo),
        ..Acc::default()
    };
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
        visit_top(child, src, file_rel_path, module_qname, module_id, repo, &mut acc);
    }

    resolve_intra_file(acc)
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
    endpoints: Vec<EndpointCandidate>,
    module_functions: HashMap<String, NodeId>,
    class_methods: HashMap<(NodeId, String), NodeId>,
    nav: CodeNav,
    /// Stashed at parse_file entry so endpoint emission can stamp position
    /// cells without threading `file_rel` through every call_collection helper.
    file_rel: String,
    repo: Option<RepoId>,
}

struct UnresolvedCall {
    from: NodeId,
    enclosing_class: Option<NodeId>,
    qualifier: CallQualifier,
}

/// An HTTP-call shape detected during the call walk. Resolved into an Endpoint
/// node + CALLS edge in `resolve_intra_file` once the import-alias set is known.
struct EndpointCandidate {
    from: NodeId,
    method: String,
    path: String,
    confidence: Confidence,
    file_rel: String,
    line: usize,
    col: usize,
    /// Some(name) means this candidate only emits if `name` is a module-level
    /// import alias (shape 2: `axios.get(url)`). None = always emit (shape 1
    /// `this.x.method()` and shape 3 `fetch()`).
    requires_import_alias: Option<String>,
}

// ============================================================================
// Top-level dispatch
// ============================================================================

#[allow(clippy::too_many_arguments)]
fn visit_top(
    n: TsNode,
    src: &[u8],
    file_rel: &str,
    module_qname: &str,
    module_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    match n.kind() {
        "import_statement" => collect_import(n, src, module_qname, acc),
        "export_statement" => {
            if let Some(decl) = n.child_by_field_name("declaration") {
                visit_top(decl, src, file_rel, module_qname, module_id, repo, acc);
            }
        }
        "class_declaration" => {
            visit_class(n, src, file_rel, module_qname, module_id, repo, acc);
        }
        "interface_declaration" => {
            visit_interface(n, src, file_rel, module_qname, module_id, repo, acc);
        }
        "function_declaration" => {
            visit_function_decl(n, src, file_rel, module_qname, module_id, repo, acc);
        }
        "lexical_declaration" | "variable_declaration" => {
            visit_lexical(n, src, file_rel, module_qname, module_id, repo, acc);
        }
        "expression_statement" => {
            // Top-level calls — record with module as source.
            collect_calls_in(n, src, module_id, None, acc);
        }
        _ => {}
    }
}

// ============================================================================
// Visitors
// ============================================================================

#[allow(clippy::too_many_arguments)]
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
        if member.kind() == "method_definition" {
            visit_method(member, src, file_rel, &class_qname, class_id, repo, acc);
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn visit_interface(
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
    let iface_qname = format!("{module_qname}::{name}");
    let iface_id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::INTERFACE, &iface_qname);
    acc.nodes.push(Node {
        id: iface_id,
        repo,
        confidence: Confidence::Strong,
        cells: build_cells(&n, src, file_rel),
    });
    acc.edges.push(Edge {
        from: module_id,
        to: iface_id,
        category: edge_category::DEFINES,
        confidence: Confidence::Strong,
    });
    acc.nav.record(
        iface_id,
        name,
        &iface_qname,
        node_kind::INTERFACE,
        Some(module_id),
    );
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
    acc.nav.record(
        method_id,
        name,
        &method_qname,
        node_kind::METHOD,
        Some(class_id),
    );

    if let Some(body) = n.child_by_field_name("body") {
        collect_calls_in(body, src, method_id, Some(class_id), acc);
    }
}

#[allow(clippy::too_many_arguments)]
fn visit_function_decl(
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
    emit_function(n, name, src, file_rel, module_qname, module_id, repo, acc);
}

#[allow(clippy::too_many_arguments)]
fn visit_lexical(
    n: TsNode,
    src: &[u8],
    file_rel: &str,
    module_qname: &str,
    module_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    // `const foo = () => {...}` or `const foo = function(){...}` are hoisted
    // to Function nodes. Other const/let bindings are data, not behaviour.
    let mut cursor = n.walk();
    for declarator in n.named_children(&mut cursor) {
        if declarator.kind() != "variable_declarator" {
            continue;
        }
        let Some(value) = declarator.child_by_field_name("value") else {
            continue;
        };
        if !matches!(value.kind(), "arrow_function" | "function_expression") {
            continue;
        }
        let Some(name_n) = declarator.child_by_field_name("name") else {
            continue;
        };
        if name_n.kind() != "identifier" {
            continue;
        }
        let name = text(name_n, src);
        emit_function_value(
            value, name, src, file_rel, module_qname, module_id, repo, acc,
        );
    }
}

#[allow(clippy::too_many_arguments)]
fn emit_function(
    n: TsNode,
    name: &str,
    src: &[u8],
    file_rel: &str,
    module_qname: &str,
    module_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    let func_qname = format!("{module_qname}::{name}");
    let func_id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::FUNCTION, &func_qname);
    acc.nodes.push(Node {
        id: func_id,
        repo,
        confidence: Confidence::Strong,
        cells: build_cells(&n, src, file_rel),
    });
    acc.edges.push(Edge {
        from: module_id,
        to: func_id,
        category: edge_category::DEFINES,
        confidence: Confidence::Strong,
    });
    acc.module_functions.insert(name.to_string(), func_id);
    acc.nav.record(
        func_id,
        name,
        &func_qname,
        node_kind::FUNCTION,
        Some(module_id),
    );

    if let Some(body) = n.child_by_field_name("body") {
        collect_calls_in(body, src, func_id, None, acc);
    }
}

#[allow(clippy::too_many_arguments)]
fn emit_function_value(
    value: TsNode,
    name: &str,
    src: &[u8],
    file_rel: &str,
    module_qname: &str,
    module_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    let func_qname = format!("{module_qname}::{name}");
    let func_id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::FUNCTION, &func_qname);
    acc.nodes.push(Node {
        id: func_id,
        repo,
        confidence: Confidence::Strong,
        cells: build_cells(&value, src, file_rel),
    });
    acc.edges.push(Edge {
        from: module_id,
        to: func_id,
        category: edge_category::DEFINES,
        confidence: Confidence::Strong,
    });
    acc.module_functions.insert(name.to_string(), func_id);
    acc.nav.record(
        func_id,
        name,
        &func_qname,
        node_kind::FUNCTION,
        Some(module_id),
    );

    if let Some(body) = value.child_by_field_name("body") {
        collect_calls_in(body, src, func_id, None, acc);
    }
}

// ============================================================================
// Imports
// ============================================================================

fn collect_import(n: TsNode, src: &[u8], from_module: &str, acc: &mut Acc) {
    let Some(source_node) = n.child_by_field_name("source") else {
        return;
    };
    let source = strip_string_quotes(text(source_node, src));

    let mut cursor = n.walk();
    let clause = n
        .named_children(&mut cursor)
        .find(|c| c.kind() == "import_clause");

    let Some(clause) = clause else {
        // Side-effect import: `import "polyfill";`
        acc.imports.push(ImportStmt {
            from_module: from_module.to_string(),
            target: ImportTarget::Module {
                path: source,
                alias: None,
            },
        });
        return;
    };

    let mut cursor2 = clause.walk();
    for part in clause.named_children(&mut cursor2) {
        match part.kind() {
            "identifier" => {
                // `import Foo from "src"` — default import.
                acc.imports.push(ImportStmt {
                    from_module: from_module.to_string(),
                    target: ImportTarget::Symbol {
                        module: source.clone(),
                        name: "default".to_string(),
                        alias: Some(text(part, src).to_string()),
                        level: 0,
                    },
                });
            }
            "namespace_import" => {
                // `import * as Foo from "src"`
                let mut ns_cursor = part.walk();
                if let Some(id) = part.named_children(&mut ns_cursor).next()
                    && id.kind() == "identifier"
                {
                    acc.imports.push(ImportStmt {
                        from_module: from_module.to_string(),
                        target: ImportTarget::Module {
                            path: source.clone(),
                            alias: Some(text(id, src).to_string()),
                        },
                    });
                }
            }
            "named_imports" => {
                // `import { a, b as c } from "src"`
                let mut ni_cursor = part.walk();
                for spec in part.named_children(&mut ni_cursor) {
                    if spec.kind() != "import_specifier" {
                        continue;
                    }
                    let Some(name_node) = spec.child_by_field_name("name") else {
                        continue;
                    };
                    let name = text(name_node, src).to_string();
                    let alias = spec
                        .child_by_field_name("alias")
                        .map(|a| text(a, src).to_string());
                    acc.imports.push(ImportStmt {
                        from_module: from_module.to_string(),
                        target: ImportTarget::Symbol {
                            module: source.clone(),
                            name,
                            alias,
                            level: 0,
                        },
                    });
                }
            }
            _ => {}
        }
    }
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
        // Nested fn/class bodies own their own from-node — walked separately.
        if matches!(
            kind,
            "function_declaration"
                | "function_expression"
                | "arrow_function"
                | "method_definition"
                | "class_declaration"
                | "class_expression"
        ) {
            continue;
        }
        if kind == "call_expression" {
            if let Some(q) = extract_call_qualifier(node, src) {
                acc.unresolved.push(UnresolvedCall {
                    from,
                    enclosing_class,
                    qualifier: q,
                });
            }
            try_detect_endpoint(node, src, from, acc);
        }
        let mut cursor = node.walk();
        for child in node.named_children(&mut cursor) {
            stack.push(child);
        }
    }
}

// ============================================================================
// Endpoint extraction (v0.4.4)
// ============================================================================
//
// Three call shapes get classified as HTTP endpoint hits:
//   1. `this.<x>.<method>(<first>, …)`  — Angular HttpClient via DI and any
//      service-with-HTTP-client-field pattern. Always emit (no import check).
//   2. `<x>.<method>(<first>, …)` where `<x>` is a module-level import alias
//      — direct axios/got/ky calls.
//   3. `fetch(<first>, <opts>?)` — built-in. Method defaults to GET unless
//      `opts` carries `method: '...'`.
//
// Path is classified into a Confidence:
//   - String literal                                        → Strong
//   - Template with only static parts                       → Strong
//   - Template with interpolations                          → Medium (path
//     keeps literal prefix + `${…}` placeholders)
//   - Call expression (URL-builder wrapper) — pluck inner   → Weak
//     literal as hint
//   - Anything else (identifier, conditional, …)            → Weak,
//     path = `<unresolved>`
//
// Method/path normalisation (e.g. `:id` ↔ `{id}`) is HttpStackResolver's job;
// the parser stores the raw text as written.

const HTTP_METHOD_PROPS: &[&str] = &["get", "post", "put", "delete", "patch", "head", "options"];

fn try_detect_endpoint(call: TsNode, src: &[u8], from: NodeId, acc: &mut Acc) {
    let func = match call.child_by_field_name("function") {
        Some(f) => f,
        None => return,
    };

    // Shape 3 — `fetch(...)`.
    if func.kind() == "identifier" && text(func, src) == "fetch" {
        let args = match call.child_by_field_name("arguments") {
            Some(a) => a,
            None => return,
        };
        let first = match args.named_child(0) {
            Some(n) => n,
            None => return,
        };
        let (path, mut conf) = classify_path_arg(first, src);
        let method = fetch_method_from_opts(args.named_child(1), src).unwrap_or_else(|| {
            // Method override is opaque (variable, spread, conditional) — drop
            // confidence one tier.
            if args.named_child(1).is_some() {
                conf = downgrade(conf);
            }
            "GET".to_string()
        });
        push_endpoint(call, from, method, path, conf, None, acc);
        return;
    }

    // Shapes 1 & 2 — member call `<obj>.<method>(...)`.
    if func.kind() != "member_expression" {
        return;
    }
    let prop = match func.child_by_field_name("property") {
        Some(p) => p,
        None => return,
    };
    let method_lower = text(prop, src);
    if !HTTP_METHOD_PROPS.contains(&method_lower) {
        return;
    }
    let object = match func.child_by_field_name("object") {
        Some(o) => o,
        None => return,
    };

    // Shape 1: this.<x>.<method>(...) — object is itself a member_expression
    // whose object is `this`.
    let requires_alias = match object.kind() {
        "member_expression" => {
            let inner_obj = match object.child_by_field_name("object") {
                Some(o) => o,
                None => return,
            };
            if inner_obj.kind() != "this" {
                return;
            }
            None
        }
        // Shape 2: <alias>.<method>(...) — object is a plain identifier that
        // must be a module-level import alias. Validation happens in
        // resolve_intra_file once all imports are known.
        "identifier" => Some(text(object, src).to_string()),
        _ => return,
    };

    let args = match call.child_by_field_name("arguments") {
        Some(a) => a,
        None => return,
    };
    let first = match args.named_child(0) {
        Some(n) => n,
        None => return,
    };
    let (path, conf) = classify_path_arg(first, src);
    push_endpoint(
        call,
        from,
        method_lower.to_uppercase(),
        path,
        conf,
        requires_alias,
        acc,
    );
}

fn push_endpoint(
    call: TsNode,
    from: NodeId,
    method: String,
    path: String,
    confidence: Confidence,
    requires_import_alias: Option<String>,
    acc: &mut Acc,
) {
    let start = call.start_position();
    acc.endpoints.push(EndpointCandidate {
        from,
        method,
        path,
        confidence,
        file_rel: acc.file_rel.clone(),
        line: start.row + 1,
        col: start.column + 1,
        requires_import_alias,
    });
}

fn classify_path_arg(arg: TsNode, src: &[u8]) -> (String, Confidence) {
    match arg.kind() {
        "string" => {
            let raw = text(arg, src);
            (strip_string_quotes(raw), Confidence::Strong)
        }
        "template_string" => classify_template(arg, src),
        "call_expression" => {
            // URL-builder wrapper like `this.api.buildUrl('auth/login')` —
            // pluck the innermost string literal as a hint, weak confidence.
            (
                find_first_string_literal(arg, src)
                    .map(|s| strip_string_quotes(&s))
                    .unwrap_or_else(|| "<unresolved>".to_string()),
                Confidence::Weak,
            )
        }
        _ => ("<unresolved>".to_string(), Confidence::Weak),
    }
}

fn classify_template(template: TsNode, src: &[u8]) -> (String, Confidence) {
    let mut out = String::new();
    let mut has_subst = false;
    let mut cursor = template.walk();
    for child in template.named_children(&mut cursor) {
        match child.kind() {
            "template_substitution" => {
                has_subst = true;
                out.push_str("${…}");
            }
            "string_fragment" => out.push_str(text(child, src)),
            _ => {}
        }
    }
    if !has_subst && out.is_empty() {
        // Empty backticks `` `` `` — treat as Strong empty path.
        return (String::new(), Confidence::Strong);
    }
    (
        out,
        if has_subst {
            Confidence::Medium
        } else {
            Confidence::Strong
        },
    )
}

fn find_first_string_literal(n: TsNode, src: &[u8]) -> Option<String> {
    let mut stack = vec![n];
    while let Some(node) = stack.pop() {
        if node.kind() == "string" {
            return Some(text(node, src).to_string());
        }
        let mut cursor = node.walk();
        for child in node.named_children(&mut cursor) {
            stack.push(child);
        }
    }
    None
}

/// `fetch(url, { method: 'POST', … })` — pluck a string-literal `method:` value
/// from the second-arg object literal. Returns None if the second arg isn't a
/// plain object or the method value isn't a string literal.
fn fetch_method_from_opts(opts: Option<TsNode>, src: &[u8]) -> Option<String> {
    let opts = opts?;
    if opts.kind() != "object" {
        return None;
    }
    let mut cursor = opts.walk();
    for prop in opts.named_children(&mut cursor) {
        if prop.kind() != "pair" {
            continue;
        }
        let key = prop.child_by_field_name("key")?;
        let key_text = match key.kind() {
            "property_identifier" => text(key, src),
            "string" => {
                let raw = text(key, src);
                if raw.len() >= 2 {
                    &raw[1..raw.len() - 1]
                } else {
                    raw
                }
            }
            _ => continue,
        };
        if key_text != "method" {
            continue;
        }
        let value = prop.child_by_field_name("value")?;
        if value.kind() != "string" {
            return None;
        }
        return Some(strip_string_quotes(text(value, src)).to_uppercase());
    }
    None
}

fn downgrade(c: Confidence) -> Confidence {
    match c {
        Confidence::Strong => Confidence::Medium,
        Confidence::Medium => Confidence::Weak,
        Confidence::Weak => Confidence::Weak,
    }
}

fn endpoint_hit_cell(
    method: &str,
    path: &str,
    file_rel: &str,
    line: usize,
    col: usize,
    confidence: Confidence,
) -> Cell {
    #[derive(serde::Serialize)]
    struct Payload<'a> {
        method: &'a str,
        path: &'a str,
        file: &'a str,
        line: usize,
        col: usize,
        confidence: &'a str,
    }
    let conf_str = match confidence {
        Confidence::Strong => "strong",
        Confidence::Medium => "medium",
        Confidence::Weak => "weak",
    };
    let json = serde_json::to_string(&Payload {
        method,
        path,
        file: file_rel,
        line,
        col,
        confidence: conf_str,
    })
    .unwrap_or_else(|_| String::from("{}"));
    Cell {
        kind: cell_type::ENDPOINT_HIT,
        payload: CellPayload::Json(json),
    }
}

fn extract_call_qualifier(call: TsNode, src: &[u8]) -> Option<CallQualifier> {
    let func = call.child_by_field_name("function")?;
    match func.kind() {
        "identifier" => Some(CallQualifier::Bare(text(func, src).to_string())),
        "member_expression" => {
            let object = func.child_by_field_name("object")?;
            let prop = func.child_by_field_name("property")?;
            let name = text(prop, src).to_string();
            match object.kind() {
                "this" => Some(CallQualifier::SelfMethod(name)),
                "identifier" => Some(CallQualifier::Attribute {
                    base: text(object, src).to_string(),
                    name,
                }),
                _ => Some(CallQualifier::ComplexReceiver {
                    receiver: text(object, src).to_string(),
                    name,
                }),
            }
        }
        _ => None,
    }
}

// ============================================================================
// Intra-file resolution
// ============================================================================

fn resolve_intra_file(mut acc: Acc) -> Result<FileParse, ParseError> {
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

    // Endpoint emission. Build the import-alias set from `out.imports` so
    // shape-2 candidates (`axios.get(url)`) can be filtered to only those
    // whose base is a real module-level binding.
    let alias_set = build_alias_set(&out.imports);
    let mut endpoint_nav_seen: std::collections::HashSet<NodeId> =
        std::collections::HashSet::new();
    let repo = acc.repo.expect("Acc.repo set in parse_file");
    for cand in acc.endpoints {
        if let Some(req) = cand.requires_import_alias.as_ref()
            && !alias_set.contains(req.as_str())
        {
            continue;
        }
        let qname = format!("endpoint:{}:{}", cand.method, cand.path);
        let endpoint_id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::ENDPOINT, &qname);
        let cell = endpoint_hit_cell(
            &cand.method,
            &cand.path,
            &cand.file_rel,
            cand.line,
            cand.col,
            cand.confidence,
        );
        out.nodes.push(Node {
            id: endpoint_id,
            repo,
            confidence: cand.confidence,
            cells: vec![cell],
        });
        if endpoint_nav_seen.insert(endpoint_id) {
            let display = format!("{} {}", cand.method, cand.path);
            out.nav
                .record(endpoint_id, &display, &qname, node_kind::ENDPOINT, None);
        }
        out.edges.push(Edge {
            from: cand.from,
            to: endpoint_id,
            category: edge_category::CALLS,
            confidence: cand.confidence,
        });
    }

    Ok(out)
}

fn build_alias_set(imports: &[ImportStmt]) -> std::collections::HashSet<&str> {
    let mut set = std::collections::HashSet::new();
    for imp in imports {
        match &imp.target {
            ImportTarget::Module {
                alias: Some(a), ..
            } => {
                set.insert(a.as_str());
            }
            ImportTarget::Symbol {
                name,
                alias: Some(a),
                ..
            } => {
                set.insert(a.as_str());
                // For default imports (alias is the binding, name="default"),
                // also keep `name` if useful — skipped to avoid false positives.
                let _ = name;
            }
            ImportTarget::Symbol {
                name, alias: None, ..
            } => {
                set.insert(name.as_str());
            }
            _ => {}
        }
    }
    set
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
    vec![code, pos]
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

fn strip_string_quotes(s: &str) -> String {
    let t = s.trim();
    if t.len() >= 2
        && ((t.starts_with('"') && t.ends_with('"'))
            || (t.starts_with('\'') && t.ends_with('\''))
            || (t.starts_with('`') && t.ends_with('`')))
    {
        t[1..t.len() - 1].to_string()
    } else {
        t.to_string()
    }
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
        RepoId::from_canonical("test://ts_smoke")
    }

    fn has_edge(parse: &FileParse, from: NodeId, to: NodeId, cat: EdgeCategoryId) -> bool {
        parse
            .edges
            .iter()
            .any(|e| e.from == from && e.to == to && e.category == cat)
    }

    #[test]
    fn parses_module_with_function_decl_and_arrow_const() {
        let src = "\
function greet(name: string): string {
    return hello(name);
}

const hello = (n: string) => `hi ${n}`;
";
        let parse = parse_file(src, "src/greet.ts", "src::greet", repo()).unwrap();

        let module_id = NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::MODULE, "src::greet");
        let greet_id = NodeId::from_parts(
            GRAPH_TYPE,
            repo(),
            node_kind::FUNCTION,
            "src::greet::greet",
        );
        let hello_id = NodeId::from_parts(
            GRAPH_TYPE,
            repo(),
            node_kind::FUNCTION,
            "src::greet::hello",
        );

        assert!(parse.nodes.iter().any(|n| n.id == module_id));
        assert!(parse.nodes.iter().any(|n| n.id == greet_id));
        assert!(
            parse.nodes.iter().any(|n| n.id == hello_id),
            "arrow const should be hoisted to a Function node"
        );

        assert!(has_edge(&parse, module_id, greet_id, edge_category::DEFINES));
        assert!(has_edge(&parse, module_id, hello_id, edge_category::DEFINES));

        // Intra-file bare call: greet → hello
        assert!(
            has_edge(&parse, greet_id, hello_id, edge_category::CALLS),
            "expected bare call to resolve intra-file, calls: {:?}",
            parse.calls
        );
    }

    #[test]
    fn parses_class_methods_and_this_call() {
        let src = "\
export class User {
    login(password: string): boolean {
        return hashPassword(password).length > 0;
    }

    save(): void {
        this.login(\"x\");
    }
}
";
        let parse = parse_file(src, "src/user.ts", "src::user", repo()).unwrap();

        let mod_id = NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::MODULE, "src::user");
        let class_id =
            NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::CLASS, "src::user::User");
        let login_id = NodeId::from_parts(
            GRAPH_TYPE,
            repo(),
            node_kind::METHOD,
            "src::user::User::login",
        );
        let save_id = NodeId::from_parts(
            GRAPH_TYPE,
            repo(),
            node_kind::METHOD,
            "src::user::User::save",
        );

        assert!(parse.nodes.iter().any(|n| n.id == class_id));
        assert!(parse.nodes.iter().any(|n| n.id == login_id));
        assert!(parse.nodes.iter().any(|n| n.id == save_id));

        assert!(has_edge(&parse, mod_id, class_id, edge_category::DEFINES));
        assert!(has_edge(&parse, class_id, login_id, edge_category::DEFINES));
        assert!(has_edge(&parse, class_id, save_id, edge_category::DEFINES));

        // this.login() inside save resolves to User::login.
        assert!(
            has_edge(&parse, save_id, login_id, edge_category::CALLS),
            "this.login should resolve to User::login"
        );

        // hashPassword() inside login — cross-file, stays unresolved.
        assert!(
            parse.calls.iter().any(|c| c.from == login_id
                && matches!(&c.qualifier, CallQualifier::Bare(n) if n == "hashPassword")),
            "hashPassword should be unresolved, got: {:?}",
            parse.calls
        );
    }

    #[test]
    fn collects_all_import_shapes() {
        let src = "\
import \"./polyfill\";
import Default from \"./default-src\";
import * as ns from \"./ns-src\";
import { a, b as c } from \"./named-src\";
import { UserService } from \"@angular/core\";
";
        let parse = parse_file(src, "src/index.ts", "src::index", repo()).unwrap();

        // Side-effect import — module path, no alias.
        assert!(
            parse.imports.iter().any(|i| matches!(
                &i.target,
                ImportTarget::Module { path, alias: None } if path == "./polyfill"
            )),
            "side-effect import missing"
        );

        // Default import — symbol named "default" with alias.
        assert!(parse.imports.iter().any(|i| matches!(
            &i.target,
            ImportTarget::Symbol { module, name, alias: Some(a), level: 0 }
                if module == "./default-src" && name == "default" && a == "Default"
        )));

        // Namespace import — module with alias.
        assert!(parse.imports.iter().any(|i| matches!(
            &i.target,
            ImportTarget::Module { path, alias: Some(a) }
                if path == "./ns-src" && a == "ns"
        )));

        // Named, plain `a`.
        assert!(parse.imports.iter().any(|i| matches!(
            &i.target,
            ImportTarget::Symbol { module, name, alias: None, level: 0 }
                if module == "./named-src" && name == "a"
        )));

        // Named with alias, `b as c`.
        assert!(parse.imports.iter().any(|i| matches!(
            &i.target,
            ImportTarget::Symbol { module, name, alias: Some(a), level: 0 }
                if module == "./named-src" && name == "b" && a == "c"
        )));

        // Bare-module import (no leading dot).
        assert!(parse.imports.iter().any(|i| matches!(
            &i.target,
            ImportTarget::Symbol { module, name, .. }
                if module == "@angular/core" && name == "UserService"
        )));
    }

    #[test]
    fn interface_and_attribute_call_unresolved() {
        let src = "\
interface Greeter {
    hello(name: string): string;
}

export function doGreet(g: Greeter) {
    return g.hello(\"x\");
}
";
        let parse = parse_file(src, "src/g.ts", "src::g", repo()).unwrap();

        let iface_id =
            NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::INTERFACE, "src::g::Greeter");
        let fn_id = NodeId::from_parts(
            GRAPH_TYPE,
            repo(),
            node_kind::FUNCTION,
            "src::g::doGreet",
        );

        assert!(
            parse.nodes.iter().any(|n| n.id == iface_id),
            "interface node missing"
        );
        assert!(parse.nodes.iter().any(|n| n.id == fn_id));

        // g.hello(...) is an Attribute-qualified call — unresolved at parse time.
        assert!(
            parse.calls.iter().any(|c| c.from == fn_id
                && matches!(
                    &c.qualifier,
                    CallQualifier::Attribute { base, name } if base == "g" && name == "hello"
                )),
            "attribute call missing, got: {:?}",
            parse.calls
        );
    }

    #[test]
    fn syntax_error_produces_partial_graph() {
        // tree-sitter's error recovery still yields the valid top-level function.
        let src = "function ok(): void {}\n\nthis is !!! not typescript\n";
        let parse = parse_file(src, "broken.ts", "broken", repo()).unwrap();
        let ok_id = NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::FUNCTION, "broken::ok");
        assert!(parse.nodes.iter().any(|n| n.id == ok_id));
    }

    // ========================================================================
    // Endpoint extraction (v0.4.4)
    // ========================================================================

    fn endpoint_id(repo: RepoId, method: &str, path: &str) -> NodeId {
        NodeId::from_parts(
            GRAPH_TYPE,
            repo,
            node_kind::ENDPOINT,
            &format!("endpoint:{method}:{path}"),
        )
    }

    fn endpoint_payloads(parse: &FileParse, ep: NodeId) -> Vec<serde_json::Value> {
        parse
            .nodes
            .iter()
            .filter(|n| n.id == ep)
            .flat_map(|n| n.cells.iter())
            .filter(|c| c.kind == cell_type::ENDPOINT_HIT)
            .filter_map(|c| match &c.payload {
                CellPayload::Json(s) => serde_json::from_str(s).ok(),
                _ => None,
            })
            .collect()
    }

    #[test]
    fn this_http_post_string_literal_emits_strong_endpoint() {
        let src = "\
export class AuthService {
    constructor(private readonly http: any) {}
    login(payload: any): void {
        this.http.post('/api/auth/login', payload);
    }
}
";
        let parse = parse_file(src, "src/auth.service.ts", "src::auth::service", repo()).unwrap();

        let ep = endpoint_id(repo(), "POST", "/api/auth/login");
        let login_id = NodeId::from_parts(
            GRAPH_TYPE,
            repo(),
            node_kind::METHOD,
            "src::auth::service::AuthService::login",
        );

        assert!(
            parse.nodes.iter().any(|n| n.id == ep),
            "endpoint node missing"
        );
        assert!(
            parse
                .nodes
                .iter()
                .find(|n| n.id == ep)
                .map(|n| n.confidence == Confidence::Strong)
                .unwrap_or(false),
            "string literal arg should emit Strong endpoint"
        );
        assert!(
            has_edge(&parse, login_id, ep, edge_category::CALLS),
            "expected CALLS edge from login method to endpoint"
        );

        let payloads = endpoint_payloads(&parse, ep);
        assert_eq!(payloads.len(), 1);
        assert_eq!(payloads[0]["method"], "POST");
        assert_eq!(payloads[0]["path"], "/api/auth/login");
        assert_eq!(payloads[0]["confidence"], "strong");
    }

    #[test]
    fn fetch_defaults_to_get_unless_method_overridden() {
        let src = "\
function loadUsers(): void {
    fetch('/api/users');
    fetch('/api/users', { method: 'POST' });
}
";
        let parse = parse_file(src, "src/loader.ts", "src::loader", repo()).unwrap();

        let get_ep = endpoint_id(repo(), "GET", "/api/users");
        let post_ep = endpoint_id(repo(), "POST", "/api/users");

        assert!(parse.nodes.iter().any(|n| n.id == get_ep), "GET missing");
        assert!(
            parse.nodes.iter().any(|n| n.id == post_ep),
            "POST override missing"
        );
    }

    #[test]
    fn axios_get_only_emits_when_axios_imported() {
        // With import — emits.
        let with_import = "\
import axios from 'axios';
export function loadHealth(): void {
    axios.get('/health');
}
";
        let parse = parse_file(with_import, "src/h.ts", "src::h", repo()).unwrap();
        assert!(
            parse
                .nodes
                .iter()
                .any(|n| n.id == endpoint_id(repo(), "GET", "/health")),
            "axios.get with import should emit endpoint"
        );

        // Without import — `axios` could be a local variable; skip.
        let without_import = "\
export function loadHealth(axios: any): void {
    axios.get('/health');
}
";
        let parse2 = parse_file(without_import, "src/h2.ts", "src::h2", repo()).unwrap();
        assert!(
            !parse2
                .nodes
                .iter()
                .any(|n| n.id == endpoint_id(repo(), "GET", "/health")),
            "axios.get without import should be skipped (could be a local)"
        );
    }

    #[test]
    fn template_with_interpolation_emits_medium_with_placeholder_path() {
        let src = "\
export class UserService {
    constructor(private readonly http: any) {}
    show(id: string): void {
        this.http.get(`/api/users/${id}`);
    }
}
";
        let parse = parse_file(src, "src/user.service.ts", "src::user::service", repo()).unwrap();

        let ep = endpoint_id(repo(), "GET", "/api/users/${…}");
        assert!(
            parse.nodes.iter().any(|n| n.id == ep),
            "templated endpoint with placeholder missing"
        );
        let node = parse.nodes.iter().find(|n| n.id == ep).unwrap();
        assert_eq!(node.confidence, Confidence::Medium);
    }

    #[test]
    fn url_builder_wrapper_pluck_inner_literal_weak() {
        let src = "\
export class AuthService {
    constructor(private readonly http: any, private readonly api: any) {}
    login(payload: any): void {
        this.http.post(this.api.buildApiUrl('auth/login'), payload);
    }
}
";
        let parse = parse_file(src, "src/auth.ts", "src::auth", repo()).unwrap();

        // Inner literal 'auth/login' becomes the path hint, Weak confidence.
        let ep = endpoint_id(repo(), "POST", "auth/login");
        assert!(
            parse.nodes.iter().any(|n| n.id == ep),
            "URL-builder wrapped endpoint missing"
        );
        let node = parse.nodes.iter().find(|n| n.id == ep).unwrap();
        assert_eq!(node.confidence, Confidence::Weak);
    }

    #[test]
    fn multiple_callsites_same_method_path_collapse_with_stacked_cells() {
        let src = "\
export class HealthService {
    constructor(private readonly http: any) {}
    pollA(): void { this.http.get('/api/health'); }
    pollB(): void { this.http.get('/api/health'); }
}
";
        let parse =
            parse_file(src, "src/health.service.ts", "src::health::service", repo()).unwrap();

        let ep = endpoint_id(repo(), "GET", "/api/health");
        // Parser emits two Node entries — graph-build merges them into one with
        // two stacked cells.
        let occurrences = parse.nodes.iter().filter(|n| n.id == ep).count();
        assert_eq!(occurrences, 2, "expected 2 Node emissions for same endpoint");
        let payloads = endpoint_payloads(&parse, ep);
        assert_eq!(payloads.len(), 2, "expected 2 ENDPOINT_HIT cells");
    }
}
