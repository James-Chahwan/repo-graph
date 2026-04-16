//! repo-graph-graph — per-repo graph construction + resolver + traversal.
//!
//! Consumes `FileParse` outputs from the Python parser, merges them into a
//! single `RepoGraph` for the repo, resolves cross-file imports and calls
//! using the symbol table, and exposes BFS / neighbours / parent-chain.
//!
//! v0.4.3 is Python-only. v0.4.3b adds Go + TypeScript which will push the
//! language-specific resolution into its own per-parser resolver entry
//! point; the graph infrastructure stays language-agnostic.

use std::collections::{HashMap, HashSet, VecDeque};

use repo_graph_core::{Confidence, Edge, EdgeCategoryId, Node, NodeId, NodeKindId, RepoId};
use repo_graph_parser_python::{
    CallQualifier, CallSite, CodeNav, FileParse, ImportStmt, ImportTarget, edge_category,
    node_kind,
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
    let mut g = RepoGraph {
        repo,
        nodes: Vec::new(),
        edges: Vec::new(),
        nav: CodeNav::default(),
        symbols: SymbolTable::default(),
        unresolved_calls: Vec::new(),
    };

    // Stage 1: merge per-file outputs into one pool.
    let mut all_imports: Vec<ImportStmt> = Vec::new();
    let mut all_calls: Vec<CallSite> = Vec::new();
    for p in parses {
        g.nodes.extend(p.nodes);
        g.edges.extend(p.edges);
        merge_nav(&mut g.nav, p.nav);
        all_imports.extend(p.imports);
        all_calls.extend(p.calls);
    }

    // Stage 2: build symbol table from nav indices.
    build_symbol_table(&mut g);

    // Stage 3: resolve imports — emit `imports` edges + populate bindings.
    resolve_imports(&mut g, &all_imports);

    // Stage 4: resolve cross-file calls — emit `calls` edges.
    resolve_calls(&mut g, &all_calls);

    Ok(g)
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
        } else if parent_kind == Some(node_kind::CLASS) {
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

fn resolve_imports(g: &mut RepoGraph, imports: &[ImportStmt]) {
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

fn resolve_calls(g: &mut RepoGraph, calls: &[CallSite]) {
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
            CallQualifier::Attribute { base, name } => {
                bindings
                    .and_then(|b| b.get(base).copied())
                    .and_then(|base_id| {
                        let base_kind = g.nav.kind_by_id.get(&base_id).copied();
                        if base_kind == Some(node_kind::MODULE) {
                            g.symbols
                                .module_symbols
                                .get(&base_id)
                                .and_then(|s| s.get(name).copied())
                        } else if base_kind == Some(node_kind::CLASS) {
                            g.symbols
                                .class_methods
                                .get(&base_id)
                                .and_then(|m| m.get(name).copied())
                        } else {
                            None
                        }
                    })
            }
            CallQualifier::SelfMethod(_) | CallQualifier::ComplexReceiver { .. } => None,
        };

        match resolved {
            Some(to) => push_edge(g, site.from, to, edge_category::CALLS),
            None => g.unresolved_calls.push(site.clone()),
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

fn push_edge(g: &mut RepoGraph, from: NodeId, to: NodeId, category: EdgeCategoryId) {
    g.edges.push(Edge {
        from,
        to,
        category,
        confidence: Confidence::Strong,
    });
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
}
