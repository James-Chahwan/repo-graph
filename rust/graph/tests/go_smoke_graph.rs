//! Cross-file resolution test against `tests/fixtures/go_smoke/`.
//!
//! Go-specific shapes this exercises:
//! - Multi-file package dedup: `helpers/helpers.go` + `helpers/extra.go` both
//!   emit a Module node with the same `helpers` qname. Graph build collapses
//!   them onto a single node with stacked cells.
//! - Intra-package cross-file bare call resolution: `HashPassword` (helpers.go)
//!   calls `inner` (extra.go).
//! - Self-method resolution: `User.Save` calls `u.Login(...)` via the receiver
//!   variable `u`. The parser emits `CallQualifier::SelfMethod`, resolver
//!   walks to the enclosing struct and matches `Login`.
//! - Package-prefix attribute call across an aliased import: `DoLogin` calls
//!   `helpers.HashPassword` after `import "example.com/myapp/helpers"`.
//! - Import edges seeded from `go.mod` module prefix stripping.

use std::path::PathBuf;

use repo_graph_core::{EdgeCategoryId, NodeId, RepoId};
use repo_graph_graph::build_go;
use repo_graph_parser_go::{FileParse, GRAPH_TYPE, edge_category, node_kind, parse_file};

const MODULE_PREFIX: &str = "example.com/myapp";

fn fixture_root() -> PathBuf {
    let here = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    here.parent().unwrap().parent().unwrap().join("tests/fixtures/go_smoke")
}

fn repo() -> RepoId {
    RepoId::from_canonical("test://go_smoke")
}

fn parse(rel: &str, pkg: &str) -> FileParse {
    let path = fixture_root().join(rel);
    let src = std::fs::read_to_string(&path).unwrap();
    parse_file(&src, rel, pkg, MODULE_PREFIX, repo()).unwrap()
}

fn parses() -> Vec<FileParse> {
    vec![
        parse("helpers/helpers.go", "helpers"),
        parse("helpers/extra.go", "helpers"),
        parse("users/users.go", "users"),
        parse("auth/auth.go", "auth"),
        parse("server/server.go", "server"),
    ]
}

fn mod_id(qname: &str) -> NodeId {
    NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::MODULE, qname)
}
fn struct_id(qname: &str) -> NodeId {
    NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::STRUCT, qname)
}
fn func_id(qname: &str) -> NodeId {
    NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::FUNCTION, qname)
}
fn method_id(qname: &str) -> NodeId {
    NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::METHOD, qname)
}
fn route_id(path: &str) -> NodeId {
    NodeId::from_parts(
        GRAPH_TYPE,
        repo(),
        node_kind::ROUTE,
        &format!("route:{path}"),
    )
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
fn multi_file_package_dedup_and_cross_file_calls() {
    let g = build_go(repo(), parses()).unwrap();
    let tuples: Vec<(NodeId, NodeId, EdgeCategoryId)> =
        g.edges.iter().map(|e| (e.from, e.to, e.category)).collect();

    let helpers = mod_id("helpers");
    let users = mod_id("users");
    let auth = mod_id("auth");
    let user = struct_id("users::User");
    let login = method_id("users::User::Login");
    let save = method_id("users::User::Save");
    let hash = func_id("helpers::HashPassword");
    let inner = func_id("helpers::inner");
    let do_login = func_id("auth::DoLogin");

    // --- Module dedup: helpers.go and extra.go collapse onto one node.
    let helpers_nodes: Vec<_> = g.nodes.iter().filter(|n| n.id == helpers).collect();
    assert_eq!(
        helpers_nodes.len(),
        1,
        "helpers Module must collapse across multi-file package"
    );
    // Each file contributed Code + Position cells — at least 4 stacked on the
    // deduped node (two per file).
    assert!(
        helpers_nodes[0].cells.len() >= 4,
        "stacked cells from both helpers files, got {}",
        helpers_nodes[0].cells.len()
    );

    // --- IMPORTS edges (Go import path stripping).
    assert!(
        has_edge(tuples.clone(), auth, helpers, edge_category::IMPORTS),
        "auth → helpers import"
    );
    assert!(
        has_edge(tuples.clone(), auth, users, edge_category::IMPORTS),
        "auth → users import"
    );

    // --- Intra-package cross-file bare call: HashPassword → inner.
    // HashPassword lives in helpers.go, `inner` lives in extra.go. The
    // Bare-qualifier call resolves against module_symbols of `helpers`.
    assert!(
        has_edge(tuples.clone(), hash, inner, edge_category::CALLS),
        "HashPassword → inner (same-package cross-file bare)"
    );

    // --- Self-method resolution: u.Login inside Save's body.
    assert!(
        has_edge(tuples.clone(), save, login, edge_category::CALLS),
        "User.Save → User.Login (self-call via receiver var)"
    );

    // --- Cross-package attribute call: helpers.HashPassword from auth.
    assert!(
        has_edge(tuples.clone(), do_login, hash, edge_category::CALLS),
        "DoLogin → HashPassword (via helpers binding)"
    );

    // --- Struct is present and acts as a parent for methods.
    assert!(
        g.nodes.iter().any(|n| n.id == user),
        "User struct node present"
    );
    let chain = g.parent_chain(login);
    assert_eq!(chain[0], user, "Login parent is User struct");
    assert_eq!(chain[1], users, "struct's parent is users module");
}

/// Route extraction + HANDLED_BY resolution end-to-end through the graph.
///
/// `server/server.go` registers three routes against a stand-in router:
///   - `r.GET("/health", health)`        — same-package bare handler
///   - `r.POST("/login", auth.DoLogin)`  — cross-package selector handler
///   - `api.GET("/users", users.List)`   — same, behind a `Group("/api")` prefix
#[test]
fn routes_emit_handled_by_edges_via_unresolved_ref_resolution() {
    let g = build_go(repo(), parses()).unwrap();
    let tuples: Vec<(NodeId, NodeId, EdgeCategoryId)> =
        g.edges.iter().map(|e| (e.from, e.to, e.category)).collect();

    let health = route_id("/health");
    let login = route_id("/login");
    let api_users = route_id("/api/users");

    let do_login = func_id("auth::DoLogin");
    let users_list = func_id("users::List");
    let server_health = func_id("server::health");

    // --- Routes exist as nodes after the parser pass.
    assert!(g.nodes.iter().any(|n| n.id == health), "GET /health route");
    assert!(g.nodes.iter().any(|n| n.id == login), "POST /login route");
    assert!(
        g.nodes.iter().any(|n| n.id == api_users),
        "GET /api/users route (Group prefix joined)"
    );

    // --- Bare handler resolves to a same-package fn.
    assert!(
        has_edge(tuples.clone(), health, server_health, edge_category::HANDLED_BY),
        "/health → server.health (Bare → module_symbols)"
    );

    // --- Selector handler resolves cross-package via the auth import binding.
    assert!(
        has_edge(tuples.clone(), login, do_login, edge_category::HANDLED_BY),
        "/login → auth.DoLogin (Attribute → import binding → module_symbols)"
    );

    // --- Group-chained route resolves the same way.
    assert!(
        has_edge(tuples.clone(), api_users, users_list, edge_category::HANDLED_BY),
        "/api/users → users.List"
    );

    // --- No leftover unresolved refs for the routes above.
    assert!(
        g.unresolved_refs.is_empty(),
        "all route handlers resolved, leftover: {:?}",
        g.unresolved_refs
    );
}
