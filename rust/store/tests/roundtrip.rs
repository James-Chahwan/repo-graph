//! End-to-end roundtrip: build a real `RepoGraph` with `build_go` against the
//! `http_stack_smoke/backend` fixture, write it to a temp `.gmap` file, mmap
//! it back, and assert the archived form matches the owned form for every
//! surface v0.4.5a exposes.
//!
//! This is the v0.4.5a acceptance test — if this stays green, the store
//! crate's write + mmap + zero-copy access contract is working.

use std::path::PathBuf;

use repo_graph_code_domain::node_kind;
use repo_graph_core::{NodeId, RepoId};
use repo_graph_graph::build_go;
use repo_graph_parser_go::parse_file;
use repo_graph_store::{MmapContainer, write_repo_graph};

const MODULE_PREFIX: &str = "example.com/backend";

fn backend_root() -> PathBuf {
    let here = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    here.parent()
        .unwrap()
        .parent()
        .unwrap()
        .join("tests/fixtures/http_stack_smoke/backend")
}

fn repo() -> RepoId {
    RepoId::from_canonical("test://http_stack_smoke/backend")
}

fn build() -> repo_graph_graph::RepoGraph {
    let files = [
        ("users/users.go", "users"),
        ("server/server.go", "server"),
    ];
    let parses: Vec<_> = files
        .iter()
        .map(|(rel, pkg)| {
            let src = std::fs::read_to_string(backend_root().join(rel)).unwrap();
            parse_file(&src, rel, pkg, MODULE_PREFIX, repo()).unwrap()
        })
        .collect();
    build_go(repo(), parses).unwrap()
}

#[test]
fn repo_graph_roundtrips_through_gmap_file() {
    let g = build();
    let expected_node_count = g.nodes.len();
    let expected_edge_count = g.edges.len();
    let expected_nav_size = g.nav.qname_by_id.len();

    // Sanity: the backend fixture should produce a non-trivial graph —
    // otherwise a silently-empty write would pass this test meaninglessly.
    assert!(expected_node_count > 0, "backend build produced no nodes");
    assert!(expected_edge_count > 0, "backend build produced no edges");

    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("backend.gmap");
    write_repo_graph(&g, &path).unwrap();
    assert!(path.exists(), "written .gmap file should exist at {path:?}");

    let container = MmapContainer::open(&path).unwrap();
    let archived = container.archived().unwrap();

    // Header + repo round-trip.
    assert_eq!(archived.header.magic, *b"GMAP");
    assert_eq!(archived.header.version.to_native(), 1);
    assert_eq!(archived.header.graph_type.as_str(), "code");
    assert_eq!(archived.repo.0.to_native(), repo().0);

    // Node and edge counts match.
    assert_eq!(archived.nodes.len(), expected_node_count);
    assert_eq!(archived.edges.len(), expected_edge_count);

    // Nav index count matches (pre/post-flatten sizes are identical: one pair
    // per key with no dedup since the source is already a HashMap with unique
    // keys).
    assert_eq!(archived.code_nav.qname_by_id.len(), expected_nav_size);

    // Point lookup via binary search: one known node from the fixture is the
    // `/health` route — v0.4.4a tests assert its presence.
    // Find the Route node id by its qname in the owned graph, then look up
    // the same id via the archived nav.
    let route_id = g
        .nav
        .qname_by_id
        .iter()
        .find(|(_, qn)| qn.starts_with("route:"))
        .map(|(id, _)| *id)
        .expect("backend fixture has at least one Route");
    let qn_owned = g.nav.qname_by_id.get(&route_id).unwrap();
    let qn_archived = archived.qname(route_id).expect("archived qname lookup");
    assert_eq!(qn_archived, qn_owned);
    assert_eq!(archived.kind(route_id), Some(node_kind::ROUTE));

    // Unknown id returns None (binary search miss, no panic).
    assert_eq!(archived.qname(NodeId(0xDEAD_BEEF)), None);
    assert_eq!(archived.kind(NodeId(0xDEAD_BEEF)), None);

    // Edge iterator yields the same (from, to, category) triples.
    let mut from_owned: Vec<_> = g
        .edges
        .iter()
        .map(|e| (e.from.0, e.to.0, e.category.0))
        .collect();
    let mut from_archived: Vec<_> = archived
        .edges_iter()
        .map(|(f, t, c)| (f.0, t.0, c.0))
        .collect();
    from_owned.sort();
    from_archived.sort();
    assert_eq!(from_archived, from_owned);

    // File size is non-zero and reasonable — a .gmap of this fixture should
    // be hundreds of bytes to a few kB, not MB.
    assert!(container.len() > 64, "gmap file suspiciously small");
    assert!(container.len() < 1_000_000, "gmap file suspiciously large");

    // tempdir cleans up on drop; container holds an mmap of a file that's
    // about to be unlinked but the kernel keeps the inode alive until we
    // drop the mmap.
    drop(container);
    drop(dir);
}

#[test]
fn opening_a_non_gmap_file_fails_with_bad_magic_or_rkyv_error() {
    let tmp = tempfile::NamedTempFile::new().unwrap();
    std::fs::write(tmp.path(), b"NOTA gmap file, just some junk bytes").unwrap();
    let err = MmapContainer::open(tmp.path());
    assert!(err.is_err(), "garbage file should not open as a gmap");
}
