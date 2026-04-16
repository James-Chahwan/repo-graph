//! repo-graph-parser-python — tree-sitter Python → `repo_graph_core` types.
//!
//! Single-file scan: emit Module/Class/Function/Method nodes with Code/Doc/
//! Position cells, intra-file `defines` and `calls` edges. Cross-file refs
//! (imports, bare-name or attribute calls that bind to another module) are
//! recorded as `ImportStmt` / `CallSite` for v0.4.3's multi-file resolver.
//!
//! Graph-type tag is `"code"`; node-kind / edge-category / cell-type ids are
//! u32 registry slots, interpreted by the container header at v0.4.5.

use std::collections::HashMap;

use repo_graph_core::{
    Cell, CellPayload, CellTypeId, Confidence, Edge, EdgeCategoryId, Node, NodeId, NodeKindId,
    RepoId,
};
use tree_sitter::{Node as TsNode, Parser};

pub const GRAPH_TYPE: &str = "code";

pub mod node_kind {
    use super::NodeKindId;
    pub const MODULE: NodeKindId = NodeKindId(1);
    pub const CLASS: NodeKindId = NodeKindId(2);
    pub const FUNCTION: NodeKindId = NodeKindId(3);
    pub const METHOD: NodeKindId = NodeKindId(4);
}

pub mod edge_category {
    use super::EdgeCategoryId;
    pub const DEFINES: EdgeCategoryId = EdgeCategoryId(1);
    pub const CONTAINS: EdgeCategoryId = EdgeCategoryId(2);
    pub const IMPORTS: EdgeCategoryId = EdgeCategoryId(3);
    pub const CALLS: EdgeCategoryId = EdgeCategoryId(4);
    pub const USES: EdgeCategoryId = EdgeCategoryId(5);
    pub const DOCUMENTS: EdgeCategoryId = EdgeCategoryId(6);
    pub const TESTS: EdgeCategoryId = EdgeCategoryId(7);
}

pub mod cell_type {
    use super::CellTypeId;
    pub const CODE: CellTypeId = CellTypeId(1);
    pub const DOC: CellTypeId = CellTypeId(2);
    pub const POSITION: CellTypeId = CellTypeId(3);
    pub const INTENT: CellTypeId = CellTypeId(4);
}

// ============================================================================
// Error + cross-file reference records
// ============================================================================

#[derive(Debug, thiserror::Error)]
pub enum ParseError {
    #[error("tree-sitter parse produced no tree")]
    NoTree,
    #[error("tree-sitter language init failed: {0}")]
    LanguageInit(String),
}

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct ImportStmt {
    /// qname of the module doing the importing (`myapp::auth`).
    pub from_module: String,
    pub target: ImportTarget,
}

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum ImportTarget {
    /// `import foo.bar` → Module { path: "foo.bar", alias: None }
    /// `import foo as f` → Module { path: "foo", alias: Some("f") }
    Module { path: String, alias: Option<String> },
    /// `from foo.bar import baz, qux` → two Symbol records.
    /// `from . import helpers` → Symbol { module: "", name: "helpers", level: 1 }
    /// `from .foo import bar` → Symbol { module: "foo", name: "bar", level: 1 }
    Symbol {
        module: String,
        name: String,
        alias: Option<String>,
        level: u32,
    },
}

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct CallSite {
    pub from: NodeId,
    pub qualifier: CallQualifier,
}

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum CallQualifier {
    /// `foo()` — local def or imported name.
    Bare(String),
    /// `self.m()` — resolves against enclosing class.
    SelfMethod(String),
    /// `base.name()` — base is an identifier. Could be an imported module,
    /// an imported symbol, or a local variable. Disambiguation happens at
    /// v0.4.3 (cross-file resolver) using the import table.
    Attribute { base: String, name: String },
    /// `<complex>.name()` — receiver is a chained expression, not a plain
    /// identifier. Kept as the raw receiver text for diagnostics.
    ComplexReceiver { receiver: String, name: String },
}

// ============================================================================
// Output
// ============================================================================

#[derive(Debug, Default)]
pub struct FileParse {
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
    pub imports: Vec<ImportStmt>,
    pub calls: Vec<CallSite>,
    pub nav: CodeNav,
}

/// Code-domain navigation indices — what the strict Node shape pushed out of
/// `Node` fields. Merged across files by v0.4.3 into one per-repo index.
#[derive(Debug, Default, Clone)]
pub struct CodeNav {
    /// Simple name (`"login"`), not the full qualified name.
    pub name_by_id: HashMap<NodeId, String>,
    /// Full qualified name (`"myapp::users::User::login"`). Used by the v0.4.3
    /// resolver to map import targets onto node ids.
    pub qname_by_id: HashMap<NodeId, String>,
    pub kind_by_id: HashMap<NodeId, NodeKindId>,
    /// Direct parent: method → class, class → module, function → module (or
    /// enclosing function for nested defs).
    pub parent_of: HashMap<NodeId, NodeId>,
    /// Inverse of `parent_of`.
    pub children_of: HashMap<NodeId, Vec<NodeId>>,
}

impl CodeNav {
    fn record(&mut self, id: NodeId, name: &str, qname: &str, kind: NodeKindId, parent: Option<NodeId>) {
        self.name_by_id.insert(id, name.to_string());
        self.qname_by_id.insert(id, qname.to_string());
        self.kind_by_id.insert(id, kind);
        if let Some(p) = parent {
            self.parent_of.insert(id, p);
            self.children_of.entry(p).or_default().push(id);
        }
    }
}

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
                );
            }
            "import_statement" => collect_import(child, src, module_qname, &mut acc),
            "import_from_statement" => collect_import_from(child, src, module_qname, &mut acc),
            "expression_statement" => {
                // Top-level calls — record them with module as source.
                collect_calls_in(child, src, module_id, None, &mut acc);
            }
            _ => {}
        }
    }

    resolve_intra_file(acc, repo)
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
        if member.kind() == "function_definition" {
            visit_method(member, src, file_rel, &class_qname, class_id, repo, acc);
        }
    }
}

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
    acc.nav
        .record(method_id, name, &method_qname, node_kind::METHOD, Some(class_id));

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

    if let Some(body) = n.child_by_field_name("body") {
        collect_calls_in(body, src, func_id, None, acc);
        // Nested defs inside the body — visited recursively.
        let mut cursor = body.walk();
        for member in body.named_children(&mut cursor) {
            if member.kind() == "function_definition" {
                visit_function(
                    member,
                    src,
                    file_rel,
                    &func_qname,
                    module_id,
                    Some(func_id),
                    repo,
                    acc,
                );
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
}
