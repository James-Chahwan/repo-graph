//! End-to-end render of the `http_stack_smoke/backend` Go graph through the
//! dense text projection. Asserts the output structure (LEGEND, TOPOLOGY,
//! per-node blocks) matches what the format spec promises and that the real
//! graph contents — Routes, handler functions, CALLS and HANDLED_BY edges —
//! flow into the right sigils.

use std::path::PathBuf;

use repo_graph_core::RepoId;
use repo_graph_graph::build_go;
use repo_graph_parser_go::parse_file;
use repo_graph_projection_text::render_repo_graph;

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
fn backend_renders_with_legend_topology_and_node_blocks() {
    let g = build();
    let out = render_repo_graph(&g);

    // Top-level structure.
    assert!(out.starts_with("[LEGEND]"), "missing LEGEND header:\n{out}");
    assert!(out.contains("[TOPOLOGY]"), "missing TOPOLOGY header:\n{out}");

    // Routes are entry kinds — their topology lines must carry the `*` sigil.
    let topology_section = out
        .split("[TOPOLOGY]")
        .nth(1)
        .and_then(|s| s.split("\n[").next())
        .unwrap_or("");
    assert!(
        topology_section.contains("route:") && topology_section.contains(" * > "),
        "expected at least one starred route line in topology:\n{topology_section}"
    );

    // Per-node block headers exist for the Route paths the parser extracted.
    assert!(
        out.contains("[route:/api/users]"),
        "missing /api/users route block:\n{out}"
    );
    // Route qnames preserve the original path syntax (`:id`); normalisation
    // only happens inside `HttpStackResolver` for cross-repo matching.
    assert!(
        out.contains("[route:/api/users/:id]"),
        "missing /api/users/:id route block:\n{out}"
    );

    // The handler functions appear too — modules-as-Go-packages plus their
    // top-level funcs. Go qnames use simple `package::Name` form.
    assert!(
        out.contains("[users::List]"),
        "missing handler function block:\n{out}"
    );

    // HANDLED_BY edges from Routes to handler funcs land in topology.
    assert!(
        out.contains("route:/api/users * > users::List"),
        "missing route → handler topology line:\n{out}"
    );

    // Confidence and kind labels render on every node block.
    assert!(out.contains(":kind       Route"));
    assert!(out.contains(":kind       Function"));
    assert!(out.contains(":confidence strong"));
}
