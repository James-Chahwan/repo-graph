use std::collections::HashMap;
use std::path::{Path, PathBuf};

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use repo_graph_code_domain::{CodeNav, FileParse, edge_category, node_kind, GRAPH_TYPE};
use repo_graph_core::{Confidence, Edge, NodeId, RepoId};
use repo_graph_graph::{
    CliInvocationResolver, EventBusResolver, GrpcStackResolver,
    GraphQLStackResolver, HttpStackResolver, MergedGraph, QueueStackResolver,
    SharedSchemaResolver, WebSocketStackResolver,
};

// ============================================================================
// Language detection
// ============================================================================

fn detect_language(path: &str) -> Option<&'static str> {
    let ext = Path::new(path).extension()?.to_str()?;
    match ext {
        "py" => Some("python"),
        "go" => Some("go"),
        "ts" | "tsx" => {
            if path.contains(".component.ts") {
                Some("angular")
            } else {
                Some("typescript")
            }
        }
        "js" | "jsx" => Some("typescript"),
        "vue" => Some("vue"),
        "rs" => Some("rust"),
        "java" | "kt" => Some("java"),
        "cs" => Some("csharp"),
        "rb" => Some("ruby"),
        "php" => Some("php"),
        "swift" => Some("swift"),
        "c" | "cpp" | "cc" | "cxx" | "h" | "hpp" => Some("c_cpp"),
        "scala" => Some("scala"),
        "clj" | "cljs" | "cljc" => Some("clojure"),
        "dart" => Some("dart"),
        "ex" | "exs" => Some("elixir"),
        "sol" => Some("solidity"),
        "tf" | "hcl" => Some("terraform"),
        "proto" => Some("proto"),
        _ => None,
    }
}

// ============================================================================
// Parse a single file
// ============================================================================

fn parse_one(
    source: &str,
    path: &str,
    lang: &str,
    repo: RepoId,
) -> Result<FileParse, String> {
    let module_qname = path_to_qname(path);
    match lang {
        "python" => repo_graph_parser_python::parse_file(source, path, &module_qname, repo)
            .map_err(|e| e.to_string()),
        "go" => repo_graph_parser_go::parse_file(source, path, &module_qname, "", repo)
            .map_err(|e| e.to_string()),
        "typescript" | "js" => repo_graph_parser_typescript::parse_file(source, path, &module_qname, repo)
            .map_err(|e| e.to_string()),
        "rust" => repo_graph_parser_rust::parse_file(source, path, &module_qname, repo)
            .map_err(|e| e.to_string()),
        "java" => repo_graph_parser_java::parse_file(source, path, &module_qname, repo)
            .map_err(|e| e.to_string()),
        "csharp" => repo_graph_parser_csharp::parse_file(source, path, &module_qname, repo)
            .map_err(|e| e.to_string()),
        "ruby" => repo_graph_parser_ruby::parse_file(source, path, &module_qname, repo)
            .map_err(|e| e.to_string()),
        "php" => repo_graph_parser_php::parse_file(source, path, &module_qname, repo)
            .map_err(|e| e.to_string()),
        "swift" => repo_graph_parser_swift::parse_file(source, path, &module_qname, repo)
            .map_err(|e| e.to_string()),
        "c_cpp" => {
            let is_cpp = matches!(
                Path::new(path).extension().and_then(|e| e.to_str()),
                Some("cpp" | "cc" | "cxx" | "hpp")
            );
            repo_graph_parser_c_cpp::parse_file(source, path, &module_qname, is_cpp, repo)
                .map_err(|e| e.to_string())
        }
        "scala" => repo_graph_parser_scala::parse_file(source, path, &module_qname, repo)
            .map_err(|e| e.to_string()),
        "clojure" => repo_graph_parser_clojure::parse_file(source, path, &module_qname, repo)
            .map_err(|e| e.to_string()),
        "dart" => repo_graph_parser_dart::parse_file(source, path, &module_qname, repo)
            .map_err(|e| e.to_string()),
        "elixir" => repo_graph_parser_elixir::parse_file(source, path, &module_qname, repo)
            .map_err(|e| e.to_string()),
        "solidity" => repo_graph_parser_solidity::parse_file(source, path, &module_qname, repo)
            .map_err(|e| e.to_string()),
        "terraform" => repo_graph_parser_terraform::parse_file(source, path, &module_qname, repo)
            .map_err(|e| e.to_string()),
        "react" => repo_graph_parser_react::parse_file(source, path, &module_qname, repo)
            .map_err(|e| e.to_string()),
        "angular" => repo_graph_parser_angular::parse_file(source, path, &module_qname, repo)
            .map_err(|e| e.to_string()),
        "vue" => repo_graph_parser_vue::parse_file(source, path, &module_qname, repo)
            .map_err(|e| e.to_string()),
        _ => Err(format!("unsupported language: {lang}")),
    }
}

// ============================================================================
// Cross-cutting extractors — run on every parsed file and merge into its
// FileParse. These are pattern-based and language-agnostic (grpc-client,
// queue consumer/producer, CLI command/invocation, websocket handler/client,
// event emitter/handler, GraphQL operation/resolver).
// ============================================================================

fn apply_cross_cutting_extractors(
    fp: &mut FileParse,
    source: &str,
    path: &str,
    lang: &str,
    module_id: NodeId,
    repo: RepoId,
) {
    use repo_graph_code_extractors::{
        cli, eventbus, graphql, grpc, queues, ts_routes, websocket,
    };

    macro_rules! run {
        ($call:expr) => {{
            let out = $call;
            fp.nodes.extend(out.nodes);
            merge_nav(&mut fp.nav, out.nav);
        }};
    }

    run!(queues::extract_queue_consumer_nodes(source, module_id, repo));
    run!(queues::extract_queue_producer_nodes(source, module_id, repo));
    run!(cli::extract_cli_command_nodes(source, module_id, repo));
    run!(cli::extract_cli_invocation_nodes(source, module_id, repo));
    run!(websocket::extract_ws_handler_nodes(source, module_id, repo));
    run!(websocket::extract_ws_client_nodes(source, module_id, repo));
    run!(eventbus::extract_event_emitter_nodes(source, module_id, repo));
    run!(eventbus::extract_event_handler_nodes(source, module_id, repo));
    run!(graphql::extract_graphql_operation_nodes(source, module_id, repo));
    run!(graphql::extract_graphql_resolver_nodes(source, module_id, repo));
    run!(grpc::extract_grpc_client_nodes(source, module_id, repo));

    // Language-gated: backend HTTP routes for JS/TS-family files (Express,
    // Koa, Hono, Next.js file-based routing, etc.).
    if matches!(lang, "typescript" | "react" | "angular" | "vue") {
        run!(ts_routes::extract_ts_backend_routes(
            source, path, module_id, repo
        ));
    }
}

// ============================================================================
// Test-edge post-pass — match test modules to the modules they test.
// Port of the v0.2.0 `test_edges.py` post-pass. Detects test modules by qname
// (path-derived) and emits TESTS edges (category 7) to same-repo modules whose
// name matches after stripping test prefix/suffix.
// ============================================================================

fn emit_tests_edges(merged: &mut MergedGraph) {
    use std::collections::HashMap;

    // Bucket modules by their last qname segment — then disambiguate by the
    // parent path. Two modules with the same tail in different packages of a
    // monorepo (`apps/web/utils` vs `packages/ui/utils`) share a bucket but
    // win on prefix distance to the test module individually.
    let mut modules_by_tail: HashMap<String, Vec<(NodeId, String)>> = HashMap::new();
    let mut module_info: Vec<(NodeId, String)> = Vec::new();

    for g in &merged.graphs {
        for n in &g.nodes {
            if g.nav.kind_by_id.get(&n.id).copied() != Some(node_kind::MODULE) {
                continue;
            }
            let Some(qname) = g.nav.qname_by_id.get(&n.id) else {
                continue;
            };
            module_info.push((n.id, qname.clone()));
            if let Some(tail) = qname.rsplit("::").next() {
                modules_by_tail
                    .entry(tail.to_string())
                    .or_default()
                    .push((n.id, qname.clone()));
            }
        }
    }

    for (from_id, qname) in &module_info {
        if !is_test_qname(qname) {
            continue;
        }
        let Some(tail) = qname.rsplit("::").next() else {
            continue;
        };
        let stripped = strip_test_affixes(tail);
        if stripped.is_empty() || stripped == tail {
            continue;
        }
        let Some(candidates) = modules_by_tail.get(stripped) else {
            continue;
        };
        for to_id in select_test_targets(*from_id, qname, candidates) {
            merged.cross_edges.push(Edge {
                from: *from_id,
                to: to_id,
                category: edge_category::TESTS,
                confidence: Confidence::Strong,
            });
        }
    }
}

/// Pick which candidate modules the test qname is most likely testing.
/// Ranks by longest common package prefix with the test qname, breaks ties
/// by keeping them all, and caps at `MAX_TEST_TARGETS` to bound the
/// cross-product explosion monorepos would otherwise trigger (F1 in the
/// v0.4.11 sweep report: vercel/next.js emitted 818k TESTS edges with
/// tail-only matching).
fn select_test_targets(
    from_id: NodeId,
    test_qname: &str,
    candidates: &[(NodeId, String)],
) -> Vec<NodeId> {
    const MAX_TEST_TARGETS: usize = 3;

    let test_parent: Vec<&str> = qname_parent_segments(test_qname);

    let mut scored: Vec<(usize, NodeId)> = candidates
        .iter()
        .filter(|(id, _)| *id != from_id)
        .map(|(id, qn)| {
            let cand_parent = qname_parent_segments(qn);
            (common_prefix_len(&test_parent, &cand_parent), *id)
        })
        .collect();

    if scored.is_empty() {
        return Vec::new();
    }

    let max_score = scored.iter().map(|(s, _)| *s).max().unwrap_or(0);
    // Only take candidates that reach the max common prefix. If max is 0 —
    // i.e. no candidate shares even one package segment — fall through with
    // all zero-score candidates but still capped, so we don't regress the
    // flat-repo case where cross-package prefix doesn't exist.
    scored.retain(|(s, _)| *s == max_score);
    scored.truncate(MAX_TEST_TARGETS);
    scored.into_iter().map(|(_, id)| id).collect()
}

fn qname_parent_segments(qname: &str) -> Vec<&str> {
    let mut segs: Vec<&str> = qname.split("::").collect();
    segs.pop();
    segs
}

fn common_prefix_len(a: &[&str], b: &[&str]) -> usize {
    a.iter().zip(b.iter()).take_while(|(x, y)| x == y).count()
}

// ============================================================================
// Path-based confidence downgrade — port of the v0.2.0 behaviour where nodes
// derived from test/fixture/example/e2e paths get downgraded to Weak. Matching
// is segment-based against the `::`-separated qname (which is path-derived for
// modules and carries the module prefix for definitions inside them).
// ============================================================================
//
// Routes carry synthetic qnames (`route:METHOD:/path`) that don't encode a
// path, so they are left at their extractor-assigned confidence.

fn downgrade_test_paths(merged: &mut MergedGraph) {
    for g in &mut merged.graphs {
        for n in &mut g.nodes {
            let Some(qname) = g.nav.qname_by_id.get(&n.id) else {
                continue;
            };
            if qname.starts_with("route:") {
                continue;
            }
            if qname_is_noncritical_path(qname) {
                n.confidence = Confidence::Weak;
            }
        }
    }
}

// ============================================================================
// Match-based confidence tiering — after the resolvers run, ROUTE and ENDPOINT
// nodes that are *not* referenced by any HTTP_CALLS cross-edge drop from
// Strong to Medium. A matched pair is evidence that the node participates in
// real cross-stack traffic; an unmatched one might be dead, typo'd, or simply
// not yet wired. Leaves already-Weak (path-downgraded) nodes alone.
// ============================================================================

fn demote_unmatched_http_nodes(merged: &mut MergedGraph) {
    use std::collections::HashSet;

    let mut matched: HashSet<NodeId> = HashSet::new();
    for e in &merged.cross_edges {
        if e.category == edge_category::HTTP_CALLS {
            matched.insert(e.from);
            matched.insert(e.to);
        }
    }

    for g in &mut merged.graphs {
        for n in &mut g.nodes {
            let kind = g.nav.kind_by_id.get(&n.id).copied();
            let is_http_node = matches!(kind, Some(k) if k == node_kind::ROUTE || k == node_kind::ENDPOINT);
            if !is_http_node {
                continue;
            }
            if matches!(n.confidence, Confidence::Weak) {
                continue;
            }
            if !matched.contains(&n.id) {
                n.confidence = Confidence::Medium;
            }
        }
    }
}

fn qname_is_noncritical_path(qname: &str) -> bool {
    const NONCRITICAL: &[&str] = &[
        "tests", "test", "__tests__", "spec", "specs",
        "fixtures", "fixture", "examples", "example",
        "e2e", "__mocks__", "mocks", "testdata",
    ];
    qname
        .split("::")
        .any(|seg| {
            let lowered = seg.to_ascii_lowercase();
            NONCRITICAL.contains(&lowered.as_str())
        })
}

fn is_test_qname(qname: &str) -> bool {
    // Path-derived qname uses `::` as separator. Match the conventions from the
    // v0.2.0 Python pipeline: Python tests/, test_ prefix, _test suffix; JS/TS
    // __tests__/, .test / .spec; Go _test; Ruby spec/, _spec.
    let lowered = qname.to_ascii_lowercase();
    if lowered.contains("::tests::")
        || lowered.contains("::test::")
        || lowered.contains("::__tests__::")
        || lowered.contains("::spec::")
        || lowered.starts_with("tests::")
        || lowered.starts_with("test::")
        || lowered.starts_with("spec::")
    {
        return true;
    }
    let Some(tail) = qname.rsplit("::").next() else {
        return false;
    };
    let t = tail.to_ascii_lowercase();
    t.starts_with("test_")
        || t.ends_with("_test")
        || t.ends_with("_spec")
        || t.ends_with(".test")
        || t.ends_with(".spec")
}

fn strip_test_affixes(name: &str) -> &str {
    let lowered = name.to_ascii_lowercase();
    if let Some(rest) = lowered.strip_prefix("test_") {
        return &name[name.len() - rest.len()..];
    }
    for suffix in ["_test", "_spec", ".test", ".spec"] {
        if lowered.ends_with(suffix) {
            return &name[..name.len() - suffix.len()];
        }
    }
    name
}

fn merge_nav(dst: &mut CodeNav, src: CodeNav) {
    dst.name_by_id.extend(src.name_by_id);
    dst.qname_by_id.extend(src.qname_by_id);
    dst.kind_by_id.extend(src.kind_by_id);
    dst.parent_of.extend(src.parent_of);
    for (k, v) in src.children_of {
        dst.children_of.entry(k).or_default().extend(v);
    }
}

fn path_to_qname(path: &str) -> String {
    Path::new(path)
        .with_extension("")
        .to_string_lossy()
        .replace(['/', '\\'], "::")
}

// ============================================================================
// Full repo generation
// ============================================================================

fn walk_source_files(root: &Path) -> Vec<(String, String)> {
    let mut files = Vec::new();
    walk_dir(root, root, &mut files);
    files
}

fn walk_dir(root: &Path, dir: &Path, files: &mut Vec<(String, String)>) {
    let Ok(entries) = std::fs::read_dir(dir) else { return };
    for entry in entries.flatten() {
        let path = entry.path();
        let name = entry.file_name().to_string_lossy().to_string();
        if name.starts_with('.')
            || matches!(
                name.as_str(),
                "node_modules" | "vendor" | "__pycache__" | "target" | "dist" | "build"
            )
        {
            continue;
        }
        if path.is_dir() {
            walk_dir(root, &path, files);
        } else if path.is_file() {
            let rel = path.strip_prefix(root).unwrap_or(&path);
            let rel_str = rel.to_string_lossy().to_string();
            if detect_language(&rel_str).is_some()
                && let Ok(source) = std::fs::read_to_string(&path)
            {
                files.push((rel_str, source));
            }
        }
    }
}

fn generate_repo_inner(repo_path: &str) -> Result<GenerateResult, String> {
    let root = PathBuf::from(repo_path);
    if !root.is_dir() {
        return Err(format!("not a directory: {repo_path}"));
    }

    let repo = RepoId::from_canonical(&format!("file://{repo_path}"));
    let files = walk_source_files(&root);

    let mut parses_by_lang: HashMap<&str, Vec<FileParse>> = HashMap::new();
    let mut proto_parses = Vec::new();
    let mut parse_errors = Vec::new();

    for (path, source) in &files {
        let Some(lang) = detect_language(path) else { continue };

        if lang == "proto" {
            let module_id = NodeId::from_parts(
                GRAPH_TYPE,
                repo,
                node_kind::MODULE,
                &path_to_qname(path),
            );
            let svc_nodes =
                repo_graph_code_extractors::grpc::extract_grpc_service_nodes(source, module_id, repo);
            let fp = FileParse {
                nodes: svc_nodes.nodes,
                nav: svc_nodes.nav,
                ..Default::default()
            };
            proto_parses.push(fp);
            continue;
        }

        match parse_one(source, path, lang, repo) {
            Ok(mut fp) => {
                let module_id = NodeId::from_parts(
                    GRAPH_TYPE,
                    repo,
                    node_kind::MODULE,
                    &path_to_qname(path),
                );
                apply_cross_cutting_extractors(&mut fp, source, path, lang, module_id, repo);
                parses_by_lang.entry(lang).or_default().push(fp);
            }
            Err(e) => {
                parse_errors.push(format!("{path}: {e}"));
            }
        }
    }

    let mut graphs = Vec::new();

    for (lang, parses) in parses_by_lang {
        let graph = match lang {
            "python" => repo_graph_graph::build_python(repo, parses),
            "go" => repo_graph_graph::build_go(repo, parses),
            // Languages whose parsers emit dotted or already-`::` import paths.
            // build_dotted reuses the Python resolver (replace is a no-op on
            // already-`::`). Java/C#/PHP pre-convert in the parser; Rust is
            // native `::`; Scala/Clojure/Elixir use dotted natively.
            "java" | "csharp" | "php" | "rust" | "scala" | "clojure" | "elixir" => {
                repo_graph_graph::build_dotted(repo, parses)
            }
            "ruby" => repo_graph_graph::build_ruby(repo, parses),
            // TS-family + languages whose imports are raw paths (dart
            // package:, swift framework, solidity ./foo.sol, terraform module
            // sources, c_cpp #include). Closure returns None → treated as
            // external; per-repo resolver injection is future work.
            _ => repo_graph_graph::build_typescript(repo, parses, |_, _| None),
        };
        match graph {
            Ok(g) => graphs.push(g),
            Err(e) => parse_errors.push(format!("{lang} graph: {e}")),
        }
    }

    if !proto_parses.is_empty()
        && let Ok(g) = repo_graph_graph::build_python(repo, proto_parses)
    {
        graphs.push(g);
    }

    let mut merged = MergedGraph::new(graphs);
    merged.run(&HttpStackResolver);
    merged.run(&GrpcStackResolver);
    merged.run(&QueueStackResolver);
    merged.run(&GraphQLStackResolver);
    merged.run(&WebSocketStackResolver);
    merged.run(&EventBusResolver);
    merged.run(&SharedSchemaResolver);
    merged.run(&CliInvocationResolver);

    downgrade_test_paths(&mut merged);
    demote_unmatched_http_nodes(&mut merged);
    emit_tests_edges(&mut merged);

    let total_nodes: usize = merged.graphs.iter().map(|g| g.nodes.len()).sum();
    let total_edges: usize = merged.graphs.iter().map(|g| g.edges.len()).sum::<usize>()
        + merged.cross_edges.len();

    Ok(GenerateResult {
        merged,
        total_nodes,
        total_edges,
        parse_errors,
    })
}

struct GenerateResult {
    merged: MergedGraph,
    #[allow(dead_code)]
    total_nodes: usize,
    #[allow(dead_code)]
    total_edges: usize,
    parse_errors: Vec<String>,
}

// ============================================================================
// PyO3 wrappers
// ============================================================================

#[pyclass]
struct PyGraph {
    merged: MergedGraph,
}

#[pymethods]
impl PyGraph {
    fn node_count(&self) -> usize {
        self.merged.graphs.iter().map(|g| g.nodes.len()).sum()
    }

    fn edge_count(&self) -> usize {
        self.merged.graphs.iter().map(|g| g.edges.len()).sum::<usize>()
            + self.merged.cross_edges.len()
    }

    fn cross_edge_count(&self) -> usize {
        self.merged.cross_edges.len()
    }

    fn dense_text(&self) -> String {
        repo_graph_projection_text::render_merged(&self.merged)
    }

    fn nodes_json(&self) -> PyResult<String> {
        let mut out = String::from("[");
        let mut first = true;
        for g in &self.merged.graphs {
            for n in &g.nodes {
                let kind = g.nav.kind_by_id.get(&n.id).map(|k| k.0).unwrap_or(0);
                let name = g.nav.name_by_id.get(&n.id).map(|s| s.as_str()).unwrap_or("");
                let qname = g.nav.qname_by_id.get(&n.id).map(|s| s.as_str()).unwrap_or("");
                let conf = match n.confidence {
                    Confidence::Strong => "strong",
                    Confidence::Medium => "medium",
                    Confidence::Weak => "weak",
                };
                if !first {
                    out.push(',');
                }
                first = false;
                out.push_str(&format!(
                    r#"{{"id":{},"kind":{},"name":"{}","qname":"{}","confidence":"{}"}}"#,
                    n.id.0,
                    kind,
                    escape_json(name),
                    escape_json(qname),
                    conf,
                ));
            }
        }
        out.push(']');
        Ok(out)
    }

    fn edges_json(&self) -> PyResult<String> {
        let mut out = String::from("[");
        let mut first = true;
        let all_edges = self.merged.graphs.iter().flat_map(|g| g.edges.iter())
            .chain(self.merged.cross_edges.iter());
        for e in all_edges {
            if !first {
                out.push(',');
            }
            first = false;
            out.push_str(&format!(
                r#"{{"from":{},"to":{},"category":{}}}"#,
                e.from.0, e.to.0, e.category.0,
            ));
        }
        out.push(']');
        Ok(out)
    }

    fn neighbours(&self, node_id: u64) -> Vec<(u64, u32)> {
        let id = NodeId(node_id);
        let mut result = Vec::new();
        for g in &self.merged.graphs {
            for e in &g.edges {
                if e.from == id {
                    result.push((e.to.0, e.category.0));
                }
            }
        }
        for e in &self.merged.cross_edges {
            if e.from == id {
                result.push((e.to.0, e.category.0));
            }
        }
        result
    }

    fn activate(&self, seed_ids: Vec<u64>, top_k: Option<usize>) -> Vec<(u64, f64)> {
        let seeds: Vec<NodeId> = seed_ids.into_iter().map(NodeId).collect();
        let mut config = repo_graph_graph::code_activation_defaults();
        if let Some(k) = top_k {
            config.top_k = k;
        }
        let result = self.merged.activate(&seeds, &config);
        result.scores.iter().map(|(id, score)| (id.0, *score)).collect()
    }

    fn find_node(&self, name: &str) -> Option<u64> {
        for g in &self.merged.graphs {
            for (id, n) in &g.nav.name_by_id {
                if n == name {
                    return Some(id.0);
                }
            }
        }
        None
    }

    fn find_nodes_by_qname(&self, pattern: &str) -> Vec<u64> {
        let mut result = Vec::new();
        for g in &self.merged.graphs {
            for (id, q) in &g.nav.qname_by_id {
                if q.contains(pattern) {
                    result.push(id.0);
                }
            }
        }
        result
    }
}

fn escape_json(s: &str) -> String {
    s.replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
        .replace('\t', "\\t")
}

// ============================================================================
// Module functions
// ============================================================================

#[pyfunction]
fn generate(repo_path: &str) -> PyResult<PyGraph> {
    let result = generate_repo_inner(repo_path)
        .map_err(PyValueError::new_err)?;

    if !result.parse_errors.is_empty() && result.merged.graphs.iter().all(|g| g.nodes.is_empty()) {
        return Err(PyValueError::new_err(format!(
            "no nodes produced; {} parse errors: {}",
            result.parse_errors.len(),
            result.parse_errors.first().unwrap_or(&String::new())
        )));
    }

    Ok(PyGraph {
        merged: result.merged,
    })
}

#[pyfunction]
fn parse_file_to_json(source: &str, path: &str, lang: &str) -> PyResult<String> {
    let repo = RepoId(1);
    let fp = parse_one(source, path, lang, repo)
        .map_err(PyValueError::new_err)?;

    let mut out = String::from("[");
    let mut first = true;
    for n in &fp.nodes {
        let kind = fp.nav.kind_by_id.get(&n.id).map(|k| k.0).unwrap_or(0);
        let name = fp.nav.name_by_id.get(&n.id).map(|s| s.as_str()).unwrap_or("");
        let qname = fp.nav.qname_by_id.get(&n.id).map(|s| s.as_str()).unwrap_or("");
        let conf = match n.confidence {
            Confidence::Strong => "strong",
            Confidence::Medium => "medium",
            Confidence::Weak => "weak",
        };
        if !first {
            out.push(',');
        }
        first = false;
        out.push_str(&format!(
            r#"{{"id":{},"kind":{},"name":"{}","qname":"{}","confidence":"{}"}}"#,
            n.id.0,
            kind,
            escape_json(name),
            escape_json(qname),
            conf,
        ));
    }
    out.push(']');
    Ok(out)
}

#[pyfunction]
fn version() -> &'static str {
    "0.4.10"
}

// ============================================================================
// Module definition
// ============================================================================

#[pymodule]
fn repo_graph_py(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(generate, m)?)?;
    m.add_function(wrap_pyfunction!(parse_file_to_json, m)?)?;
    m.add_function(wrap_pyfunction!(version, m)?)?;
    m.add_class::<PyGraph>()?;
    Ok(())
}
