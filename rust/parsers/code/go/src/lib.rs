//! repo-graph-parser-go — tree-sitter Go → code-domain FileParse.
//!
//! Single-file scan. A Go package spans multiple files; `parse_file` emits a
//! Module node per file with the package's NodeId and one Code+Position cell.
//! The graph crate deduplicates the Module by NodeId at build time and the
//! cells from all files stack up on the single Module node (multicellular).
//!
//! Emits:
//! - Module (one per file, collapses on same NodeId at graph build)
//! - Struct / Interface (type declarations)
//! - Function (top-level `func` without receiver)
//! - Method (`func (r T) m()` — qname `pkg::T::m`, parent is the struct)
//!
//! Cross-file references recorded as `ImportStmt` and `CallSite` for the
//! resolver to wire up. All Go imports are `ImportTarget::Module` (Go has no
//! named symbol imports).

use std::collections::HashMap;

use repo_graph_core::{Cell, CellPayload, Confidence, Edge, Node, NodeId, RepoId};
use tree_sitter::{Node as TsNode, Parser};

pub use repo_graph_code_domain::{
    CallQualifier, CallSite, CodeNav, FileParse, GRAPH_TYPE, ImportStmt, ImportTarget, ParseError,
    cell_type, edge_category, node_kind,
};

// ============================================================================
// Public entry point
// ============================================================================

/// Parse one Go source file.
///
/// `package_qname` is the repo-local `::`-separated path for the package
/// (e.g. `svc::users` for `<repo>/svc/users/*.go`).
///
/// `module_import_prefix` is the `module` line from `go.mod` (e.g.
/// `github.com/foo/bar`) — used to map absolute Go import paths onto
/// repo-local qnames. Pass `""` for a packageless / single-file parse.
pub fn parse_file(
    source: &str,
    file_rel_path: &str,
    package_qname: &str,
    module_import_prefix: &str,
    repo: RepoId,
) -> Result<FileParse, ParseError> {
    let mut parser = Parser::new();
    let lang: tree_sitter::Language = tree_sitter_go::LANGUAGE.into();
    parser
        .set_language(&lang)
        .map_err(|e| ParseError::LanguageInit(e.to_string()))?;
    let tree = parser.parse(source, None).ok_or(ParseError::NoTree)?;
    let src = source.as_bytes();
    let root = tree.root_node();

    let mut acc = Acc::default();

    // Module node (one per file — collapses at graph build via NodeId dedup).
    let module_id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::MODULE, package_qname);
    acc.nodes.push(Node {
        id: module_id,
        repo,
        confidence: Confidence::Strong,
        cells: file_cells(&root, src, file_rel_path),
    });
    let module_simple = package_qname
        .rsplit("::")
        .next()
        .unwrap_or(package_qname);
    acc.nav
        .record(module_id, module_simple, package_qname, node_kind::MODULE, None);

    // Struct/interface name → NodeId map for this file. Populated in a first
    // pass so method declarations can attach to their receiver struct.
    let mut type_ids: HashMap<String, NodeId> = HashMap::new();

    // First pass: types. Go allows methods to be declared before their
    // receiver struct lexically, so collecting types up front is required.
    let mut cursor = root.walk();
    for child in root.named_children(&mut cursor) {
        if child.kind() == "type_declaration" {
            collect_types(
                child,
                src,
                file_rel_path,
                package_qname,
                module_id,
                repo,
                &mut acc,
                &mut type_ids,
            );
        }
    }

    // Second pass: everything else.
    let mut cursor = root.walk();
    for child in root.named_children(&mut cursor) {
        match child.kind() {
            "package_clause" => { /* already known; nothing to emit */ }
            "import_declaration" => {
                collect_imports(child, src, package_qname, module_import_prefix, &mut acc);
            }
            "function_declaration" => {
                visit_function(
                    child,
                    src,
                    file_rel_path,
                    package_qname,
                    module_id,
                    repo,
                    &mut acc,
                );
            }
            "method_declaration" => {
                visit_method(
                    child,
                    src,
                    file_rel_path,
                    package_qname,
                    repo,
                    &type_ids,
                    module_id,
                    &mut acc,
                );
            }
            "type_declaration" => { /* already collected in first pass */ }
            _ => {}
        }
    }

    Ok(FileParse {
        nodes: acc.nodes,
        edges: acc.edges,
        imports: acc.imports,
        calls: acc.calls,
        nav: acc.nav,
    })
}

// ============================================================================
// Accumulator
// ============================================================================

#[derive(Default)]
struct Acc {
    nodes: Vec<Node>,
    edges: Vec<Edge>,
    imports: Vec<ImportStmt>,
    calls: Vec<CallSite>,
    nav: CodeNav,
}

// ============================================================================
// Type declarations (struct + interface)
// ============================================================================

#[allow(clippy::too_many_arguments)]
fn collect_types(
    type_decl: TsNode,
    src: &[u8],
    file_rel: &str,
    package_qname: &str,
    module_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
    type_ids: &mut HashMap<String, NodeId>,
) {
    let mut cursor = type_decl.walk();
    for spec in type_decl.named_children(&mut cursor) {
        if spec.kind() != "type_spec" {
            continue;
        }
        let Some(name_node) = spec.child_by_field_name("name") else {
            continue;
        };
        let name = text_of(name_node, src).to_string();
        let qname = format!("{package_qname}::{name}");

        let Some(type_node) = spec.child_by_field_name("type") else {
            continue;
        };

        let kind = match type_node.kind() {
            "struct_type" => node_kind::STRUCT,
            "interface_type" => node_kind::INTERFACE,
            // Type aliases (`type Foo = Bar`) and non-struct/non-interface
            // types skipped for v0.4.3b.
            _ => continue,
        };

        let id = NodeId::from_parts(GRAPH_TYPE, repo, kind, &qname);
        acc.nodes.push(Node {
            id,
            repo,
            confidence: Confidence::Strong,
            cells: entity_cells(spec, src, file_rel),
        });
        acc.nav.record(id, &name, &qname, kind, Some(module_id));
        acc.edges.push(Edge {
            from: module_id,
            to: id,
            category: edge_category::DEFINES,
            confidence: Confidence::Strong,
        });
        type_ids.insert(name, id);
    }
}

// ============================================================================
// Function + method visitors
// ============================================================================

fn visit_function(
    decl: TsNode,
    src: &[u8],
    file_rel: &str,
    package_qname: &str,
    module_id: NodeId,
    repo: RepoId,
    acc: &mut Acc,
) {
    let Some(name_node) = decl.child_by_field_name("name") else {
        return;
    };
    let name = text_of(name_node, src).to_string();
    let qname = format!("{package_qname}::{name}");
    let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::FUNCTION, &qname);

    acc.nodes.push(Node {
        id,
        repo,
        confidence: Confidence::Strong,
        cells: entity_cells(decl, src, file_rel),
    });
    acc.nav
        .record(id, &name, &qname, node_kind::FUNCTION, Some(module_id));
    acc.edges.push(Edge {
        from: module_id,
        to: id,
        category: edge_category::DEFINES,
        confidence: Confidence::Strong,
    });

    if let Some(body) = decl.child_by_field_name("body") {
        collect_calls_in(body, src, id, None, acc);
    }
}

#[allow(clippy::too_many_arguments)]
fn visit_method(
    decl: TsNode,
    src: &[u8],
    file_rel: &str,
    package_qname: &str,
    repo: RepoId,
    type_ids: &HashMap<String, NodeId>,
    module_id: NodeId,
    acc: &mut Acc,
) {
    let Some(name_node) = decl.child_by_field_name("name") else {
        return;
    };
    let name = text_of(name_node, src).to_string();

    // Receiver: `(r *User)` — we want the receiver type name (User) and the
    // bound variable name (r). The type can be a pointer or bare identifier.
    let Some(receiver) = decl.child_by_field_name("receiver") else {
        return;
    };
    let (receiver_var, receiver_type) = parse_receiver(receiver, src);
    let Some(receiver_type) = receiver_type else {
        return;
    };

    // Parent: the struct this method belongs to. If we haven't seen it (could
    // be declared in another file of the same package), we still attach to the
    // module — the graph crate will rewire under the struct at build time via
    // class_methods lookup by qname.
    let parent_id = type_ids.get(&receiver_type).copied().unwrap_or(module_id);

    let qname = format!("{package_qname}::{receiver_type}::{name}");
    let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::METHOD, &qname);

    acc.nodes.push(Node {
        id,
        repo,
        confidence: Confidence::Strong,
        cells: entity_cells(decl, src, file_rel),
    });
    acc.nav
        .record(id, &name, &qname, node_kind::METHOD, Some(parent_id));
    acc.edges.push(Edge {
        from: parent_id,
        to: id,
        category: edge_category::DEFINES,
        confidence: Confidence::Strong,
    });

    if let Some(body) = decl.child_by_field_name("body") {
        collect_calls_in(body, src, id, receiver_var.as_deref(), acc);
    }
}

/// Pull the receiver variable name and type name out of a `parameter_list`
/// like `(r *User)`. Returns `(Some("r"), Some("User"))` — either may be None
/// for unusual receiver forms (e.g. bare `_` receiver).
fn parse_receiver(receiver: TsNode, src: &[u8]) -> (Option<String>, Option<String>) {
    // Receiver is a parameter_list with one parameter_declaration.
    let mut cursor = receiver.walk();
    for param in receiver.named_children(&mut cursor) {
        if param.kind() != "parameter_declaration" {
            continue;
        }
        let name = param
            .child_by_field_name("name")
            .map(|n| text_of(n, src).to_string());
        let type_node = param.child_by_field_name("type");
        let type_name = type_node.map(|t| extract_type_name(t, src));
        return (name, type_name);
    }
    (None, None)
}

/// Extract the bare type name from a type expression. Strips pointer (`*T`),
/// generic args (`T[U]`), package qualifier (`pkg.T`) down to just `T`.
fn extract_type_name(type_node: TsNode, src: &[u8]) -> String {
    match type_node.kind() {
        "pointer_type" => {
            let mut cursor = type_node.walk();
            if let Some(c) = type_node.named_children(&mut cursor).next() {
                return extract_type_name(c, src);
            }
            text_of(type_node, src).trim_start_matches('*').to_string()
        }
        "generic_type" => {
            if let Some(inner) = type_node.child_by_field_name("type") {
                extract_type_name(inner, src)
            } else {
                text_of(type_node, src).split('[').next().unwrap_or("").to_string()
            }
        }
        "qualified_type" => {
            // pkg.Name → take just the name side.
            if let Some(name) = type_node.child_by_field_name("name") {
                text_of(name, src).to_string()
            } else {
                text_of(type_node, src).rsplit('.').next().unwrap_or("").to_string()
            }
        }
        _ => text_of(type_node, src).to_string(),
    }
}

// ============================================================================
// Import collection
// ============================================================================

fn collect_imports(
    decl: TsNode,
    src: &[u8],
    package_qname: &str,
    module_import_prefix: &str,
    acc: &mut Acc,
) {
    // import_declaration may wrap an import_spec_list or a single import_spec.
    let mut cursor = decl.walk();
    for child in decl.named_children(&mut cursor) {
        match child.kind() {
            "import_spec" => {
                record_import(child, src, package_qname, module_import_prefix, acc);
            }
            "import_spec_list" => {
                let mut inner = child.walk();
                for spec in child.named_children(&mut inner) {
                    if spec.kind() == "import_spec" {
                        record_import(spec, src, package_qname, module_import_prefix, acc);
                    }
                }
            }
            _ => {}
        }
    }
}

fn record_import(
    spec: TsNode,
    src: &[u8],
    package_qname: &str,
    module_import_prefix: &str,
    acc: &mut Acc,
) {
    // import_spec children: optional name (alias) + path (interpreted_string_literal).
    let alias = spec
        .child_by_field_name("name")
        .map(|n| text_of(n, src).to_string());
    let Some(path_node) = spec.child_by_field_name("path") else {
        return;
    };
    // Strip the surrounding quotes.
    let raw = text_of(path_node, src);
    let path_str = raw.trim_matches('"').to_string();

    // If the import lies within the go.mod module, convert to repo-local qname.
    let qname = if !module_import_prefix.is_empty() && path_str.starts_with(module_import_prefix) {
        let rel = path_str.trim_start_matches(module_import_prefix).trim_start_matches('/');
        if rel.is_empty() {
            // `import "github.com/foo/bar"` with module == "github.com/foo/bar" —
            // degenerate; ignore.
            return;
        }
        rel.replace('/', "::")
    } else {
        // External import (stdlib or third-party). Keep the raw path for now;
        // cross-repo resolution is a v0.4.4 concern.
        path_str.replace('/', "::")
    };

    acc.imports.push(ImportStmt {
        from_module: package_qname.to_string(),
        target: ImportTarget::Module {
            path: qname,
            alias,
        },
    });
}

// ============================================================================
// Call collection
// ============================================================================

fn collect_calls_in(
    node: TsNode,
    src: &[u8],
    from: NodeId,
    receiver_var: Option<&str>,
    acc: &mut Acc,
) {
    let mut cursor = node.walk();
    for child in node.named_children(&mut cursor) {
        if child.kind() == "call_expression"
            && let Some(q) = classify_call(child, src, receiver_var)
        {
            acc.calls.push(CallSite {
                from,
                qualifier: q,
            });
        }
        if child.kind() != "func_literal" {
            collect_calls_in(child, src, from, receiver_var, acc);
        }
    }
}

fn classify_call(call: TsNode, src: &[u8], receiver_var: Option<&str>) -> Option<CallQualifier> {
    let func = call.child_by_field_name("function")?;
    match func.kind() {
        "identifier" => Some(CallQualifier::Bare(text_of(func, src).to_string())),
        "selector_expression" => {
            let operand = func.child_by_field_name("operand")?;
            let field = func.child_by_field_name("field")?;
            let name = text_of(field, src).to_string();
            match operand.kind() {
                "identifier" => {
                    let base = text_of(operand, src).to_string();
                    if Some(base.as_str()) == receiver_var {
                        Some(CallQualifier::SelfMethod(name))
                    } else {
                        Some(CallQualifier::Attribute { base, name })
                    }
                }
                _ => Some(CallQualifier::ComplexReceiver {
                    receiver: text_of(operand, src).to_string(),
                    name,
                }),
            }
        }
        _ => None,
    }
}

// ============================================================================
// Cell helpers
// ============================================================================

fn file_cells(root: &TsNode, src: &[u8], file_rel: &str) -> Vec<Cell> {
    vec![
        Cell {
            kind: cell_type::CODE,
            payload: CellPayload::Text(text_of(*root, src).to_string()),
        },
        position_cell(*root, file_rel),
    ]
}

fn entity_cells(node: TsNode, src: &[u8], file_rel: &str) -> Vec<Cell> {
    vec![
        Cell {
            kind: cell_type::CODE,
            payload: CellPayload::Text(text_of(node, src).to_string()),
        },
        position_cell(node, file_rel),
    ]
}

fn position_cell(node: TsNode, file_rel: &str) -> Cell {
    let start = node.start_position();
    let end = node.end_position();
    let json = format!(
        r#"{{"file":"{}","start_line":{},"end_line":{}}}"#,
        file_rel.replace('\\', "\\\\").replace('"', "\\\""),
        start.row + 1,
        end.row + 1
    );
    Cell {
        kind: cell_type::POSITION,
        payload: CellPayload::Json(json),
    }
}

fn text_of<'a>(node: TsNode, src: &'a [u8]) -> &'a str {
    std::str::from_utf8(&src[node.byte_range()]).unwrap_or("")
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use repo_graph_core::EdgeCategoryId;

    fn repo() -> RepoId {
        RepoId::from_canonical("test://go_smoke")
    }

    fn has_edge(parse: &FileParse, from: NodeId, to: NodeId, cat: EdgeCategoryId) -> bool {
        parse
            .edges
            .iter()
            .any(|e| e.from == from && e.to == to && e.category == cat)
    }

    const HELPERS: &str = r#"package helpers

func HashPassword(p string) string {
    return inner(p)
}

func inner(p string) string {
    return p
}
"#;

    #[test]
    fn parses_package_and_two_functions() {
        let parse =
            parse_file(HELPERS, "svc/helpers/helpers.go", "svc::helpers", "", repo()).unwrap();

        let mod_id = NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::MODULE, "svc::helpers");
        let hash_id = NodeId::from_parts(
            GRAPH_TYPE,
            repo(),
            node_kind::FUNCTION,
            "svc::helpers::HashPassword",
        );
        let inner_id = NodeId::from_parts(
            GRAPH_TYPE,
            repo(),
            node_kind::FUNCTION,
            "svc::helpers::inner",
        );

        assert!(parse.nodes.iter().any(|n| n.id == mod_id));
        assert!(parse.nodes.iter().any(|n| n.id == hash_id));
        assert!(parse.nodes.iter().any(|n| n.id == inner_id));
        assert!(has_edge(&parse, mod_id, hash_id, edge_category::DEFINES));
        assert!(has_edge(&parse, mod_id, inner_id, edge_category::DEFINES));

        // intra-file bare call: HashPassword → inner
        assert!(parse.calls.iter().any(|c| {
            c.from == hash_id && matches!(&c.qualifier, CallQualifier::Bare(n) if n == "inner")
        }));
    }

    const USERS: &str = r#"package users

type User struct {
    name string
}

type Greeter interface {
    Greet() string
}

func (u *User) Login(password string) error {
    u.save()
    return nil
}

func (u *User) save() error {
    return nil
}
"#;

    #[test]
    fn parses_struct_interface_and_methods_with_self_call() {
        let parse = parse_file(USERS, "svc/users/users.go", "svc::users", "", repo()).unwrap();

        let struct_id = NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::STRUCT, "svc::users::User");
        let iface_id = NodeId::from_parts(
            GRAPH_TYPE,
            repo(),
            node_kind::INTERFACE,
            "svc::users::Greeter",
        );
        let login_id = NodeId::from_parts(
            GRAPH_TYPE,
            repo(),
            node_kind::METHOD,
            "svc::users::User::Login",
        );
        let save_id = NodeId::from_parts(
            GRAPH_TYPE,
            repo(),
            node_kind::METHOD,
            "svc::users::User::save",
        );

        assert!(parse.nodes.iter().any(|n| n.id == struct_id));
        assert!(parse.nodes.iter().any(|n| n.id == iface_id));
        assert!(parse.nodes.iter().any(|n| n.id == login_id));
        assert!(parse.nodes.iter().any(|n| n.id == save_id));

        // Methods are children of the struct.
        assert!(has_edge(&parse, struct_id, login_id, edge_category::DEFINES));
        assert!(has_edge(&parse, struct_id, save_id, edge_category::DEFINES));

        // Self-call `u.save()` inside Login's body maps to SelfMethod (because
        // `u` is the receiver variable).
        assert!(parse.calls.iter().any(|c| {
            c.from == login_id
                && matches!(&c.qualifier, CallQualifier::SelfMethod(n) if n == "save")
        }));
    }

    const AUTH: &str = r#"package auth

import (
    "context"
    users "github.com/foo/bar/svc/users"
    "github.com/foo/bar/svc/helpers"
)

func Login(ctx context.Context) error {
    u := users.User{}
    _ = u
    return helpers.HashPassword("x")
}
"#;

    #[test]
    fn collects_imports_and_attribute_calls() {
        let parse = parse_file(
            AUTH,
            "svc/auth/auth.go",
            "svc::auth",
            "github.com/foo/bar",
            repo(),
        )
        .unwrap();

        // Three imports, two within-module.
        assert_eq!(parse.imports.len(), 3);
        assert!(parse.imports.iter().any(|i| {
            matches!(&i.target, ImportTarget::Module { path, alias }
                if path == "svc::users" && alias.as_deref() == Some("users"))
        }));
        assert!(parse.imports.iter().any(|i| {
            matches!(&i.target, ImportTarget::Module { path, alias: None }
                if path == "svc::helpers")
        }));
        assert!(parse.imports.iter().any(|i| {
            matches!(&i.target, ImportTarget::Module { path, .. } if path == "context")
        }));

        // helpers.HashPassword → Attribute call
        let login_id =
            NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::FUNCTION, "svc::auth::Login");
        assert!(parse.calls.iter().any(|c| {
            c.from == login_id
                && matches!(&c.qualifier, CallQualifier::Attribute { base, name }
                    if base == "helpers" && name == "HashPassword")
        }));
    }

    #[test]
    fn syntax_error_produces_partial_graph() {
        // Missing closing brace; tree-sitter still recovers.
        let broken = "package x\n\nfunc Foo() {\n    bar(\n";
        let parse = parse_file(broken, "x.go", "x", "", repo()).unwrap();
        // At minimum we got the module node.
        let mod_id = NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::MODULE, "x");
        assert!(parse.nodes.iter().any(|n| n.id == mod_id));
    }
}
