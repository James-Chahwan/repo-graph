//! Cross-file resolution test against `tests/fixtures/ts_smoke/`.
//!
//! TypeScript-specific shapes this exercises:
//! - Named import binding: `import { hashPassword } from "./helpers"` binds
//!   `hashPassword` in the importing module to the exported function.
//! - Namespace import: `import * as helpers from "./helpers"` binds `helpers`
//!   to the module itself, enabling `helpers.hashPassword(...)` attribute call
//!   resolution.
//! - Self-method via `this.`: `this.login(...)` inside `save()` resolves to
//!   the sibling method on the enclosing class.
//! - Intra-file bare call: `inner` invoked from `hashPassword` in the same file.
//! - Import source resolution seam: caller-provided closure maps raw
//!   specifiers (`./helpers`) to module qnames (`src::helpers`).

use std::path::PathBuf;

use repo_graph_core::{EdgeCategoryId, NodeId, RepoId};
use repo_graph_graph::build_typescript;
use repo_graph_parser_typescript::{FileParse, GRAPH_TYPE, edge_category, node_kind, parse_file};

fn fixture_root() -> PathBuf {
    let here = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    here.parent().unwrap().parent().unwrap().join("tests/fixtures/ts_smoke")
}

fn repo() -> RepoId {
    RepoId::from_canonical("test://ts_smoke")
}

fn parse(rel: &str, qname: &str) -> FileParse {
    let path = fixture_root().join(rel);
    let src = std::fs::read_to_string(&path).unwrap();
    parse_file(&src, rel, qname, repo()).unwrap()
}

fn parses() -> Vec<FileParse> {
    vec![
        parse("src/helpers.ts", "src::helpers"),
        parse("src/user.ts", "src::user"),
        parse("src/auth.ts", "src::auth"),
    ]
}

fn mod_id(qname: &str) -> NodeId {
    NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::MODULE, qname)
}
fn class_id(qname: &str) -> NodeId {
    NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::CLASS, qname)
}
fn func_id(qname: &str) -> NodeId {
    NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::FUNCTION, qname)
}
fn method_id(qname: &str) -> NodeId {
    NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::METHOD, qname)
}

fn has_edge<I: IntoIterator<Item = (NodeId, NodeId, EdgeCategoryId)> + Clone>(
    edges: I,
    from: NodeId,
    to: NodeId,
    cat: EdgeCategoryId,
) -> bool {
    edges
        .into_iter()
        .any(|(f, t, c)| f == from && t == to && c == cat)
}

/// Toy resolver: relative specifiers map to `src::<basename>` under our
/// fixture. Anything else (node_modules, absolute paths) is treated as external.
fn resolve(from: &str, raw: &str) -> Option<String> {
    let _ = from;
    if let Some(rest) = raw.strip_prefix("./") {
        let rest = rest.trim_end_matches(".ts");
        return Some(format!("src::{}", rest.replace('/', "::")));
    }
    None
}

#[test]
fn cross_file_imports_and_calls_resolve() {
    let g = build_typescript(repo(), parses(), resolve).unwrap();
    let tuples: Vec<(NodeId, NodeId, EdgeCategoryId)> =
        g.edges.iter().map(|e| (e.from, e.to, e.category)).collect();

    let helpers = mod_id("src::helpers");
    let user = mod_id("src::user");
    let auth = mod_id("src::auth");
    let user_cls = class_id("src::user::User");
    let login = method_id("src::user::User::login");
    let save = method_id("src::user::User::save");
    let hash = func_id("src::helpers::hashPassword");
    let inner = func_id("src::helpers::inner");

    // --- IMPORTS edges (via resolver closure).
    assert!(
        has_edge(tuples.clone(), user, helpers, edge_category::IMPORTS),
        "user → helpers import (named import)"
    );
    assert!(
        has_edge(tuples.clone(), auth, helpers, edge_category::IMPORTS),
        "auth → helpers import (namespace import)"
    );
    assert!(
        has_edge(tuples.clone(), auth, user, edge_category::IMPORTS),
        "auth → user import (named import)"
    );

    // --- Intra-file bare call: hashPassword → inner.
    assert!(
        has_edge(tuples.clone(), hash, inner, edge_category::CALLS),
        "hashPassword → inner (same-file bare)"
    );

    // --- Cross-file bare call via named import binding.
    assert!(
        has_edge(tuples.clone(), login, hash, edge_category::CALLS),
        "User.login → hashPassword (via named import from ./helpers)"
    );

    // --- Self-method via `this.`.
    assert!(
        has_edge(tuples.clone(), save, login, edge_category::CALLS),
        "User.save → User.login (this-call)"
    );

    // --- Class is present and acts as parent for methods.
    assert!(
        g.nodes.iter().any(|n| n.id == user_cls),
        "User class node present"
    );
    let chain = g.parent_chain(login);
    assert_eq!(chain[0], user_cls, "login's parent is User class");
    assert_eq!(chain[1], user, "class's parent is module");
}
