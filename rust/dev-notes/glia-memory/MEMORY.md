# Glia memory seed

These memory files were copied from the repo-graph project memory on 2026-04-18, before the planned `git filter-repo` split of `rust/` into the standalone `glia` repo. When that split happens, this directory becomes `dev-notes/glia-memory/` in the new repo and can seed a fresh Claude memory directory there.

The files preserve the architectural, design, and positioning context that shaped glia. They're frozen snapshots — treat them as historical context, not live state, and refresh against current code when anything looks off.

## Product direction

- [project_vision.md](project_vision.md) — brain-structure-map framing, why LLMs need it
- [project_larger_vision.md](project_larger_vision.md) — foundation of graph-based IDE + mempalace bridge + multicellular nodes + latent-vector future
- [project_040_vision.md](project_040_vision.md) — Rust rewrite + new dense format + multicellular + dense text + mempalace bridge
- [project_050_domain_agnostic.md](project_050_domain_agnostic.md) — code is first primitive; chemistry/video/policy/climate slot in via registries
- [project_competitive_landscape.md](project_competitive_landscape.md) — code-graph MCP space commoditising; moat is multicellular + dense text + latent + mempalace + HippoRAG
- [project_naming_glia.md](project_naming_glia.md) — rename to glia for v0.5.0 (gmap format name stays)
- [project_positioning_glia_primary.md](project_positioning_glia_primary.md) — glia carries the value, repo-graph is the demo
- [project_repo_split_plan.md](project_repo_split_plan.md) — git filter-repo extraction plan

## Architecture & spec

- [reference_format_spec.md](reference_format_spec.md) — strict Node, multicellular cells, domain-owned indices, three projections, sigil legend
- [reference_rkyv_design.md](reference_rkyv_design.md) — zero-copy + mmap, Owned vs Archived, write-once-rebuild-whole-file, sharding
- [reference_code_domain_registries.md](reference_code_domain_registries.md) — locked u32 values for NodeKind/EdgeCategory/CellType; `::` qname; extraction-vs-resolution
- [reference_kind_category_ids.md](reference_kind_category_ids.md) — correct u32 IDs (ROUTE=5, CLASS=2, etc.)
- [reference_parser_graph_split.md](reference_parser_graph_split.md) — locked v0.4.3b: parsers extract, graph resolves uniformly
- [reference_route_qname_formats.md](reference_route_qname_formats.md) — shape A vs shape B; resolver accepts both
- [reference_treesitter_quirks.md](reference_treesitter_quirks.md) — Swift all-class, Dart no field names, Elixir dot targets, HCL body, Clojure linking
- [reference_hipporag_assessment.md](reference_hipporag_assessment.md) — PPR with damping=0.5, not custom spreading activation
- [reference_candle_embed_hook.md](reference_candle_embed_hook.md) — candle `forward_input_embed` latent-injection hook
- [reference_swe_bench_plan.md](reference_swe_bench_plan.md) — Qwen 2.5 Coder 7B, Runpod 4090, N=20-30
- [reference_dev_notes.md](reference_dev_notes.md) — decisions log convention, [SCOPE-DRIVEN]/[PRINCIPLED] tags
- [project_workspace_layout.md](project_workspace_layout.md) — `parsers/<domain>/<language>/` nesting, scales to v0.5.0

## v0.4.x progress logs

- [project_8step_roadmap.md](project_8step_roadmap.md)
- [project_030_roadmap.md](project_030_roadmap.md)
- [project_020_release_scope.md](project_020_release_scope.md)
- [project_020_known_gaps.md](project_020_known_gaps.md) — AST-layer target list for 0.3.0
- [project_040_stack_resolvers_backlog.md](project_040_stack_resolvers_backlog.md) — GraphQL, gRPC, Queue, WebSocket, etc.
- [project_044_http_extractor_design.md](project_044_http_extractor_design.md)
- [project_044a_complete.md](project_044a_complete.md) · [project_044b_complete.md](project_044b_complete.md)
- [project_045_plan.md](project_045_plan.md) · [project_045_complete.md](project_045_complete.md) — .gmap store, dense text
- [project_046_activation_design.md](project_046_activation_design.md) · [project_046_complete.md](project_046_complete.md) · [project_046a_prefix_strip.md](project_046a_prefix_strip.md) · [project_046_merged_into_0411.md](project_046_merged_into_0411.md)
- [project_047_progress.md](project_047_progress.md) — multicellular cell types 7–14, text compression
- [project_048_complete.md](project_048_complete.md) — cell write API
- [project_049_scope.md](project_049_scope.md) · [project_049_complete.md](project_049_complete.md) — 20 parser crates + extractor crate
- [project_0410_sequence.md](project_0410_sequence.md) — resolvers, pyo3, clean break, regression
- [project_0410b_complete.md](project_0410b_complete.md) — pyo3 0.28 bindings via maturin
- [project_0410c_complete.md](project_0410c_complete.md) — Python clean break
- [project_0410d_regression.md](project_0410d_regression.md) — Python vs Rust on quokka
- [project_0411_sweep.md](project_0411_sweep.md) · [project_0411_sweep_findings.md](project_0411_sweep_findings.md) · [project_0411_patches.md](project_0411_patches.md)
- [project_0411a_scope.md](project_0411a_scope.md) · [project_0411a_complete.md](project_0411a_complete.md) · [project_0411a_smoke_10repos.md](project_0411a_smoke_10repos.md)

## Design history (earlier phases, useful background)

- [project_generalization.md](project_generalization.md) — pluggable analyzer architecture (pre-Rust)
- [project_fileindex_refactor.md](project_fileindex_refactor.md) — shared FileIndex across analyzers
- [project_config_yaml.md](project_config_yaml.md) — .ai/repo-graph/config.yaml escape hatch
- [project_auto_flows.md](project_auto_flows.md) — generator auto-builds flows from routes
- [project_graphic_map_idea.md](project_graphic_map_idea.md) — graph_view tool
- [project_data_sources_analyzer.md](project_data_sources_analyzer.md) — cross-cutting DB/cache/queue/blob/search/email detection
- [project_cross_stack_linking.md](project_cross_stack_linking.md) — frontend endpoint_* to backend route_* linking
- [project_quokka_rust_dump.md](project_quokka_rust_dump.md) — quokka-stack benchmark numbers
- [project_dense_text_compression.md](project_dense_text_compression.md) — prefix/default/module dedup
- [project_language_expansion.md](project_language_expansion.md) — 20 analyzers timeline
- [project_init_bootstrap_design.md](project_init_bootstrap_design.md) — LLM-assisted first-run config

## Design principles (feedback)

- [feedback_02_not_a_ceiling.md](feedback_02_not_a_ceiling.md) — 0.4.x extracts what AST makes available, not capped at 0.2.0 regex
- [feedback_detect_prefilter_tightness.md](feedback_detect_prefilter_tightness.md) — cross-cutting detect() uses import-boundary signals, not substrings
- [feedback_bidirectional_file_anchors.md](feedback_bidirectional_file_anchors.md) — `_resolve_file_edges` rewrites both sides
- [feedback_domain_assumptions.md](feedback_domain_assumptions.md) — check "universal" claims against video/audio/molecules
- [feedback_consistent_language_support.md](feedback_consistent_language_support.md)
- [feedback_flow_key_matching.md](feedback_flow_key_matching.md) — never convert `_` to `-` in flow keys
- [feedback_relative_paths_for_skips.md](feedback_relative_paths_for_skips.md) — always `rel_path()` before skip checks
- [feedback_config_adds_never_replaces.md](feedback_config_adds_never_replaces.md) — config roots/skip always union, never swap
- [feedback_text_projection_priority.md](feedback_text_projection_priority.md) — text is legacy, binary + activation are the real value
- [feedback_write_surface_over_bridge.md](feedback_write_surface_over_bridge.md) — build generic write APIs, not bespoke bridges
- [feedback_python_never_new_format.md](feedback_python_never_new_format.md) — Python codebase ends at enriched JSON v1; Rust owns new format
- [feedback_push_back_on_sequence.md](feedback_push_back_on_sequence.md) — if a skip has a hard dep, flag it
- [feedback_research_timing.md](feedback_research_timing.md) — give N, hours, $, days; never "weeks vs months"
- [feedback_monorepo_layouts.md](feedback_monorepo_layouts.md) — scan_project_dirs must handle src/*, crates/*, lib/*
- [feedback_python_find_packages_monorepo.md](feedback_python_find_packages_monorepo.md)

## Cross-cutting (applies to glia and to the Python wrapper equally)

- [user_identity.md](user_identity.md)
- [feedback_writing_voice.md](feedback_writing_voice.md)
- [feedback_facts_over_polish.md](feedback_facts_over_polish.md)
- [feedback_no_legacy.md](feedback_no_legacy.md) — clean breaks over backwards-compat shims
- [feedback_no_invented_process.md](feedback_no_invented_process.md) — don't repackage simple requests into PR/phase plans
- [feedback_walk_through_before_release.md](feedback_walk_through_before_release.md)
- [feedback_trust_instructions.md](feedback_trust_instructions.md)
- [feedback_external_repo_validation.md](feedback_external_repo_validation.md) — clone from GitHub/GitLab, not just local
