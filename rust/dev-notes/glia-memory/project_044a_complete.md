---
name: v0.4.4a HTTP stack (intra-repo half) complete
description: Parser-go route extraction + parser-typescript endpoint extraction + graph-crate UnresolvedRef resolver done; v0.4.4b (CrossGraphResolver / HttpStackResolver) is next
type: project
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**Status 2026-04-17**: v0.4.4a sub-track done, v0.4.4b pending. All 47 workspace tests pass, clippy clean. Not yet committed — waiting on user decision about commit boundary before 0.4.4b.

## What shipped in 0.4.4a

**code-domain registry** (`rust/code-domain/src/lib.rs`):
- `edge_category::HANDLED_BY = 9`, `HTTP_CALLS = 10`
- `cell_type::ROUTE_METHOD = 5`, `ENDPOINT_HIT = 6`
- `UnresolvedRef { from, from_module, qualifier, category }` — ref records that need cross-file binding resolution into an edge of a specific category (distinct from `CallSite`, which always lands on CALLS). `from_module` exists because Route nodes are path-only and have no enclosing module to walk to.
- `FileParse.refs: Vec<UnresolvedRef>` added.

**parser-go route extraction** (`rust/parsers/code/go/src/lib.rs`, +~250 lines):
- `collect_routes_in(body, …)` plugged into `visit_function` and `visit_method` alongside `collect_calls_in`.
- Matches `<recv>.<METHOD>(path, handler)` where METHOD ∈ {GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS}.
- `record_group_assignment` tracks `x := y.Group("/prefix")` chains; nested groups resolve through a `prefix_map` keyed by the receiver identifier.
- Route NodeId qname: `route:<full_path>` — path-only, package-agnostic, so the same path across files/packages naturally dedups at `merge_parses`.
- Second arg classification: identifier → `CallQualifier::Bare`, `pkg.Name` selector → `CallQualifier::Attribute`. Emitted as `UnresolvedRef` with `category = HANDLED_BY` and `from_module = <registering package>`.
- 5 unit tests cover: per-path Route node, identifier-vs-selector handlers, Group prefix chain, two-methods-same-path cell stacking, templated path retained verbatim.

**parser-typescript endpoint extraction** (`rust/parsers/code/typescript/src/lib.rs`, +~270 lines):
- Three syntactic shapes matched (framework-agnostic):
  1. `this.<x>.<method>(first, …)` — Angular HttpClient + any service-with-client-field pattern.
  2. `<alias>.<method>(first, …)` — only emits if `<alias>` is a module-level import binding (prevents `map.get(key)` false positives).
  3. `fetch(first, opts?)` — method defaults to GET unless `opts` is an object literal carrying a string-literal `method:`.
- Path classification into Confidence tiers: string literal → Strong, template-no-interp → Strong, template-with-interp → Medium (path = literal prefix + `${…}` per substitution), call-expression (URL-builder wrapper) → Weak with innermost literal plucked, anything else → Weak with path = `<unresolved>`. `fetch(url, opts)` where opts is present but lacks a string-literal `method:` downgrades confidence one tier.
- Endpoint NodeId qname: `endpoint:<METHOD>:<path>` — **distinct per method** (unlike Routes). Rationale: a Route is a server resource where one path naturally has multiple verbs; an Endpoint is a client callsite where each call is semantically per-method. Multiple callsites to the same (method, path) collapse into one Endpoint node with stacked cells.
- Queue-then-resolve pattern: candidates pushed to `acc.endpoints` during the call walk, filtered + emitted in `resolve_intra_file` once `acc.imports` is fully populated. Necessary because the alias-set check depends on knowing all imports.
- `Acc` gained `file_rel: String` and `repo: Option<RepoId>` fields stashed at `parse_file` entry — avoids threading those through every helper.
- CALLS edge emitted from enclosing scope → Endpoint with the endpoint's confidence.
- 5 unit tests cover: `this.http.post` strong string-literal, `fetch` GET-default + POST-override, `axios.get` alias-gated, template-interpolation medium confidence, URL-builder wrapper weak, same-(method,path) cell stacking.

**graph crate UnresolvedRef resolver** (`rust/graph/src/lib.rs`):
- `merge_parses` signature now returns `(RepoGraph, Vec<ImportStmt>, Vec<CallSite>, Vec<UnresolvedRef>)`.
- `RepoGraph.unresolved_refs: Vec<UnresolvedRef>` added alongside `unresolved_calls` — same diagnostic role.
- `resolve_refs(g, &all_refs)` — mirrors `resolve_calls` but uses `r.from_module` directly (skips `enclosing_module`) and emits edges with the ref's declared `category` instead of hardcoded CALLS. Handles `Bare` and `Attribute` qualifiers; `SelfMethod`/`ComplexReceiver` push to `unresolved_refs` for diagnostics.
- Wired into all three `build_*` functions after `resolve_calls`.
- New go_smoke fixture `tests/fixtures/go_smoke/server/server.go` registers three routes against a stand-in `Router` interface (bare handler, cross-package selector, Group-prefixed route). New end-to-end test `routes_emit_handled_by_edges_via_unresolved_ref_resolution` asserts all three handlers resolve to HANDLED_BY edges and `unresolved_refs` is empty.

## Why Route `route:<path>` but Endpoint `endpoint:<METHOD>:<path>`

The asymmetry is deliberate and worth keeping in mind for v0.4.4b HttpStackResolver matching:
- **Route** represents a server-side HTTP resource. `GET /users` and `POST /users` share the same logical resource; collapsing them onto one Route node (with method cells stacked) matches how REST APIs are conceptually organised and how routers register paths.
- **Endpoint** represents a client-side callsite invocation. `this.http.get('/users')` and `this.http.post('/users')` are two different logical operations from the caller's POV; collapsing them would lose the ability to query "which functions POST to /users specifically."

HttpStackResolver pairs endpoints to routes by (METHOD, normalised_path) — it reads method from the Endpoint qname and from the Route's method cells.

## Next step (v0.4.4b)

CrossGraphResolver trait + MergedGraph + HttpStackResolver + cross-repo smoke test. Task #32 still pending. Last session user was explicit: HttpStackResolver first, then the rest of 0.4.4.

**Fixture plan:** new self-contained pair at `tests/fixtures/http_stack_smoke/` — `frontend/` (TS, Angular-style `this.http.get('/api/users')`) + `backend/` (Go, `r.GET("/api/users", users.List)` behind a `Group("/api")` chain). Each parsed as a separate `RepoId`, fed into a `MergedGraph`, `HttpStackResolver` emits `HttpCalls` Endpoint→Route. Do **not** depend on cloning quokka-stack — that's external real-world validation, not a checked-in smoke test. (Clarification saved 2026-04-17 after user called out loose "quokka fixtures" wording.)
