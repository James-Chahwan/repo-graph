# glia handoff — v6 (2026-07-08)

The next leap for glia, derived from a full session of A/B evals of the MCP tools
against grep on real repos. This is **not** "port the Python bits" — it's a
substrate + primitive investment driven by one thesis.

## The thesis (everything hangs off this)

**The graph's value is a function of (size × complexity × cross-boundary-ness)
exceeding what fits in context.** Small project + clear goal → the model reads it,
grep wins, the graph is pure overhead. As scale / rules-docs / multi-project
cross-cutting grow past context capacity, the graph wins — and *reliably*.

**We cannot win on context economy.** The MCP layer taxes us: tool schemas +
server instructions are fixed per-turn overhead whether or not a tool fires. We
will never be the "fewer tokens" option. So every glia decision must serve
**correct, complete, cross-boundary answers in few high-value calls** — never
"smaller output."

## Evidence (this session, clean env, `--setting-sources project`, recall/precision grader)

- **oci schema-blast (complex, non-symbol dependents):** graph-driven **recall 0.75 /
  precision 1.00 / 0 dead-cited** vs grep **0.58 / 0.88 / 1 dead-cited**. Graph
  correctly reasoned live-vs-dead (excluded the unimported `src/process` mirror).
- **quokka-stack monorepo (turps Go + quokka_web Angular + quokka_android Flutter),
  notifications blast radius across all 3 projects:** graph+grep **1.00/1.00 reliably**
  (both runs, cheaper: $0.38) vs grep **bimodal 0.0/1.0, median 0.50**. BUT the graph
  found the Flutter side **via grep, not its own edges** — it's blind to Dart
  `dio.get`. The combined arm papered over the substrate gap.
- Trivial `find-routes` on small repos: grep ties. Graph earns nothing there.

Caveat: n=2 per arm; grep's 0.0 runs were 1-turn give-ups. The robust claim is
"graph+grep is *consistently complete*; grep-alone is *variable* and blind to
cross-boundary semantic links."

## The four priorities (in order)

### P1 — Substrate completeness (the ceiling on all value)
Every missing edge is a task grep wins *today* that would flip to the graph. Close
them all, eval-driven. **First artifact: a substrate-gap eval** (below). Confirmed
gap cells so far:
- **Flutter/Dart HTTP calls** — `dio.get('/x')` → route. Graph is blind to a whole
  frontend on the monorepo. Highest-value hole.
- **Angular DI** — `@Injectable` services have ZERO reference edges, so the liveness
  signal false-flags them `⊘` dead. `INJECTS` (category id 8) exists in the registry
  but isn't emitted for DI. Emit it → liveness stops lying + "who uses this service"
  works.
- **Synthetic endpoint nodes carry no path** (`path=None`) — can't trace a route back
  to the specific frontend call-site file. Endpoint should carry its call-site path.
- **`impact` fans out through `imports` edges** — depth-6 traversal pulls in noise via
  shared imports (agent had to "rule out by inspection"). Blast-radius traversal must
  be edge-category-aware (calls/accesses_data/http_calls carry the radius; imports/
  contains do not, or are down-weighted).

### P2 — Confidence / completeness signaling (turn blind spots into smart fallbacks)
The winning pattern is **graph+grep** — but only works if the agent *knows* where
the graph is blind. Tag coverage: "this subtree is Dart — HTTP extraction is
partial, verify with grep." A silent blind spot is a wrong answer; a declared one
is a correct fallback. Makes the combined pattern deliberate, not lucky.

### P3 — Answer-shaped primitives in the engine (kill the spiral, earn the tax)
The agent spiraled to 44 tool calls because our tools are *primitives it composes*.
Glia should expose the composed answer:
- `blast_radius(node)` → complete, deduped, **live-filtered**, PPR-ranked, located
  closure with per-node edge-reason — in ONE call. Not find→impact→activate→read×N.
- `cross_stack_trace(feature)` → full path with mechanism labels (http/queue/file).
- `resolve(signal)` → stacktrace/diff → ranked located nodes.
A single correct call is what justifies the fixed schema cost.

### P4 — Consolidate the tool surface (the one lever on the tax)
**13 tools is itself part of the overhead.** Fewer, more powerful, answer-shaped
tools = less fixed schema in every prompt + less agent confusion. Collapse toward
~4 (e.g. `orient` / `blast_radius` / `trace` / `read`) powered by a complete
substrate. OPEN DESIGN QUESTION: exactly which ~4, and what each subsumes.

## Substrate-gap eval (P1's first artifact)

A fixture matrix `framework × edge-category`. For each of the 20 analyzers, a tiny
repo with **known ground-truth edges**; measure **extraction recall** per category.

- Rows: the 20 analyzers (Go, TS/Angular, Dart/Flutter, Python, Java/Ktor/WebFlux,
  React, Vue, Swift, Kotlin, ...).
- Cols (edge categories that matter): `http_calls`, `handled_by`, `injects`,
  `accesses_data`, `tests`, `imports`, `calls`, `shares_schema`, `event_flows`,
  `queue_flows`.
- Cell value: recall of expected edges (hand-enumerated per fixture).
- Output: the full map of blind spots — which (framework, edge) cells are 0.

This generalizes the grader approach in `bench/grade.py` (recall over a
hand-enumerated key) down to the edge-extraction layer. Reuse that pattern.

## Python → glia migration (respects "keep Python minimal")

Prototype-in-Python, harden-in-glia once semantics are proven — which is what we
did. Graduate in this order, each gated on the substrate:
1. **Fix edges first** (P1) — liveness is only as correct as the edges it counts;
   today it false-flags DI *because* the substrate is incomplete.
2. **Then migrate liveness** into glia as a real `reachable_from_entrypoint` node
   property (correct once INJECTS + dynamic-dispatch edges exist).
3. **Then migrate answer-shaping** (rank + locate + why + live-filter) into the
   engine primitives (P3) so TUI / 3d-viewer / MCP all share it and the wrapper
   goes thin again.

## What stays in repo-graph (the wrapper)
Thin presentation over glia answers. The features built this session (path:line,
`⊘` marker, ranked impact, batch read, node_cells surfacing, cheap status,
recall/precision grader, `--setting-sources project` isolation) stay until the
engine primitives (P3) supersede them.

## Backing artifacts (in repo-graph)
- `bench/grade.py` — recall/precision grader (the eval pattern to reuse for P1)
- `bench/answer_keys/oci-schema-blast.json`, `bench/answer_keys/quokka-notifications-xstack.json`
- `bench/smoke_decisive.py`, `/tmp/qs_eval.py` — the clean eval runners
- `bench/run_bench.py` — now isolates via `--setting-sources project`
