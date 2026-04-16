// Step 0 — rkyv hello world.
//
// Goal: prove the JSON ↔ owned ↔ rkyv-binary ↔ mmap roundtrip works end-to-end,
// and feel rkyv's Owned/Archived split in ~50 lines before committing to the
// full type hierarchy. See memory: reference_rkyv_design.md, project_040_vision.md.
//
// First attempt used a recursive `enum NodeId { ..., Class { module: Box<NodeId>, ... } }`
// — rkyv 0.8 immediately failed with `error[E0275]: overflow evaluating the requirement
// Box<NodeId>: Archive`. Self-recursive enums via Box can't resolve rkyv's trait bounds
// without manual `#[rkyv(omit_bounds)]` ceremony.
//
// The design doc had already concluded flat ID + side table was the right shape for
// edge storage; the toolchain just confirmed it. Pivoted to the flat layout below.

use std::fs::{File, metadata};
use std::io::Write;

use memmap2::Mmap;
use rkyv::rancor::Error as RkyvError;

// Opaque ID — u64. No hierarchy in the ID itself.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
struct NodeId(u64);

// Kind tag — unit variants only, no payload.
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
#[rkyv(derive(Debug))]   // ask rkyv to derive Debug on ArchivedNodeKind too
enum NodeKind { Module, Class, Method }

// Metadata for a node. Hierarchy lives here as `parent: Option<NodeId>`,
// not inside the ID. No Box, no recursion, no rkyv friction.
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]
struct NodeMeta {
    id:     NodeId,
    kind:   NodeKind,
    name:   String,
    parent: Option<NodeId>,
}

fn build_nodes() -> Vec<NodeMeta> {
    let m = NodeMeta { id: NodeId(1), kind: NodeKind::Module, name: "myapp.users".into(), parent: None };
    let c = NodeMeta { id: NodeId(2), kind: NodeKind::Class,  name: "User".into(),        parent: Some(m.id) };
    let f = NodeMeta { id: NodeId(3), kind: NodeKind::Method, name: "login".into(),       parent: Some(c.id) };
    vec![m, c, f]
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let nodes = build_nodes();

    // --- JSON roundtrip (owned → file → owned) ---
    serde_json::to_writer_pretty(File::create("nodes.json")?, &nodes)?;
    let json_back: Vec<NodeMeta> = serde_json::from_reader(File::open("nodes.json")?)?;
    assert_eq!(nodes, json_back, "JSON roundtrip failed");

    // --- rkyv roundtrip (owned → bytes → file → mmap → archived → owned) ---
    let bytes = rkyv::to_bytes::<RkyvError>(&nodes)?;
    File::create("nodes.gmap")?.write_all(&bytes)?;

    let mmap = unsafe { Mmap::map(&File::open("nodes.gmap")?)? };
    // Zero-copy access. Note the type: &Archived<Vec<NodeMeta>>, NOT &Vec<NodeMeta>.
    // This is the Owned/Archived split made physical — different type, same shape.
    let archived = rkyv::access::<rkyv::Archived<Vec<NodeMeta>>, RkyvError>(&mmap[..])?;

    // Demonstrate zero-copy reads: walk the archived data without deserialising.
    println!("zero-copy reads from mmap:");
    for n in archived.iter() {
        // n.name is ArchivedString; derefs to &str. n.id.0 is an Archived<u64>.
        println!("  id={} kind={:?} name={}", n.id.0.to_native(), n.kind, n.name.as_str());
    }

    // Deserialise back to owned (allocates) so we can `assert_eq!` against `nodes`.
    let rkyv_back: Vec<NodeMeta> = rkyv::deserialize::<Vec<NodeMeta>, RkyvError>(archived)?;
    assert_eq!(nodes, rkyv_back, "rkyv roundtrip failed");

    println!();
    println!("JSON size: {} bytes", metadata("nodes.json")?.len());
    println!("gmap size: {} bytes", metadata("nodes.gmap")?.len());
    println!("Both roundtrips passed.");
    Ok(())
}

#[cfg(test)]
mod tests {
    #[test] fn full_roundtrip() { super::main().unwrap(); }
}
