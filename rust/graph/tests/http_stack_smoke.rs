//! Cross-repo HTTP stack resolution test against
//! `tests/fixtures/http_stack_smoke/`.
//!
//! Two synthetic repos — a Go backend registering routes against a stand-in
//! router, and a TypeScript Angular-style frontend calling those routes via
//! `this.http.<method>()`. The test builds each as its own `RepoGraph`, wraps
//! them in a `MergedGraph`, runs `HttpStackResolver`, and asserts that
//! `HTTP_CALLS` edges cross-link each Endpoint to its matching Route.
//!
//! Matches this exercise:
//! - `/api/users` GET: string-literal path on the frontend, `Group("/api") +
//!   api.GET("/users", ...)` on the backend.
//! - `/api/users` POST: same path, different method — distinct Endpoint qname
//!   (endpoint:POST:/api/users) but same Route node.
//! - `/api/users/{}`: template interpolation on the frontend (`\`.../${id}\``)
//!   matches the backend's `:id` path param after normalisation, at Medium
//!   endpoint confidence.

use std::path::PathBuf;

use repo_graph_code_domain::{cell_type, edge_category, node_kind};
use repo_graph_core::{CellPayload, Confidence, NodeId, RepoId};
use repo_graph_graph::{
    CrossGraphResolver, HttpStackResolver, MergedGraph, build_go, build_typescript,
};

const BACKEND_MODULE_PREFIX: &str = "example.com/backend";

fn fixture_root() -> PathBuf {
    let here = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    here.parent().unwrap().parent().unwrap().join("tests/fixtures/http_stack_smoke")
}

fn backend_repo() -> RepoId {
    RepoId::from_canonical("test://http_stack_smoke/backend")
}
fn frontend_repo() -> RepoId {
    RepoId::from_canonical("test://http_stack_smoke/frontend")
}

fn parse_backend() -> repo_graph_graph::RepoGraph {
    let root = fixture_root().join("backend");
    let files = [
        ("users/users.go", "users"),
        ("server/server.go", "server"),
    ];
    let parses: Vec<_> = files
        .iter()
        .map(|(rel, pkg)| {
            let src = std::fs::read_to_string(root.join(rel)).unwrap();
            repo_graph_parser_go::parse_file(&src, rel, pkg, BACKEND_MODULE_PREFIX, backend_repo())
                .unwrap()
        })
        .collect();
    build_go(backend_repo(), parses).unwrap()
}

fn parse_frontend() -> repo_graph_graph::RepoGraph {
    let root = fixture_root().join("frontend");
    let rel = "src/app/user.service.ts";
    let src = std::fs::read_to_string(root.join(rel)).unwrap();
    let parse = repo_graph_parser_typescript::parse_file(
        &src,
        rel,
        "src::app::user_service",
        frontend_repo(),
    )
    .unwrap();
    // No cross-file imports in this fixture — resolver is a no-op.
    build_typescript(frontend_repo(), vec![parse], |_, _| None).unwrap()
}

fn route_id(path: &str) -> NodeId {
    NodeId::from_parts(
        repo_graph_parser_go::GRAPH_TYPE,
        backend_repo(),
        node_kind::ROUTE,
        &format!("route:{path}"),
    )
}

fn endpoint_id(method: &str, path: &str) -> NodeId {
    NodeId::from_parts(
        repo_graph_parser_typescript::GRAPH_TYPE,
        frontend_repo(),
        node_kind::ENDPOINT,
        &format!("endpoint:{method}:{path}"),
    )
}

fn route_method_cells(g: &repo_graph_graph::RepoGraph, id: NodeId) -> Vec<String> {
    g.nodes
        .iter()
        .filter(|n| n.id == id)
        .flat_map(|n| n.cells.iter())
        .filter(|c| c.kind == cell_type::ROUTE_METHOD)
        .filter_map(|c| match &c.payload {
            CellPayload::Json(j) => {
                // Tiny inline extraction — same minimal parse the resolver uses.
                let key = "\"method\"";
                let idx = j.find(key)?;
                let after = &j[idx + key.len()..];
                let colon = after.find(':')?;
                let rest = after[colon + 1..].trim_start().strip_prefix('"')?;
                let end = rest.find('"')?;
                Some(rest[..end].to_string())
            }
            _ => None,
        })
        .collect()
}

#[test]
fn frontend_endpoints_link_to_backend_routes_via_http_calls_edges() {
    let backend = parse_backend();
    let frontend = parse_frontend();

    // --- Backend sanity: three routes exist with the expected methods.
    let users_route = route_id("/api/users");
    let user_by_id_route = route_id("/api/users/:id");

    assert!(
        backend.nodes.iter().any(|n| n.id == users_route),
        "backend /api/users Route node present"
    );
    assert!(
        backend.nodes.iter().any(|n| n.id == user_by_id_route),
        "backend /api/users/:id Route node present"
    );
    let users_methods = route_method_cells(&backend, users_route);
    assert!(users_methods.contains(&"GET".to_string()));
    assert!(users_methods.contains(&"POST".to_string()));
    let by_id_methods = route_method_cells(&backend, user_by_id_route);
    assert_eq!(by_id_methods, vec!["GET".to_string()]);

    // --- Frontend sanity: three endpoint nodes exist (method-specific qnames).
    let ep_get_users = endpoint_id("GET", "/api/users");
    let ep_post_users = endpoint_id("POST", "/api/users");
    let ep_get_user_by_id = endpoint_id("GET", "/api/users/${…}");

    assert!(frontend.nodes.iter().any(|n| n.id == ep_get_users));
    assert!(frontend.nodes.iter().any(|n| n.id == ep_post_users));
    assert!(frontend.nodes.iter().any(|n| n.id == ep_get_user_by_id));

    // --- Template-interpolation endpoint is Medium confidence; the string-
    //     literal endpoints stay Strong. The resolver should propagate that
    //     down onto the cross-repo edge via `weakest(endpoint, route)`.
    let ep_medium_confidence = frontend
        .nodes
        .iter()
        .find(|n| n.id == ep_get_user_by_id)
        .map(|n| n.confidence);
    assert_eq!(ep_medium_confidence, Some(Confidence::Medium));

    // --- Run HttpStackResolver.
    let mut merged = MergedGraph::new(vec![backend, frontend]);
    HttpStackResolver.resolve(&mut merged);

    let cross: Vec<_> = merged
        .cross_edges
        .iter()
        .filter(|e| e.category == edge_category::HTTP_CALLS)
        .collect();
    assert!(
        !cross.is_empty(),
        "expected HTTP_CALLS cross-edges, got {cross:?}"
    );

    // --- GET /api/users endpoint → /api/users route (Strong ∧ Strong = Strong).
    let e1 = cross
        .iter()
        .find(|e| e.from == ep_get_users && e.to == users_route)
        .expect("GET endpoint → /api/users route edge");
    assert_eq!(e1.confidence, Confidence::Strong);

    // --- POST /api/users endpoint → same /api/users route, distinct edge.
    let e2 = cross
        .iter()
        .find(|e| e.from == ep_post_users && e.to == users_route)
        .expect("POST endpoint → /api/users route edge");
    assert_eq!(e2.confidence, Confidence::Strong);

    // --- GET /api/users/${…} endpoint → /api/users/:id route via path
    //     normalisation. Edge confidence weakens to Medium because the
    //     endpoint itself was Medium.
    let e3 = cross
        .iter()
        .find(|e| e.from == ep_get_user_by_id && e.to == user_by_id_route)
        .expect("template-path endpoint → :id route edge");
    assert_eq!(
        e3.confidence,
        Confidence::Medium,
        "template endpoint's Medium confidence propagates to the cross-edge"
    );

    // --- Intra-repo edges untouched — HttpStackResolver only writes to
    //     `cross_edges`, never to the per-repo edge lists.
    let backend_http = merged.graphs[0]
        .edges
        .iter()
        .any(|e| e.category == edge_category::HTTP_CALLS);
    let frontend_http = merged.graphs[1]
        .edges
        .iter()
        .any(|e| e.category == edge_category::HTTP_CALLS);
    assert!(!backend_http && !frontend_http);
}
