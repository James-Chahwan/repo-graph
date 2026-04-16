//! One-shot dump of quokka-stack (Go backend + TS frontend) to /tmp/quokka-gmap/.
//! Run: `cargo test -p repo-graph-store --test quokka_dump -- --nocapture`

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use repo_graph_core::RepoId;
use repo_graph_graph::{build_go, build_typescript, HttpStackResolver, MergedGraph, RepoGraph};
use repo_graph_parser_go as go;
use repo_graph_parser_typescript as ts;
use repo_graph_projection_text::{render_merged, render_repo_graph};
use repo_graph_store::write_sharded;

const GO_ROOT: &str = "/home/ivy/Code/quokka-stack/turps";
const TS_ROOT: &str = "/home/ivy/Code/quokka_web";
const GO_MODULE_PREFIX: &str = "turps";
const OUTPUT_DIR: &str = "/tmp/quokka-gmap";

fn go_repo() -> RepoId {
    RepoId::from_canonical("quokka-stack://turps")
}

fn ts_repo() -> RepoId {
    RepoId::from_canonical("quokka-stack://quokka_web")
}

fn walk_files(root: &Path, ext: &str) -> Vec<PathBuf> {
    let mut out = Vec::new();
    walk_rec(root, ext, &mut out);
    out.sort();
    out
}

fn walk_rec(dir: &Path, ext: &str, acc: &mut Vec<PathBuf>) {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for e in entries.flatten() {
        let p = e.path();
        if p.is_dir() {
            let name = p.file_name().unwrap_or_default().to_str().unwrap_or("");
            if name == "node_modules" || name == "dist" || name == "vendor" || name == ".git" {
                continue;
            }
            walk_rec(&p, ext, acc);
        } else if p.extension().and_then(|e| e.to_str()) == Some(ext) {
            acc.push(p);
        }
    }
}

fn build_go_graph() -> RepoGraph {
    let root = PathBuf::from(GO_ROOT);
    let files = walk_files(&root, "go");
    let repo = go_repo();

    let mut parses = Vec::new();
    let mut skipped = 0u32;

    for path in &files {
        let src = std::fs::read_to_string(path).unwrap();

        // Skip generated files.
        if src.starts_with("// Code generated") || src.starts_with("// Package docs Code generated")
        {
            skipped += 1;
            continue;
        }

        let rel = path.strip_prefix(&root).unwrap().to_str().unwrap();
        let dir = path.parent().unwrap();
        let pkg_qname = if dir == root {
            "main".to_string()
        } else {
            dir.strip_prefix(&root)
                .unwrap()
                .to_str()
                .unwrap()
                .replace('/', "::")
        };

        match go::parse_file(&src, rel, &pkg_qname, GO_MODULE_PREFIX, repo) {
            Ok(fp) => parses.push(fp),
            Err(e) => eprintln!("SKIP {rel}: {e}"),
        }
    }

    eprintln!(
        "Go: parsed {} files, skipped {skipped} generated",
        parses.len()
    );
    build_go(repo, parses).unwrap()
}

fn build_ts_graph() -> RepoGraph {
    let root = PathBuf::from(TS_ROOT);
    let src_root = root.join("src");
    let files = walk_files(&src_root, "ts");
    let repo = ts_repo();

    // Build a lookup table of qname → true for the resolve closure.
    let mut qname_of_file: HashMap<PathBuf, String> = HashMap::new();
    let mut parses = Vec::new();

    // First pass: collect all file → qname mappings.
    for path in &files {
        if path
            .file_name()
            .unwrap_or_default()
            .to_str()
            .unwrap_or("")
            .ends_with(".spec.ts")
        {
            continue;
        }
        let rel = path.strip_prefix(&root).unwrap();
        let qname = rel
            .to_str()
            .unwrap()
            .trim_end_matches(".ts")
            .replace('/', "::");
        qname_of_file.insert(path.clone(), qname);
    }

    // Build a set of known qnames for the resolver.
    let known_qnames: HashMap<String, bool> = qname_of_file
        .values()
        .map(|q| (q.clone(), true))
        .collect();

    // Parse all files.
    for (path, qname) in &qname_of_file {
        let src_text = std::fs::read_to_string(path).unwrap();
        let rel = path.strip_prefix(&root).unwrap().to_str().unwrap();
        match ts::parse_file(&src_text, rel, qname, repo) {
            Ok(fp) => parses.push(fp),
            Err(e) => eprintln!("SKIP {rel}: {e}"),
        }
    }

    eprintln!("TS: parsed {} files", parses.len());

    // Resolve closure: relative paths → qnames.
    let resolver = move |from_qname: &str, raw_source: &str| -> Option<String> {
        if !raw_source.starts_with('.') {
            return None; // external (npm package)
        }
        // Compute directory of the importing module from its qname.
        let from_parts: Vec<&str> = from_qname.rsplitn(2, "::").collect();
        let from_dir = if from_parts.len() == 2 {
            from_parts[1].replace("::", "/")
        } else {
            String::new()
        };

        // Resolve relative path.
        let resolved = PathBuf::from(&from_dir).join(raw_source);
        let mut components = Vec::new();
        for c in resolved.components() {
            match c {
                std::path::Component::ParentDir => {
                    components.pop();
                }
                std::path::Component::Normal(s) => {
                    components.push(s.to_str().unwrap_or("").to_string());
                }
                _ => {}
            }
        }
        let base = components.join("::");

        // Try exact match, then with /index suffix.
        if known_qnames.contains_key(&base) {
            return Some(base);
        }
        let with_index = format!("{base}::index");
        if known_qnames.contains_key(&with_index) {
            return Some(with_index);
        }
        None
    };

    build_typescript(repo, parses, resolver).unwrap()
}

#[test]
fn dump_quokka_gmap() {
    let go_g = build_go_graph();
    let ts_g = build_ts_graph();

    eprintln!(
        "Go graph: {} nodes, {} edges",
        go_g.nodes.len(),
        go_g.edges.len()
    );
    eprintln!(
        "TS graph: {} nodes, {} edges",
        ts_g.nodes.len(),
        ts_g.edges.len()
    );

    // --- Merged graph with HTTP cross-linking.
    let mut merged = MergedGraph::new(vec![go_g, ts_g]);
    merged.run(&HttpStackResolver);

    eprintln!("Cross edges: {}", merged.cross_edges.len());

    // --- Dense text projection.
    let text = render_merged(&merged);
    let text_path = PathBuf::from(OUTPUT_DIR).join("gmap-text.txt");
    std::fs::create_dir_all(OUTPUT_DIR).unwrap();
    std::fs::write(&text_path, &text).unwrap();
    eprintln!("Text projection: {} bytes → {}", text.len(), text_path.display());

    // --- Per-repo text for reference.
    for (i, g) in merged.graphs.iter().enumerate() {
        let name = if i == 0 { "turps" } else { "quokka_web" };
        let t = render_repo_graph(g);
        let p = PathBuf::from(OUTPUT_DIR).join(format!("{name}-text.txt"));
        std::fs::write(&p, &t).unwrap();
        eprintln!("  {name}: {} bytes → {}", t.len(), p.display());
    }

    // --- Sharded .gmap binary output.
    let shards: Vec<(&str, &RepoGraph)> = merged
        .graphs
        .iter()
        .enumerate()
        .map(|(i, g)| {
            let name: &str = if i == 0 { "turps" } else { "quokka_web" };
            (name, g)
        })
        .collect();
    let manifest = write_sharded(&shards, &merged.cross_edges, Path::new(OUTPUT_DIR)).unwrap();

    eprintln!("\nManifest written to {OUTPUT_DIR}/manifest.json");
    eprintln!("Shards:");
    for s in &manifest.shards {
        let size = std::fs::metadata(PathBuf::from(OUTPUT_DIR).join(&s.path))
            .map(|m| m.len())
            .unwrap_or(0);
        eprintln!("  {} — {} bytes (hash: {})", s.path, size, s.content_hash);
    }
    if let Some(ref c) = manifest.cross {
        let size = std::fs::metadata(PathBuf::from(OUTPUT_DIR).join(&c.path))
            .map(|m| m.len())
            .unwrap_or(0);
        eprintln!("  {} — {} bytes (hash: {})", c.path, size, c.content_hash);
    }

    // --- Verify we can reopen.
    let reopened = repo_graph_store::ShardedMmap::open(Path::new(OUTPUT_DIR)).unwrap();
    let total_edges: usize = reopened.edges_iter().count();
    eprintln!("\nReopened: {total_edges} total edges across all shards");

    // --- Activation smoke test on the merged graph.
    let defaults = repo_graph_graph::code_activation_defaults();

    // Pick a known Go route as seed (any route node will do).
    let route_seeds: Vec<_> = merged
        .graphs
        .iter()
        .flat_map(|g| {
            g.nav
                .kind_by_id
                .iter()
                .filter(|(_, k)| **k == repo_graph_code_domain::node_kind::ROUTE)
                .map(|(id, _)| *id)
        })
        .take(3)
        .collect();

    if !route_seeds.is_empty() {
        let result = merged.activate(&route_seeds, &defaults);
        eprintln!(
            "\nActivation: {} seeds → {} activated nodes, {} iterations",
            route_seeds.len(),
            result.scores.len(),
            result.iterations
        );
        for (id, score) in result.scores.iter().take(10) {
            let name = merged
                .graphs
                .iter()
                .find_map(|g| g.nav.name_by_id.get(id))
                .map(|s| s.as_str())
                .unwrap_or("?");
            let qname = merged
                .graphs
                .iter()
                .find_map(|g| g.nav.qname_by_id.get(id))
                .map(|s| s.as_str())
                .unwrap_or("?");
            eprintln!("  {score:.6}  {name}  ({qname})");
        }
        assert!(!result.scores.is_empty(), "activation should find reachable nodes");
        assert!(result.iterations < 100, "should converge before max_iterations");
    }
}
