# glia requirements — repo-graph roadmap (post-0.4.18)

Engine-side work repo-graph needs from glia (`repo-graph-py` pyo3 wheel) to ship the
0.4.19+ tool changes. Pure-Python items (new tool wiring, param plumbing, sniffers,
rendering) stay in the repo-graph wrapper and are **not** listed here — this is only what
the wrapper cannot do without engine support.

## BUG-1 (glia data-sources) — SQL data_entity false positives from prose · P1

Found 2026-06-09 on quokka-stack (MongoDB-only): **every** `data_entity` node is
`data_entity:sql:<englishword>` — `sql:the`, `sql:a`, `sql:all`, `sql:from`, `sql:each`,
`sql:already`, `sql:matches`, `sql:caller`, ... 40 nodes, ~all garbage, zero real SQL in the
repo. Pollutes activation/impact/dense_text on the data tier and reads as broken in any demo.

Root cause in `parsers/code/extractors/src/data_entities.rs`:
1. `has_sql_context(source)` is a coarse **file-level** gate — one `"select "` / `"update…set"`
   substring (incl. in comments/UI strings) opens the *entire file* to the table scan.
2. `scan_sql_tables(source)` then scans `FROM/JOIN/INTO/UPDATE <word>` over the **whole file
   text including comments** (header says "inside string literals" but it scans raw `source`).
   The Swagger `@Description` doc-comments in quokka's Go controllers ("…request **from the**
   user", "…**from all** group", "…**into a** group", "is **already** shared **into the**…")
   get minted as tables.
3. `is_noise_entity_name` is a stopword blocklist (`this/that/it/self/...`) that doesn't catch
   `the/a/all/from/each/already/matches/...` — and a blocklist is unwinnable here anyway.

Fix direction (not a bigger blocklist): scan only inside actual **SQL string literals**, or
require the `FROM/JOIN/INTO x` to be in the *same literal/statement* as a SQL signature
(`SELECT … FROM x`), not merely the same file. Separately, quokka's Mongo collections aren't
captured as `nosql:` at all — the mongoose/`.collection()` scanners don't match the Go
mongo-driver access pattern, so the data tier is *both* polluted (false SQL) and *missing*
(no real collections). Not a 0.4.19 wrapper blocker; a glia analyzer fix.

Hand-off target: glia repo (`/home/ivy/Code/glia`), shared crates
(`graph`, `store`, `core`, `projection-text`, `activation`) + the `py` binding.

## Current py-binding surface (repo-graph-py 0.4.14, verified 2026-06-09)

`PyGraph` methods the wrapper relies on today:

| method | signature | returns |
|--------|-----------|---------|
| `nodes_json()` | `($self)` | JSON list; each node = `{id, kind:u32, name, qname, confidence}` |
| `edges_json()` | `($self)` | JSON list; each edge = `{from, to, category:u32}` |
| `activate(seed_ids, top_k)` | `($self, seed_ids, top_k)` | scored node results (ranking already present) |
| `dense_text()` / `dense_text_full()` | `($self)` | whole-graph dense sigil text (full = untruncated cell bodies) |
| `find_node(query)` / `find_nodes_by_qname(query)` | | id / list of ids |
| `neighbours(node_id)` | `($self, node_id)` | adjacency |
| `node_count` `edge_count` `cross_edge_count` | | counts |
| `save_to` `save_to_default` | | persist `.gmap` |

Module: `generate`, `generate_many`, `load_from_gmap`, `is_stale`, `default_gmap_dir`,
`parse_file_to_json`, `version`.

**The gaps below are the entire engine ask.** Priorities mirror the repo-graph change spec.

---

## GR-1 — Node source spans in `nodes_json()`  · P0 · blocks `read`, scoped `dense_text`

Nodes carry no file location. The `read` tool (resolve node → return its source block)
has nothing to slice; the wrapper currently *guesses* a path by appending `.py/.go/.ts/...`
to the qname (`graph.py::file_line_count`) — fragile and language-limited.

**Need:** add to each node in `nodes_json()` (and the underlying Node):

```jsonc
{ "id": ..., "kind": ..., "name": ..., "qname": ..., "confidence": ...,
  "path": "src/auth/login.ts",   // repo-relative; null for synthetic/cross-stack nodes
  "start_line": 42,               // 1-based inclusive; null if no source span
  "end_line": 88 }
```

**Acceptance:** every node parsed from source carries `path`/`start_line`/`end_line`;
nodes without a source location (synthetic, cross-stack endpoints) carry `null`. Spans
round-trip through `.gmap` save/load.

---

## GR-2 — Signal resolver binding  · P0 · blocks `locate`

The one true capability gap. `locate` takes a failure signal (stacktrace / failing-test id
/ diff / changed-file list) and resolves it to seed node ids, then reuses the existing
`activate` engine. The resolver logic exists in glia (`stack_resolvers.rs`) but isn't in
the shared graph crate or exposed to Python.

**Need:** port `stack_resolvers.rs` into the shared `graph` crate, expose:

```python
PyGraph.resolve_signal(text: str, kind: str) -> list[int]
# kind ∈ {"stacktrace", "test", "diff", "auto"}; returns seed node ids (possibly empty)
```

The wrapper handles the `auto` sniffer fallback and rendering; the engine does frame/
symbol/path → node-id resolution.

**Acceptance:** a Python/Node/Go traceback resolves to its frame nodes; a `path::test_name`
resolves to the test node; a unified diff or newline file-list resolves to changed-file
nodes. Unresolvable tokens are simply absent from the result (wrapper reports them).

---

## GR-3 — Subset / prose projection  · P1 · blocks `mode=prose`, scoped `dense_text`

`dense_text()` / `dense_text_full()` are whole-graph only. `mode=prose` (on
activate/impact/locate) and scoped `dense_text(seed=...)` both need to render a *node-id
subset* through `projection-text`.

**Need:** a subset projection binding, e.g.:

```python
PyGraph.dense_text_subset(node_ids: list[int], full: bool = False) -> str   # scoped dense sigil
PyGraph.prose(node_ids: list[int]) -> str                                   # primed prose-anchor output
```

(Naming flexible — what matters is: given a ranked subset from `activate`, return that
slice as dense text and as prose.)

**Acceptance:** passing the top-K from `activate` returns text/prose for exactly those
nodes (plus structural glue), not the whole graph.

---

## GR-4 — Incremental indexing  · P1 · the only large item · performance parity

Confirmed absent: no content-hash, mtime, merkle, or dirty propagation. `generate`/`reload`
full-rebuild and `store` reads/writes the whole container. On a large monorepo the git-hook
freshness path is a full re-scan — the one place repo-graph loses to the field.

**Need (store + core crates):**
- Per-file content hash (BLAKE3) stored in the container.
- On generate/reload: stat + hash each file, re-parse only files whose hash changed.
- Dirty propagation: when a node signature changes, mark downstream context stale so
  cross-stack edges and any cached projections regenerate for affected nodes only.
- mtime fast-path: skip unchanged directory subtrees before hashing (same skip set as
  today: `.git`, `target`, `node_modules`, `.venv`, `__pycache__`, `.ai/`).

**Surface (default on):**
```python
generate(repo_path, incremental: bool = True)
# + an incremental reload entry point (or reuse load_from_gmap + diff)
```
`incremental=False` forces a clean rebuild.

**Acceptance:** touch one file in a ~22k-node repo → reload re-parses ~1 file, not all;
the resulting graph is byte-identical to a clean rebuild.

---

## GR-5 — `profile` edge-weight presets on `activate`  · P2

`activate` already uses domain-tuned edge weights internally. Expose the knob so the same
engine serves different agent tasks.

**Need:**
```python
PyGraph.activate(seed_ids, top_k, profile: str = "default")
# profile ∈ {"default", "repair", "review", "onboard"} — a weight preset over edge kinds
# (repair upweights call/data edges; onboard upweights entry-point + module edges)
```

**Acceptance:** same seeds + same top_k, different `profile` → measurably different ranking
reflecting the preset weights.

---

## GR-6 — with/without benchmark axis  · P1 · proof (entirely glia-side)

Add a repo-graph context axis to glia's Qwen SWE-bench Lite matrix (3×2 → 3×2×2: with vs
without repo-graph as a context layer). Reuses the existing bench harness. Publish one line:
"repo-graph lifts solve rate by N% as a context layer." Highest marketing-per-effort move.

---

## Verify-first / open questions for glia

1. `activate` returns `scores` — confirm the shape (list of `(id, score)`? ids only?) so the
   wrapper can render rank consistently across `activate`/`impact`/`locate`.
2. Is edge weight worth exposing in `edges_json()` too (for client-side display), or keep it
   engine-internal? Not required for any tool above — only asked if cheap.
3. `read` budget/truncation: wrapper will cap the returned span. No engine change needed
   unless you'd rather the engine truncate cell bodies (it already does for `dense_text`).

## Priority order for glia

1. **GR-1** (node spans) + **GR-2** (resolve_signal) — unblock the P0 `read`+`locate` loop, ship together.
2. **GR-3** (subset/prose) — unblocks the P1 prose/scoped-dense cluster.
3. **GR-4** (incremental) — the big one, performance parity.
4. **GR-6** (benchmark) — runs on existing harness, do alongside.
5. **GR-5** (profile) — P2 polish.

Each GR ships as a `repo-graph-py` wheel bump; repo-graph pins `repo-graph-py>=<that version>`
and lights up the corresponding tool in the same release.
