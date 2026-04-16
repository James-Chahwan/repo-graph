//! Sharded `.gmap` directory roundtrip — the v0.4.5c acceptance test.
//!
//! Writes a 2-shard layout (real Go backend graph from `http_stack_smoke` +
//! a synthetic single-Endpoint frontend graph) plus a cross-stack edge
//! linking the Endpoint to a backend Route, then re-opens the directory via
//! `ShardedMmap::open` and asserts:
//!
//! - manifest has the right schema version, shard count, and a `cross` entry,
//! - per-shard hashes match what's on disk (no silent corruption),
//! - the cross-stack mmap holds exactly the cross edges and zero nodes,
//! - the per-shard graphs survive roundtrip with their node/edge counts intact.

use std::path::PathBuf;

use repo_graph_code_domain::{CodeNav, edge_category, node_kind};
use repo_graph_core::{
    Cell, CellPayload, CellTypeId, Confidence, Edge, Node, NodeId, RepoId,
};
use repo_graph_graph::{RepoGraph, SymbolTable, build_go};
use repo_graph_parser_go::parse_file;
use repo_graph_store::{
    CROSS_STACK_NAME, MANIFEST_NAME, MANIFEST_VERSION, ShardedMmap, write_sharded,
};

const MODULE_PREFIX: &str = "example.com/backend";

fn backend_root() -> PathBuf {
    let here = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    here.parent()
        .unwrap()
        .parent()
        .unwrap()
        .join("tests/fixtures/http_stack_smoke/backend")
}

fn backend_repo() -> RepoId {
    RepoId::from_canonical("test://http_stack_smoke/backend")
}

fn frontend_repo() -> RepoId {
    RepoId::from_canonical("test://http_stack_smoke/frontend")
}

fn build_backend() -> RepoGraph {
    let files = [
        ("users/users.go", "users"),
        ("server/server.go", "server"),
    ];
    let parses: Vec<_> = files
        .iter()
        .map(|(rel, pkg)| {
            let src = std::fs::read_to_string(backend_root().join(rel)).unwrap();
            parse_file(&src, rel, pkg, MODULE_PREFIX, backend_repo()).unwrap()
        })
        .collect();
    build_go(backend_repo(), parses).unwrap()
}

/// Synthetic single-Endpoint "frontend" graph. Skips parsing TypeScript so the
/// store crate doesn't need a parser-typescript dev-dep just for this test.
fn build_synthetic_frontend() -> (RepoGraph, NodeId) {
    let endpoint_id = NodeId::from_parts(
        "code",
        frontend_repo(),
        node_kind::ENDPOINT,
        "endpoint:GET:/api/users",
    );
    let mut nav = CodeNav::default();
    nav.record(
        endpoint_id,
        "/api/users",
        "endpoint:GET:/api/users",
        node_kind::ENDPOINT,
        None,
    );
    let g = RepoGraph {
        repo: frontend_repo(),
        nodes: vec![Node {
            id: endpoint_id,
            repo: frontend_repo(),
            confidence: Confidence::Strong,
            cells: vec![Cell {
                kind: CellTypeId(6),
                payload: CellPayload::Json(
                    "{\"method\":\"GET\",\"path\":\"/api/users\"}".to_string(),
                ),
            }],
        }],
        edges: Vec::new(),
        nav,
        symbols: SymbolTable::default(),
        unresolved_calls: Vec::new(),
        unresolved_refs: Vec::new(),
    };
    (g, endpoint_id)
}

fn backend_route_id(g: &RepoGraph, path: &str) -> NodeId {
    let needle = format!("route:{path}");
    *g.nav
        .qname_by_id
        .iter()
        .find(|(_, q)| q.as_str() == needle)
        .map(|(id, _)| id)
        .expect("backend should expose this route")
}

#[test]
fn sharded_layout_roundtrips_with_cross_edges() {
    let backend = build_backend();
    let (frontend, endpoint_id) = build_synthetic_frontend();
    let route_id = backend_route_id(&backend, "/api/users");

    let backend_node_count = backend.nodes.len();
    let backend_edge_count = backend.edges.len();
    let frontend_node_count = frontend.nodes.len();

    let cross_edges = vec![Edge {
        from: endpoint_id,
        to: route_id,
        category: edge_category::HTTP_CALLS,
        confidence: Confidence::Strong,
    }];

    let dir = tempfile::tempdir().unwrap();
    let manifest = write_sharded(
        &[("backend", &backend), ("frontend", &frontend)],
        &cross_edges,
        dir.path(),
    )
    .unwrap();

    // Manifest shape sanity.
    assert_eq!(manifest.schema_version, MANIFEST_VERSION);
    assert_eq!(manifest.shards.len(), 2);
    assert_eq!(manifest.shards[0].name, "backend");
    assert_eq!(manifest.shards[0].path, "backend.gmap");
    assert_eq!(manifest.shards[1].name, "frontend");
    assert_eq!(manifest.shards[1].path, "frontend.gmap");
    let cross = manifest.cross.as_ref().expect("cross entry expected");
    assert_eq!(cross.path, CROSS_STACK_NAME);
    // Hashes are 16 hex chars (xxhash64).
    for entry in &manifest.shards {
        assert_eq!(entry.content_hash.len(), 16);
        assert!(entry.content_hash.chars().all(|c| c.is_ascii_hexdigit()));
    }

    // Files on disk match what the manifest claims.
    assert!(dir.path().join(MANIFEST_NAME).exists());
    assert!(dir.path().join("backend.gmap").exists());
    assert!(dir.path().join("frontend.gmap").exists());
    assert!(dir.path().join(CROSS_STACK_NAME).exists());

    // Re-open and verify per-shard archived contents.
    let opened = ShardedMmap::open(dir.path()).unwrap();
    assert_eq!(opened.shards.len(), 2);

    let (be_name, be_mmap) = &opened.shards[0];
    assert_eq!(be_name, "backend");
    let be_arch = be_mmap.archived().unwrap();
    assert_eq!(be_arch.nodes.len(), backend_node_count);
    assert_eq!(be_arch.edges.len(), backend_edge_count);

    let (fe_name, fe_mmap) = &opened.shards[1];
    assert_eq!(fe_name, "frontend");
    let fe_arch = fe_mmap.archived().unwrap();
    assert_eq!(fe_arch.nodes.len(), frontend_node_count);
    assert_eq!(fe_arch.edges.len(), 0);

    // Cross-stack shard: empty nodes, exactly the cross edges supplied.
    let cross_mmap = opened.cross.as_ref().expect("cross mmap expected");
    let cross_arch = cross_mmap.archived().unwrap();
    assert_eq!(cross_arch.nodes.len(), 0);
    assert_eq!(cross_arch.edges.len(), cross_edges.len());
    let (from, to, cat) = cross_arch.edges_iter().next().unwrap();
    assert_eq!(from, endpoint_id);
    assert_eq!(to, route_id);
    assert_eq!(cat, edge_category::HTTP_CALLS);

    // edges_iter sums per-shard edges + cross edges.
    let total_edges: usize = opened.edges_iter().count();
    assert_eq!(total_edges, backend_edge_count + cross_edges.len());

    drop(opened);
    drop(dir);
}

#[test]
fn no_cross_edges_writes_no_cross_stack_file() {
    let backend = build_backend();
    let dir = tempfile::tempdir().unwrap();
    let manifest =
        write_sharded(&[("backend", &backend)], &[], dir.path()).unwrap();
    assert!(manifest.cross.is_none());
    assert!(!dir.path().join(CROSS_STACK_NAME).exists());

    let opened = ShardedMmap::open(dir.path()).unwrap();
    assert!(opened.cross.is_none());
    assert_eq!(opened.shards.len(), 1);
}

#[test]
fn corrupted_shard_is_caught_by_hash_check() {
    let backend = build_backend();
    let dir = tempfile::tempdir().unwrap();
    write_sharded(&[("backend", &backend)], &[], dir.path()).unwrap();

    // Tamper with the shard file after the manifest was written.
    let shard_path = dir.path().join("backend.gmap");
    let mut bytes = std::fs::read(&shard_path).unwrap();
    let len = bytes.len();
    // Flip a byte well inside the file (header is at the start; mutate body).
    bytes[len / 2] ^= 0xFF;
    std::fs::write(&shard_path, &bytes).unwrap();

    let err = match ShardedMmap::open(dir.path()) {
        Ok(_) => panic!("expected hash-mismatch error, got Ok"),
        Err(e) => e,
    };
    let msg = format!("{err}");
    assert!(
        msg.contains("content hash mismatch") && msg.contains("backend"),
        "expected hash-mismatch error, got: {msg}"
    );
}
