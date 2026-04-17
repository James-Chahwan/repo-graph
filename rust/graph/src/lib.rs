//! repo-graph-graph — per-repo graph construction + resolver + traversal.
//!
//! Consumes `FileParse` outputs from the language parsers, merges them into a
//! single `RepoGraph` for the repo, resolves cross-file imports and calls
//! using a symbol table, and exposes BFS / neighbours / parent-chain.
//!
//! One entry point per parser — `build_python`, `build_go`, `build_typescript`
//! — because their import semantics differ (dotted qnames vs. stripped go.mod
//! paths vs. relative/bare module sources). The symbol-table + traversal
//! infrastructure is shared.
//!
//! v0.4.4b adds `MergedGraph` + `CrossGraphResolver` for cross-repo resolution.
//! The first resolver, `HttpStackResolver`, pairs frontend Endpoints with
//! backend Routes by (method, normalised path) and emits `HTTP_CALLS` edges.
//! Other stack resolvers (GraphQL, gRPC, queues, shared-schema) land at v0.4.10
//! against the same trait.

use std::collections::{HashMap, HashSet, VecDeque};

use repo_graph_code_domain::{
    CallQualifier, CallSite, CodeNav, FileParse, ImportStmt, ImportTarget, UnresolvedRef,
    cell_type, edge_category, node_kind,
};
use repo_graph_core::{
    Cell, CellPayload, Confidence, Edge, EdgeCategoryId, Node, NodeId, NodeKindId, RepoId,
};

// ============================================================================
// Output graph
// ============================================================================

#[derive(Debug)]
pub struct RepoGraph {
    pub repo: RepoId,
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
    pub nav: CodeNav,
    pub symbols: SymbolTable,
    /// Call sites left unresolved after cross-file resolution. Kept as a
    /// diagnostic surface (at v0.4.5 they also feed the dense-text `?` sigil).
    pub unresolved_calls: Vec<CallSite>,
    /// `UnresolvedRef`s the resolver couldn't bind. Same diagnostic role as
    /// `unresolved_calls`. v0.4.4 use case: gin route handler refs that point
    /// at packages the parser couldn't link to a known module.
    pub unresolved_refs: Vec<UnresolvedRef>,
}

/// Symbol index built during resolution. Everything keyed by node id so
/// consumers never re-parse qnames.
#[derive(Debug, Default)]
pub struct SymbolTable {
    /// Module qname (`"myapp::users"`) → module node id.
    pub module_by_qname: HashMap<String, NodeId>,
    /// Module node id → (top-level def name → def node id).
    /// Used for `from X import Y` resolution and for module-attribute calls.
    pub module_symbols: HashMap<NodeId, HashMap<String, NodeId>>,
    /// Class node id → (method name → method node id).
    pub class_methods: HashMap<NodeId, HashMap<String, NodeId>>,
    /// Module node id → (bound name in that module → target node id).
    /// Populated from resolved imports. Powers cross-file call resolution.
    pub module_import_bindings: HashMap<NodeId, HashMap<String, NodeId>>,
}

// ============================================================================
// Errors
// ============================================================================

#[derive(Debug, thiserror::Error)]
pub enum GraphError {
    #[error("module qname collision: {0}")]
    ModuleCollision(String),
}

// ============================================================================
// Public entry point
// ============================================================================

/// Build a per-repo Python graph from a set of file-parse outputs.
pub fn build_python(repo: RepoId, parses: Vec<FileParse>) -> Result<RepoGraph, GraphError> {
    let (mut g, all_imports, all_calls, all_refs) = merge_parses(repo, parses);
    build_symbol_table(&mut g);
    resolve_imports_python(&mut g, &all_imports);
    resolve_calls(&mut g, &all_calls, |_, _| None);
    resolve_refs(&mut g, &all_refs);
    Ok(g)
}

/// Build a per-repo Go graph. Go packages span multiple files — modules with
/// the same qname produce the same NodeId and their cells stack on one node.
pub fn build_go(repo: RepoId, parses: Vec<FileParse>) -> Result<RepoGraph, GraphError> {
    let (mut g, all_imports, all_calls, all_refs) = merge_parses(repo, parses);
    build_symbol_table(&mut g);
    resolve_imports_go(&mut g, &all_imports);
    resolve_calls(&mut g, &all_calls, |_, _| None);
    resolve_refs(&mut g, &all_refs);
    Ok(g)
}

/// Build a per-repo TypeScript graph. TS import sources are raw strings
/// (`./user`, `@angular/core`) that the caller resolves to module qnames via
/// `resolve_source`. Returning `None` treats the import as external (no edge).
pub fn build_typescript<R>(
    repo: RepoId,
    parses: Vec<FileParse>,
    resolve_source: R,
) -> Result<RepoGraph, GraphError>
where
    R: Fn(&str, &str) -> Option<String>,
{
    let (mut g, all_imports, all_calls, all_refs) = merge_parses(repo, parses);
    build_symbol_table(&mut g);
    resolve_imports_ts(&mut g, &all_imports, &resolve_source);
    resolve_calls(&mut g, &all_calls, |_, _| None);
    resolve_refs(&mut g, &all_refs);
    Ok(g)
}

// ============================================================================
// Shared merge: multi-file modules with the same NodeId collapse — their cells
// stack on a single Module node (Go packages, TS re-exports, etc.).
// ============================================================================

fn merge_parses(
    repo: RepoId,
    parses: Vec<FileParse>,
) -> (
    RepoGraph,
    Vec<ImportStmt>,
    Vec<CallSite>,
    Vec<UnresolvedRef>,
) {
    let mut g = RepoGraph {
        repo,
        nodes: Vec::new(),
        edges: Vec::new(),
        nav: CodeNav::default(),
        symbols: SymbolTable::default(),
        unresolved_calls: Vec::new(),
        unresolved_refs: Vec::new(),
    };

    let mut all_imports: Vec<ImportStmt> = Vec::new();
    let mut all_calls: Vec<CallSite> = Vec::new();
    let mut all_refs: Vec<UnresolvedRef> = Vec::new();
    let mut index: HashMap<NodeId, usize> = HashMap::new();

    for p in parses {
        for n in p.nodes {
            if let Some(&idx) = index.get(&n.id) {
                // Duplicate NodeId — append cells onto the existing node.
                append_cells(&mut g.nodes[idx].cells, n.cells);
            } else {
                index.insert(n.id, g.nodes.len());
                g.nodes.push(n);
            }
        }
        g.edges.extend(p.edges);
        merge_nav(&mut g.nav, p.nav);
        all_imports.extend(p.imports);
        all_calls.extend(p.calls);
        all_refs.extend(p.refs);
    }

    (g, all_imports, all_calls, all_refs)
}

fn append_cells(existing: &mut Vec<Cell>, incoming: Vec<Cell>) {
    existing.extend(incoming);
}

// ============================================================================
// Nav merge
// ============================================================================

fn merge_nav(dst: &mut CodeNav, src: CodeNav) {
    dst.name_by_id.extend(src.name_by_id);
    dst.qname_by_id.extend(src.qname_by_id);
    dst.kind_by_id.extend(src.kind_by_id);
    dst.parent_of.extend(src.parent_of);
    for (k, v) in src.children_of {
        dst.children_of.entry(k).or_default().extend(v);
    }
}

// ============================================================================
// Symbol table
// ============================================================================

fn build_symbol_table(g: &mut RepoGraph) {
    for (id, qname) in &g.nav.qname_by_id {
        if g.nav.kind_by_id.get(id) == Some(&node_kind::MODULE) {
            g.symbols.module_by_qname.insert(qname.clone(), *id);
        }
    }

    // module_symbols: for each module, bare name → node id for its top-level defs.
    // Walk children_of; if parent kind == MODULE, child goes in module_symbols.
    for (parent, children) in &g.nav.children_of {
        let parent_kind = g.nav.kind_by_id.get(parent).copied();
        if parent_kind == Some(node_kind::MODULE) {
            let entry = g.symbols.module_symbols.entry(*parent).or_default();
            for child in children {
                if let Some(name) = g.nav.name_by_id.get(child) {
                    entry.insert(name.clone(), *child);
                }
            }
        } else if parent_kind == Some(node_kind::CLASS) || parent_kind == Some(node_kind::STRUCT) {
            let entry = g.symbols.class_methods.entry(*parent).or_default();
            for child in children {
                if let Some(name) = g.nav.name_by_id.get(child)
                    && g.nav.kind_by_id.get(child) == Some(&node_kind::METHOD)
                {
                    entry.insert(name.clone(), *child);
                }
            }
        }
    }
}

// ============================================================================
// Import resolution
// ============================================================================

fn resolve_imports_python(g: &mut RepoGraph, imports: &[ImportStmt]) {
    for stmt in imports {
        let Some(from_mod_id) = g
            .symbols
            .module_by_qname
            .get(&stmt.from_module)
            .copied()
        else {
            continue;
        };

        match &stmt.target {
            ImportTarget::Module { path, alias } => {
                // `import foo.bar` — convert `.` → `::` and look up by qname.
                let target_qname = path.replace('.', "::");
                if let Some(target_id) = g.symbols.module_by_qname.get(&target_qname).copied() {
                    push_edge(g, from_mod_id, target_id, edge_category::IMPORTS);
                    let bound_name = alias.clone().unwrap_or_else(|| {
                        path.split('.').next().unwrap_or(path).to_string()
                    });
                    g.symbols
                        .module_import_bindings
                        .entry(from_mod_id)
                        .or_default()
                        .insert(bound_name, target_id);
                }
            }
            ImportTarget::Symbol { module, name, alias, level } => {
                let target_module_qname = resolve_module_reference(&stmt.from_module, module, *level);

                // Try `module::name` as a submodule first — matches Python's
                // `from pkg import mod` → edge to pkg.mod if submodule exists.
                let submodule_qname = if target_module_qname.is_empty() {
                    name.clone()
                } else {
                    format!("{target_module_qname}::{name}")
                };

                let bound = alias.clone().unwrap_or_else(|| name.clone());

                if let Some(submodule_id) = g.symbols.module_by_qname.get(&submodule_qname).copied()
                {
                    // `from pkg import mod` where mod is a submodule.
                    push_edge(g, from_mod_id, submodule_id, edge_category::IMPORTS);
                    g.symbols
                        .module_import_bindings
                        .entry(from_mod_id)
                        .or_default()
                        .insert(bound, submodule_id);
                } else if let Some(target_mod_id) = g
                    .symbols
                    .module_by_qname
                    .get(&target_module_qname)
                    .copied()
                {
                    // `from pkg.mod import Name` — target is a symbol inside pkg.mod.
                    push_edge(g, from_mod_id, target_mod_id, edge_category::IMPORTS);
                    if let Some(symbol_id) = g
                        .symbols
                        .module_symbols
                        .get(&target_mod_id)
                        .and_then(|t| t.get(name))
                        .copied()
                    {
                        g.symbols
                            .module_import_bindings
                            .entry(from_mod_id)
                            .or_default()
                            .insert(bound, symbol_id);
                    }
                }
            }
        }
    }
}

/// Go imports: the parser has already stripped the go.mod prefix and produced
/// `ImportTarget::Module { path }` with `path` = repo-local `::` qname for
/// imports that resolve inside this module. External imports keep the raw
/// `std::io`-style form and won't match anything.
fn resolve_imports_go(g: &mut RepoGraph, imports: &[ImportStmt]) {
    for stmt in imports {
        let Some(from_mod_id) = g
            .symbols
            .module_by_qname
            .get(&stmt.from_module)
            .copied()
        else {
            continue;
        };
        let ImportTarget::Module { path, alias } = &stmt.target else {
            continue;
        };
        let Some(target_id) = g.symbols.module_by_qname.get(path).copied() else {
            continue;
        };
        push_edge(g, from_mod_id, target_id, edge_category::IMPORTS);
        let bound = alias
            .clone()
            .unwrap_or_else(|| path.rsplit("::").next().unwrap_or(path).to_string());
        g.symbols
            .module_import_bindings
            .entry(from_mod_id)
            .or_default()
            .insert(bound, target_id);
    }
}

/// TypeScript imports: the parser keeps import sources as raw strings
/// (`./user`, `@angular/core`). `resolve_source(from_qname, raw)` converts a
/// raw source string to a module qname; `None` marks the import external.
fn resolve_imports_ts<R: Fn(&str, &str) -> Option<String>>(
    g: &mut RepoGraph,
    imports: &[ImportStmt],
    resolve_source: &R,
) {
    for stmt in imports {
        let Some(from_mod_id) = g
            .symbols
            .module_by_qname
            .get(&stmt.from_module)
            .copied()
        else {
            continue;
        };
        match &stmt.target {
            ImportTarget::Module { path, alias } => {
                let Some(target_qname) = resolve_source(&stmt.from_module, path) else {
                    continue;
                };
                let Some(target_id) = g.symbols.module_by_qname.get(&target_qname).copied() else {
                    continue;
                };
                push_edge(g, from_mod_id, target_id, edge_category::IMPORTS);
                // Namespace import alias is the binding; bare side-effect has none.
                if let Some(a) = alias {
                    g.symbols
                        .module_import_bindings
                        .entry(from_mod_id)
                        .or_default()
                        .insert(a.clone(), target_id);
                }
            }
            ImportTarget::Symbol {
                module,
                name,
                alias,
                ..
            } => {
                let Some(target_qname) = resolve_source(&stmt.from_module, module) else {
                    continue;
                };
                let Some(target_mod_id) = g.symbols.module_by_qname.get(&target_qname).copied()
                else {
                    continue;
                };
                push_edge(g, from_mod_id, target_mod_id, edge_category::IMPORTS);
                let bound = alias.clone().unwrap_or_else(|| name.clone());
                // Default import — bind to the module itself.
                // Named import — bind to the specific symbol inside that module.
                let target_id = if name == "default" {
                    Some(target_mod_id)
                } else {
                    g.symbols
                        .module_symbols
                        .get(&target_mod_id)
                        .and_then(|s| s.get(name))
                        .copied()
                };
                if let Some(t) = target_id {
                    g.symbols
                        .module_import_bindings
                        .entry(from_mod_id)
                        .or_default()
                        .insert(bound, t);
                }
            }
        }
    }
}

/// Convert a (possibly relative) `from X import Y` module reference into an
/// absolute qname using `::` separators.
fn resolve_module_reference(from_module: &str, module_ref: &str, level: u32) -> String {
    if level == 0 {
        return module_ref.replace('.', "::");
    }
    // Relative: strip `level` trailing components from `from_module`, then
    // append `module_ref`. `level=1` pops 1 (the current file stays at package level).
    let mut parts: Vec<&str> = from_module.split("::").collect();
    for _ in 0..level {
        parts.pop();
    }
    let base = parts.join("::");
    if module_ref.is_empty() {
        base
    } else if base.is_empty() {
        module_ref.replace('.', "::")
    } else {
        format!("{base}::{}", module_ref.replace('.', "::"))
    }
}

// ============================================================================
// Call resolution
// ============================================================================

/// Cross-file call resolution — same recipe for all languages.
///
/// `extra_hook` is an escape hatch for language-specific resolution shapes
/// that the generic pass doesn't cover. Unused today (pass `|_, _| None`);
/// it's the seam for future Go method-on-struct-via-package-alias lookups
/// and similar language-specific call shapes.
fn resolve_calls<H>(g: &mut RepoGraph, calls: &[CallSite], extra_hook: H)
where
    H: Fn(&RepoGraph, &CallSite) -> Option<NodeId>,
{
    for site in calls {
        let Some(from_module) = enclosing_module(&g.nav, site.from) else {
            g.unresolved_calls.push(site.clone());
            continue;
        };
        let bindings = g.symbols.module_import_bindings.get(&from_module);

        let resolved: Option<NodeId> = match &site.qualifier {
            CallQualifier::Bare(name) => {
                // Priority: local import binding → same-module top-level def.
                bindings
                    .and_then(|b| b.get(name).copied())
                    .or_else(|| {
                        g.symbols
                            .module_symbols
                            .get(&from_module)
                            .and_then(|s| s.get(name).copied())
                    })
            }
            CallQualifier::Attribute { base, name } => bindings
                .and_then(|b| b.get(base).copied())
                .and_then(|base_id| {
                    let base_kind = g.nav.kind_by_id.get(&base_id).copied();
                    if base_kind == Some(node_kind::MODULE) {
                        g.symbols
                            .module_symbols
                            .get(&base_id)
                            .and_then(|s| s.get(name).copied())
                    } else if base_kind == Some(node_kind::CLASS)
                        || base_kind == Some(node_kind::STRUCT)
                    {
                        g.symbols
                            .class_methods
                            .get(&base_id)
                            .and_then(|m| m.get(name).copied())
                    } else {
                        None
                    }
                }),
            CallQualifier::SelfMethod(name) => {
                enclosing_class_or_struct(&g.nav, site.from).and_then(|parent_id| {
                    g.symbols
                        .class_methods
                        .get(&parent_id)
                        .and_then(|m| m.get(name).copied())
                })
            }
            CallQualifier::ComplexReceiver { .. } => None,
        };

        let resolved = resolved.or_else(|| extra_hook(g, site));

        match resolved {
            Some(to) => push_edge(g, site.from, to, edge_category::CALLS),
            None => g.unresolved_calls.push(site.clone()),
        }
    }
}

/// Resolve `UnresolvedRef`s the same way `resolve_calls` resolves `CallSite`s,
/// but using the ref's `from_module` directly (refs come from sources like
/// Route nodes that have no enclosing module to walk to) and emitting an edge
/// of the ref's declared `category` instead of CALLS.
///
/// Today's only producer is parser-go's route extraction, where `category` is
/// `HANDLED_BY` and the qualifier shape is either `Bare(name)` (handler is a
/// same-package fn) or `Attribute { base, name }` (handler is `pkg.Name`).
fn resolve_refs(g: &mut RepoGraph, refs: &[UnresolvedRef]) {
    for r in refs {
        let bindings = g.symbols.module_import_bindings.get(&r.from_module);
        let resolved: Option<NodeId> = match &r.qualifier {
            CallQualifier::Bare(name) => bindings
                .and_then(|b| b.get(name).copied())
                .or_else(|| {
                    g.symbols
                        .module_symbols
                        .get(&r.from_module)
                        .and_then(|s| s.get(name).copied())
                }),
            CallQualifier::Attribute { base, name } => bindings
                .and_then(|b| b.get(base).copied())
                .and_then(|base_id| {
                    let base_kind = g.nav.kind_by_id.get(&base_id).copied();
                    if base_kind == Some(node_kind::MODULE) {
                        g.symbols
                            .module_symbols
                            .get(&base_id)
                            .and_then(|s| s.get(name).copied())
                    } else if base_kind == Some(node_kind::CLASS)
                        || base_kind == Some(node_kind::STRUCT)
                    {
                        g.symbols
                            .class_methods
                            .get(&base_id)
                            .and_then(|m| m.get(name).copied())
                    } else {
                        None
                    }
                }),
            // SelfMethod and ComplexReceiver are non-sensical for refs at v0.4.4 —
            // refs come from contexts (Route nodes) that have no `self`. Treat as
            // unresolved for diagnostics.
            CallQualifier::SelfMethod(_) | CallQualifier::ComplexReceiver { .. } => None,
        };

        match resolved {
            Some(to) => push_edge(g, r.from, to, r.category),
            None => g.unresolved_refs.push(r.clone()),
        }
    }
}

/// Walk `parent_of` until we hit a module node. For a top-level function this
/// returns its module directly; for a method it walks method → class → module.
fn enclosing_module(nav: &CodeNav, mut id: NodeId) -> Option<NodeId> {
    loop {
        if nav.kind_by_id.get(&id) == Some(&node_kind::MODULE) {
            return Some(id);
        }
        id = *nav.parent_of.get(&id)?;
    }
}

/// Walk parents to find the enclosing CLASS or STRUCT. Used to resolve
/// self-method calls (Go `u.Save()`, TS `this.save()`, etc.) to a sibling
/// method on the same type.
fn enclosing_class_or_struct(nav: &CodeNav, start: NodeId) -> Option<NodeId> {
    let mut cur = start;
    loop {
        let parent = *nav.parent_of.get(&cur)?;
        let k = nav.kind_by_id.get(&parent).copied();
        if k == Some(node_kind::CLASS) || k == Some(node_kind::STRUCT) {
            return Some(parent);
        }
        cur = parent;
    }
}

fn push_edge(g: &mut RepoGraph, from: NodeId, to: NodeId, category: EdgeCategoryId) {
    g.edges.push(Edge {
        from,
        to,
        category,
        confidence: Confidence::Strong,
    });
}

// ============================================================================
// Cross-graph resolution (v0.4.4b)
// ============================================================================

/// A bundle of per-repo `RepoGraph`s plus edges that cross repo boundaries.
///
/// Per-repo graphs stay owned and addressable by their `RepoId`. Cross-edges
/// sit on the merged container so the per-repo graphs remain round-trippable
/// through the v0.4.5 rkyv store without the intra-repo edge list being
/// polluted by cross-repo references that only make sense once multiple repos
/// are in scope.
#[derive(Debug, Default)]
pub struct MergedGraph {
    pub graphs: Vec<RepoGraph>,
    pub cross_edges: Vec<Edge>,
}

impl MergedGraph {
    pub fn new(graphs: Vec<RepoGraph>) -> Self {
        Self {
            graphs,
            cross_edges: Vec::new(),
        }
    }

    pub fn run<R: CrossGraphResolver>(&mut self, resolver: &R) {
        resolver.resolve(self);
    }

    /// All cross-repo edges plus each per-repo graph's intra edges. Used by
    /// consumers that want a single iterator over the whole merged graph.
    pub fn all_edges(&self) -> impl Iterator<Item = &Edge> + '_ {
        self.graphs
            .iter()
            .flat_map(|g| g.edges.iter())
            .chain(self.cross_edges.iter())
    }
}

/// Emits edges that cross `RepoGraph` boundaries. v0.4.10 will add
/// `GraphQLResolver`, `GrpcResolver`, `QueueResolver`, etc. against the same
/// trait. Each resolver owns its own matching rule — path normalisation,
/// schema-name matching, queue-topic matching, etc.
pub trait CrossGraphResolver {
    fn resolve(&self, merged: &mut MergedGraph);
}

/// Pairs frontend HTTP Endpoints with backend HTTP Routes by (method,
/// normalised path) and emits `HTTP_CALLS` edges.
///
/// Matching rule:
/// - Endpoint qname `endpoint:<METHOD>:<path>` is the source side. Method comes
///   straight from the qname; path is normalised (see `normalise_http_path`).
/// - Route qname `route:<path>` — one Route node per path across all methods.
///   Methods live on stacked `ROUTE_METHOD` cells. Each (path, method) pair is
///   a distinct target.
/// - Cross-repo is the common case (Angular → Go gin backend), but same-repo
///   matches also link correctly (Next.js route-handlers + fetchers, etc.).
/// - Emitted edge confidence = min(endpoint_node_confidence, Strong) since
///   Routes are always Strong at v0.4.4 — i.e. the endpoint's confidence wins.
///
/// Collisions (multiple Routes with the same method+path across repos) emit
/// one edge per target. Rare in real corpora but cheap to handle.
pub struct HttpStackResolver;

impl CrossGraphResolver for HttpStackResolver {
    fn resolve(&self, merged: &mut MergedGraph) {
        let index = build_route_index(&merged.graphs);
        for g in &merged.graphs {
            for n in &g.nodes {
                if g.nav.kind_by_id.get(&n.id) != Some(&node_kind::ENDPOINT) {
                    continue;
                }
                let Some(qname) = g.nav.qname_by_id.get(&n.id) else {
                    continue;
                };
                let Some((method, raw_path)) = parse_endpoint_qname(qname) else {
                    continue;
                };
                if raw_path == "<unresolved>" {
                    continue;
                }
                let norm = normalise_http_path(raw_path);
                let targets = lookup_route_with_prefix_strip(&index, &method, &norm);
                for target in targets {
                    merged.cross_edges.push(Edge {
                        from: n.id,
                        to: target.route_id,
                        category: edge_category::HTTP_CALLS,
                        confidence: weakest(n.confidence, target.confidence),
                    });
                }
            }
        }
    }
}

#[derive(Debug, Clone, Copy)]
struct RouteTarget {
    route_id: NodeId,
    confidence: Confidence,
}

/// Build `(METHOD, normalised_path) → Vec<RouteTarget>` across every graph in
/// the merge. One entry per `ROUTE_METHOD` cell found on each Route node.
fn build_route_index(
    graphs: &[RepoGraph],
) -> HashMap<(String, String), Vec<RouteTarget>> {
    let mut index: HashMap<(String, String), Vec<RouteTarget>> = HashMap::new();
    for g in graphs {
        for n in &g.nodes {
            if g.nav.kind_by_id.get(&n.id) != Some(&node_kind::ROUTE) {
                continue;
            }
            let Some(qname) = g.nav.qname_by_id.get(&n.id) else {
                continue;
            };
            let Some(path) = qname.strip_prefix("route:") else {
                continue;
            };
            let norm = normalise_http_path(path);
            for cell in &n.cells {
                if cell.kind != cell_type::ROUTE_METHOD {
                    continue;
                }
                let CellPayload::Json(json) = &cell.payload else {
                    continue;
                };
                let Some(method) = extract_method_field(json) else {
                    continue;
                };
                index
                    .entry((method.to_uppercase(), norm.clone()))
                    .or_default()
                    .push(RouteTarget {
                        route_id: n.id,
                        confidence: n.confidence,
                    });
            }
        }
    }
    index
}

fn parse_endpoint_qname(qname: &str) -> Option<(String, &str)> {
    let rest = qname.strip_prefix("endpoint:")?;
    let (method, path) = rest.split_once(':')?;
    Some((method.to_uppercase(), path))
}

/// Extract the `method` string field from a `ROUTE_METHOD` cell's JSON payload.
/// Minimal parse — the payload is a flat object written by parser-go, not
/// arbitrary user JSON, so a tight scan is enough and keeps us off serde_json
/// as a graph-crate dependency.
fn extract_method_field(json: &str) -> Option<&str> {
    let key = "\"method\"";
    let idx = json.find(key)?;
    let after = &json[idx + key.len()..];
    let colon = after.find(':')?;
    let rest = after[colon + 1..].trim_start();
    let rest = rest.strip_prefix('"')?;
    let end = rest.find('"')?;
    Some(&rest[..end])
}

/// Collapse path param syntaxes into a stable form so a frontend endpoint's
/// `/users/${id}` matches a backend route's `/users/:id` or `/users/{id}`.
/// Rules:
/// - Leading slash normalised to exactly one.
/// - Trailing slash stripped (except on the root).
/// - Segment matching `:x`, `{x}`, `${…}` (tree-sitter substitution marker),
///   or any segment containing `${` → `{}`.
/// - Empty segments collapse (so `//foo` → `/foo`).
pub fn normalise_http_path(raw: &str) -> String {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return "/".to_string();
    }
    let body = trimmed.trim_matches('/');
    if body.is_empty() {
        return "/".to_string();
    }
    let segs: Vec<String> = body
        .split('/')
        .filter(|s| !s.is_empty())
        .map(normalise_segment)
        .collect();
    format!("/{}", segs.join("/"))
}

fn normalise_segment(seg: &str) -> String {
    if seg.starts_with(':')
        || (seg.starts_with('{') && seg.ends_with('}'))
        || seg.contains("${")
    {
        "{}".to_string()
    } else {
        seg.to_string()
    }
}

// Hardcoded for now — move to config.yaml if a real codebase needs a custom prefix.
const API_PREFIXES: &[&str] = &["protected", "api", "public", "internal", "v1", "v2", "v3"];

fn lookup_route_with_prefix_strip<'a>(
    index: &'a HashMap<(String, String), Vec<RouteTarget>>,
    method: &str,
    norm_path: &str,
) -> &'a [RouteTarget] {
    let key = (method.to_string(), norm_path.to_string());
    if let Some(targets) = index.get(&key) {
        return targets;
    }
    let segments: Vec<&str> = norm_path
        .trim_start_matches('/')
        .split('/')
        .filter(|s| !s.is_empty())
        .collect();
    for strip in 1..=2.min(segments.len().saturating_sub(1)) {
        if !API_PREFIXES.contains(&segments[strip - 1]) {
            break;
        }
        let stripped = format!("/{}", segments[strip..].join("/"));
        let key = (method.to_string(), stripped);
        if let Some(targets) = index.get(&key) {
            return targets;
        }
    }
    &[]
}

fn weakest(a: Confidence, b: Confidence) -> Confidence {
    fn rank(c: Confidence) -> u8 {
        match c {
            Confidence::Strong => 2,
            Confidence::Medium => 1,
            Confidence::Weak => 0,
        }
    }
    if rank(a) <= rank(b) { a } else { b }
}

// ============================================================================
// GrpcStackResolver — matches gRPC client → service by service name
// ============================================================================

pub struct GrpcStackResolver;

impl CrossGraphResolver for GrpcStackResolver {
    fn resolve(&self, merged: &mut MergedGraph) {
        let index = build_grpc_service_index(&merged.graphs);
        for g in &merged.graphs {
            for n in &g.nodes {
                if g.nav.kind_by_id.get(&n.id) != Some(&node_kind::GRPC_CLIENT) {
                    continue;
                }
                let Some(qname) = g.nav.qname_by_id.get(&n.id) else { continue };
                let Some(svc_name) = qname.strip_prefix("grpc_client:") else { continue };
                let key = svc_name.split('.').next().unwrap_or(svc_name);
                if let Some(targets) = index.get(key) {
                    for t in targets {
                        merged.cross_edges.push(Edge {
                            from: n.id,
                            to: t.id,
                            category: edge_category::GRPC_CALLS,
                            confidence: weakest(n.confidence, t.confidence),
                        });
                    }
                }
            }
        }
    }
}

struct ServiceTarget {
    id: NodeId,
    confidence: Confidence,
}

fn build_grpc_service_index(graphs: &[RepoGraph]) -> HashMap<String, Vec<ServiceTarget>> {
    let mut index: HashMap<String, Vec<ServiceTarget>> = HashMap::new();
    for g in graphs {
        for n in &g.nodes {
            if g.nav.kind_by_id.get(&n.id) != Some(&node_kind::GRPC_SERVICE) {
                continue;
            }
            let Some(qname) = g.nav.qname_by_id.get(&n.id) else { continue };
            let Some(svc_name) = qname.strip_prefix("grpc:") else { continue };
            index
                .entry(svc_name.to_string())
                .or_default()
                .push(ServiceTarget {
                    id: n.id,
                    confidence: n.confidence,
                });
        }
    }
    index
}

// ============================================================================
// QueueStackResolver — matches producer → consumer by topic name
// ============================================================================

pub struct QueueStackResolver;

impl CrossGraphResolver for QueueStackResolver {
    fn resolve(&self, merged: &mut MergedGraph) {
        let consumer_index = build_queue_index(&merged.graphs, node_kind::QUEUE_CONSUMER, "queue_consumer:");
        for g in &merged.graphs {
            for n in &g.nodes {
                if g.nav.kind_by_id.get(&n.id) != Some(&node_kind::QUEUE_PRODUCER) {
                    continue;
                }
                let Some(qname) = g.nav.qname_by_id.get(&n.id) else { continue };
                let Some(topic) = qname.strip_prefix("queue_producer:") else { continue };
                if let Some(targets) = consumer_index.get(topic) {
                    for t in targets {
                        merged.cross_edges.push(Edge {
                            from: n.id,
                            to: t.id,
                            category: edge_category::QUEUE_FLOWS,
                            confidence: weakest(n.confidence, t.confidence),
                        });
                    }
                }
            }
        }
    }
}

fn build_queue_index(
    graphs: &[RepoGraph],
    kind: NodeKindId,
    prefix: &str,
) -> HashMap<String, Vec<ServiceTarget>> {
    let mut index: HashMap<String, Vec<ServiceTarget>> = HashMap::new();
    for g in graphs {
        for n in &g.nodes {
            if g.nav.kind_by_id.get(&n.id) != Some(&kind) {
                continue;
            }
            let Some(qname) = g.nav.qname_by_id.get(&n.id) else { continue };
            let Some(topic) = qname.strip_prefix(prefix) else { continue };
            index
                .entry(topic.to_string())
                .or_default()
                .push(ServiceTarget {
                    id: n.id,
                    confidence: n.confidence,
                });
        }
    }
    index
}

// ============================================================================
// GraphQLStackResolver — matches operation → resolver by name
// ============================================================================

pub struct GraphQLStackResolver;

impl CrossGraphResolver for GraphQLStackResolver {
    fn resolve(&self, merged: &mut MergedGraph) {
        let resolver_index = build_kind_index(&merged.graphs, node_kind::GRAPHQL_RESOLVER, "graphql_resolver:");
        for g in &merged.graphs {
            for n in &g.nodes {
                if g.nav.kind_by_id.get(&n.id) != Some(&node_kind::GRAPHQL_OPERATION) {
                    continue;
                }
                let Some(qname) = g.nav.qname_by_id.get(&n.id) else { continue };
                let Some(op_name) = qname.strip_prefix("graphql_op:") else { continue };
                for (resolver_key, targets) in &resolver_index {
                    if names_match_graphql(op_name, resolver_key) {
                        for t in targets {
                            merged.cross_edges.push(Edge {
                                from: n.id,
                                to: t.id,
                                category: edge_category::GRAPHQL_CALLS,
                                confidence: weakest(n.confidence, t.confidence),
                            });
                        }
                    }
                }
            }
        }
    }
}

fn names_match_graphql(operation: &str, resolver: &str) -> bool {
    let op_lower = operation.to_lowercase();
    let res_lower = resolver.to_lowercase();
    op_lower == res_lower
        || op_lower.contains(&res_lower)
        || res_lower.contains(&op_lower)
}

// ============================================================================
// WebSocketStackResolver — matches WS client → handler by path
// ============================================================================

pub struct WebSocketStackResolver;

impl CrossGraphResolver for WebSocketStackResolver {
    fn resolve(&self, merged: &mut MergedGraph) {
        let handler_index = build_kind_index(&merged.graphs, node_kind::WS_HANDLER, "ws:");
        for g in &merged.graphs {
            for n in &g.nodes {
                if g.nav.kind_by_id.get(&n.id) != Some(&node_kind::WS_CLIENT) {
                    continue;
                }
                let Some(qname) = g.nav.qname_by_id.get(&n.id) else { continue };
                let Some(client_path) = qname.strip_prefix("ws_client:") else { continue };
                for (handler_key, targets) in &handler_index {
                    if ws_paths_match(client_path, handler_key) {
                        for t in targets {
                            merged.cross_edges.push(Edge {
                                from: n.id,
                                to: t.id,
                                category: edge_category::WS_CONNECTS,
                                confidence: weakest(n.confidence, t.confidence),
                            });
                        }
                    }
                }
            }
        }
    }
}

fn ws_paths_match(client: &str, handler: &str) -> bool {
    let norm_c = client.trim_matches('/').to_lowercase();
    let norm_h = handler.trim_matches('/').to_lowercase();
    norm_c == norm_h
        || norm_c.ends_with(&norm_h)
        || norm_h.ends_with(&norm_c)
        || (norm_c == "ws" || norm_h == "ws" || norm_h == "default")
}

// ============================================================================
// EventBusResolver — matches event emitter → handler by event name
// ============================================================================

pub struct EventBusResolver;

impl CrossGraphResolver for EventBusResolver {
    fn resolve(&self, merged: &mut MergedGraph) {
        let handler_index = build_kind_index(&merged.graphs, node_kind::EVENT_HANDLER, "event_handle:");
        for g in &merged.graphs {
            for n in &g.nodes {
                if g.nav.kind_by_id.get(&n.id) != Some(&node_kind::EVENT_EMITTER) {
                    continue;
                }
                let Some(qname) = g.nav.qname_by_id.get(&n.id) else { continue };
                let Some(event_name) = qname.strip_prefix("event_emit:") else { continue };
                if let Some(targets) = handler_index.get(event_name) {
                    for t in targets {
                        merged.cross_edges.push(Edge {
                            from: n.id,
                            to: t.id,
                            category: edge_category::EVENT_FLOWS,
                            confidence: weakest(n.confidence, t.confidence),
                        });
                    }
                }
            }
        }
    }
}

// ============================================================================
// SharedSchemaResolver — detects shared imports across repos
// ============================================================================

pub struct SharedSchemaResolver;

impl CrossGraphResolver for SharedSchemaResolver {
    fn resolve(&self, merged: &mut MergedGraph) {
        let mut import_index: HashMap<String, Vec<(NodeId, RepoId, Confidence)>> = HashMap::new();
        for g in &merged.graphs {
            for n in &g.nodes {
                if g.nav.kind_by_id.get(&n.id) != Some(&node_kind::MODULE) {
                    continue;
                }
                if let Some(children) = g.nav.children_of.get(&n.id) {
                    for &child in children {
                        if let Some(qname) = g.nav.qname_by_id.get(&child)
                            && is_schema_type(qname, g.nav.kind_by_id.get(&child).copied())
                        {
                            import_index
                                .entry(g.nav.name_by_id.get(&child).cloned().unwrap_or_default())
                                .or_default()
                                .push((child, g.repo, n.confidence));
                        }
                    }
                }
            }
        }

        for refs in import_index.values() {
            if refs.len() < 2 {
                continue;
            }
            let repos: HashSet<RepoId> = refs.iter().map(|(_, r, _)| *r).collect();
            if repos.len() < 2 {
                continue;
            }
            for i in 0..refs.len() {
                for j in (i + 1)..refs.len() {
                    if refs[i].1 != refs[j].1 {
                        merged.cross_edges.push(Edge {
                            from: refs[i].0,
                            to: refs[j].0,
                            category: edge_category::SHARES_SCHEMA,
                            confidence: weakest(
                                refs[i].2,
                                refs[j].2,
                            ),
                        });
                    }
                }
            }
        }
    }
}

fn is_schema_type(qname: &str, kind: Option<NodeKindId>) -> bool {
    let schema_hints = [
        "Schema", "Validator", "Type", "Model", "Entity", "DTO",
        "Input", "Output", "Params", "Request", "Response",
    ];
    let is_type_kind = matches!(
        kind,
        Some(k) if k == node_kind::CLASS || k == node_kind::INTERFACE || k == node_kind::STRUCT
    );
    is_type_kind && schema_hints.iter().any(|h| qname.contains(h))
}

// ============================================================================
// CliInvocationResolver — matches CLI invocations → CLI commands
// ============================================================================

pub struct CliInvocationResolver;

impl CrossGraphResolver for CliInvocationResolver {
    fn resolve(&self, merged: &mut MergedGraph) {
        let command_index = build_kind_index(&merged.graphs, node_kind::CLI_COMMAND, "cli:");
        for g in &merged.graphs {
            for n in &g.nodes {
                if g.nav.kind_by_id.get(&n.id) != Some(&node_kind::CLI_INVOCATION) {
                    continue;
                }
                let Some(qname) = g.nav.qname_by_id.get(&n.id) else { continue };
                let Some(tool) = qname.strip_prefix("cli_invoke:") else { continue };
                if let Some(targets) = command_index.get(tool) {
                    for t in targets {
                        merged.cross_edges.push(Edge {
                            from: n.id,
                            to: t.id,
                            category: edge_category::CLI_INVOKES,
                            confidence: weakest(n.confidence, t.confidence),
                        });
                    }
                }
            }
        }
    }
}

// ============================================================================
// Shared index builder
// ============================================================================

fn build_kind_index(
    graphs: &[RepoGraph],
    kind: NodeKindId,
    prefix: &str,
) -> HashMap<String, Vec<ServiceTarget>> {
    let mut index: HashMap<String, Vec<ServiceTarget>> = HashMap::new();
    for g in graphs {
        for n in &g.nodes {
            if g.nav.kind_by_id.get(&n.id) != Some(&kind) {
                continue;
            }
            let Some(qname) = g.nav.qname_by_id.get(&n.id) else { continue };
            let Some(key) = qname.strip_prefix(prefix) else { continue };
            index
                .entry(key.to_string())
                .or_default()
                .push(ServiceTarget {
                    id: n.id,
                    confidence: n.confidence,
                });
        }
    }
    index
}

// ============================================================================
// Traversal primitives
// ============================================================================

impl RepoGraph {
    /// Outgoing neighbours of `id`: `(target, category)` pairs.
    pub fn neighbours(&self, id: NodeId) -> Vec<(NodeId, EdgeCategoryId)> {
        self.edges
            .iter()
            .filter(|e| e.from == id)
            .map(|e| (e.to, e.category))
            .collect()
    }

    /// Node ids reachable from `start` following edges in `follow` up to
    /// `max_depth`. Start node excluded.
    pub fn bfs(
        &self,
        start: NodeId,
        follow: &[EdgeCategoryId],
        max_depth: usize,
    ) -> Vec<NodeId> {
        let allow: HashSet<EdgeCategoryId> = follow.iter().copied().collect();
        let mut visited: HashSet<NodeId> = HashSet::from([start]);
        let mut out = Vec::new();
        let mut queue: VecDeque<(NodeId, usize)> = VecDeque::from([(start, 0)]);
        while let Some((node, depth)) = queue.pop_front() {
            if depth >= max_depth {
                continue;
            }
            for e in self.edges.iter().filter(|e| e.from == node) {
                if !allow.contains(&e.category) {
                    continue;
                }
                if visited.insert(e.to) {
                    out.push(e.to);
                    queue.push_back((e.to, depth + 1));
                }
            }
        }
        out
    }

    /// Walk `parent_of` from `id` to the top. Excludes `id` itself.
    pub fn parent_chain(&self, id: NodeId) -> Vec<NodeId> {
        let mut out = Vec::new();
        let mut cur = id;
        while let Some(parent) = self.nav.parent_of.get(&cur).copied() {
            out.push(parent);
            cur = parent;
        }
        out
    }

    /// Count nodes of a given kind.
    pub fn count_of_kind(&self, kind: NodeKindId) -> usize {
        self.nav
            .kind_by_id
            .values()
            .filter(|k| **k == kind)
            .count()
    }

    /// Spreading activation (PPR) over this repo's graph.
    pub fn activate(
        &self,
        seeds: &[NodeId],
        config: &repo_graph_activation::ActivationConfig,
    ) -> repo_graph_activation::ActivationResult {
        let node_ids: Vec<NodeId> = self.nodes.iter().map(|n| n.id).collect();
        repo_graph_activation::activate(&node_ids, &self.edges, seeds, config)
    }
}

impl MergedGraph {
    /// Spreading activation over the full merged graph (all repos + cross edges).
    pub fn activate(
        &self,
        seeds: &[NodeId],
        config: &repo_graph_activation::ActivationConfig,
    ) -> repo_graph_activation::ActivationResult {
        let node_ids: Vec<NodeId> = self
            .graphs
            .iter()
            .flat_map(|g| g.nodes.iter().map(|n| n.id))
            .collect();
        let edges: Vec<Edge> = self.all_edges().cloned().collect();
        repo_graph_activation::activate(&node_ids, &edges, seeds, config)
    }
}

// ============================================================================
// Code-domain activation defaults
// ============================================================================

/// Default `ActivationConfig` for code graphs. Weights: `calls` and
/// `http_calls` highest, `imports` medium, structural edges (`contains`,
/// `defines`) lowest. Direction forward (impact analysis default).
pub fn code_activation_defaults() -> repo_graph_activation::ActivationConfig {
    use repo_graph_activation::{ActivationConfig, Direction, Specificity};

    let mut weights = HashMap::new();
    weights.insert(edge_category::CALLS, 5.0);
    weights.insert(edge_category::HTTP_CALLS, 5.0);
    weights.insert(edge_category::GRPC_CALLS, 5.0);
    weights.insert(edge_category::GRAPHQL_CALLS, 5.0);
    weights.insert(edge_category::QUEUE_FLOWS, 4.0);
    weights.insert(edge_category::WS_CONNECTS, 4.0);
    weights.insert(edge_category::EVENT_FLOWS, 4.0);
    weights.insert(edge_category::CLI_INVOKES, 3.0);
    weights.insert(edge_category::HANDLED_BY, 4.0);
    weights.insert(edge_category::IMPORTS, 3.0);
    weights.insert(edge_category::USES, 3.0);
    weights.insert(edge_category::SHARES_SCHEMA, 2.0);
    weights.insert(edge_category::TESTS, 2.0);
    weights.insert(edge_category::INJECTS, 2.0);
    weights.insert(edge_category::DEFINES, 1.0);
    weights.insert(edge_category::CONTAINS, 1.0);
    weights.insert(edge_category::DOCUMENTS, 0.5);

    ActivationConfig {
        damping: 0.5,
        direction: Direction::Forward,
        edge_weights: weights,
        node_specificity: Specificity::None,
        top_k: 50,
        max_iterations: 100,
        epsilon: 1e-6,
    }
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn repo() -> RepoId {
        RepoId::from_canonical("test://unit")
    }

    #[test]
    fn relative_import_resolution() {
        assert_eq!(resolve_module_reference("myapp::users", "helpers", 1), "myapp::helpers");
        assert_eq!(resolve_module_reference("a::b::c", "d", 2), "a::d");
        assert_eq!(resolve_module_reference("a::b", "c.d", 0), "c::d");
        assert_eq!(resolve_module_reference("a::b::c", "", 1), "a::b");
    }

    #[test]
    fn empty_repo_builds_cleanly() {
        let g = build_python(repo(), vec![]).unwrap();
        assert!(g.nodes.is_empty());
        assert!(g.edges.is_empty());
    }

    #[test]
    fn normalise_http_path_collapses_all_param_syntaxes() {
        assert_eq!(normalise_http_path("/users/:id"), "/users/{}");
        assert_eq!(normalise_http_path("/users/{id}"), "/users/{}");
        assert_eq!(normalise_http_path("/users/${…}"), "/users/{}");
        assert_eq!(normalise_http_path("/api/users/:id/posts/:pid"), "/api/users/{}/posts/{}");
        assert_eq!(normalise_http_path("users/list"), "/users/list");
        assert_eq!(normalise_http_path("/users/list/"), "/users/list");
        assert_eq!(normalise_http_path("//double//slash"), "/double/slash");
        assert_eq!(normalise_http_path("/"), "/");
        assert_eq!(normalise_http_path(""), "/");
    }

    #[test]
    fn parse_endpoint_qname_splits_method_and_path() {
        assert_eq!(
            parse_endpoint_qname("endpoint:GET:/users"),
            Some(("GET".to_string(), "/users"))
        );
        assert_eq!(
            parse_endpoint_qname("endpoint:POST:/api/login"),
            Some(("POST".to_string(), "/api/login"))
        );
        assert_eq!(parse_endpoint_qname("route:/users"), None);
    }

    #[test]
    fn extract_method_field_handles_ordering_and_whitespace() {
        let json = r#"{"method":"POST","handler":"h","file":"x.go","line":1,"col":2}"#;
        assert_eq!(extract_method_field(json), Some("POST"));
        let spaced = r#"{ "method" : "GET" , "line" : 0 }"#;
        assert_eq!(extract_method_field(spaced), Some("GET"));
    }

    #[test]
    fn weakest_confidence_is_min_rank() {
        assert_eq!(weakest(Confidence::Strong, Confidence::Strong), Confidence::Strong);
        assert_eq!(weakest(Confidence::Strong, Confidence::Medium), Confidence::Medium);
        assert_eq!(weakest(Confidence::Medium, Confidence::Weak), Confidence::Weak);
        assert_eq!(weakest(Confidence::Weak, Confidence::Strong), Confidence::Weak);
    }
}
