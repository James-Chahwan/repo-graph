//! repo-graph-code-domain — shared code-domain types for every language parser.
//!
//! Extracted from `repo-graph-parser-python` at v0.4.3b so Go + TypeScript
//! parsers can share the constants + structural types without a weird
//! inter-parser dependency. All code-language parsers produce a `FileParse`,
//! and `repo-graph-graph` consumes the uniform shape.
//!
//! Registry-locked u32 values live here as the single source of truth.
//! See `memory/reference_code_domain_registries.md` for the semantic notes.

use std::collections::HashMap;

use repo_graph_core::{CellTypeId, Edge, EdgeCategoryId, Node, NodeId, NodeKindId};

/// Graph-type tag for any code-language graph. First arg to `NodeId::from_parts`.
pub const GRAPH_TYPE: &str = "code";

// ============================================================================
// Node kinds
// ============================================================================

pub mod node_kind {
    use super::NodeKindId;

    // v0.4.1 — universal entity kinds
    pub const MODULE: NodeKindId = NodeKindId(1);
    pub const CLASS: NodeKindId = NodeKindId(2);
    pub const FUNCTION: NodeKindId = NodeKindId(3);
    pub const METHOD: NodeKindId = NodeKindId(4);

    // v0.4.3b — framework / type-system additions
    pub const ROUTE: NodeKindId = NodeKindId(5);
    pub const PACKAGE: NodeKindId = NodeKindId(6);
    pub const INTERFACE: NodeKindId = NodeKindId(7);
    pub const STRUCT: NodeKindId = NodeKindId(8);
    pub const ENDPOINT: NodeKindId = NodeKindId(9);
    pub const ENUM: NodeKindId = NodeKindId(10);

    // v0.4.10 — cross-stack entity kinds
    pub const GRPC_SERVICE: NodeKindId = NodeKindId(11);
    pub const GRPC_CLIENT: NodeKindId = NodeKindId(12);
    pub const QUEUE_CONSUMER: NodeKindId = NodeKindId(13);
    pub const QUEUE_PRODUCER: NodeKindId = NodeKindId(14);
    pub const GRAPHQL_RESOLVER: NodeKindId = NodeKindId(15);
    pub const GRAPHQL_OPERATION: NodeKindId = NodeKindId(16);
    pub const WS_HANDLER: NodeKindId = NodeKindId(17);
    pub const WS_CLIENT: NodeKindId = NodeKindId(18);
    pub const EVENT_HANDLER: NodeKindId = NodeKindId(19);
    pub const EVENT_EMITTER: NodeKindId = NodeKindId(20);
    pub const CLI_COMMAND: NodeKindId = NodeKindId(21);
    pub const CLI_INVOCATION: NodeKindId = NodeKindId(22);

    // v0.4.11a — data source entity kinds (D1)
    pub const DATABASE: NodeKindId = NodeKindId(23);
    pub const CACHE: NodeKindId = NodeKindId(24);
    pub const BLOB_STORE: NodeKindId = NodeKindId(25);
    pub const SEARCH_INDEX: NodeKindId = NodeKindId(26);
    pub const EMAIL_SERVICE: NodeKindId = NodeKindId(27);
}

// ============================================================================
// Edge categories
// ============================================================================

pub mod edge_category {
    use super::EdgeCategoryId;

    // v0.4.1
    pub const DEFINES: EdgeCategoryId = EdgeCategoryId(1);
    pub const CONTAINS: EdgeCategoryId = EdgeCategoryId(2);
    pub const IMPORTS: EdgeCategoryId = EdgeCategoryId(3);
    pub const CALLS: EdgeCategoryId = EdgeCategoryId(4);
    pub const USES: EdgeCategoryId = EdgeCategoryId(5);
    pub const DOCUMENTS: EdgeCategoryId = EdgeCategoryId(6);
    pub const TESTS: EdgeCategoryId = EdgeCategoryId(7);

    // v0.4.3b
    pub const INJECTS: EdgeCategoryId = EdgeCategoryId(8);

    // v0.4.4 — HTTP stack
    /// Route → handler function. Emitted when gin/chi/net-http route
    /// registration links a path to a handler identifier.
    pub const HANDLED_BY: EdgeCategoryId = EdgeCategoryId(9);
    /// Endpoint → Route cross-repo link. Emitted by `HttpStackResolver`
    /// when a frontend HTTP call matches a backend route by (method, path).
    pub const HTTP_CALLS: EdgeCategoryId = EdgeCategoryId(10);

    // v0.4.10 — cross-stack resolvers
    pub const GRPC_CALLS: EdgeCategoryId = EdgeCategoryId(11);
    pub const QUEUE_FLOWS: EdgeCategoryId = EdgeCategoryId(12);
    pub const GRAPHQL_CALLS: EdgeCategoryId = EdgeCategoryId(13);
    pub const WS_CONNECTS: EdgeCategoryId = EdgeCategoryId(14);
    pub const EVENT_FLOWS: EdgeCategoryId = EdgeCategoryId(15);
    pub const SHARES_SCHEMA: EdgeCategoryId = EdgeCategoryId(16);
    pub const CLI_INVOKES: EdgeCategoryId = EdgeCategoryId(17);

    // v0.4.11a — module → data-source access (D1)
    pub const ACCESSES_DATA: EdgeCategoryId = EdgeCategoryId(18);
}

// ============================================================================
// Cell types
// ============================================================================

pub mod cell_type {
    use super::CellTypeId;
    pub const CODE: CellTypeId = CellTypeId(1);
    pub const DOC: CellTypeId = CellTypeId(2);
    pub const POSITION: CellTypeId = CellTypeId(3);
    pub const INTENT: CellTypeId = CellTypeId(4);
    pub const ROUTE_METHOD: CellTypeId = CellTypeId(5);
    pub const ENDPOINT_HIT: CellTypeId = CellTypeId(6);
    pub const TEST: CellTypeId = CellTypeId(7);
    pub const ATTN: CellTypeId = CellTypeId(8);
    pub const FAIL: CellTypeId = CellTypeId(9);
    pub const CONSTRAINT: CellTypeId = CellTypeId(10);
    pub const DECISION: CellTypeId = CellTypeId(11);
    pub const ENV: CellTypeId = CellTypeId(12);
    pub const CONV: CellTypeId = CellTypeId(13);
    pub const VECTOR: CellTypeId = CellTypeId(14);
}

// ============================================================================
// Errors
// ============================================================================

#[derive(Debug, thiserror::Error)]
pub enum ParseError {
    #[error("tree-sitter parse produced no tree")]
    NoTree,
    #[error("tree-sitter language init failed: {0}")]
    LanguageInit(String),
}

// ============================================================================
// Import records (language-agnostic shape)
// ============================================================================

/// An import statement as parsed from a source file. The resolver uses this
/// to wire cross-file bindings regardless of the source language.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug))]
pub struct ImportStmt {
    /// qname of the module doing the importing (`myapp::auth`, `svc::users`).
    pub from_module: String,
    pub target: ImportTarget,
}

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug))]
pub enum ImportTarget {
    /// Whole-module import — Python `import foo.bar`, Go `import "github.com/x/y"`,
    /// TS `import * as f from "./foo"` or `import "./foo"`.
    /// Alias is the bound name in the importing module (None = default name).
    Module { path: String, alias: Option<String> },
    /// Named symbol import — Python `from foo.bar import baz`, TS `import { baz } from "./foo"`.
    /// Go doesn't have this form; Go imports are always Module.
    /// `level` is Python-specific (relative-import dot count); non-Python parsers pass 0.
    Symbol {
        module: String,
        name: String,
        alias: Option<String>,
        level: u32,
    },
}

// ============================================================================
// Call records
// ============================================================================

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug))]
pub struct CallSite {
    pub from: NodeId,
    pub qualifier: CallQualifier,
}

/// An identifier reference that needs cross-file resolution into an edge of
/// a specific category. Used at v0.4.4 for route handler references.
///
/// Shape: parser sees `r.POST("/login", controllers.AuthHandler)` inside
/// `server.setupRoutes()`. It emits
/// ```ignore
/// UnresolvedRef {
///     from: route_id,                     // edge source (the Route node)
///     from_module: server_module_id,      // whose binding table resolves the qualifier
///     qualifier: Attribute { base: "controllers", name: "AuthHandler" },
///     category: HANDLED_BY,
/// }
/// ```
/// `from_module` is separate from `from` because Route nodes are path-only
/// (package-agnostic) and have no unique enclosing module — the parser must
/// tell the resolver which package's imports to use.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug))]
pub struct UnresolvedRef {
    pub from: NodeId,
    pub from_module: NodeId,
    pub qualifier: CallQualifier,
    pub category: EdgeCategoryId,
}

/// Classification of a call site by its syntactic shape. Resolution (which
/// node id the call actually targets) happens in `repo-graph-graph` using the
/// import table + symbol table, not in the parser.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug))]
pub enum CallQualifier {
    /// `foo()` — bare name. Resolves to a local def, an imported symbol, or
    /// stays unresolved.
    Bare(String),
    /// Call on the enclosing method's receiver — Python `self.m()`, TS
    /// `this.m()`, Go `u.m()` where `u` is the method receiver. Resolves
    /// against the enclosing class's method set.
    SelfMethod(String),
    /// `base.name()` where `base` is a plain identifier. Could be an imported
    /// module, an imported symbol, a struct instance, or a local variable.
    /// Disambiguation lives in the cross-file resolver.
    Attribute { base: String, name: String },
    /// `<complex>.name()` — receiver is a chained expression, not a plain
    /// identifier. Kept verbatim for diagnostics; not resolved at v0.4.3b.
    ComplexReceiver { receiver: String, name: String },
}

// ============================================================================
// FileParse + CodeNav
// ============================================================================

/// The per-file output every code-language parser produces. `repo-graph-graph`
/// consumes a `Vec<FileParse>` to build a `RepoGraph`.
#[derive(Debug, Default)]
pub struct FileParse {
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
    pub imports: Vec<ImportStmt>,
    pub calls: Vec<CallSite>,
    /// Identifier refs that aren't call expressions but still need cross-file
    /// resolution into an edge. v0.4.4 use case: route handler references.
    pub refs: Vec<UnresolvedRef>,
    pub nav: CodeNav,
}

/// Code-domain navigation indices — what the strict `Node` shape pushed out of
/// per-node fields. Merged across files by v0.4.3 into one per-repo index.
#[derive(Debug, Default, Clone)]
pub struct CodeNav {
    /// Simple name (`"login"`), not the full qualified name.
    pub name_by_id: HashMap<NodeId, String>,
    /// Full qualified name (`"myapp::users::User::login"`). Used by the resolver
    /// to map import targets onto node ids.
    pub qname_by_id: HashMap<NodeId, String>,
    pub kind_by_id: HashMap<NodeId, NodeKindId>,
    /// Direct parent: method → class, class → module, function → module (or
    /// enclosing function for nested defs).
    pub parent_of: HashMap<NodeId, NodeId>,
    /// Inverse of `parent_of`.
    pub children_of: HashMap<NodeId, Vec<NodeId>>,
}

impl CodeNav {
    /// Record a node's navigation metadata. Parsers call this right after
    /// pushing the `Node` onto the FileParse.
    pub fn record(
        &mut self,
        id: NodeId,
        name: &str,
        qname: &str,
        kind: NodeKindId,
        parent: Option<NodeId>,
    ) {
        self.name_by_id.insert(id, name.to_string());
        self.qname_by_id.insert(id, qname.to_string());
        self.kind_by_id.insert(id, kind);
        if let Some(p) = parent {
            self.parent_of.insert(id, p);
            self.children_of.entry(p).or_default().push(id);
        }
    }
}
