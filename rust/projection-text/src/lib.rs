//! repo-graph-projection-text — dense text projection of a `RepoGraph` or
//! `MergedGraph`, following the sigil notation in `reference_format_spec.md`.
//!
//! v0.4.7 compression:
//! - `[SCOPES]` — common qname prefixes abbreviated (e.g. `SC = Server::Controllers`)
//! - `[DEFAULTS]` — majority kind/confidence declared once, nodes only emit deviations
//! - Module file collapse — multi-file modules render `:files` instead of N×`:code`+`:position`

use std::collections::{HashMap, HashSet};
use std::fmt::Write;

use repo_graph_code_domain::{cell_type, edge_category, node_kind};
use repo_graph_core::{
    CellPayload, CellTypeId, Confidence, Edge, EdgeCategoryId, Node, NodeId, NodeKindId,
};
use repo_graph_graph::{MergedGraph, RepoGraph};

const LEGEND: &str = "\
[LEGEND]
> depends    * entry point    @ external";

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
    let scopes = build_scopes(graphs);
    let defaults = compute_defaults(graphs);

    let mut out = String::new();
    out.push_str(LEGEND);
    out.push('\n');

    if !scopes.is_empty() {
        out.push('\n');
        out.push_str("[SCOPES]\n");
        for (alias, prefix) in &scopes {
            let _ = writeln!(out, "{alias} = {prefix}");
        }
    }

    if defaults.kind.is_some() || defaults.confidence.is_some() {
        out.push('\n');
        out.push_str("[DEFAULTS]\n");
        if let Some(k) = defaults.kind {
            let _ = writeln!(out, ":kind       {}", kind_name(k));
        }
        if let Some(c) = defaults.confidence {
            let _ = writeln!(out, ":confidence {}", confidence_name(c));
        }
    }

    out.push('\n');
    render_topology(&mut out, graphs, cross_edges, &scopes);
    out.push('\n');
    render_nodes(&mut out, graphs, &scopes, &defaults);
    out
}

// ============================================================================
// Scopes — common qname prefix abbreviation
// ============================================================================

const MAX_SCOPES: usize = 25;
const MIN_SCOPE_USES: usize = 3;
const MIN_SCOPE_LEN: usize = 10;

fn build_scopes(graphs: &[&RepoGraph]) -> Vec<(String, String)> {
    let mut prefix_counts: HashMap<&str, usize> = HashMap::new();

    for g in graphs {
        for q in g.nav.qname_by_id.values() {
            if let Some(idx) = q.rfind("::") {
                let prefix = &q[..idx];
                if prefix.len() >= MIN_SCOPE_LEN {
                    *prefix_counts.entry(prefix).or_default() += 1;
                }
            }
        }
    }

    let mut candidates: Vec<(&str, usize)> = prefix_counts
        .into_iter()
        .filter(|(_, c)| *c >= MIN_SCOPE_USES)
        .collect();

    candidates.sort_by_key(|&(p, c)| {
        let seg_count = p.matches("::").count() + 1;
        let alias_len = if seg_count == 1 { 2 } else { seg_count };
        let legend_cost = p.len() + alias_len + 3;
        let gross = c * (p.len() - alias_len);
        std::cmp::Reverse(gross.saturating_sub(legend_cost))
    });

    let mut used: HashSet<String> = HashSet::new();
    let mut scopes = Vec::new();

    for (prefix, _) in candidates.iter().take(MAX_SCOPES) {
        let alias = make_alias(prefix, &used);
        used.insert(alias.clone());
        scopes.push((alias, prefix.to_string()));
    }

    // Longer prefixes first so abbreviate() matches greedily.
    scopes.sort_by_key(|b| std::cmp::Reverse(b.1.len()));
    scopes
}

fn make_alias(prefix: &str, used: &HashSet<String>) -> String {
    let segments: Vec<&str> = prefix.split("::").collect();

    let base: String = if segments.len() == 1 {
        let s = segments[0];
        let mut chars = s.chars();
        let first = chars.next().unwrap_or('X').to_ascii_uppercase();
        let second = chars.next().unwrap_or('x').to_ascii_lowercase();
        format!("{first}{second}")
    } else {
        segments
            .iter()
            .filter_map(|s| s.chars().next())
            .map(|c| c.to_ascii_uppercase())
            .collect()
    };

    if !used.contains(&base) {
        return base;
    }

    if let Some(last) = segments.last()
        && let Some(c2) = last.chars().nth(1)
    {
        let extended = format!("{base}{}", c2.to_ascii_lowercase());
        if !used.contains(&extended) {
            return extended;
        }
    }

    for i in 2..=99 {
        let numbered = format!("{base}{i}");
        if !used.contains(&numbered) {
            return numbered;
        }
    }

    base
}

fn abbreviate(qname: &str, scopes: &[(String, String)]) -> String {
    for (alias, prefix) in scopes {
        if let Some(rest) = qname.strip_prefix(prefix.as_str()) {
            if rest.starts_with("::") {
                return format!("{alias}{rest}");
            }
            if rest.is_empty() {
                return alias.clone();
            }
        }
    }
    qname.to_string()
}

// ============================================================================
// Defaults — majority kind/confidence declared once
// ============================================================================

struct Defaults {
    kind: Option<NodeKindId>,
    confidence: Option<Confidence>,
}

fn compute_defaults(graphs: &[&RepoGraph]) -> Defaults {
    let mut kind_counts: HashMap<NodeKindId, usize> = HashMap::new();
    let mut conf_counts: HashMap<Confidence, usize> = HashMap::new();
    let mut total = 0usize;

    for g in graphs {
        for n in &g.nodes {
            total += 1;
            if let Some(k) = g.nav.kind_by_id.get(&n.id) {
                *kind_counts.entry(*k).or_default() += 1;
            }
            *conf_counts.entry(n.confidence).or_default() += 1;
        }
    }

    let threshold = total / 2;

    Defaults {
        kind: kind_counts
            .into_iter()
            .max_by_key(|(_, c)| *c)
            .filter(|(_, c)| *c > threshold)
            .map(|(k, _)| k),
        confidence: conf_counts
            .into_iter()
            .max_by_key(|(_, c)| *c)
            .filter(|(_, c)| *c > threshold)
            .map(|(c, _)| c),
    }
}

// ============================================================================
// Topology block
// ============================================================================

fn render_topology(
    out: &mut String,
    graphs: &[&RepoGraph],
    cross_edges: &[Edge],
    scopes: &[(String, String)],
) {
    out.push_str("[TOPOLOGY]\n");
    let mut lines: Vec<String> = Vec::new();

    for g in graphs {
        for e in &g.edges {
            if !is_depends_category(e.category) {
                continue;
            }
            if let Some(line) = edge_line(graphs, g, e, scopes) {
                lines.push(line);
            }
        }
    }

    for e in cross_edges {
        if !is_depends_category(e.category) {
            continue;
        }
        let Some(from_g) = find_owning_graph(graphs, e.from) else {
            continue;
        };
        if let Some(line) = edge_line(graphs, from_g, e, scopes) {
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

fn edge_line(
    graphs: &[&RepoGraph],
    src_g: &RepoGraph,
    e: &Edge,
    scopes: &[(String, String)],
) -> Option<String> {
    let src_qname = src_g.nav.qname_by_id.get(&e.from)?.as_str();
    let src_kind = src_g.nav.kind_by_id.get(&e.from).copied();
    let dst_qname = lookup_qname(graphs, e.to);

    let mut line = String::new();
    line.push_str(&abbreviate(src_qname, scopes));
    if src_kind.is_some_and(is_entry_kind) {
        line.push_str(" *");
    }
    line.push_str(" > ");
    match dst_qname {
        Some(q) => line.push_str(&abbreviate(q, scopes)),
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

// ============================================================================
// Node blocks
// ============================================================================

fn render_nodes(
    out: &mut String,
    graphs: &[&RepoGraph],
    scopes: &[(String, String)],
    defaults: &Defaults,
) {
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
        render_node_block(out, qname, node, g, scopes, defaults);
        out.push('\n');
    }
}

fn render_node_block(
    out: &mut String,
    qname: &str,
    n: &Node,
    g: &RepoGraph,
    scopes: &[(String, String)],
    defaults: &Defaults,
) {
    out.push('[');
    out.push_str(&abbreviate(qname, scopes));
    out.push(']');
    let kind = g.nav.kind_by_id.get(&n.id).copied();
    if kind.is_some_and(is_entry_kind) {
        out.push_str(" *");
    }
    out.push('\n');

    if let Some(k) = kind
        && defaults.kind != Some(k)
    {
        let _ = writeln!(out, ":kind       {}", kind_name(k));
    }
    if defaults.confidence != Some(n.confidence) {
        let _ = writeln!(out, ":confidence {}", confidence_name(n.confidence));
    }

    if kind == Some(node_kind::MODULE) && has_multi_file_code(n) {
        render_module_files(out, n);
    } else {
        for cell in &n.cells {
            render_cell(out, cell);
        }
    }
}

fn has_multi_file_code(n: &Node) -> bool {
    n.cells
        .iter()
        .filter(|c| c.kind == cell_type::CODE)
        .count()
        > 1
}

fn render_module_files(out: &mut String, n: &Node) {
    let mut files: Vec<String> = Vec::new();
    let mut other_cells: Vec<&repo_graph_core::Cell> = Vec::new();

    for cell in &n.cells {
        if cell.kind == cell_type::POSITION
            && let CellPayload::Json(j) = &cell.payload
            && let Some(file) = extract_filename(j)
        {
            files.push(file);
            continue;
        }
        if cell.kind == cell_type::CODE {
            continue;
        }
        other_cells.push(cell);
    }

    if !files.is_empty() {
        let _ = writeln!(out, ":files      {}", files.join(", "));
    }
    for cell in other_cells {
        render_cell(out, cell);
    }
}

fn extract_filename(json: &str) -> Option<String> {
    let marker = "\"file\":\"";
    let start = json.find(marker)? + marker.len();
    let end = json[start..].find('"')? + start;
    let path = &json[start..end];
    path.rsplit('/').next().map(|s| s.to_string())
}

fn render_cell(out: &mut String, cell: &repo_graph_core::Cell) {
    let label = cell_label(cell.kind);
    if cell.kind == cell_type::POSITION
        && let CellPayload::Json(j) = &cell.payload
    {
        let _ = writeln!(out, ":{:<10} {}", label, compact_position(j));
        return;
    }
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

fn compact_position(json: &str) -> String {
    let file = extract_json_str(json, "file").unwrap_or_default();
    let start = extract_json_num(json, "start_line").unwrap_or(0);
    let end = extract_json_num(json, "end_line").unwrap_or(0);
    if end > start {
        format!("{file}:{start}-{end}")
    } else {
        format!("{file}:{start}")
    }
}

fn extract_json_str<'a>(json: &'a str, key: &str) -> Option<&'a str> {
    let marker = format!("\"{key}\":\"");
    let start = json.find(&marker)? + marker.len();
    let end = json[start..].find('"')? + start;
    Some(&json[start..end])
}

fn extract_json_num(json: &str, key: &str) -> Option<u32> {
    let marker = format!("\"{key}\":");
    let start = json.find(&marker)? + marker.len();
    let num_str: String = json[start..].chars().take_while(|c| c.is_ascii_digit()).collect();
    num_str.parse().ok()
}

// ============================================================================
// Label / name helpers
// ============================================================================

fn cell_label(c: CellTypeId) -> &'static str {
    match c.0 {
        1 => "code",
        2 => "doc",
        3 => "position",
        4 => "intent",
        5 => "method",
        6 => "hit",
        7 => "test",
        8 => "attn",
        9 => "fail",
        10 => "constraint",
        11 => "decision",
        12 => "env",
        13 => "conv",
        14 => "vector",
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

    // --- v0.4.7 compression tests ---

    #[test]
    fn scopes_abbreviate_common_prefixes() {
        let repo = RepoId::from_canonical("test://scopes");
        let parent = NodeId::from_parts("code", repo, node_kind::MODULE, "Server::Controllers");
        let ids: Vec<NodeId> = (0..4)
            .map(|i| {
                NodeId::from_parts(
                    "code",
                    repo,
                    node_kind::FUNCTION,
                    &format!("Server::Controllers::handler_{i}"),
                )
            })
            .collect();

        let mut g = RepoGraph {
            repo,
            nodes: std::iter::once(Node {
                id: parent,
                repo,
                confidence: Confidence::Strong,
                cells: vec![],
            })
            .chain(ids.iter().map(|id| Node {
                id: *id,
                repo,
                confidence: Confidence::Strong,
                cells: vec![],
            }))
            .collect(),
            edges: ids
                .iter()
                .map(|id| Edge {
                    from: parent,
                    to: *id,
                    category: edge_category::CALLS,
                    confidence: Confidence::Strong,
                })
                .collect(),
            nav: Default::default(),
            symbols: Default::default(),
            unresolved_calls: Vec::new(),
            unresolved_refs: Vec::new(),
        };
        g.nav.record(
            parent,
            "Controllers",
            "Server::Controllers",
            node_kind::MODULE,
            None,
        );
        for (i, id) in ids.iter().enumerate() {
            g.nav.record(
                *id,
                &format!("handler_{i}"),
                &format!("Server::Controllers::handler_{i}"),
                node_kind::FUNCTION,
                Some(parent),
            );
        }

        let s = render_repo_graph(&g);
        assert!(s.contains("[SCOPES]"), "missing scopes section:\n{s}");
        assert!(
            s.contains("SC = Server::Controllers"),
            "missing scope alias:\n{s}"
        );
        assert!(
            s.contains("SC::handler_0"),
            "topology not abbreviated:\n{s}"
        );
        assert!(
            s.contains("[SC::handler_0]"),
            "node block not abbreviated:\n{s}"
        );
        assert!(
            !s.contains("[Server::Controllers::handler_0]"),
            "full qname should be abbreviated:\n{s}"
        );
    }

    #[test]
    fn defaults_omit_majority_kind_and_confidence() {
        let repo = RepoId::from_canonical("test://defaults");
        let mut g = RepoGraph {
            repo,
            nodes: Vec::new(),
            edges: vec![],
            nav: Default::default(),
            symbols: Default::default(),
            unresolved_calls: Vec::new(),
            unresolved_refs: Vec::new(),
        };

        // 5 strong Functions + 1 medium Module → Function and strong are defaults
        for i in 0..5 {
            let id = NodeId::from_parts("code", repo, node_kind::FUNCTION, &format!("f{i}"));
            g.nodes.push(Node {
                id,
                repo,
                confidence: Confidence::Strong,
                cells: vec![],
            });
            g.nav
                .record(id, &format!("f{i}"), &format!("f{i}"), node_kind::FUNCTION, None);
        }
        let mod_id = NodeId::from_parts("code", repo, node_kind::MODULE, "mod");
        g.nodes.push(Node {
            id: mod_id,
            repo,
            confidence: Confidence::Medium,
            cells: vec![],
        });
        g.nav
            .record(mod_id, "mod", "mod", node_kind::MODULE, None);

        let s = render_repo_graph(&g);
        assert!(s.contains("[DEFAULTS]"), "missing defaults:\n{s}");
        assert!(
            s.contains("[DEFAULTS]\n:kind       Function\n:confidence strong"),
            "defaults wrong:\n{s}"
        );
        // The Module node should still emit its kind (differs from default)
        assert!(
            s.contains(":kind       Module"),
            "non-default kind missing:\n{s}"
        );
        assert!(
            s.contains(":confidence medium"),
            "non-default confidence missing:\n{s}"
        );
        // Function nodes should NOT emit :kind or :confidence
        let f0_block = s.split("[f0]").nth(1).unwrap_or("");
        let f0_end = f0_block.find("\n\n").unwrap_or(f0_block.len());
        let f0_section = &f0_block[..f0_end];
        assert!(
            !f0_section.contains(":kind"),
            "default-kind function should omit :kind:\n{f0_section}"
        );
        assert!(
            !f0_section.contains(":confidence"),
            "default-confidence function should omit :confidence:\n{f0_section}"
        );
    }

    #[test]
    fn module_file_collapse() {
        let repo = RepoId::from_canonical("test://collapse");
        let mod_id = NodeId::from_parts("code", repo, node_kind::MODULE, "pkg");

        let g = RepoGraph {
            repo,
            nodes: vec![Node {
                id: mod_id,
                repo,
                confidence: Confidence::Strong,
                cells: vec![
                    Cell {
                        kind: cell_type::CODE,
                        payload: CellPayload::Text("package pkg".into()),
                    },
                    Cell {
                        kind: cell_type::POSITION,
                        payload: CellPayload::Json(
                            r#"{"file":"pkg/alpha.go","start_line":1,"end_line":50}"#.into(),
                        ),
                    },
                    Cell {
                        kind: cell_type::CODE,
                        payload: CellPayload::Text("package pkg".into()),
                    },
                    Cell {
                        kind: cell_type::POSITION,
                        payload: CellPayload::Json(
                            r#"{"file":"pkg/beta.go","start_line":1,"end_line":30}"#.into(),
                        ),
                    },
                ],
            }],
            edges: vec![],
            nav: Default::default(),
            symbols: Default::default(),
            unresolved_calls: Vec::new(),
            unresolved_refs: Vec::new(),
        };
        let mut gg = g;
        gg.nav
            .record(mod_id, "pkg", "pkg", node_kind::MODULE, None);

        let s = render_repo_graph(&gg);
        assert!(
            s.contains(":files      alpha.go, beta.go"),
            "module files not collapsed:\n{s}"
        );
        assert!(
            !s.contains(":code       package pkg"),
            "repeated code lines should be collapsed:\n{s}"
        );
    }

    #[test]
    fn scope_alias_collision_resolved() {
        let used: HashSet<String> = ["SC".to_string()].into_iter().collect();
        let alias = make_alias("Services::chat", &used);
        assert_ne!(alias, "SC", "should not collide with existing SC");
        assert!(
            alias.starts_with("SC"),
            "should extend from initials: {alias}"
        );
    }
}
