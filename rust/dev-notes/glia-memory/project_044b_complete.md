---
name: v0.4.4b complete — MergedGraph + CrossGraphResolver + HttpStackResolver
description: Cross-repo HTTP stack resolution shipped 2026-04-17; closes v0.4.4 umbrella. Next sub-track is v0.4.5 (rkyv store + dense text projection).
type: project
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**Status 2026-04-17**: v0.4.4b done, v0.4.4 umbrella (#13) closed, #32 closed. 48 workspace tests pass, clippy clean across workspace with `-D warnings`. **Committed as `f3cef6a` and tagged `v0.4.4` (umbrella tag covers both 4a and 4b).**

## What shipped

**graph crate** (`rust/graph/src/lib.rs`):
- `MergedGraph { graphs: Vec<RepoGraph>, cross_edges: Vec<Edge> }` — per-repo graphs stay owned and addressable by `RepoId`. Cross-edges sit on the merged container, NOT on per-repo `edges` lists. Reason: keeps per-repo graphs round-trippable through the v0.4.5 rkyv store without polluting the intra-repo edge list with refs that only exist when multiple repos are in scope.
- `MergedGraph::all_edges()` returns a chained iterator (per-repo edges + cross_edges) for consumers that want the whole merged view.
- `CrossGraphResolver` trait — single method `resolve(&self, merged: &mut MergedGraph)`. The seam for v0.4.10 resolvers (GraphQL, gRPC, Queue, SharedSchema, EventBus, DB, CLI).
- `HttpStackResolver` (unit struct) — first impl. Algorithm:
  1. `build_route_index(graphs) -> HashMap<(METHOD, normalised_path), Vec<RouteTarget>>` — scans every Route node across every graph, reads its `ROUTE_METHOD` cells, indexes by (uppercased method, normalised path).
  2. For each Endpoint node across every graph: parse qname `endpoint:<METHOD>:<path>` via `parse_endpoint_qname`, normalise path, look up in index. Skip if `path == "<unresolved>"` (Weak fallback from URL-builder wrapper).
  3. For each match, push `Edge { from: endpoint_id, to: route_id, category: HTTP_CALLS, confidence: weakest(endpoint_conf, route_conf) }` onto `merged.cross_edges`.
- `normalise_http_path(raw)` — collapses `:id`, `{id}`, and `${…}` (the tree-sitter substitution marker the TS parser emits) all into `{}`. Strips trailing `/`, normalises double slashes. Public function so other resolvers can reuse it.
- `extract_method_field(json)` — minimal substring-based JSON parser that pulls the `"method": "..."` value from a `ROUTE_METHOD` cell payload. Tight scan instead of dragging serde_json into the graph crate as a dep — payloads are flat objects written by parser-go, not arbitrary user JSON.
- `weakest(a, b)` — returns the lower-rank Confidence (Strong=2, Medium=1, Weak=0).

**fixture pair** (`tests/fixtures/http_stack_smoke/`):
- `backend/` — Go module `example.com/backend` with `users/users.go` (`List`, `Create`, `Get` handlers) and `server/server.go` registering routes against a stand-in `Router` interface behind a `Group("/api")` prefix chain. Three routes: `GET /api/users → users.List`, `POST /api/users → users.Create`, `GET /api/users/:id → users.Get`.
- `frontend/` — TypeScript `src/app/user.service.ts` with a stand-in `HttpClient` class field on `UserService`. Three endpoints: `this.http.get('/api/users')` (Strong), `this.http.post('/api/users', payload)` (Strong), `this.http.get(\`/api/users/${id}\`)` (Medium — template substitution).

**cross-repo smoke test** (`rust/graph/tests/http_stack_smoke.rs`):
- Builds backend with `build_go`, frontend with `build_typescript` (no-op resolver since the fixture has no cross-file imports).
- Asserts backend Route nodes exist with correct `ROUTE_METHOD` cells.
- Asserts frontend Endpoint nodes exist; the template-interpolation endpoint qname is `endpoint:GET:/api/users/${…}` (note: `…` is the literal Unicode ellipsis the TS parser writes for substitutions).
- Wraps both in `MergedGraph::new(vec![backend, frontend])`, runs `HttpStackResolver.resolve(&mut merged)`.
- Asserts three `HTTP_CALLS` cross-edges:
  1. GET `/api/users` endpoint → `/api/users` route, confidence = Strong
  2. POST `/api/users` endpoint → SAME route node (different method cell), confidence = Strong
  3. GET `/api/users/${…}` endpoint → `/api/users/:id` route via path normalisation, confidence = Medium (endpoint's Medium propagates through `weakest`)
- Asserts `merged.graphs[i].edges` lists are NOT polluted with `HTTP_CALLS` edges — those only live on `cross_edges`.

**4 new graph-crate unit tests**: `normalise_http_path_collapses_all_param_syntaxes`, `parse_endpoint_qname_splits_method_and_path`, `extract_method_field_handles_ordering_and_whitespace`, `weakest_confidence_is_min_rank`.

## Key design decision: cross_edges live on MergedGraph, not per-repo

Quote from in-code comment: *"Cross-edges sit on the merged container so the per-repo graphs remain round-trippable through the v0.4.5 rkyv store without the intra-repo edge list being polluted by cross-repo references that only make sense once multiple repos are in scope."*

This is load-bearing for v0.4.5: a per-repo `.gmap` file should be self-contained. Cross-repo edges get stored elsewhere (likely a separate `merged.gmap` container, TBD at v0.4.5).

## Fixture-naming clarification (saved earlier this session)

User called out my loose "quokka fixtures" wording — quokka-stack is an external real-world validation target, not a checked-in fixture. The actual smoke test uses a synthetic `tests/fixtures/http_stack_smoke/` pair. Same principle applies to all v0.4.4+ cross-repo testing: synthetic fixtures live in `tests/fixtures/`, real-world validation uses external clones (out of band).

## Next step (v0.4.5)

Task #14 — rkyv store + dense text projection. Code-domain registry's CellTypeId values feed into this; `RepoGraph` already implements rkyv via the core types but a serialise-to-disk + mmap-on-read store is the next layer.
