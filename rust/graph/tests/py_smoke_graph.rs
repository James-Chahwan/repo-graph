//! Cross-file resolution test against `tests/fixtures/py_smoke/`.
//!
//! Asserts that v0.4.3's resolver reproduces the five call edges the Python
//! 0.3.0 analyzer produced on the same fixture, plus the three import edges
//! between modules. The one intentional non-edge (`do_login → User.login`,
//! dropped because `u`'s type is unknown) is also checked.

use std::path::PathBuf;

use repo_graph_core::{EdgeCategoryId, NodeId, RepoId};
use repo_graph_graph::build_python;
use repo_graph_parser_python::{FileParse, GRAPH_TYPE, edge_category, node_kind, parse_file};

fn fixture_root() -> PathBuf {
    let here = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    here.parent().unwrap().parent().unwrap().join("tests/fixtures/py_smoke")
}

fn repo() -> RepoId {
    RepoId::from_canonical("test://py_smoke")
}

fn parse(rel: &str, qname: &str) -> FileParse {
    let path = fixture_root().join(rel);
    let src = std::fs::read_to_string(&path).unwrap();
    parse_file(&src, rel, qname, repo()).unwrap()
}

fn parses() -> Vec<FileParse> {
    vec![
        parse("myapp/helpers.py", "myapp::helpers"),
        parse("myapp/users.py", "myapp::users"),
        parse("myapp/auth.py", "myapp::auth"),
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

#[test]
fn cross_file_imports_and_calls_resolve() {
    let g = build_python(repo(), parses()).unwrap();
    let tuples: Vec<(NodeId, NodeId, EdgeCategoryId)> =
        g.edges.iter().map(|e| (e.from, e.to, e.category)).collect();

    let auth = mod_id("myapp::auth");
    let users = mod_id("myapp::users");
    let helpers = mod_id("myapp::helpers");
    let user_cls = class_id("myapp::users::User");
    let login = method_id("myapp::users::User::login");
    let save = method_id("myapp::users::User::save");
    let hash = func_id("myapp::helpers::hash_password");
    let inner = func_id("myapp::helpers::_inner");
    let do_login = func_id("myapp::auth::do_login");

    // --- Cross-file IMPORTS edges (v0.4.3 contribution).
    assert!(
        has_edge(tuples.clone(), auth, users, edge_category::IMPORTS),
        "expected auth → users import"
    );
    assert!(
        has_edge(tuples.clone(), auth, helpers, edge_category::IMPORTS),
        "expected auth → helpers import (from myapp import helpers)"
    );
    assert!(
        has_edge(tuples.clone(), users, helpers, edge_category::IMPORTS),
        "expected users → helpers import (relative)"
    );

    // --- The five CALLS edges from the Python 0.3.0 analyzer.
    // Intra-file (already in parse output):
    assert!(
        has_edge(tuples.clone(), save, login, edge_category::CALLS),
        "User.save → User.login (self-call)"
    );
    assert!(
        has_edge(tuples.clone(), hash, inner, edge_category::CALLS),
        "hash_password → _inner (same-file bare)"
    );

    // Cross-file (v0.4.3 contribution):
    assert!(
        has_edge(tuples.clone(), login, hash, edge_category::CALLS),
        "User.login → hash_password (via `from .helpers import hash_password`)"
    );
    assert!(
        has_edge(tuples.clone(), do_login, user_cls, edge_category::CALLS),
        "do_login → User (constructor call via import binding)"
    );
    assert!(
        has_edge(tuples.clone(), do_login, hash, edge_category::CALLS),
        "do_login → hash_password (helpers.hash_password via module-attribute)"
    );

    // --- The intentional non-edge: do_login → User.login stays unresolved
    // because `u` is a local variable with no known type.
    assert!(
        !has_edge(tuples.clone(), do_login, login, edge_category::CALLS),
        "do_login → User.login must NOT resolve (local variable, no type)"
    );

    // The unresolved call should still be recorded for diagnostics.
    assert!(
        g.unresolved_calls.iter().any(|c| c.from == do_login),
        "u.login(...) should appear in unresolved_calls"
    );
}

#[test]
fn traversal_primitives_work() {
    let g = build_python(repo(), parses()).unwrap();
    let do_login = func_id("myapp::auth::do_login");
    let hash = func_id("myapp::helpers::hash_password");

    // BFS along CALLS reaches _inner transitively through hash_password.
    let reachable = g.bfs(do_login, &[edge_category::CALLS], 10);
    let inner = func_id("myapp::helpers::_inner");
    assert!(reachable.contains(&hash), "do_login reaches hash_password");
    assert!(reachable.contains(&inner), "do_login reaches _inner via hash");

    // Parent chain on User.login climbs method → class → module.
    let login = method_id("myapp::users::User::login");
    let chain = g.parent_chain(login);
    assert_eq!(chain[0], class_id("myapp::users::User"));
    assert_eq!(chain[1], mod_id("myapp::users"));
}
