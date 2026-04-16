//! repo-graph-core — domain-agnostic knowledge graph primitives.
//!
//! Strict Node shape: `{id, repo, confidence, cells}`. Navigation lives in
//! domain-owned indices stored in the container, not in Node fields — this
//! keeps the core agnostic to code vs chemistry vs video vs policy.
//!
//! Cell payloads are one of `Text` / `Json` / `Bytes`. Cell/Edge/NodeKind
//! tags are `u32` registry-backed; the registries live in the container
//! header (not in this crate). `GraphType` is a self-describing string.
//!
//! See memory: `reference_format_spec.md`, `project_040_vision.md`.

use core::hash::Hasher;
use twox_hash::XxHash64;

// ============================================================================
// IDs
// ============================================================================

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug, PartialEq, Eq, Hash))]
pub struct NodeId(pub u64);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug, PartialEq, Eq, Hash))]
pub struct RepoId(pub u64);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug, PartialEq, Eq, Hash))]
pub struct ShardId(pub u64);

/// Self-describing graph-type tag — one per container file.
/// Code = `"code"`, chemistry = `"chemistry"`, etc. Core interprets no values.
#[derive(Debug, Clone, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug))]
pub struct GraphType(pub String);

impl GraphType {
    pub fn code() -> Self { Self("code".into()) }
    pub fn as_str(&self) -> &str { &self.0 }
}

impl NodeId {
    /// `NodeId = xxhash(graph_type, repo, kind, qualified_name)`.
    /// Separators prevent field-boundary collisions.
    pub fn from_parts(graph_type: &str, repo: RepoId, kind: NodeKindId, qname: &str) -> Self {
        let mut h = XxHash64::with_seed(0);
        h.write(graph_type.as_bytes());
        h.write_u8(0xFF);
        h.write_u64(repo.0);
        h.write_u8(0xFF);
        h.write_u32(kind.0);
        h.write_u8(0xFF);
        h.write(qname.as_bytes());
        Self(h.finish())
    }
}

impl RepoId {
    pub fn from_canonical(url_or_path: &str) -> Self {
        let mut h = XxHash64::with_seed(0);
        h.write(url_or_path.as_bytes());
        Self(h.finish())
    }
}

impl ShardId {
    pub fn from_parts(repo: RepoId, shard_name: &str) -> Self {
        let mut h = XxHash64::with_seed(0);
        h.write_u64(repo.0);
        h.write_u8(0xFF);
        h.write(shard_name.as_bytes());
        Self(h.finish())
    }
}

// ============================================================================
// Kinds & registry-backed tags
// ============================================================================

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug, PartialEq, Eq, Hash))]
pub enum Confidence {
    Strong,
    Medium,
    Weak,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug, PartialEq, Eq, Hash))]
pub enum FlowKind {
    Http,
    Page,
    Cli,
    Grpc,
    Queue,
}

/// Registry-backed cell type tag. Interpretation lives in the per-domain
/// cell registry stored in the container header.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug, PartialEq, Eq, Hash))]
pub struct CellTypeId(pub u32);

/// Registry-backed edge category tag. Interpretation lives in the per-domain
/// edge registry stored in the container header.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug, PartialEq, Eq, Hash))]
pub struct EdgeCategoryId(pub u32);

/// Registry-backed node-kind tag. Code: Module/Class/Method/Route/...
/// Chemistry: Atom/Bond/Molecule/...
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug, PartialEq, Eq, Hash))]
pub struct NodeKindId(pub u32);

// ============================================================================
// Cells
// ============================================================================

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug))]
pub enum CellPayload {
    /// Most cells: code, intent, doc, conv.
    Text(String),
    /// Structured cells: position, attn, decisions.
    Json(String),
    /// Binary cells: cached embeddings.
    Bytes(Vec<u8>),
}

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug))]
pub struct Cell {
    pub kind: CellTypeId,
    pub payload: CellPayload,
}

// ============================================================================
// Core graph types
// ============================================================================

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug))]
pub struct Node {
    pub id: NodeId,
    pub repo: RepoId,
    pub confidence: Confidence,
    pub cells: Vec<Cell>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug, PartialEq, Eq, Hash))]
pub struct Edge {
    pub from: NodeId,
    pub to: NodeId,
    pub category: EdgeCategoryId,
    pub confidence: Confidence,
}

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug))]
pub struct Flow {
    pub kind: FlowKind,
    pub entry: NodeId,
    pub steps: Vec<NodeId>,
    pub confidence: Confidence,
}

// ============================================================================
// Traits — same surface on Owned and Archived forms
// ============================================================================

pub trait NodeLike {
    fn id(&self) -> NodeId;
    fn repo(&self) -> RepoId;
    fn confidence(&self) -> Confidence;
    fn cell_count(&self) -> usize;
}

impl NodeLike for Node {
    fn id(&self) -> NodeId { self.id }
    fn repo(&self) -> RepoId { self.repo }
    fn confidence(&self) -> Confidence { self.confidence }
    fn cell_count(&self) -> usize { self.cells.len() }
}

impl NodeLike for ArchivedNode {
    fn id(&self) -> NodeId { NodeId(self.id.0.to_native()) }
    fn repo(&self) -> RepoId { RepoId(self.repo.0.to_native()) }
    fn confidence(&self) -> Confidence { (&self.confidence).into() }
    fn cell_count(&self) -> usize { self.cells.len() }
}

pub trait EdgeLike {
    fn from_id(&self) -> NodeId;
    fn to_id(&self) -> NodeId;
    fn category(&self) -> EdgeCategoryId;
    fn confidence(&self) -> Confidence;
}

impl EdgeLike for Edge {
    fn from_id(&self) -> NodeId { self.from }
    fn to_id(&self) -> NodeId { self.to }
    fn category(&self) -> EdgeCategoryId { self.category }
    fn confidence(&self) -> Confidence { self.confidence }
}

impl EdgeLike for ArchivedEdge {
    fn from_id(&self) -> NodeId { NodeId(self.from.0.to_native()) }
    fn to_id(&self) -> NodeId { NodeId(self.to.0.to_native()) }
    fn category(&self) -> EdgeCategoryId { EdgeCategoryId(self.category.0.to_native()) }
    fn confidence(&self) -> Confidence { (&self.confidence).into() }
}

// Bridge the archived unit-variant enum back to its owned form — needed to
// make the traits uniform across Owned/Archived.
impl From<&ArchivedConfidence> for Confidence {
    fn from(v: &ArchivedConfidence) -> Self {
        match v {
            ArchivedConfidence::Strong => Confidence::Strong,
            ArchivedConfidence::Medium => Confidence::Medium,
            ArchivedConfidence::Weak => Confidence::Weak,
        }
    }
}

// ============================================================================
// Errors
// ============================================================================

#[derive(Debug, thiserror::Error)]
pub enum CoreError {
    #[error("id collision: {0}")]
    IdCollision(String),
    #[error("missing parent for node {0:?}")]
    MissingParent(NodeId),
    #[error("invalid utf-8: {0}")]
    InvalidUtf8(#[from] core::str::Utf8Error),
    #[error("registry has no entry for id {0}")]
    RegistryUnknown(u32),
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn node_id_deterministic() {
        let repo = RepoId::from_canonical("github.com/x/y");
        let a = NodeId::from_parts("code", repo, NodeKindId(1), "foo.bar.baz");
        let b = NodeId::from_parts("code", repo, NodeKindId(1), "foo.bar.baz");
        assert_eq!(a, b);
    }

    #[test]
    fn node_id_separators_prevent_field_collision() {
        let repo = RepoId::from_canonical("r");
        let a = NodeId::from_parts("co", repo, NodeKindId(1), "de");
        let b = NodeId::from_parts("c", repo, NodeKindId(1), "ode");
        assert_ne!(a, b);
    }

    #[test]
    fn rkyv_roundtrip_nodes() {
        let nodes = vec![Node {
            id: NodeId::from_parts("code", RepoId(1), NodeKindId(1), "mod.a"),
            repo: RepoId(1),
            confidence: Confidence::Strong,
            cells: vec![Cell {
                kind: CellTypeId(0),
                payload: CellPayload::Text("hello".into()),
            }],
        }];
        let bytes = rkyv::to_bytes::<rkyv::rancor::Error>(&nodes).unwrap();
        let archived =
            rkyv::access::<rkyv::Archived<Vec<Node>>, rkyv::rancor::Error>(&bytes).unwrap();
        let back: Vec<Node> =
            rkyv::deserialize::<Vec<Node>, rkyv::rancor::Error>(archived).unwrap();
        assert_eq!(nodes, back);
    }

    #[test]
    fn node_like_trait_works_on_both_forms() {
        let n = Node {
            id: NodeId(42),
            repo: RepoId(7),
            confidence: Confidence::Medium,
            cells: vec![],
        };
        // Owned
        assert_eq!(n.id(), NodeId(42));
        assert_eq!(n.repo(), RepoId(7));
        assert_eq!(n.confidence(), Confidence::Medium);
        assert_eq!(n.cell_count(), 0);

        // Archived
        let nodes = vec![n.clone()];
        let bytes = rkyv::to_bytes::<rkyv::rancor::Error>(&nodes).unwrap();
        let archived =
            rkyv::access::<rkyv::Archived<Vec<Node>>, rkyv::rancor::Error>(&bytes).unwrap();
        let arch_n = &archived[0];
        assert_eq!(arch_n.id(), NodeId(42));
        assert_eq!(arch_n.repo(), RepoId(7));
        assert_eq!(arch_n.confidence(), Confidence::Medium);
        assert_eq!(arch_n.cell_count(), 0);
    }

    #[test]
    fn edge_like_trait_works_on_both_forms() {
        let e = Edge {
            from: NodeId(1),
            to: NodeId(2),
            category: EdgeCategoryId(5),
            confidence: Confidence::Weak,
        };
        assert_eq!(e.from_id(), NodeId(1));

        let edges = vec![e];
        let bytes = rkyv::to_bytes::<rkyv::rancor::Error>(&edges).unwrap();
        let archived =
            rkyv::access::<rkyv::Archived<Vec<Edge>>, rkyv::rancor::Error>(&bytes).unwrap();
        let arch_e = &archived[0];
        assert_eq!(arch_e.from_id(), NodeId(1));
        assert_eq!(arch_e.to_id(), NodeId(2));
        assert_eq!(arch_e.category(), EdgeCategoryId(5));
        assert_eq!(arch_e.confidence(), Confidence::Weak);
    }

    #[test]
    fn hash_collision_smoke_1000() {
        use std::collections::HashSet;
        let repo = RepoId::from_canonical("repo");
        let mut seen = HashSet::new();
        for i in 0..1000 {
            let id = NodeId::from_parts("code", repo, NodeKindId(1), &format!("entity_{i}"));
            assert!(seen.insert(id), "collision at i={i}");
        }
    }
}
