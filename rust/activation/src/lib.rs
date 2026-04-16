//! repo-graph-activation — domain-agnostic Personalized PageRank.
//!
//! Implements spreading activation via power-iteration PPR, adapted from
//! the HippoRAG insight (arXiv 2405.14831) but stripped of NER/OpenIE/
//! synonymy machinery. The algorithm is domain-agnostic: direction,
//! edge-type weights, and node-specificity scoring are all caller-provided
//! via `ActivationConfig`.
//!
//! Code domain provides its own defaults (calls > imports > contains).
//! Other domains (chemistry, policy, video) provide theirs.

use std::collections::HashMap;

use repo_graph_core::{Edge, EdgeCategoryId, NodeId};

// ============================================================================
// Config
// ============================================================================

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Direction {
    /// Follow edges from→to. Use for impact analysis ("what does this affect?").
    Forward,
    /// Follow edges to→from. Use for trace/provenance ("what leads here?").
    Backward,
    /// Both directions. Use for neighbourhood/context queries.
    Undirected,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Specificity {
    /// No adjustment — PPR scores used as-is.
    None,
    /// Boost rare/isolated nodes (HippoRAG-style IDF). Good for NL knowledge
    /// graphs where specific entities are more informative.
    Idf,
    /// Boost highly-connected nodes. Good for code where widely-used utilities
    /// are important *because* they're central.
    InverseIdf,
}

#[derive(Debug, Clone)]
pub struct ActivationConfig {
    /// Restart probability. 0.5 = aggressive (stays local around seeds).
    /// 0.85 = classic PageRank (spreads wider). Range: (0, 1).
    pub damping: f64,
    /// Which direction activation flows along edges.
    pub direction: Direction,
    /// Weight per edge category. Missing categories get weight 1.0.
    pub edge_weights: HashMap<EdgeCategoryId, f64>,
    /// Post-PPR node scoring adjustment.
    pub node_specificity: Specificity,
    /// Maximum nodes in the result.
    pub top_k: usize,
    /// Power iteration cap.
    pub max_iterations: usize,
    /// Convergence threshold (L1 norm of score change).
    pub epsilon: f64,
}

impl Default for ActivationConfig {
    fn default() -> Self {
        Self {
            damping: 0.5,
            direction: Direction::Forward,
            edge_weights: HashMap::new(),
            node_specificity: Specificity::None,
            top_k: 50,
            max_iterations: 100,
            epsilon: 1e-6,
        }
    }
}

// ============================================================================
// Result
// ============================================================================

#[derive(Debug)]
pub struct ActivationResult {
    /// (NodeId, score) pairs sorted descending by score.
    pub scores: Vec<(NodeId, f64)>,
    /// How many power-iteration rounds ran before convergence or cap.
    pub iterations: usize,
}

impl ActivationResult {
    pub fn top_ids(&self) -> Vec<NodeId> {
        self.scores.iter().map(|(id, _)| *id).collect()
    }

    pub fn score_of(&self, id: NodeId) -> f64 {
        self.scores
            .iter()
            .find(|(nid, _)| *nid == id)
            .map(|(_, s)| *s)
            .unwrap_or(0.0)
    }
}

// ============================================================================
// Core algorithm
// ============================================================================

/// Run Personalized PageRank over an arbitrary node/edge set.
///
/// `node_ids` — the full set of graph nodes (defines the PPR vector size).
/// `edges` — all edges to consider (intra + cross, caller decides).
/// `seeds` — query-relevant nodes that receive restart probability.
/// `config` — direction, weights, specificity, damping, etc.
pub fn activate(
    node_ids: &[NodeId],
    edges: &[Edge],
    seeds: &[NodeId],
    config: &ActivationConfig,
) -> ActivationResult {
    let n = node_ids.len();
    if n == 0 || seeds.is_empty() {
        return ActivationResult {
            scores: vec![],
            iterations: 0,
        };
    }

    let id_to_idx: HashMap<NodeId, usize> =
        node_ids.iter().enumerate().map(|(i, &id)| (id, i)).collect();

    // Build adjacency: incoming[i] = [(source_idx, weight)] — who can send
    // activation to node i. out_weight[j] = total outgoing weight from j.
    let mut incoming: Vec<Vec<(usize, f64)>> = vec![vec![]; n];
    let mut out_weight: Vec<f64> = vec![0.0; n];

    for edge in edges {
        let w = config
            .edge_weights
            .get(&edge.category)
            .copied()
            .unwrap_or(1.0);
        if w <= 0.0 {
            continue;
        }

        let from_idx = id_to_idx.get(&edge.from).copied();
        let to_idx = id_to_idx.get(&edge.to).copied();

        match (from_idx, to_idx) {
            (Some(fi), Some(ti)) => match config.direction {
                Direction::Forward => {
                    incoming[ti].push((fi, w));
                    out_weight[fi] += w;
                }
                Direction::Backward => {
                    incoming[fi].push((ti, w));
                    out_weight[ti] += w;
                }
                Direction::Undirected => {
                    incoming[ti].push((fi, w));
                    incoming[fi].push((ti, w));
                    out_weight[fi] += w;
                    out_weight[ti] += w;
                }
            },
            _ => continue,
        }
    }

    // Personalization vector: equal weight on seed nodes.
    let mut personalization = vec![0.0; n];
    let seed_count = seeds
        .iter()
        .filter(|s| id_to_idx.contains_key(s))
        .count();
    if seed_count == 0 {
        return ActivationResult {
            scores: vec![],
            iterations: 0,
        };
    }
    let seed_weight = 1.0 / seed_count as f64;
    for seed in seeds {
        if let Some(&idx) = id_to_idx.get(seed) {
            personalization[idx] = seed_weight;
        }
    }

    // Power iteration: v = (1-d) * p + d * M * v
    let d = config.damping.clamp(0.01, 0.99);
    let mut scores = personalization.clone();
    let mut iterations = 0;

    for _ in 0..config.max_iterations {
        let mut new_scores = vec![0.0; n];

        // Dangling nodes (no outgoing edges) would lose activation into the
        // void. Standard PPR redistributes their mass back to the
        // personalization vector — keeps scores summing to 1.0.
        let dangling_sum: f64 = (0..n)
            .filter(|&j| out_weight[j] == 0.0)
            .map(|j| scores[j])
            .sum();

        for i in 0..n {
            let propagated: f64 = incoming[i]
                .iter()
                .map(|&(j, w)| {
                    if out_weight[j] > 0.0 {
                        scores[j] * w / out_weight[j]
                    } else {
                        0.0
                    }
                })
                .sum();

            new_scores[i] =
                (1.0 - d) * personalization[i] + d * (propagated + dangling_sum * personalization[i]);
        }

        let diff: f64 = scores
            .iter()
            .zip(new_scores.iter())
            .map(|(a, b)| (a - b).abs())
            .sum();

        scores = new_scores;
        iterations += 1;

        if diff < config.epsilon {
            break;
        }
    }

    // Node specificity adjustment (post-PPR).
    if config.node_specificity != Specificity::None {
        let mut degree = vec![0usize; n];
        for edge in edges {
            if let Some(&fi) = id_to_idx.get(&edge.from) {
                degree[fi] += 1;
            }
            if let Some(&ti) = id_to_idx.get(&edge.to) {
                degree[ti] += 1;
            }
        }

        for i in 0..n {
            let d = degree[i] as f64;
            match config.node_specificity {
                Specificity::Idf => scores[i] /= 1.0 + d,
                Specificity::InverseIdf => scores[i] *= (1.0 + d).ln_1p(),
                Specificity::None => unreachable!(),
            }
        }
    }

    // Collect, sort descending, truncate to top_k.
    let mut result: Vec<(NodeId, f64)> = node_ids
        .iter()
        .zip(scores.iter())
        .filter(|(_, s)| **s > 0.0)
        .map(|(&id, &s)| (id, s))
        .collect();
    result.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    result.truncate(config.top_k);

    ActivationResult {
        scores: result,
        iterations,
    }
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use repo_graph_core::{Confidence, EdgeCategoryId, NodeId};

    const CAT_CALLS: EdgeCategoryId = EdgeCategoryId(4);
    const CAT_CONTAINS: EdgeCategoryId = EdgeCategoryId(2);
    #[allow(dead_code)]
    const CAT_IMPORTS: EdgeCategoryId = EdgeCategoryId(3);

    fn edge(from: u64, to: u64, cat: EdgeCategoryId) -> Edge {
        Edge {
            from: NodeId(from),
            to: NodeId(to),
            category: cat,
            confidence: Confidence::Strong,
        }
    }

    fn ids(ns: &[u64]) -> Vec<NodeId> {
        ns.iter().map(|&n| NodeId(n)).collect()
    }

    #[test]
    fn empty_graph() {
        let r = activate(&[], &[], &[NodeId(1)], &ActivationConfig::default());
        assert!(r.scores.is_empty());
        assert_eq!(r.iterations, 0);
    }

    #[test]
    fn empty_seeds() {
        let r = activate(&ids(&[1, 2]), &[], &[], &ActivationConfig::default());
        assert!(r.scores.is_empty());
    }

    #[test]
    fn single_node_seed() {
        let nodes = ids(&[1]);
        let r = activate(&nodes, &[], &[NodeId(1)], &ActivationConfig::default());
        assert_eq!(r.scores.len(), 1);
        assert_eq!(r.scores[0].0, NodeId(1));
        assert!((r.scores[0].1 - 1.0).abs() < 0.01);
    }

    #[test]
    fn chain_forward_decay() {
        // A→B→C, seed A. Forward: B should score higher than C.
        let nodes = ids(&[1, 2, 3]);
        let edges = vec![edge(1, 2, CAT_CALLS), edge(2, 3, CAT_CALLS)];
        let config = ActivationConfig {
            direction: Direction::Forward,
            ..Default::default()
        };
        let r = activate(&nodes, &edges, &[NodeId(1)], &config);

        let sa = r.score_of(NodeId(1));
        let sb = r.score_of(NodeId(2));
        let sc = r.score_of(NodeId(3));
        assert!(sa > sb, "seed A ({sa}) should beat B ({sb})");
        assert!(sb > sc, "B ({sb}) should beat C ({sc})");
    }

    #[test]
    fn multi_path_convergence() {
        // A→B, A→D, B→D. Seed A. D gets activation via two paths (direct +
        // through B), so D should score higher than B.
        let nodes = ids(&[1, 2, 4]);
        let edges = vec![
            edge(1, 2, CAT_CALLS),
            edge(1, 4, CAT_CALLS),
            edge(2, 4, CAT_CALLS),
        ];
        let config = ActivationConfig {
            direction: Direction::Forward,
            ..Default::default()
        };
        let r = activate(&nodes, &edges, &[NodeId(1)], &config);

        let sb = r.score_of(NodeId(2));
        let sd = r.score_of(NodeId(4));
        assert!(
            sd > sb,
            "D ({sd}) should beat B ({sb}) via multi-path convergence"
        );
    }

    #[test]
    fn backward_direction() {
        // A→B→C, seed C, backward. Activation flows C←B←A.
        let nodes = ids(&[1, 2, 3]);
        let edges = vec![edge(1, 2, CAT_CALLS), edge(2, 3, CAT_CALLS)];
        let config = ActivationConfig {
            direction: Direction::Backward,
            ..Default::default()
        };
        let r = activate(&nodes, &edges, &[NodeId(3)], &config);

        let sb = r.score_of(NodeId(2));
        let sa = r.score_of(NodeId(1));
        assert!(sb > sa, "B ({sb}) should beat A ({sa}) in backward from C");
        assert!(sb > 0.0, "B should receive activation");
    }

    #[test]
    fn edge_weights_change_scores() {
        // A→B (calls, weight 5.0), A→C (contains, weight 1.0).
        // B should score higher than C.
        let nodes = ids(&[1, 2, 3]);
        let edges = vec![edge(1, 2, CAT_CALLS), edge(1, 3, CAT_CONTAINS)];
        let mut weights = HashMap::new();
        weights.insert(CAT_CALLS, 5.0);
        weights.insert(CAT_CONTAINS, 1.0);
        let config = ActivationConfig {
            direction: Direction::Forward,
            edge_weights: weights,
            ..Default::default()
        };
        let r = activate(&nodes, &edges, &[NodeId(1)], &config);

        let sb = r.score_of(NodeId(2));
        let sc = r.score_of(NodeId(3));
        assert!(
            sb > sc,
            "B ({sb}) should beat C ({sc}) with calls weight 5x contains"
        );
    }

    #[test]
    fn zero_weight_edge_excluded() {
        // A→B (weight 0.0 = blocked), A→C (weight 1.0).
        let nodes = ids(&[1, 2, 3]);
        let edges = vec![edge(1, 2, CAT_CALLS), edge(1, 3, CAT_CONTAINS)];
        let mut weights = HashMap::new();
        weights.insert(CAT_CALLS, 0.0);
        let config = ActivationConfig {
            direction: Direction::Forward,
            edge_weights: weights,
            ..Default::default()
        };
        let r = activate(&nodes, &edges, &[NodeId(1)], &config);

        assert_eq!(r.score_of(NodeId(2)), 0.0, "B should get zero — edge blocked");
        assert!(r.score_of(NodeId(3)) > 0.0, "C should get activation");
    }

    #[test]
    fn top_k_limits_output() {
        let nodes = ids(&[1, 2, 3, 4, 5]);
        let edges = vec![
            edge(1, 2, CAT_CALLS),
            edge(1, 3, CAT_CALLS),
            edge(1, 4, CAT_CALLS),
            edge(1, 5, CAT_CALLS),
        ];
        let config = ActivationConfig {
            direction: Direction::Forward,
            top_k: 2,
            ..Default::default()
        };
        let r = activate(&nodes, &edges, &[NodeId(1)], &config);
        assert!(r.scores.len() <= 2);
    }

    #[test]
    fn multiple_seeds() {
        // A→C, B→C, A→D. Seeds: A and B. C gets activation from both seeds,
        // D only from A. C should beat D.
        let nodes = ids(&[1, 2, 3, 4]);
        let edges = vec![
            edge(1, 3, CAT_CALLS),
            edge(2, 3, CAT_CALLS),
            edge(1, 4, CAT_CALLS),
        ];
        let config = ActivationConfig {
            direction: Direction::Forward,
            ..Default::default()
        };
        let r = activate(&nodes, &edges, &[NodeId(1), NodeId(2)], &config);

        let sc = r.score_of(NodeId(3));
        let sd = r.score_of(NodeId(4));
        assert!(sc > sd, "C ({sc}) should beat D ({sd}) — C fed by both seeds");
    }

    #[test]
    fn undirected_reaches_both_ways() {
        // A→B, seed B, undirected. A should get activation.
        let nodes = ids(&[1, 2]);
        let edges = vec![edge(1, 2, CAT_CALLS)];
        let config = ActivationConfig {
            direction: Direction::Undirected,
            ..Default::default()
        };
        let r = activate(&nodes, &edges, &[NodeId(2)], &config);

        assert!(
            r.score_of(NodeId(1)) > 0.0,
            "A should get activation in undirected mode even though edge is A→B"
        );
    }

    #[test]
    fn converges_quickly_on_small_graph() {
        let nodes = ids(&[1, 2, 3]);
        let edges = vec![edge(1, 2, CAT_CALLS), edge(2, 3, CAT_CALLS)];
        let config = ActivationConfig {
            direction: Direction::Forward,
            max_iterations: 1000,
            epsilon: 1e-10,
            ..Default::default()
        };
        let r = activate(&nodes, &edges, &[NodeId(1)], &config);
        assert!(r.iterations < 50, "should converge in <50 iters, got {}", r.iterations);
    }

    #[test]
    fn idf_boosts_rare_nodes() {
        // A→B, A→C, A→D, A→E, B→F. F has degree 1, B/C/D/E have degree 2+.
        // With IDF, F should be boosted relative to its raw PPR score.
        let nodes = ids(&[1, 2, 3, 4, 5, 6]);
        let edges = vec![
            edge(1, 2, CAT_CALLS),
            edge(1, 3, CAT_CALLS),
            edge(1, 4, CAT_CALLS),
            edge(1, 5, CAT_CALLS),
            edge(2, 6, CAT_CALLS),
        ];

        let config_none = ActivationConfig {
            direction: Direction::Forward,
            node_specificity: Specificity::None,
            ..Default::default()
        };
        let config_idf = ActivationConfig {
            direction: Direction::Forward,
            node_specificity: Specificity::Idf,
            ..Default::default()
        };

        let r_none = activate(&nodes, &edges, &[NodeId(1)], &config_none);
        let r_idf = activate(&nodes, &edges, &[NodeId(1)], &config_idf);

        let ratio_none = r_none.score_of(NodeId(6)) / r_none.score_of(NodeId(2));
        let ratio_idf = r_idf.score_of(NodeId(6)) / r_idf.score_of(NodeId(2));
        assert!(
            ratio_idf > ratio_none,
            "IDF should boost F relative to B: idf_ratio={ratio_idf:.4}, none_ratio={ratio_none:.4}"
        );
    }
}
