//! repo-graph-projection-text — dense text projection of a `RepoGraph` or
//! `MergedGraph`, following the sigil notation in `reference_format_spec.md`.
//!
//! Output shape:
//! ```text
//! [LEGEND]          sigils defined once per window
//! [TOPOLOGY]        entrypoint > callee lines (graph shape first)
//! [<qname>] *       per-node typed-cell blocks
//! :kind ...
//! :code ...
//! ```
//!
//! v0.4.5b ships `>` (depends/CALLS/HANDLED_BY/HTTP_CALLS), `*` (entry point /
//! Route / Endpoint), and `@` (external — target id not present in any known
//! graph's nav). Other sigils (`$`, `^`, `!`, `?`, `#`, `~`) wait on the cell
//! populators landing at v0.4.8; they stay in the LEGEND as a stable contract.
//!
//! Reads from `RepoGraph`'s owned form today. An `Archived`-side renderer will
//! land when a caller needs it; the owned and archived forms share the
//! `NodeLike`/`EdgeLike` traits, but the nav indices currently only exist on
//! the owned side (`MmapContainer` exposes them separately via `qname(id)` /
//! `kind(id)`, not as a full map).

use std::fmt::Write;

use repo_graph_code_domain::{edge_category, node_kind};
use repo_graph_core::{
    CellPayload, CellTypeId, Confidence, Edge, EdgeCategoryId, Node, NodeId, NodeKindId,
};
use repo_graph_graph::{MergedGraph, RepoGraph};

const LEGEND: &str = "[LEGEND]
> depends    * entry point    @ external
";

/// Render a single-repo graph.
pub fn render_repo_graph(g: &RepoGraph) -> String {
    let slice: &[&RepoGraph] = &[g];
    render(slice, &[])
}

/// Render a merged multi-repo graph with cross-repo edges (HTTP_CALLS, etc.).
pub fn render_merged(m: &MergedGraph) -> String {
    let graphs: Vec<&RepoGraph> = m.graphs.iter().collect();
    render(&graphs, &m.cross_edges)
}

fn render(graphs: &[&RepoGraph], cross_edges: &[Edge]) -> String {
    let mut out = String::new();
    out.push_str(LEGEND);
    out.push('\n');
    render_topology(&mut out, graphs, cross_edges);
    out.push('\n');
    render_nodes(&mut out, graphs);
    out
}

// ----------------------------------------------------------------------------
// Topology block
// ----------------------------------------------------------------------------

fn render_topology(out: &mut String, graphs: &[&RepoGraph], cross_edges: &[Edge]) {
    out.push_str("[TOPOLOGY]\n");
    let mut lines: Vec<String> = Vec::new();

    for g in graphs {
        for e in &g.edges {
            if !is_depends_category(e.category) {
                continue;
            }
            if let Some(line) = edge_line(graphs, g, e) {
                lines.push(line);
            }
        }
    }

    // Cross-repo edges: `from` belongs to whichever graph owns that id's nav.
    for e in cross_edges {
        if !is_depends_category(e.category) {
            continue;
        }
        let Some(from_g) = find_owning_graph(graphs, e.from) else {
            continue;
        };
        if let Some(line) = edge_line(graphs, from_g, e) {
            lines.push(line);
        }
    }

    lines.sort();
    lines.dedup();
    for l in lines {
        out.push_str(&l);
        out.push('\n');
    }
}

fn edge_line(graphs: &[&RepoGraph], src_g: &RepoGraph, e: &Edge) -> Option<String> {
    let src_qname = src_g.nav.qname_by_id.get(&e.from)?.as_str();
    let src_kind = src_g.nav.kind_by_id.get(&e.from).copied();
    let dst_qname = lookup_qname(graphs, e.to);

    let mut line = String::new();
    line.push_str(src_qname);
    if src_kind.is_some_and(is_entry_kind) {
        line.push_str(" *");
    }
    line.push_str(" > ");
    match dst_qname {
        Some(q) => line.push_str(q),
        None => {
            let _ = write!(&mut line, "@unresolved#{:x}", e.to.0);
        }
    }
    Some(line)
}

fn lookup_qname<'a>(graphs: &'a [&RepoGraph], id: NodeId) -> Option<&'a str> {
    for g in graphs {
        if let Some(q) = g.nav.qname_by_id.get(&id) {
            return Some(q.as_str());
        }
    }
    None
}

fn find_owning_graph<'a>(graphs: &'a [&'a RepoGraph], id: NodeId) -> Option<&'a RepoGraph> {
    graphs
        .iter()
        .copied()
        .find(|g| g.nav.qname_by_id.contains_key(&id))
}

fn is_depends_category(c: EdgeCategoryId) -> bool {
    c == edge_category::CALLS
        || c == edge_category::HANDLED_BY
        || c == edge_category::HTTP_CALLS
}

fn is_entry_kind(k: NodeKindId) -> bool {
    k == node_kind::ROUTE || k == node_kind::ENDPOINT
}

// ----------------------------------------------------------------------------
// Node blocks
// ----------------------------------------------------------------------------

fn render_nodes(out: &mut String, graphs: &[&RepoGraph]) {
    let mut items: Vec<(&str, &Node, &RepoGraph)> = Vec::new();
    for g in graphs {
        for n in &g.nodes {
            if let Some(q) = g.nav.qname_by_id.get(&n.id) {
                items.push((q.as_str(), n, *g));
            }
        }
    }
    items.sort_by_key(|(q, _, _)| *q);

    for (qname, node, g) in items {
        render_node_block(out, qname, node, g);
        out.push('\n');
    }
}

fn render_node_block(out: &mut String, qname: &str, n: &Node, g: &RepoGraph) {
    out.push('[');
    out.push_str(qname);
    out.push(']');
    let kind = g.nav.kind_by_id.get(&n.id).copied();
    if kind.is_some_and(is_entry_kind) {
        out.push_str(" *");
    }
    out.push('\n');

    if let Some(k) = kind {
        let _ = writeln!(out, ":kind       {}", kind_name(k));
    }
    let _ = writeln!(out, ":confidence {}", confidence_name(n.confidence));

    for cell in &n.cells {
        let label = cell_label(cell.kind);
        match &cell.payload {
            CellPayload::Text(t) => {
                let _ = writeln!(out, ":{:<10} {}", label, one_line_preview(t));
            }
            CellPayload::Json(j) => {
                let _ = writeln!(out, ":{:<10} {}", label, one_line_preview(j));
            }
            CellPayload::Bytes(b) => {
                let _ = writeln!(out, ":{:<10} <{} bytes>", label, b.len());
            }
        }
    }
}

fn cell_label(c: CellTypeId) -> &'static str {
    match c.0 {
        1 => "code",
        2 => "doc",
        3 => "position",
        4 => "intent",
        5 => "method",
        6 => "hit",
        _ => "cell",
    }
}

fn kind_name(k: NodeKindId) -> &'static str {
    match k.0 {
        1 => "Module",
        2 => "Class",
        3 => "Function",
        4 => "Method",
        5 => "Route",
        6 => "Package",
        7 => "Interface",
        8 => "Struct",
        9 => "Endpoint",
        _ => "Node",
    }
}

fn confidence_name(c: Confidence) -> &'static str {
    match c {
        Confidence::Strong => "strong",
        Confidence::Medium => "medium",
        Confidence::Weak => "weak",
    }
}

fn one_line_preview(s: &str) -> String {
    const MAX: usize = 120;
    let first = s.lines().next().unwrap_or("");
    let truncated: String = first.chars().take(MAX).collect();
    let multi_line = s.contains('\n');
    let over_len = first.chars().count() > MAX;
    if multi_line || over_len {
        format!("{truncated}…")
    } else {
        truncated
    }
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use repo_graph_core::{Cell, RepoId};

    fn mini_graph() -> RepoGraph {
        let repo = RepoId::from_canonical("test://mini");
        let mod_id = NodeId::from_parts("code", repo, node_kind::MODULE, "m::a");
        let fn_id = NodeId::from_parts("code", repo, node_kind::FUNCTION, "m::a::f");

        let mut g = RepoGraph {
            repo,
            nodes: vec![
                Node {
                    id: mod_id,
                    repo,
                    confidence: Confidence::Strong,
                    cells: vec![],
                },
                Node {
                    id: fn_id,
                    repo,
                    confidence: Confidence::Medium,
                    cells: vec![Cell {
                        kind: CellTypeId(1),
                        payload: CellPayload::Text("fn f() {}".into()),
                    }],
                },
            ],
            edges: vec![Edge {
                from: mod_id,
                to: fn_id,
                category: edge_category::CALLS,
                confidence: Confidence::Medium,
            }],
            nav: Default::default(),
            symbols: Default::default(),
            unresolved_calls: Vec::new(),
            unresolved_refs: Vec::new(),
        };
        g.nav.record(mod_id, "a", "m::a", node_kind::MODULE, None);
        g.nav
            .record(fn_id, "f", "m::a::f", node_kind::FUNCTION, Some(mod_id));
        g
    }

    #[test]
    fn render_has_legend_topology_and_node_blocks() {
        let g = mini_graph();
        let s = render_repo_graph(&g);
        assert!(s.contains("[LEGEND]"));
        assert!(s.contains("[TOPOLOGY]"));
        assert!(s.contains("m::a > m::a::f"));
        assert!(s.contains("[m::a]"));
        assert!(s.contains("[m::a::f]"));
        assert!(s.contains(":kind       Module"));
        assert!(s.contains(":kind       Function"));
        assert!(s.contains(":confidence strong"));
        assert!(s.contains(":confidence medium"));
        assert!(s.contains(":code       fn f() {}"));
    }

    #[test]
    fn entry_kind_gets_star_sigil() {
        let repo = RepoId::from_canonical("test://entry");
        let route_id = NodeId::from_parts("code", repo, node_kind::ROUTE, "route:/x");
        let fn_id = NodeId::from_parts("code", repo, node_kind::FUNCTION, "m::h");

        let mut g = RepoGraph {
            repo,
            nodes: vec![
                Node {
                    id: route_id,
                    repo,
                    confidence: Confidence::Strong,
                    cells: vec![],
                },
                Node {
                    id: fn_id,
                    repo,
                    confidence: Confidence::Strong,
                    cells: vec![],
                },
            ],
            edges: vec![Edge {
                from: route_id,
                to: fn_id,
                category: edge_category::HANDLED_BY,
                confidence: Confidence::Strong,
            }],
            nav: Default::default(),
            symbols: Default::default(),
            unresolved_calls: Vec::new(),
            unresolved_refs: Vec::new(),
        };
        g.nav
            .record(route_id, "/x", "route:/x", node_kind::ROUTE, None);
        g.nav
            .record(fn_id, "h", "m::h", node_kind::FUNCTION, None);

        let s = render_repo_graph(&g);
        assert!(
            s.contains("route:/x * > m::h"),
            "topology missing star sigil on route: {s}"
        );
        assert!(s.contains("[route:/x] *"), "node block missing star: {s}");
    }

    #[test]
    fn unresolved_target_renders_as_external() {
        let repo = RepoId::from_canonical("test://ext");
        let fn_id = NodeId::from_parts("code", repo, node_kind::FUNCTION, "m::caller");
        let ghost = NodeId(0xDEAD);

        let mut g = RepoGraph {
            repo,
            nodes: vec![Node {
                id: fn_id,
                repo,
                confidence: Confidence::Strong,
                cells: vec![],
            }],
            edges: vec![Edge {
                from: fn_id,
                to: ghost,
                category: edge_category::CALLS,
                confidence: Confidence::Weak,
            }],
            nav: Default::default(),
            symbols: Default::default(),
            unresolved_calls: Vec::new(),
            unresolved_refs: Vec::new(),
        };
        g.nav
            .record(fn_id, "caller", "m::caller", node_kind::FUNCTION, None);

        let s = render_repo_graph(&g);
        assert!(
            s.contains("m::caller > @unresolved#dead"),
            "external target not rendered: {s}"
        );
    }

    #[test]
    fn merged_graph_renders_cross_repo_edges() {
        // Two mini graphs — a frontend Endpoint and a backend Route — linked by
        // a cross-repo HTTP_CALLS edge. Confirms `render_merged` picks up
        // `merged.cross_edges` and both sides resolve their qnames.
        let be_repo = RepoId::from_canonical("test://be");
        let fe_repo = RepoId::from_canonical("test://fe");
        let route_id = NodeId::from_parts("code", be_repo, node_kind::ROUTE, "route:/api/x");
        let endpoint_id = NodeId::from_parts(
            "code",
            fe_repo,
            node_kind::ENDPOINT,
            "endpoint:GET:/api/x",
        );

        let mut be = RepoGraph {
            repo: be_repo,
            nodes: vec![Node {
                id: route_id,
                repo: be_repo,
                confidence: Confidence::Strong,
                cells: vec![],
            }],
            edges: vec![],
            nav: Default::default(),
            symbols: Default::default(),
            unresolved_calls: Vec::new(),
            unresolved_refs: Vec::new(),
        };
        be.nav
            .record(route_id, "/api/x", "route:/api/x", node_kind::ROUTE, None);

        let mut fe = RepoGraph {
            repo: fe_repo,
            nodes: vec![Node {
                id: endpoint_id,
                repo: fe_repo,
                confidence: Confidence::Medium,
                cells: vec![],
            }],
            edges: vec![],
            nav: Default::default(),
            symbols: Default::default(),
            unresolved_calls: Vec::new(),
            unresolved_refs: Vec::new(),
        };
        fe.nav.record(
            endpoint_id,
            "/api/x",
            "endpoint:GET:/api/x",
            node_kind::ENDPOINT,
            None,
        );

        let mut merged = MergedGraph::new(vec![be, fe]);
        merged.cross_edges.push(Edge {
            from: endpoint_id,
            to: route_id,
            category: edge_category::HTTP_CALLS,
            confidence: Confidence::Medium,
        });

        let s = render_merged(&merged);
        assert!(
            s.contains("endpoint:GET:/api/x * > route:/api/x"),
            "missing cross-repo topology line:\n{s}"
        );
        assert!(s.contains("[route:/api/x] *"));
        assert!(s.contains("[endpoint:GET:/api/x] *"));
    }

    #[test]
    fn one_line_preview_truncates_multiline() {
        let p = one_line_preview("first\nsecond");
        assert!(p.ends_with('…'));
        assert!(p.starts_with("first"));
    }
}
