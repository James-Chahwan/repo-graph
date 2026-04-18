---
name: 0.2.0 known AST-layer gaps (target list for 0.3.0)
description: Concrete bugs/gaps identified during 0.3.0 planning review of 0.2.0 code; 0.3.0 must close these
type: project
originSessionId: f5091c3e-4ad2-47ca-be6b-233c911fb6a7
---
Identified 2026-04-16 during 0.3.0 planning review of `repo_graph/`:

**Python analyzer (`analyzers/python_lang.py`):**
- `_IMPORT_ABS` regex defined at line 30 but **never used**. Only relative imports (`from .x import y`) produce edges. Absolute internal imports (`from myproject.foo import bar`) silently dropped. Caps edge count on most real Python repos.
- No method-level nodes. Class is one node, no edges to its methods. `impact("UserRepo.find_by_email")` is unexpressible.
- Top-level function filter via indent inspection works but means methods aren't extracted at all.
- No call graph. `flow login` shows containment, never actual call chain.

**Routing (across analyzers):**
- `route_id` built from path string only. Two `GET /users` in different routers/blueprints silently merge.
- `@app.get` works; `APIRouter()` with prefix mounting, Flask `Blueprint`, Django CBVs, FastAPI dependencies — invisible.
- Decorators stripped. `@requires_auth` then `def login()` — auth context lost.

**Flow generation (`generator.py:_auto_flows`):**
- Walks `defines` + `contains` + `imports` + `calls` indiscriminately (`_FOLLOW_TYPES`). Result: a flow includes every symbol the handler module defines, not just what it uses.
- Concrete on-disk evidence: `.ai/repo-graph/flows/foo.yaml` has 16 steps, ~11 are unrelated symbols defined in `base.py`. The flow dilutes signal.
- Fix in 0.3.0: prefer `calls` over `defines`/`contains` when both exist from same source.

**ID stability:**
- IDs are path-encoded (`py_func_py_mod_repo_graph_analyzers_base_render_flow_yaml`). File move → all flow references break.
- AST will produce richer IDs but changing them is the most disruptive single thing. Hold ID scheme change for 0.4.0 (Rust rewrite renumbers anyway).

**Test edges (`test_edges.py`):**
- `tests` edges go test→module, not test→symbol. `impact(fn, include_tests=True)` undercounts.

**Performance/structural:**
- `get_file_analyzer` (`analyzers/__init__.py:82`) rebuilds the FileIndex on every call. One `bloat_report` ≈ one full repo walk.
- No tests in repo. `pyproject.toml` has zero. Validation is real-repo sweeps. Untenable once AST lands or schema changes.
