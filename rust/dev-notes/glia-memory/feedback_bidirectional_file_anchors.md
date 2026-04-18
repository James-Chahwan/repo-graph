---
name: File-anchor edges resolve both directions
description: `_resolve_file_edges` must rewrite `file::<rel>` on from AND to sides — CLI handled_by edges put it on the to side
type: feedback
originSessionId: e18af0c7-26eb-409e-8c0d-89cbaf6550d0
---
`generator._resolve_file_edges` was originally written for data_sources analyzer which emits `file::src/x.py → data_source_*` (anchor on `from`). CliEntrypointAnalyzer emits `cli_command → file::src/x.py` (anchor on `to`). The resolver must handle both.

**Why:** during Step 4a smoke test, CLI emitted 3 cli_command nodes but 0 flows — because the handled_by edge target stayed as unresolved `file::src/mycli/cli.py` and the BFS couldn't follow it to a real module node.

**How to apply:** whenever adding a new analyzer that uses `file::<rel>` synthetic ids for edge targets OR sources, the resolver already handles it. But if you add a new edge topology, verify the resolver sees both sides. The fix is in `generator.py _resolve_file_edges`: both `src_is_anchor` and `dst_is_anchor` branches, with `_best_for()` called for each.
