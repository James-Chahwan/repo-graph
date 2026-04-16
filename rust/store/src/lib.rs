//! repo-graph-store — `.gmap` container format: write a `RepoGraph` to disk
//! as a single rkyv-archived `Container`, mmap it back zero-copy, and traverse
//! the archived form via `NodeLike` / `EdgeLike` (see `repo-graph-core`).
//!
//! Design notes (locked 2026-04-17):
//! - **Single rkyv-archived top-level `Container` per file**, not the
//!   sectioned-byte-ranges layout from the spec. Sectioned layout becomes
//!   relevant at v0.4.5c (sharding) or v0.4.10 (multi-domain). For one
//!   single-domain repo, one container is simpler and gives us everything
//!   the zero-copy invariant promises.
//! - **HashMaps converted to sorted `Vec<(K, V)>` at the serialise boundary.**
//!   Reasons: rkyv 0.8 supports `HashMap` but the cost is real; sorted Vecs
//!   align with the spec's "domain-owned indices as named byte ranges" model;
//!   binary-search lookup on the archived form is fast enough for the access
//!   patterns we have today (resolver lookups happen during build, not on
//!   the read path; on-disk read path is BFS which iterates rather than
//!   point-queries).
//! - **`.gmap` extension** — confirmed name (also matches the LLM-interface
//!   framing: `gmap binary / gmap text / gmap vectors`).
//! - **Atomic write via `.gmap.tmp` + rename** — no torn-write window.
//! - **Self-referential mmap holder** — the `MmapContainer` ties the `Mmap`
//!   and the borrow into one struct via a private constructor that bounds
//!   the lifetime. No `ouroboros`; the surface is small enough to hand-roll.

use std::{
    fs::{File, OpenOptions, rename},
    io::Write,
    path::{Path, PathBuf},
};

use memmap2::{Mmap, MmapOptions};
use repo_graph_code_domain::{CallSite, CodeNav, UnresolvedRef};
use repo_graph_core::{Edge, EdgeCategoryId, Node, NodeId, NodeKindId, RepoId};
use repo_graph_graph::{RepoGraph, SymbolTable};

// ============================================================================
// Container shape
// ============================================================================

/// Magic bytes carried in the container header — `b"GMAP"`.
pub const MAGIC: [u8; 4] = *b"GMAP";

/// Format version. Bump on any layout change. Loader rejects mismatches.
pub const FORMAT_VERSION: u32 = 1;

/// Top-level on-disk shape. Owned form = what the writer builds; Archived form
/// = `&ArchivedContainer`, what mmap returns.
#[derive(Debug, Clone, PartialEq)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug))]
pub struct Container {
    pub header: Header,
    pub repo: RepoId,
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
    pub code_nav: CodeNavStore,
    pub symbols: SymbolTableStore,
    pub unresolved_calls: Vec<CallSite>,
    pub unresolved_refs: Vec<UnresolvedRef>,
}

/// File header. Magic + version are checked on load. Registries are
/// diagnostic-only at v0.4.5a — not load-bearing — but they let a future
/// `gmap inspect` command name the u32 ids.
#[derive(Debug, Clone, PartialEq)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug))]
pub struct Header {
    pub magic: [u8; 4],
    pub version: u32,
    pub graph_type: String,
    pub cell_registry: Vec<RegistryEntry>,
    pub edge_category_registry: Vec<RegistryEntry>,
    pub node_kind_registry: Vec<RegistryEntry>,
}

#[derive(Debug, Clone, PartialEq)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug))]
pub struct RegistryEntry {
    pub id: u32,
    pub name: String,
}

// ============================================================================
// CodeNav / SymbolTable — serialised mirrors using sorted Vecs
// ============================================================================

/// Serialised mirror of `CodeNav`. Each field is the source HashMap flattened
/// into a Vec of pairs, **sorted by key**. Sorting makes the on-disk bytes
/// deterministic (so two builds of the same graph produce byte-identical files,
/// useful for content-hash-based shard manifests at v0.4.5c) and lets future
/// readers binary-search the archived form for point lookups.
#[derive(Debug, Clone, PartialEq, Default)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug))]
pub struct CodeNavStore {
    pub name_by_id: Vec<(NodeId, String)>,
    pub qname_by_id: Vec<(NodeId, String)>,
    pub kind_by_id: Vec<(NodeId, NodeKindId)>,
    pub parent_of: Vec<(NodeId, NodeId)>,
    pub children_of: Vec<(NodeId, Vec<NodeId>)>,
}

#[derive(Debug, Clone, PartialEq, Default)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug))]
pub struct SymbolTableStore {
    pub module_by_qname: Vec<(String, NodeId)>,
    pub module_symbols: Vec<(NodeId, Vec<(String, NodeId)>)>,
    pub class_methods: Vec<(NodeId, Vec<(String, NodeId)>)>,
    pub module_import_bindings: Vec<(NodeId, Vec<(String, NodeId)>)>,
}

impl CodeNavStore {
    pub fn from_owned(nav: &CodeNav) -> Self {
        let mut name_by_id: Vec<_> = nav
            .name_by_id
            .iter()
            .map(|(k, v)| (*k, v.clone()))
            .collect();
        name_by_id.sort_by_key(|(k, _)| k.0);

        let mut qname_by_id: Vec<_> = nav
            .qname_by_id
            .iter()
            .map(|(k, v)| (*k, v.clone()))
            .collect();
        qname_by_id.sort_by_key(|(k, _)| k.0);

        let mut kind_by_id: Vec<_> =
            nav.kind_by_id.iter().map(|(k, v)| (*k, *v)).collect();
        kind_by_id.sort_by_key(|(k, _)| k.0);

        let mut parent_of: Vec<_> =
            nav.parent_of.iter().map(|(k, v)| (*k, *v)).collect();
        parent_of.sort_by_key(|(k, _)| k.0);

        let mut children_of: Vec<_> = nav
            .children_of
            .iter()
            .map(|(k, v)| (*k, v.clone()))
            .collect();
        children_of.sort_by_key(|(k, _)| k.0);

        Self {
            name_by_id,
            qname_by_id,
            kind_by_id,
            parent_of,
            children_of,
        }
    }
}

impl SymbolTableStore {
    pub fn from_owned(sym: &SymbolTable) -> Self {
        let mut module_by_qname: Vec<_> = sym
            .module_by_qname
            .iter()
            .map(|(k, v)| (k.clone(), *v))
            .collect();
        module_by_qname.sort_by(|a, b| a.0.cmp(&b.0));

        let to_pair_vec = |m: &std::collections::HashMap<NodeId, std::collections::HashMap<String, NodeId>>| {
            let mut out: Vec<_> = m
                .iter()
                .map(|(k, inner)| {
                    let mut pairs: Vec<_> =
                        inner.iter().map(|(s, n)| (s.clone(), *n)).collect();
                    pairs.sort_by(|a, b| a.0.cmp(&b.0));
                    (*k, pairs)
                })
                .collect();
            out.sort_by_key(|(k, _)| k.0);
            out
        };

        Self {
            module_by_qname,
            module_symbols: to_pair_vec(&sym.module_symbols),
            class_methods: to_pair_vec(&sym.class_methods),
            module_import_bindings: to_pair_vec(&sym.module_import_bindings),
        }
    }
}

impl Container {
    /// Build a `Container` from an owned `RepoGraph`. Cheap conversion: clones
    /// nodes/edges and flattens the maps. Caller drops the source graph after
    /// writing.
    pub fn from_repo_graph(g: &RepoGraph) -> Self {
        Self {
            header: Header::for_code(),
            repo: g.repo,
            nodes: g.nodes.clone(),
            edges: g.edges.clone(),
            code_nav: CodeNavStore::from_owned(&g.nav),
            symbols: SymbolTableStore::from_owned(&g.symbols),
            unresolved_calls: g.unresolved_calls.clone(),
            unresolved_refs: g.unresolved_refs.clone(),
        }
    }

    /// Build a `Container` carrying only cross-repo edges. Used by the sharded
    /// layout to write `cross_stack.gmap` — nodes/nav/symbols are empty because
    /// every cross-edge's endpoints live in some other shard. The synthetic
    /// `repo` comes from `RepoId::from_canonical("cross_stack")` so the file
    /// is self-identifying without needing a new container variant.
    pub fn for_cross_edges(edges: Vec<Edge>) -> Self {
        Self {
            header: Header::for_code(),
            repo: RepoId::from_canonical("cross_stack"),
            nodes: Vec::new(),
            edges,
            code_nav: CodeNavStore::default(),
            symbols: SymbolTableStore::default(),
            unresolved_calls: Vec::new(),
            unresolved_refs: Vec::new(),
        }
    }
}

impl Header {
    /// Header for a code-domain container. v0.4.5a leaves the registries
    /// empty — they're diagnostic surfaces and the per-domain crates haven't
    /// exposed a registration API yet (lands at v0.4.10).
    pub fn for_code() -> Self {
        Self {
            magic: MAGIC,
            version: FORMAT_VERSION,
            graph_type: "code".to_string(),
            cell_registry: Vec::new(),
            edge_category_registry: Vec::new(),
            node_kind_registry: Vec::new(),
        }
    }
}

// ============================================================================
// Errors
// ============================================================================

#[derive(Debug, thiserror::Error)]
pub enum StoreError {
    #[error("io: {0}")]
    Io(#[from] std::io::Error),
    #[error("rkyv: {0}")]
    Rkyv(#[from] rkyv::rancor::Error),
    #[error("bad magic bytes — expected {expected:?}, got {got:?}")]
    BadMagic { expected: [u8; 4], got: [u8; 4] },
    #[error("unsupported format version {0} (this build supports {1})")]
    UnsupportedVersion(u32, u32),
    #[error("manifest json: {0}")]
    ManifestJson(#[from] serde_json::Error),
    #[error(
        "unsupported manifest schema version {got} (this build supports {supported})"
    )]
    ManifestSchemaVersion { got: u32, supported: u32 },
    #[error(
        "content hash mismatch on shard {shard} — manifest says {expected}, file is {got}"
    )]
    ContentHashMismatch {
        shard: String,
        expected: String,
        got: String,
    },
    #[error("manifest references shard {0} but the file is missing")]
    ShardMissing(String),
}

// ============================================================================
// Write — atomic via .tmp + rename
// ============================================================================

/// Serialise a `RepoGraph` to a `.gmap` file. Writes to `<path>.tmp` first,
/// then atomically renames over `<path>` so a crash mid-write never leaves a
/// half-written file in place. Existing readers' mmaps stay valid against the
/// old inode until they re-open.
pub fn write_repo_graph(g: &RepoGraph, path: &Path) -> Result<(), StoreError> {
    let container = Container::from_repo_graph(g);
    let bytes = rkyv::to_bytes::<rkyv::rancor::Error>(&container)?;
    write_atomic(path, &bytes)
}

fn write_atomic(path: &Path, bytes: &[u8]) -> Result<(), StoreError> {
    let tmp_path: PathBuf = with_tmp_suffix(path);
    {
        let mut f = OpenOptions::new()
            .create(true)
            .truncate(true)
            .write(true)
            .open(&tmp_path)?;
        f.write_all(bytes)?;
        f.sync_all()?;
    }
    rename(&tmp_path, path)?;
    Ok(())
}

fn with_tmp_suffix(path: &Path) -> PathBuf {
    let mut s = path.as_os_str().to_owned();
    s.push(".tmp");
    PathBuf::from(s)
}

// ============================================================================
// Read — mmap zero-copy
// ============================================================================

/// Owns the mmap'd bytes and exposes a borrowed `&ArchivedContainer` view.
///
/// The archived view is reborrowed out of `bytes` via `rkyv::access`. We hold
/// the `Mmap` alive for the lifetime of `MmapContainer` so the borrow stays
/// valid; the `archived()` accessor returns a borrow tied to `&self`, which is
/// exactly what the caller wants — they can't outlive the mmap.
pub struct MmapContainer {
    bytes: Mmap,
}

impl MmapContainer {
    /// Open a `.gmap` file zero-copy. Validates magic + version on first
    /// access; the file stays mmap'd for the life of the returned struct.
    pub fn open(path: &Path) -> Result<Self, StoreError> {
        let f = File::open(path)?;
        // Safety: the file is opened read-only and Mmap is read-only. Other
        // processes mutating this exact path while we hold the mmap could
        // surprise us, but the write path uses tmp+rename so concurrent
        // writers replace the inode rather than mutate it in place — our
        // mmap stays pinned to the old inode until we drop.
        let bytes = unsafe { MmapOptions::new().map(&f)? };
        let s = Self { bytes };
        s.validate_header()?;
        Ok(s)
    }

    fn validate_header(&self) -> Result<(), StoreError> {
        let archived = self.archived()?;
        let magic_bytes: [u8; 4] = [
            archived.header.magic[0],
            archived.header.magic[1],
            archived.header.magic[2],
            archived.header.magic[3],
        ];
        if magic_bytes != MAGIC {
            return Err(StoreError::BadMagic {
                expected: MAGIC,
                got: magic_bytes,
            });
        }
        let v = archived.header.version.to_native();
        if v != FORMAT_VERSION {
            return Err(StoreError::UnsupportedVersion(v, FORMAT_VERSION));
        }
        Ok(())
    }

    /// Borrow the archived container for the life of `self`. Cheap: a single
    /// `rkyv::access` call. Cache the result if you call it in a hot loop.
    pub fn archived(&self) -> Result<&ArchivedContainer, StoreError> {
        Ok(rkyv::access::<ArchivedContainer, rkyv::rancor::Error>(
            &self.bytes,
        )?)
    }

    /// Raw mmap byte length — useful for diagnostics and size-on-disk asserts.
    pub fn len(&self) -> usize {
        self.bytes.len()
    }

    pub fn is_empty(&self) -> bool {
        self.bytes.is_empty()
    }
}

// ============================================================================
// Convenience accessors on the archived form
// ============================================================================

impl ArchivedContainer {
    /// Walk the archived edges, yielding `(from, to, category)`. Useful for
    /// cheap edge counts and traversal without rehydrating into owned types.
    pub fn edges_iter(&self) -> impl Iterator<Item = (NodeId, NodeId, EdgeCategoryId)> + '_ {
        self.edges.iter().map(|e| {
            (
                NodeId(e.from.0.to_native()),
                NodeId(e.to.0.to_native()),
                EdgeCategoryId(e.category.0.to_native()),
            )
        })
    }

    /// Look up a node id's qname via binary search on the sorted nav vec.
    pub fn qname(&self, id: NodeId) -> Option<&str> {
        let pairs = &self.code_nav.qname_by_id;
        let i = pairs
            .binary_search_by(|entry| entry.0.0.to_native().cmp(&id.0))
            .ok()?;
        Some(pairs[i].1.as_str())
    }

    /// Look up a node id's kind via binary search.
    pub fn kind(&self, id: NodeId) -> Option<NodeKindId> {
        let pairs = &self.code_nav.kind_by_id;
        let i = pairs
            .binary_search_by(|entry| entry.0.0.to_native().cmp(&id.0))
            .ok()?;
        Some(NodeKindId(pairs[i].1.0.to_native()))
    }
}

// ============================================================================
// Sharded layout — manifest.json + per-shard .gmap + cross_stack.gmap
// ============================================================================

/// Manifest schema version. Bump on any manifest JSON shape change.
pub const MANIFEST_VERSION: u32 = 1;
/// Filename of the manifest inside a sharded directory.
pub const MANIFEST_NAME: &str = "manifest.json";
/// Filename of the cross-stack edge shard inside a sharded directory.
pub const CROSS_STACK_NAME: &str = "cross_stack.gmap";

/// Top-level manifest for a sharded `.gmap` directory.
///
/// One entry per per-repo `.gmap` plus an optional `cross` entry for the
/// cross-stack edge shard. Each entry carries a content hash so the loader
/// can detect on-disk corruption or stale shards from a partial rewrite.
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct Manifest {
    pub schema_version: u32,
    pub shards: Vec<ShardEntry>,
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub cross: Option<ShardEntry>,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct ShardEntry {
    /// Caller-provided name for this shard ("backend", "frontend", ...).
    pub name: String,
    /// Path to the `.gmap` file relative to the manifest's directory.
    pub path: String,
    /// xxhash64 of the shard's bytes, hex-encoded (16 lowercase hex chars).
    pub content_hash: String,
}

/// Write a sharded `.gmap` layout: one `<name>.gmap` per input graph plus a
/// `cross_stack.gmap` if `cross_edges` is non-empty, plus a `manifest.json`.
/// Returns the manifest that was written so callers can inspect hashes.
///
/// Shard names must be unique and non-empty — duplicates produce a manifest
/// whose loader will reject it.
pub fn write_sharded(
    shards: &[(&str, &RepoGraph)],
    cross_edges: &[Edge],
    dir: &Path,
) -> Result<Manifest, StoreError> {
    std::fs::create_dir_all(dir)?;

    let mut entries = Vec::with_capacity(shards.len());
    for (name, g) in shards {
        let file_name = format!("{name}.gmap");
        let shard_path = dir.join(&file_name);
        let container = Container::from_repo_graph(g);
        let bytes = rkyv::to_bytes::<rkyv::rancor::Error>(&container)?;
        write_atomic(&shard_path, &bytes)?;
        entries.push(ShardEntry {
            name: (*name).to_string(),
            path: file_name,
            content_hash: hex_xxhash64(&bytes),
        });
    }

    let cross = if cross_edges.is_empty() {
        None
    } else {
        let shard_path = dir.join(CROSS_STACK_NAME);
        let container = Container::for_cross_edges(cross_edges.to_vec());
        let bytes = rkyv::to_bytes::<rkyv::rancor::Error>(&container)?;
        write_atomic(&shard_path, &bytes)?;
        Some(ShardEntry {
            name: "cross_stack".to_string(),
            path: CROSS_STACK_NAME.to_string(),
            content_hash: hex_xxhash64(&bytes),
        })
    };

    let manifest = Manifest {
        schema_version: MANIFEST_VERSION,
        shards: entries,
        cross,
    };
    let manifest_bytes = serde_json::to_vec_pretty(&manifest)?;
    write_atomic(&dir.join(MANIFEST_NAME), &manifest_bytes)?;
    Ok(manifest)
}

fn hex_xxhash64(bytes: &[u8]) -> String {
    use core::hash::Hasher;
    use twox_hash::XxHash64;
    let mut h = XxHash64::with_seed(0);
    h.write(bytes);
    format!("{:016x}", h.finish())
}

/// A sharded layout opened zero-copy. Each per-shard `.gmap` is its own mmap'd
/// `MmapContainer`; the manifest is loaded eagerly and verified against the
/// files on disk.
pub struct ShardedMmap {
    pub manifest: Manifest,
    pub shards: Vec<(String, MmapContainer)>,
    pub cross: Option<MmapContainer>,
}

impl ShardedMmap {
    /// Open a sharded directory. Validates the manifest schema version, then
    /// opens each shard's `.gmap` and verifies its content hash against the
    /// manifest. Returns on the first hash mismatch or missing file.
    pub fn open(dir: &Path) -> Result<Self, StoreError> {
        let manifest_bytes = std::fs::read(dir.join(MANIFEST_NAME))?;
        let manifest: Manifest = serde_json::from_slice(&manifest_bytes)?;
        if manifest.schema_version != MANIFEST_VERSION {
            return Err(StoreError::ManifestSchemaVersion {
                got: manifest.schema_version,
                supported: MANIFEST_VERSION,
            });
        }

        let mut shards = Vec::with_capacity(manifest.shards.len());
        for entry in &manifest.shards {
            let shard_path = dir.join(&entry.path);
            verify_hash(entry, &shard_path)?;
            let mmap = MmapContainer::open(&shard_path)?;
            shards.push((entry.name.clone(), mmap));
        }

        let cross = if let Some(entry) = &manifest.cross {
            let shard_path = dir.join(&entry.path);
            verify_hash(entry, &shard_path)?;
            Some(MmapContainer::open(&shard_path)?)
        } else {
            None
        };

        Ok(Self {
            manifest,
            shards,
            cross,
        })
    }

    /// Iterate all edges across every shard and the cross-stack shard. Useful
    /// for whole-merged-graph walks without rehydrating owned types.
    pub fn edges_iter(&self) -> impl Iterator<Item = (NodeId, NodeId, EdgeCategoryId)> + '_ {
        let shard_edges = self.shards.iter().flat_map(|(_, mmap)| match mmap.archived() {
            Ok(a) => Some(a.edges_iter()),
            Err(_) => None,
        }).flatten();
        let cross_edges = self
            .cross
            .as_ref()
            .and_then(|m| m.archived().ok())
            .map(|a| a.edges_iter())
            .into_iter()
            .flatten();
        shard_edges.chain(cross_edges)
    }
}

fn verify_hash(entry: &ShardEntry, path: &Path) -> Result<(), StoreError> {
    if !path.exists() {
        return Err(StoreError::ShardMissing(entry.name.clone()));
    }
    let bytes = std::fs::read(path)?;
    let got = hex_xxhash64(&bytes);
    if got != entry.content_hash {
        return Err(StoreError::ContentHashMismatch {
            shard: entry.name.clone(),
            expected: entry.content_hash.clone(),
            got,
        });
    }
    Ok(())
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn header_round_trips_via_rkyv() {
        let h = Header::for_code();
        let bytes = rkyv::to_bytes::<rkyv::rancor::Error>(&h).unwrap();
        let archived =
            rkyv::access::<ArchivedHeader, rkyv::rancor::Error>(&bytes).unwrap();
        assert_eq!(archived.magic, MAGIC);
        assert_eq!(archived.version.to_native(), FORMAT_VERSION);
        assert_eq!(archived.graph_type.as_str(), "code");
    }

    #[test]
    fn empty_container_round_trips() {
        let c = Container {
            header: Header::for_code(),
            repo: RepoId::from_canonical("test://empty"),
            nodes: Vec::new(),
            edges: Vec::new(),
            code_nav: CodeNavStore::default(),
            symbols: SymbolTableStore::default(),
            unresolved_calls: Vec::new(),
            unresolved_refs: Vec::new(),
        };
        let bytes = rkyv::to_bytes::<rkyv::rancor::Error>(&c).unwrap();
        let archived =
            rkyv::access::<ArchivedContainer, rkyv::rancor::Error>(&bytes).unwrap();
        assert_eq!(archived.nodes.len(), 0);
        assert_eq!(archived.edges.len(), 0);
    }

    #[test]
    fn nav_store_sorts_by_node_id() {
        let mut nav = CodeNav::default();
        nav.record(NodeId(50), "b", "m::b", NodeKindId(1), None);
        nav.record(NodeId(10), "a", "m::a", NodeKindId(1), None);
        nav.record(NodeId(30), "c", "m::c", NodeKindId(1), None);
        let store = CodeNavStore::from_owned(&nav);
        let ids: Vec<u64> = store.name_by_id.iter().map(|(k, _)| k.0).collect();
        assert_eq!(ids, vec![10, 30, 50]);
    }
}
