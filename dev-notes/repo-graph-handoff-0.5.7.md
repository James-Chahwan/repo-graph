# repo-graph handoff - glia 0.5.6 -> 0.5.7

For: repo-graph (the MCP server wrapping glia-py). **Pin: `glia-py==0.5.7`.** Apply on top of the 0.5.6 port
(repo-graph `c8c18e7`, "move onto glia 0.5.6, pinned exactly").

**Status: written at glia HEAD `01a74953` (after wave W12 of 0.5.7), before the bump.** The version bump, the
`v0.5.7` tag and the `glia-py` / `glia-cli` publish are James's release steps after these docs; take the pin
above **once James tags `v0.5.7`**. Until then the workspace reads 0.5.6 and a wheel built from `main` reports
`0.5.6+p<stamp>` from `glia_py.build_stamp()`.

**Where repo-graph stands.** Read read-only at HEAD `c8c18e7` (clean tree): `pyproject.toml:31` pins
`glia-py==0.5.6`, `CLAUDE.md:28` and `:82` say `==0.5.6`, and `CLAUDE.md:140` holds the "glia 0.5.3 -> 0.5.6
boundary notes". The 0.5.4, 0.5.5 and 0.5.6 handoffs are applied. Act on repo-graph only.

0.5.7 is the first half of the 0.5.7 scope (plan `dev-notes/next-leap-0.5.7.md`, packets
`dev-notes/leap-057-packets.json`, waves W0-W13): HP proof and process (close-out gate reuse, build timings,
the doc linker's DOCUMENTS floor, the precision run), HF flows (declared entries seed entry flows, MCP servers
as a Python and a TypeScript host, Rails nested resources), HT build-target graphs (id blocks per domain,
`glia ids`, the bazel snapshot / parser / targets sidecar / answers, contribution seams, `scripts/pr-check.sh`),
HC calibrated confidence (a model-written overlay stanza's pairings tier heuristic; audited precision beside
each tier), HQ the confidence run's false-edge fixes. No new id in the code block (next free stays node 51 /
edge 39 / cell 28; HT.4's 12 ids are in block 2, build targets only), no `FORMAT_VERSION` (3) or
`MANIFEST_VERSION` (2) change, no Cargo.lock move.

Sources, in order of authority: the code at `01a74953`; `git diff v0.5.6..HEAD -- py/api_surface/ cli/surface/`;
each packet's landed result (its `breaking` text) and commit body; the `HANDOFF FROM ..` paragraphs routed to
HZ.2 in `dev-notes/leap-057-corrections.json`. Packet ids are glossed in words; the hash after an id is the glia
commit that landed it.

---

## 0. TL;DR

1. **No wrapper code change is required.** The pyo3 calls repo-graph makes (`generate`, `load_from_gmap`,
   `WatchSession`, `dense_text`, `resolve`, `blast_radius`, `cross_stack_trace`, `node_cells`,
   `governing_docs`, `coverage`, `entry_flows`, `nodes_json`, `find`, `bfs`, `predecessors`) keep their
   signatures. Every surface change is a trailing keyword, a new method or a new dict key (section 2).
2. **More entry flows and more `entry: true` nodes** (HF.1 `f70f3957`, section 3.1). A node carrying an
   ENTRYPOINT cell (host starts, scripts, `__main__` guards, pytest fixtures, overlay `[entrypoints]`) is now a
   flow entry, as it already was a liveness seed. `RustGraph.entry_flows` / `.flows` (`repo_graph/graph.py:63-75`)
   gain keys, and `nodes_json`'s `entry` (`graph.py:56`) reads true for them. A test that pins a flow count
   re-records.
3. **repo-graph's own tools now read live.** HF.3 (`cd3e04a3`) reads Python MCP servers as a host: on
   repo-graph itself, `repo_graph/server.py`'s six tools become CLI_COMMAND `host_cmd:mcp:tool:<name>`
   HANDLED_BY their functions (`[host] lang=python commands=6 .. hosts=mcp:6 file=repo_graph/server.py`), so
   `orient` / `find` / `impact` / `trace` / `read` / `refresh` leave dead code and appear as `glia flows`
   entries.
4. **The coverage footer may change** (section 3.3): new `ruby` HANDLED_BY and `solidity` EVENT_FLOWS caveat
   rows and rewritten Python / TypeScript host notes. `_coverage_note` (`server.py:1252`) shows the first 8
   rows, so on a Ruby or Solidity repo a new row can push an older one past the cut.
5. **Overlay users: mark hand-written stanzas `origin = "human"`** (HC.1 `104fd310`, section 3.2). An
   unmarked or `origin = "llm"` `[[wrapper]]` / `[constants]` / `[[route_prefix]]` stanza now tiers its HTTP
   and queue pairings heuristic (EVIDENCE rule `<rule>/overlay_llm`), and HQ.12 (`583f91ca`) writes no
   http_model identity class that rests only on such a pairing.
6. **Graph content moves** (section 4): Rails nested resources, C# verb-constrained routes and usings,
   Angular lazy and computed nav paths, Solidity events, heritage never ending at a namespace, nearer
   same-stem TESTS, fewer Python ATTRIBUTEs, fewer DOCUMENTS. Any test pinning a route name, a page qname, an
   edge or node count on such a repo re-records.
7. **Opt-ins worth adopting** (section 5): `precision` beside each tier in why / check / query / implementors /
   review, and the build-target answers `targets_*` for Bazel repos.

## 1. The pin

| file:line (repo-graph working tree, read-only) | now | change to |
|---|---|---|
| `pyproject.toml:31` | `"glia-py==0.5.6",` | `"glia-py==0.5.7",` |
| `CLAUDE.md:28` | runtime deps `glia-py==0.5.6` | `glia-py==0.5.7` |
| `CLAUDE.md:82` | consumes the published `glia-py` wheel (`==0.5.6`) | `==0.5.7` |
| `CLAUDE.md:140` | "glia 0.5.3 -> 0.5.6 boundary notes" | add a 0.5.6 -> 0.5.7 block (sections 2-4 here) |

**Stamps and caches.** PARSER_STAMP / BUILD_STAMP moved (graph, engine, code-domain, parsers, core,
build-domain and store edits): the first build after the upgrade reparses everything and rewrites
`.glia/graph/`. A calibration record (`glia history calibrate`) is read only by the build that wrote it:
recalibrate. Vectors (`.glia/vectors.jsonl`) stay valid; `glia embed` re-embeds only nodes whose text moved.
A `.glia/.gitignore` glia writes fresh gains a seventh line, `targets-snapshot/` (HT.3 `ae76e579`); an
existing one is left as it is.

## 2. API and surface changes (all additive for a Python caller)

From `git diff v0.5.6..HEAD -- py/api_surface/ cli/surface/`:

| packet | pyo3 | CLI |
|---|---|---|
| HC.4 audited precision beside the tier (`ffa6454d`, review's pyo3 half `cf64d1af`) | `PyGraph.why(.., category=None, precision=True)`, `PyGraph.check(strict=False, precision=True)`, `PyGraph.query(.., max_mb=None, precision=True)`, `PyGraph.query_gql(.., max_mb=None, precision=True)`, `PyGraph.implementors(.., transitive=True, precision=True)`, `review_vs_rev(.., offset=0, precision=True)` | `--no-precision` on `why`, `check`, `query`, `implementors`, `review` |
| HT.7 build-target answers (`8ed03244`) | `glia_py.targets_sync(repo, bazel="bazel", workspace="", expr="//...:*", from_file=None)`; `PyGraph.targets_owners(files)`, `targets_deps(label, depth=3, workspace=None)`, `targets_rdeps(label, depth=3, workspace=None)`, `targets_affected(files=None, base="HEAD")` | `glia targets sync\|owners\|deps\|rdeps\|affected` |
| HT.2 ids on the surfaces (`f0864aa0`) | - | hidden `glia ids ls [--domain <d>] [--json]`, `glia ids next --domain <d> --table <t> [--private]`; `glia inspect --json` rows gain `block` |

Nothing else on `py/api_surface/` or `cli/surface/` moved.

### Keys that changed meaning or gained values

- **`precision`** (HC.4). The dicts of `why`, `check`, `query` / `query_gql`, `implementors` and
  `review_vs_rev` gain a `precision` object beside each tier: `{lo, p, hi, n, stratum, audit}`, plus `census`,
  `under_floor`, `unmeasured`, each only when true. review's dict also gains `counts.precision_by_tier`.
  Markdown tier cells read `fact (>= 0.91 on CALLS|fact, n=41)`, `.., under floor)` or `(unmeasured
  stratum)`, and review's `_by tier:` line gains the per-tier estimate. No row, order, tier, `blocking` or
  exit code changes. `precision=False` / `--no-precision` gives the 0.5.6 bytes. repo-graph calls none of
  these today. What the number is and is not: `docs/rules.md`, "Precision beside the tier".
- **`targets`** (HT.8 `8edfc013`). With a `.glia/targets-snapshot/` (written only by `glia targets sync` /
  `targets_sync`), `review_vs_rev`'s dict, `PyGraph.diff_impact` / `diff_impact_vs_rev` and review /
  diff-impact `--json` gain a last key `targets` (`changed`, `owners`, `targets`, `tests`, `unowned`,
  `caveats`), and review markdown gains a last `### Build targets` section. Without a snapshot the output is
  byte-identical to 0.5.6. A merge (`--with`) reads only the lowest-id root's snapshot.
- **`targets_*` without a snapshot** raise `ValueError`; they read the snapshot and a `.glia/graph/targets.gmap`
  sidecar the first targets call writes (HT.6 `36b96b0e`). Nothing else writes or reads that sidecar.
- **`glia inspect --json`** (HT.2): every kinds / categories / node_cells / edge_cells row, per shard and in
  totals, gains `block` (last). A code layout's text output is unchanged; an id >= 0x10000 prints as
  `0x<8 hex> [<block>]`.
- **EVIDENCE rules** (HC.1): a pairing that rests on a model-written overlay stanza reads `<rule>/overlay_llm`
  (`exact/overlay_llm`, `base_fold/overlay_llm`, `pattern/overlay_llm`, `binding/overlay_llm` ..), and why /
  check / review / query tier it heuristic with the note `rests on a model-written overlay stanza (<base
  rule>)`. Strip the suffix for the base rule.

## 3. Cells, coverage and overlay

### 3.1 Entries (HF.1)

No cell changes: what moves is who reads the existing ENTRYPOINT cells. `entry_flows`, `find --flows` /
`find_flows`, concept search (`flows --concept`, `concept_flows`, trace's concept fallback), trace's entry
tier and `duplicate_flows` now include every node with an ENTRYPOINT cell (sources `config`, `main_guard`,
`host:<h>`, `shebang`, `script_arg`, ..). `nodes_json`'s `entry` reads true for them. A repo with no
ENTRYPOINT cell answers byte for byte as 0.5.6. `_entry_read_from()` (`server.py:887`) labels these cells
already; nothing to change there.

### 3.2 Overlay origin (HC.1, HQ.12)

- An unmarked or `origin = "llm"` `[[wrapper]]` / `[constants]` / `[[route_prefix]]` stanza in
  `.glia/overlay.toml` now gives its HTTP_CALLS / QUEUE_FLOWS pairings rule `<rule>/overlay_llm` and tier
  heuristic, so a `check` / `review` violation through one is advisory. `origin = "human"` stanzas are
  unchanged. Write `origin = "human"` on stanzas a person wrote; `skills/glia-overlay/SKILL.md` (glia) already
  tells a model to write `origin = "llm"`.
- The ENDPOINT_HIT cell of an ENDPOINT an llm `[[wrapper]]` minted gains a trailing `"overlay":"wrapper#<n>"`
  (a `[constants]` pin keeps its `const:<KEY>` value). `_cell_text` (`server.py:825`) prints the JSON as is.
- HQ.12: an http_model SAME_AS class that rested only on such a pairing is no longer written, so `find` /
  `blast_radius` / trace stop folding or walking through it; a `suffix/overlay_llm` pairing counts as weak,
  as plain `suffix` did. When two endpoints pair one route under different rules, a contract-field /
  model-break row's `rule` now names its own endpoint's rule.

### 3.3 Coverage rows (`coverage()`, absences, check / query caveats)

| packet | row |
|---|---|
| HQ.11 Rails route caveat (`f04c1317`) | new `ruby` HANDLED_BY row on a repo with `.rb` files |
| HQ.3 Solidity events (`d50142cb`) | new `solidity` EVENT_FLOWS row: a Solidity repo's EVENT_FLOWS caveat lists `["*", "solidity"]` |
| HF.3 Python MCP host (`cd3e04a3`) | the python HANDLED_BY host note: "Python host events are read for one host only, Flask, .." -> "Python host registrations are read for two hosts, Flask and MCP servers. .." |
| HF.4 TypeScript MCP host (`5a2a7040`) | the typescript HANDLED_BY note rewritten |
| HQ.6 computed nav parents (`77a64cc1`) | the typescript NAVIGATES_TO caveat gains one clause |

### 3.4 IMPORT_BINDINGS on C# (HQ.13 `96a17709`)

A `.cs` MODULE's IMPORT_BINDINGS cell now lists every `using`, in-repo or external. Rows gain `form`
(`namespace` / `static` / `alias`) and `global`; a namespace row's spec is the whole namespace with `name`
null. `node_cells` returns it as JSON text.

## 4. Graph content (no code change; answers change)

**Resolve passes: still 19** (`[passes] domain=code resolve=19 post=9 finalize=2`).

### 4.1 Re-keyed nodes (a qname moved)

| packet | old -> new |
|---|---|
| HF.5 Rails nested resources (`e2ac26ea`) | ROUTEs under a `resources` block nest: `ANY /api/v1/notifications` -> `ANY /api/v1/accounts/:account_id/notifications`; each plural `resources` gains `ANY /<r>/:id` (unless `only:` / `except:` leave none); member / collection / `on:` / symbol-verb routes appear (chatwoot: 472 routes, 402 nested) |
| HQ.2 C# verb + `[Route]` (`eda7a215`) | an action with `[HttpX]` and `[Route(t)]` is `X /t` (was `X <prefix>` plus `ANY /t`); the shared `<VERB> /` ROUTEs are gone (squidex: 108 `GET /` HANDLED_BY -> 1); HTTP_CALLS re-pair by verb; ApiExplorer / Swashbuckle ops on such actions are keyed (squidex ops 4 -> 204) |
| HQ.5 Angular lazy child tables (`e0d19816`) | nav pages of a `loadChildren` table gain their parent prefix (squidex `page:/:schemaName` -> `page:/app/:appName/schemas/:schemaName`); a lazy table's `''` page no longer merges into `page:/`; literal links that param-bound a prefix-less page become dead-link rows the root catch-all absorbs (squidex: 14) |
| HQ.6 computed parent paths (`77a64cc1`) | a nav ROUTE under a computed parent (a call, identifier, member path or `${..}` template) keeps an opaque head: `page:/list` -> `page:/~frontendURL/accounts/:accountId/settings/custom-roles/list`; the computed parent itself is a page (chatwoot: 69 -> 178 page ROUTEs). Page qnames may now hold a `~<name>` segment: render as is |
| HQ.14 JPQL `JOIN FETCH` (`b609daa1`) | `data_entity:sql:fetch` is gone; the ACCESSES_DATA goes to the entity `join fetch <Entity>` names |

### 4.2 New nodes

- **MCP servers as a host.** Python (HF.3): `@<server>.tool()` / `.prompt()` / `.resource(<uri>)` and the
  low-level `Server`'s handlers mint CLI_COMMAND `host_cmd:mcp:tool|prompt:<name>` and EVENT_HANDLER
  `host_event:mcp:resource:<uri>` / `host_event:mcp:<handler>`, HANDLED_BY the function (EVIDENCE
  `parser:python`, rule `host_decorator`). TypeScript (HF.4): `tool` / `prompt` / `resource` and `register*`
  on `new McpServer(..)` from `@modelcontextprotocol/sdk` mint `host_cmd:mcp:tool:<name>`,
  `host_cmd:mcp:prompt:<name>` and `host_event:mcp:resource:<uri>` (or `resource:<name>`), HANDLED_BY
  (`parser:typescript`, rule `host_handler`); an inline handler becomes its own FUNCTION `<module>::command
  tool:<name>` / `<module>::on resource:<uri>` with a DEFINES from the MODULE, and owns the handler's calls.
  The handlers and the helpers they call read live.
- **Build targets** (HT.4-HT.6) live in their own sidecar `.glia/graph/targets.gmap` with ids in block 2; a
  code layout never holds one, and no code answer reads it except the `targets` key above.

### 4.3 New, removed and re-stamped edges

- **Heritage never ends at a namespace** (HQ.1 `b383c243`): no INHERITS_FROM / IMPLEMENTS ends at a PACKAGE
  or MODULE; the hit is looked up again among types (squidex: -48, +32 heuristic). PHP gains the in-repo
  bases DH.14 used to skip.
- **C# usings** (HQ.13): heritage EVIDENCE rule `global_unique` (heuristic) -> `nested_type` /
  `enclosing_namespace` / `using_namespace` / `using_static` (fact; squidex 1460 edges restamp, 0
  `global_unique` left); a namespace `using` IMPORTS its PACKAGE (rule `using_namespace`, fact; squidex 7033,
  was 1458 `tail_unique` heuristic); an undeclared namespace gets no tail guess. `implementors` tiers on C#
  move heuristic -> fact.
- **Solidity events** (HQ.3): no EVENT_FLOWS edge ends at a missing node. An inherited emit is a
  `graph:solidity` EVENT_FLOWS to the base's EVENT_EMITTER (rule `inherited_event`, or
  `inherited_event_by_name`, heuristic), a qualified emit to the named type's event (`qualified_event` /
  `qualified_event_by_name`), else no edge (zora-protocol: 216 dangling rows -> 0, EVENT_FLOWS 291 -> 215).
  Anything that assumed every EVENT_FLOWS is `parser:solidity` fact must update.
- **Solidity HANDLED_BY** (HQ.4 `c2095fee`): every RPC_PROCEDURE HANDLED_BY carries an explicit EVIDENCE
  `{emitter parser:solidity, file, line, basis site}` at its handler declaration (was basis `from_node`); twin
  contracts each get their own copy's file. A delta against a pre-0.5.7 rev shows one `restamped` row per edge.
- **TESTS** (HQ.10 `793dca86`): a test with several same-stem candidates pairs the best by import rank, then
  shared directory names, trailing run, common prefix; more than 3 ties pair nothing (was the first 3).
  tests-for and review's tests-to-run lose the false same-stem rows.
- **Python ATTRIBUTE** (HQ.9 `9d779ba9`): a `self.X` read declares no ATTRIBUTE for the class's own METHOD /
  property or an inherited member; an own-property assignment is a setter call. METHOD / ATTRIBUTE qname twins
  are gone (mealie: HAS_ATTRIBUTE 3513 -> 2695, twins 388 -> 0), so a cell write or `find` on such a qname is
  no longer ambiguous.
- **DOCUMENTS** (HP.4 `313e7d93`): fewer. A token in a rule / key / kind position, a key chord (`Alt` +
  `Tab`), a private Rust `fn` from outside its project and a bare cross-project mention from a sub-project's
  doc bind nothing; some picks move to a public twin. `governing_docs` (`server.py:979`) and docs-for move.
- **Removed, test and queue noise:** a test module that mocks a store client, or names one only in a
  camel-middle identifier or quoted text, loses its ACCESSES_DATA -> `data_source:*` (HQ.8 `e0222291`); a file
  naming `redis` only inside a longer identifier mints no Redis pub/sub nodes (HQ.7 `f1b7e38d`; tolgee loses
  `queue_consumer:unresolved:redispubsub`).

### 4.4 Answers that move with it

- **impact / blast-radius / find / trace** over the edges above, and the PPR / co-change rankings of
  blast-radius, diff-impact, review and pack may reorder on repos whose graph moved; the close-out's rank and
  cohort gates read them.
- **dead code** shrinks on MCP servers (HF.3, HF.4).
- **pages** (`glia pages`) show the prefixed and opaque page qnames and more dead-link rows (HQ.5, HQ.6).

## 5. New primitives worth adopting (all optional)

- **Precision beside the tier.** `why` / `check` / `query` / `implementors` / `review_vs_rev` return an
  audited precision `{lo, p, hi, n, stratum}` per row (HC.4), released because the held-out calibration
  passed its committed rule (`dev-notes/confidence-gate-0.5.7.md`, HC.3 `6cbcf536`):
  `CONFIDENCE: R1=yes (25/25) R2=yes (0.0218) R3=yes (25) -> PASS`. Caveats in that report: the re-judge was
  the same agent re-reading source, so its kappa 1.000 is self-consistency, not inter-judge agreement; 13
  held-out strata sit outside K (12 with no fit row, NAVIGATES_TO|derived and EVENT_FLOWS|fact, the two worst,
  among them), so no transfer was measured there; and five strata (DEFINES|fact 0.355, CALLS|fact 0.324, ..)
  carry 0.858 of R2's weight. A `why` tool could print the `p` beside the tier word.
- **Build targets.** For a Bazel repo, `targets_sync(repo)` once, then `PyGraph.targets_owners(files)` /
  `targets_deps` / `targets_rdeps` / `targets_affected` answer "which targets own / need / are affected by
  these files"; each needs the snapshot first (else `ValueError`).

## 6. Not in 0.5.7

- **The precision claim fails its committed rule.** HP.5 (`528c7e4c`, `dev-notes/edge-precision-0.5.7.md`):
  `[edge-audit] rule 0.5.7 verdict=FAIL under_floor=ACCESSES_DATA|fact,CONTAINS|fact,EVENT_FLOWS|fact,HANDLED_BY|fact,HAS_ATTRIBUTE|fact,INHERITS_FROM|fact,NAVIGATES_TO|derived,NAVIGATES_TO|fact,TESTS|derived fact=0.993 derived=0.878 heuristic=0.990 kappa=1.000`.
  Every under-floor stratum there comes from the held-out panel's verdicts on edges the candidate mostly no
  longer writes (26 of its 28 wrong edges are in no stratum of the candidate's build); the fit panel, drawn at
  the candidate, reads fact 1.000, derived 0.936, heuristic 1.000. The re-measure on a held-out panel re-drawn
  at the candidate (HP.7 / HP.8 `3fc11b04`): `[edge-audit] rule 0.5.7b verdict=FAIL
  under_floor=ACCESSES_DATA|fact fact=0.999 derived=0.991 heuristic=1.000 kappa=1.000` and `[edge-audit] rule
  0.5.7b rejudge independent=64 self=3`. The one under-floor stratum is a single wrong edge (tolgee's JPQL
  `join fetch` -> `data_entity:sql:fetch`), whose cause HQ.14 fixed after the draw.
- **No goal layer, clarification queue, PR intent, repair loop, `decide/` or `glia judge`.** `glia explain` is
  0.5.8, a small release of its own; the goal layer (GOAL_UNIT / TRACES / UNIT get their emitter there) is
  0.5.9.
- **No Rust body-only watch path, no `glia place`, no docs-as-a-second-graph rows** (unchanged from 0.5.6).
- **The rank gate's accepted rows are 2** (shell `PT*` mrr, websocket `B0` mrr); FD.79's four glia impact rows
  were retired by HP.6 (`673c3065`), so a glia impact drop now fails the gate. Nothing for repo-graph to do.

## 7. Re-test

1. `pip install glia-py==0.5.7` into repo-graph's venv; `make test` (or `pytest tests/`).
2. Expect re-records where a test pins: a flow count or entry list (HF.1), a coverage footer on a Ruby /
   Solidity repo, a route or page qname on Rails / C# / Angular, a dead-code row of an MCP tool, a tests-for
   row on a repo with same-stem tests.
3. In a live MCP session on repo-graph itself: `orient` lists the six tools as entries; `impact` on
   `repo_graph/server.py`'s tool functions no longer flags them dead.
4. With an overlay: an unmarked `[[wrapper]]` pairing reads heuristic in `glia why`; mark it
   `origin = "human"` and it reads derived again.

## 8. stderr markers (only for a stderr parser)

New lines: `[flows] declared entries=<n> new=<m> sources=(config= main_guard= host= script= other=)` (HF.1),
`[overlay-tier] model_rested=<n> (http=<h> queue=<q>)` (HC.1), `[confidence] surface=<cli|py> rows=<r>
measured=<m> unmeasured=<u> under_floor=<f> audit=<12 hex>` (HC.4), `[heritage] namespace targets
refused=<n> (..) rebound=<r>` (HQ.1; `[php-heritage] namespace-named bases skipped=` is retired), `[cs-scope]
heritage ..` and `[imports] csharp usings ..` (HQ.13), `[sol-events] ..` (HQ.3), `[csharp-routes] verb
constraints applied=<a> route_templates=<t> in <file>` (HQ.2), `[nav-mounts] ..` (HQ.5), `[py-attrs] ..`
(HQ.9), `[queues] gate word refused ..` (HQ.7), `[data-entity] jpql join fetch skipped=<n> path=<p>` (HQ.14),
`[coverage] ruby: ..` (HQ.11), `[targets] sync ..`, `[targets] sidecar built|reused ..`, `[targets] answer
kind=<k> rows=<r> tests=<t>[ surface=<s>]`, `[targets] surface=<cli|py> cmd=<c> ..` (HT.3, HT.6-HT.8), `[ids]
ls ..` / `[ids] next ..` (HT.2). Lines that gained fields: `[ruby-routes]` (` nested= member= collection=
id_routes=`, and it prints for a prefix-less routes.rb, HF.5), `[doclink] precision:` (` position= private=
other_project= chord=`, HP.4), `[models] classes=` (` model_rested=`, HQ.12), `[tests] module TESTS edges:`
(` nearest= ambiguous=`, HQ.10), `[sol-abi]` (` handled_sited=` before ` path=`, HQ.4), `[data-sources]
refused` (` test_mocked= test_camel= test_quoted=` before `path=`, HQ.8), `[extract] nav-routes marked:`
(` opaque_parents= opaque_children=`, HQ.6), `[nav]` (` opaque_unmatched=` when non-zero), `[evidence-rules]
resolver=http|queue` (`<rule>/overlay_llm=<n>` slots, HC.1).

## 9. Packet index

Every 0.5.7 packet and where it is listed. Declared consumer-visible change: HC.1 (s2, s3.2), HC.4 (s2, s5),
HF.1 (s0, s3.1), HF.3 (s0, s3.3, s4.2), HF.4 (s3.3, s4.2), HF.5 (s4.1), HP.4 (s4.3), HQ.1 (s4.3), HQ.2 (s4.1),
HQ.3 (s3.3, s4.3), HQ.4 (s4.3), HQ.5 (s4.1), HQ.6 (s3.3, s4.1), HQ.7 (s4.3), HQ.8 (s4.3), HQ.9 (s4.3), HQ.10
(s4.3), HQ.11 (s3.3), HQ.12 (s3.2), HQ.13 (s3.4, s4.3), HQ.14 (s4.1), HT.2 (s2), HT.7 (s2, s5), HT.8 (s2).
Process only, nothing for repo-graph: HP.1 (close-out gate reuse; clippy is a close-out gate), HP.2, HP.3.
Measured, no shipped change: HC.2, HC.3 (s5), HF.2 (the concept gate re-run, `CONCEPT: C1=yes (4/5) C2=yes
(4/5) -> PASS`, so the semantic tier stays), HP.5, HP.7, HP.8 (s6), HP.6 (s6). Additive engine-only or
tooling, nothing for repo-graph: HT.1, HT.3, HT.4, HT.5, HT.6, HT.9, HT.10.
