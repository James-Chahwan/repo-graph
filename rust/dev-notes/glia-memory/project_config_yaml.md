---
name: Config.yaml escape hatch
description: Step 2 of 8-step roadmap — completed 2026-04-15. Users can drop .ai/repo-graph/config.yaml with skip:/roots: to override auto-detection.
type: project
originSessionId: e18af0c7-26eb-409e-8c0d-89cbaf6550d0
---
Step 2 of roadmap complete. Users can drop `.ai/repo-graph/config.yaml` (or `.yml` / `.json`) into a target repo. Shape:

```yaml
skip:
  - legacy
roots:
  - path: apps/weird
    kind: python
```

**Why:** roadmap goal was "drop a config.yaml in a weird monorepo, watch it override heuristics". Kept zero-dep constraint by writing a bespoke minimal YAML parser (top-level keys, block list of scalars or inline dicts, comments, quoted strings — no anchors/flow/multi-line).

**How to apply:** Config adds to auto-detection, never replaces it — `skip` extends FileIndex's default skip set, `roots` unions with each analyzer's `extra_roots(kind)`. Kinds match analyzer names: go, rust, python, typescript, react, vue, angular, java, scala, clojure, csharp, ruby, php, swift, c_cpp, dart, elixir, solidity, terraform.

Files: `repo_graph/config.py` (loader + parser), `repo_graph/discovery.py` (FileIndex.config_roots + roots_for/extra_roots helpers), `repo_graph/generator.py` (wires config into build_index). All 19 analyzer root-finders updated. Validated end-to-end with /tmp/rg-config-test.
