//! Golden test against `tests/fixtures/py_smoke/`. Asserts the single-file
//! parser produces the nodes + intra-file edges the 0.3.0 Python analyzer
//! produced for the same sources. Cross-file call edges land in v0.4.3.

use std::path::PathBuf;

use repo_graph_core::{EdgeCategoryId, NodeId, RepoId};
use repo_graph_parser_python::{
    CallQualifier, FileParse, GRAPH_TYPE, ImportTarget, cell_type, edge_category, node_kind,
    parse_file,
};

fn fixture_root() -> PathBuf {
    // cargo runs tests from the crate dir — walk up to the repo root.
    let here = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    here.parent().unwrap().parent().unwrap().join("tests/fixtures/py_smoke")
}

fn repo() -> RepoId {
    RepoId::from_canonical("test://py_smoke")
}

fn parse(rel: &str, qname: &str) -> FileParse {
    let path = fixture_root().join(rel);
    let src = std::fs::read_to_string(&path).unwrap_or_else(|e| {
        panic!("could not read fixture {}: {e}", path.display());
    });
    parse_file(&src, rel, qname, repo()).unwrap()
}

fn has_edge(p: &FileParse, from: NodeId, to: NodeId, cat: EdgeCategoryId) -> bool {
    p.edges
        .iter()
        .any(|e| e.from == from && e.to == to && e.category == cat)
}

#[test]
fn helpers_py_emits_functions_and_intra_file_call() {
    let p = parse("myapp/helpers.py", "myapp::helpers");

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

    assert!(p.nodes.iter().any(|n| n.id == module_id));
    assert!(p.nodes.iter().any(|n| n.id == hash_id));
    assert!(p.nodes.iter().any(|n| n.id == inner_id));

    assert!(has_edge(&p, module_id, hash_id, edge_category::DEFINES));
    assert!(has_edge(&p, module_id, inner_id, edge_category::DEFINES));

    // Python analyzer: `helpers.hash_password → helpers._inner` (same-file bare).
    assert!(has_edge(&p, hash_id, inner_id, edge_category::CALLS));
}

#[test]
fn users_py_emits_class_methods_and_self_call() {
    let p = parse("myapp/users.py", "myapp::users");

    let mod_id = NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::MODULE, "myapp::users");
    let class_id =
        NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::CLASS, "myapp::users::User");
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

    assert!(p.nodes.iter().any(|n| n.id == class_id));
    assert!(p.nodes.iter().any(|n| n.id == login_id));
    assert!(p.nodes.iter().any(|n| n.id == save_id));

    assert!(has_edge(&p, mod_id, class_id, edge_category::DEFINES));
    assert!(has_edge(&p, class_id, login_id, edge_category::DEFINES));
    assert!(has_edge(&p, class_id, save_id, edge_category::DEFINES));

    // Python analyzer: `User.save → User.login` (self-call).
    assert!(has_edge(&p, save_id, login_id, edge_category::CALLS));

    // Relative import: `from .helpers import hash_password`.
    assert!(p.imports.iter().any(|i| matches!(
        &i.target,
        ImportTarget::Symbol { module, name, level, .. }
            if module == "helpers" && name == "hash_password" && *level == 1
    )));

    // hash_password(...) call inside login body stays unresolved (cross-file).
    assert!(p.calls.iter().any(|c| {
        c.from == login_id && matches!(&c.qualifier, CallQualifier::Bare(n) if n == "hash_password")
    }));
}

#[test]
fn auth_py_emits_function_and_records_imports() {
    let p = parse("myapp/auth.py", "myapp::auth");

    let mod_id = NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::MODULE, "myapp::auth");
    let func_id = NodeId::from_parts(
        GRAPH_TYPE,
        repo(),
        node_kind::FUNCTION,
        "myapp::auth::do_login",
    );

    assert!(p.nodes.iter().any(|n| n.id == func_id));
    assert!(has_edge(&p, mod_id, func_id, edge_category::DEFINES));

    // Two absolute imports recorded.
    assert!(p.imports.iter().any(|i| matches!(
        &i.target,
        ImportTarget::Symbol { module, name, level, .. }
            if module == "myapp.users" && name == "User" && *level == 0
    )));
    assert!(p.imports.iter().any(|i| matches!(
        &i.target,
        ImportTarget::Symbol { module, name, level, .. }
            if module == "myapp" && name == "helpers" && *level == 0
    )));

    // Three unresolved call sites inside do_login.
    let sites: Vec<&CallQualifier> = p
        .calls
        .iter()
        .filter(|c| c.from == func_id)
        .map(|c| &c.qualifier)
        .collect();
    assert_eq!(sites.len(), 3, "expected 3 unresolved calls, got: {sites:?}");
}

#[test]
fn every_code_entity_has_code_and_position_cells() {
    let p = parse("myapp/users.py", "myapp::users");
    for n in &p.nodes {
        assert!(
            n.cells.iter().any(|c| c.kind == cell_type::CODE),
            "node {:?} missing code cell",
            n.id
        );
        assert!(
            n.cells.iter().any(|c| c.kind == cell_type::POSITION),
            "node {:?} missing position cell",
            n.id
        );
    }
}
