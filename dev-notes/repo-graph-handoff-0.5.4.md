# repo-graph handoff - glia 0.5.4 (0.5.2 -> 0.5.4)

**Status: written at glia HEAD `9bd4d3f0` (after the W26 close-out), before the bump.** The version bump,
the `v0.5.4` tag and the `glia-py` 0.5.4 publish are James's release steps after these docs. Every pin
below is the pin to take **once James tags `v0.5.4`**. Until then the workspace reads 0.5.3 and a wheel
built from `main` reports `0.5.3+p<stamp>` from `glia_py.build_stamp()` (this tree: `0.5.3+p53276b0bd7c90122`).

**Span (ruling HANDOFF-SPAN, James 2026-10-24): 0.5.2 -> 0.5.4.** repo-graph never applied
`dev-notes/repo-graph-handoff-0.5.3.md` (its working tree still holds the uncommitted 0.5.2 port), so this
doc carries it forward (section 3) and adds 0.5.4's changes. Read it in the repo-graph session and act
on repo-graph only.

0.5.4 shipped tracks T0 (ids, crates, slots, rustfmt), T1 (the agent before / after harness), T2 (self-graph
hygiene, one tier vocabulary), T3 (the edge-precision audit and its fixes), T5 (embeddings and the embedding
gate), TS (the fused semantic find / pack, after the fusion gate passed), T10 (org-internal package routing),
T11 (zero-install CLI, skills into glia), TH (the cohort follow-up: compact answers, boundary health,
style-agnostic drift, endpoint inference) and TZ (these docs): 121 landed packets in waves W0-W26 of
`dev-notes/leap-054-packets.json` since `v0.5.3` (`929d99ee`). **Not shipped (ruling OPTION-3, James
2026-10-30):** T4 (per-language residuals), T6 (the goal layer and clarification queue), T7 (concept search,
PR intent, placement), T8 (incremental resolution, multi-repo watch), T9 (build-target graphs). The public
slots `glia_engine::goal`, `glia_engine::clarify`, `glia_engine::targets` and `glia_code_domain::goal` ship
**empty, reserved for 0.5.5**: nothing to adopt, no pyo3 or CLI surface.

Sources, in order of authority: the landed code at `9bd4d3f0` and the surface snapshots diffed
`v0.5.3..HEAD -- py/api_surface/ cli/surface/`; each packet's landed result (its `breaking` text) and
commit body; the routed paragraphs in `dev-notes/leap-054-corrections.json` (FZ.2's entry). Every wrapper
`file:line` was read read-only in repo-graph's working tree: HEAD `0f8ecfa` plus the uncommitted 0.5.2 port
(23 dirty paths, the same as at the 0.5.3 handoff). Packet ids are glossed in words; the hash after an id
is the glia commit that landed it.

---

## 0. TL;DR

**Two wrapper code changes are required, one test edit, and the skills move.**

1. **`impact` is cut to 25 rows and its rows are slim** (compact answers, FH.8 `f92a1ad1` / FH.8b
   `0f6ce15d` / FH.8c `ad730731`). `server.py:503` calls `blast_radius(names, dir_engine, depth, None,
   live_only)`: `top_k=None` used to mean every row and now means 25 (`DEFAULT_OVERVIEW_ROWS`). In such a
   cut answer each row's `name` is **absent when it equals the qname's last `::` segment**, so
   `server.py:538` `r.get('name', '?')` prints `?` for most rows. Fix: `r.get('name') or
   r['qname'].rsplit('::', 1)[-1]`, and either pass `full=True` (every row, every field, the 0.5.2 shape;
   never together with `top_k` or `offset`, a `ValueError`) or render the new `areas` / `truncated`
   (section 2, rows 20-23).
2. **`absence.tier` is lowercase** (one tier spelling on the wire, FD.7d `fb975599`): `_render_absence`
   (`server.py:289`) now prints `(no_match, fact)`. `tests/test_mcp_tools.py:206` `assert "FACT" in out or
   "HEURISTIC" in out` fails; match `fact` / `heuristic`. Its docstring (`server.py:290`) says FACT/HEURISTIC.
3. **The six task skills now live in glia** (FE.7 `1d17d689`): `skills/` and `claude-plugin/skills/`
   become copies of glia's `skills/glia-{orient,find,debug,impact,trace,init}` (names `repo-graph-<verb>`
   -> `glia-<verb>`), and `tests/test_skills.py` and the Makefile `skills` target follow (section 2 row 31).
4. Everything else the wrapper calls binds and reads as before: `find`, `cross_stack_trace`,
   `entry_flows`, `activate`, `resolve`, `node_cells` (VECTOR already skipped), `governing_docs`,
   `coverage`, the registries, `generate`, `load_from_gmap`, `WatchSession`. New keys (`blind`,
   `named_in`, `selection`, `files`) are absent when empty (section 6).
5. **Graph content moves a lot** (section 4): the precision group removes phantom nodes and edges in
   every language (no node a wrapper names by hand). **Nodes re-key** (FD.4d, FD.78, FD.76, FD.77): any
   state keyed by qname orphans; the wrapper keeps none.
6. **The W26 / W31 wrapper fixes routed in 0.5.2 are already in the working tree** (uncommitted, section 8):
   `_dial_text` returns None on `method` (`server.py:823`), renders `via=evm` by library / ABI (825-829),
   `_cell_text` renders SCHEMA_FIELDS as `name: type` (777-788), and a `main_guard` ENTRYPOINT reads
   `entry point` (855-856). Commit them with the port.

Bump order: (1) glia (James): `[workspace.package].version` (which `cli/pyproject.toml` reads), `py/pyproject.toml` and
`engram-export/Cargo.toml` move 0.5.3 -> 0.5.4 in the release commit; tag `v0.5.4`; `wheels-py.yml` publishes
`glia-py` and, once the PyPI pending publisher exists, `wheels-cli.yml` publishes `glia-cli`. (2) repo-graph:
pin `glia-py==0.5.4`, apply sections 0-2, run section 7 against a local wheel, release after the publish.

## 1. The pin

| file:line (working tree) | now | change to |
|---|---|---|
| `pyproject.toml:31` | `"glia-py==0.5.2",` | `"glia-py==0.5.4",` |
| `CLAUDE.md:28` | runtime deps `glia-py==0.5.2` | `glia-py==0.5.4` |
| `CLAUDE.md:82` | "consumes the published `glia-py` wheel (`==0.5.2`)" | `==0.5.4` |
| `CLAUDE.md:127-138` | "glia 0.5.2 boundary notes" | add 0.5.3 + 0.5.4 boundary notes from sections 2-4 |
| `CLAUDE.md:228` | "glia 0.5.3 follows with its own 0.5.2 -> 0.5.3 handoff" | point at this file |

**Stamps and caches.** PARSER_STAMP / BUILD_STAMP moved at every packet that edited a hashed source, and
once more by design: F0.6 (`fed4d59b`, ruling STAMP-LOCK) makes the stamp count the hashed crates'
dependency closure, so one commit gives one stamp however it is checked out or packaged (wheel == sdist).
The first `load_from_gmap` / `refresh` after the upgrade is a full reparse, and **every repo recalibrates
once** (`history_calibrate`; a calibration record is bound to the BUILD_STAMP that wrote it).

**Mixed versions until both sides move.** 0.5.4 writes that a 0.5.3 glia cannot read:
- a `.glia/vectors.jsonl` row with `text_hash` (FB.2 `c7af7f02`) or `device` (FB.14 `a4975faf`): a 0.5.3
  reader rejects the row (its struct denies unknown fields);
- a `.glia/overlay.toml` holding `[[convention]]` (FB.12a `abeef44d`): a 0.5.3 glia ignores the whole file;
- `.glia/vocab-snapshot/` (FB.13a `41fa72b8`): unknown to 0.5.3. The `.glia/.gitignore` template gains
  `vocab-snapshot/`; an existing `.glia/.gitignore` is never rewritten, so add the line by hand.

**The wheel** (FB.5c `79395f1e`, FB.14 `a4975faf`): `glia-py` now builds with `embed` on and ships a
`glia-embed-worker` binary plus the Dawn library (about +15 MB worker and +12 MB Dawn on linux x86_64).
Embedding defaults to the GPU (ORT WebGPU over Dawn) with a CPU fallback; `GLIA_EMBED_DEVICE=cpu|webgpu|cuda`
overrides it. Dawn needs glibc >= 2.38 (older: `fallback=no_worker:status=127`, CPU). The Apple-silicon
wheel's minimum is macOS 13.4 (ruling MAC-ARM-13.4); the Intel-macOS wheel keeps its 10.12 tag and ships
**without** embeddings (ruling INTEL-MAC-NO-EMBED: `model="bge-small"` raises there). The model downloads on
first use into `FASTEMBED_CACHE_DIR`, else `~/.cache/glia/fastembed`, never a repo directory. Nothing embeds
unless `glia embed` / `glia_py.embed` is called.

## 2. Breaks that reach the wrapper

Every row: the glia packet and commit, old -> new, and the wrapper site. The pyo3 surface diff
`v0.5.3..HEAD -- py/api_surface/` is rows 5, 9, 11, 14, 15, 20, 22, 24, 26 and 30's signatures.

| # | packet (commit) | old -> new | wrapper site and action |
|---|---|---|---|
| 1 | F0.1 registry ids (`a27aa00e`) | `kind_names` 49 -> 50 (`GOAL_UNIT` = 50), `category_names` 37 -> 38 (`TRACES` = 38), `cell_type_names` 25 -> 27 (`UNIT` = 26, `IMPORT_BINDINGS` = 27); `glia hubs --category` lists `TRACES`. No build emits a GOAL_UNIT / TRACES / UNIT (their track did not ship) | decoded by name (`_CELL_TYPE_NAMES`): none |
| 2 | FA.21 the IMPORT_BINDINGS cell (`bff59e64`) | every code MODULE with an external import gains cell 27 right after IMPORTS: JSON rows `{"spec","name","alias","line"}` (`spec` the import path as stored, Go's `::`-joined; `name` / `alias` null when absent; `line` 0-based), sorted by (spec, name, alias, line), at most 256 rows then a trailing `{"capped":<n>}`. MODULE only. `node_cells` and the dense text show it (label `cell`, like IMPORTS) | not in `_READ_CELL_TYPES`, so `read` shows nothing; add a label if wanted |
| 3 | FB.2 the VectorRow contract (`c7af7f02`) | vectors keyed by `(qname, kind)` (a same-qname twin keeps two rows), optional `text_hash` (`t<digits>:<16 hex>`); `glia cell ls --check` prints `issue <kind> .glia/vectors.jsonl:<line> ..` lines, gains `vector_audit` in `--json` and `vector_issues= models=` in its marker, and **exits 1** on an audit issue (was 0) | the wrapper writes no vectors |
| 4 | FB.3 vectors are query-time (`94106c1f`) | `PyGraph.node_cells` / `node_cell_bytes` no longer return VECTOR; a VECTOR `set_cell` / `write_cell` / `remove_cell` reports `write_through == "sidecar_only"` and never rewrites the layout or the live graph; writing `.glia/vectors.jsonl` or `.glia/vocab-snapshot/**` no longer stales a layout or wakes a `WatchSession` | `_SKIP_CELL_TYPES = {"VECTOR"}` (`server.py:737`) is now redundant; the watcher sees no update for these writes |
| 5 | FB.5b / FB.5c `glia embed` (`cec1e38d`, `79395f1e`) | new `glia embed <repo> [--model bge-small\|test-hash] [--recipe t1\|t2] [--replace] [--limit <n>] [--check] [--json]` (exit 0; 1 under `--check` when nodes need embedding; 2 on an error) and `glia_py.embed(repo_path, model="bge-small", recipe=None, replace=False, limit=None, check=False)` -> `{repo, model, recipe, dims, nodes, cached, reused, embedded, ambiguous, deferred, stale_dropped, foreign_kept, rows_written, ms}`, a `ValueError` on failure. A snapshot step: it writes `.glia/vectors.jsonl`, never runs inside a build | optional (section 5.1) |
| 6 | FB.7a the default recipe (`77141f1a`) | `DEFAULT_RECIPE` t1 -> **t2**: an embed with no recipe writes t2 rows, an existing t1 sidecar re-embeds in full, and under t2 a function edit re-embeds its MODULE too (its text holds the file) | with row 5 |
| 7 | FB.14 GPU embeddings (`a4975faf`) | vectors.jsonl rows gain optional `device` (`cpu` / `webgpu` / `cuda`; absent = cpu; never decides freshness); fastembed 4.9.1 -> 6.0.0 / ort rc.9 -> rc.13 moves CPU vectors at most ~3e-7 (rankings unchanged); GPU by default, `GLIA_EMBED_DEVICE` | section 1 (the wheel) |
| 8 | FB.7b the fused find --files (`9626e53f`) | with fresh t2 vectors of the surface model in `.glia/vectors.jsonl`, `find --files` / `PyGraph.find_files` rank by `LX[IDR,FUSE[T1s,SEMp:t2]]` (was `LX[IDR,T1s]`): rows may carry `sem`, the CLI table gains a `sem` column; `glia find --no-semantic` (requires `--files`); `GLIA_EMBED_MODEL` (`bge-small` \| `test-hash`) picks which model's vectors are read | optional adoption (section 5.2) |
| 9 | FB.7b (`9626e53f`) | `PyGraph.find_files(query, top_k=20)` -> `(query, top_k=20, semantic=None)` (None auto, True on, False off); under `semantic=True` with no vectors a fallback `selection.reason` reads `no_vectors` | appended last: nothing binds differently |
| 10 | FB.7d calibration measures the blend (`bb7be623`) | `history_calibrate(.., sets=None)` -> `(.., sets=None, semantic=None)`; `glia history calibrate --no-semantic`. A repo with vectors records a **13-candidate SELf2t row** that `find_files` reads only with vectors (and a record written without vectors is read only without: reason `candidate_set`). **Recalibrate after `glia embed`** | optional (section 5.1) |
| 11 | FB.8 pack's semantic fallback (`a8512f91`) | `PyGraph.pack(.., cochange=True)` -> `(.., cochange=True, semantic=None)`; `glia pack --no-semantic`; when the query names nothing and the repo holds fresh t2 vectors, the pack seeds from them: `PackedNode.similarity` and `Pack.seed_absence` (both absent when None), `[pack] .. seeds_from=find\|semantic\|ids\|none`. **A non-empty pack is no longer proof of a name match** (read `seed_absence`) | no pack tool today |
| 12 | FB.11 notes in pack (`e6999de7`) | pack / dense ladder text: a node with DECISION / CONV entries gains `note[<source>/<id>, <tier>]: <text>` lines (at most 3, then `(+k more notes)`); `PackedNode.notes` (absent when 0); `[pack] .. notes=<n>`; `glia cell ls --check --rekey` skips a rekeyed row whose id has a `<ns>:` prefix unless `--writer <ns>` names it | no pack tool |
| 13 | FB.12a `[[convention]]` (`abeef44d`) | overlay `[[convention]]` loads (a 0.5.3 glia ignored such a file whole); a CONV entry may carry `kind: "convention"` (needs a `scope`); **a CONV entry with any other `kind` is refused** by `glia cell set`, the cells.jsonl stage and pyo3 `write_cell` / `set_cell`; stderr `[declared] .. note=<n> convention=<v> anchored=..`, `[overlay] loaded (..) .. convention=<n>` | the wrapper writes no cells |
| 14 | FB.12b conventions in answers (`d88bce65`) | `pack` / `review_vs_rev` dicts gain `conventions` (absent when empty); pack text `## conventions`, review markdown `### Conventions`; `[pack] .. conventions=`, `[review] conventions=<n>` | no pack / review tool |
| 15 | FB.13b `glia vocab sync` (`122f93b4`) | new `glia vocab sync <REPO> [--rev <REV>] [--json]` (exit 0 / 1) and `glia_py.vocab_sync(repo_path, rev=None)` -> `{rev, files, tokens, common, skipped_binary, skipped_large, ms}`, writing `.glia/vocab-snapshot/` | optional (section 5.3) |
| 16 | FB.13c named but not modelled (`080dfb0d`) | with a vocab snapshot, `find`'s `no_match` absence gains `named_in` [{token, occurrences, files (<= 5), file_count, common}] and its note "`X` occurs in <k> tracked file(s) (..) but no node is named X"; gaps gains category `named_not_modelled` (kind `identifier`, tier `fact`; CATEGORIES 13 -> 14, `glia gaps --category`, `glia overlay propose --category`) | `_render_absence` prints the note as is; no gaps tool |
| 17 | FD.7b implementors tiers (`5704f581`) | implementors rows' `tier` lowercase and read from evidence; C# / Java heritage rows now read `heuristic` (a name-only `global_unique` binding) | no implementors tool |
| 18 | FD.7d one tier spelling (`fb975599`) | every answer's `absence.tier` `"FACT"` -> `"fact"`; feature-flow `data_sources[].tier` and the `flows.yaml` `glia flows --features --out` writes `fact` / `heuristic`. CLI markdown (`> FACT:`) unchanged | **TL;DR item 2** |
| 19 | FD.7a / FD.7c (`8a0405dc`, `278d8734`) | Rust API only: `IdentityTier` -> `glia_activation::profile::Tier`; per-module tier consts removed | none (pyo3 words unchanged) |
| 20 | FH.8 compact answers (`f92a1ad1`) | `blast_radius` / `diff_impact` / `diff_impact_vs_rev` / review's impact: rows cut, `truncated` = {results, seeds} (absent when nothing was cut), `full=True` / `--full` keeps every row; null / empty / default fields left out of the JSON and the dicts (`unresolved`, `files`, `absence`, a row's `file` / `line`, a seed's `query` when it equals `qname`, `linked_seeds`; DiffImpact's `base`, `edges_added`, `edges_removed`, `unresolved_diff_files`; a changed row's `file` / `line`, `seed` when false). A cut table ends `_(<shown> of <total> rows; --full lists every row)_` | `server.py:508-509` already read `seeds` / `unresolved` with `.get(..) or []`; **TL;DR item 1** |
| 21 | FH.8b (`0f6ce15d`) | in a capped answer a seed's `identity.also_in` beyond 3 is cut to 3 plus `also_in_count`; diff-impact / review `changed` rows whose seed is shown become `{id, change}`; `files` rows omit `cochange` unless co-change ranked and `ppr` / `depth` when null; `review_vs_rev(.., full=False)` | `_identity_note` reads `also_in` (shows 3); read `also_in_count` for the rest |
| 22 | FH.8c the overview answer (`ad730731`) | `--top-k` default 200 -> **25** (`top_k=None` = 25); review `--max-impact` / `max_impact=` 50 -> 25; seeds and `changed` capped at 25 (`changed_truncated`); compact answers gain `areas` [{area, rows, files, top_file, scope}] (the 10 largest) and `truncated.{offset, areas, next{scope, offset}}`; compact rows: `seed` -> `seed_index` (a row whose seed was cut keeps `seed`), `name` absent when it repeats the qname tail, `score` to 4 significant digits; `--offset` / `offset=0` (last keyword; a `ValueError` with `full=True`); review `### Impact areas`; Rust `DEFAULT_ANSWER_ROWS` removed (`DEFAULT_OVERVIEW_ROWS`) | **TL;DR item 1**; page with `offset=`, drill down with `scope=areas[i].scope` |
| 23 | FH.8d review's caps (`7c64bb7a`) | review `name_breaks` cut to 25 (`name_breaks_truncated`, absent when 0; `counts.name_breaks` uncut); tests `--max-tests` / `max_tests=` 50 -> 25; a folded name row's `at` cell renders `<N> sites in <M> files (e.g. a, b, c)`; `[answer-size] surface=review .. names= names_shown= tests_shown=` | no review tool; pass `full=True` for every row |
| 24 | FH.9 answers say when they are blind (`7fa70727`) | `blind: [{tier:"fact", mechanism, verdict:"BLIND"\|"DEGRADED", reason, measure}]` on contract-breaks, review, diff-impact, blast-radius (FH.8b), trace answers, each entry flow, gaps and serves, absent when every mechanism is OK; review markdown `blind: http (clients paired 7% of 14)`; stderr `[blind] ..` | optional: render it in `impact` / `trace` (section 5.4) |
| 25 | FH.2b / FH.26 `glia health` (`e9bd5bf2`, `1cf4bcd9`) | new `glia health <repo> [--with ..] [--json]` and `PyGraph.health()` -> `{repos, role, role_basis, verdict, reason, mechanisms, parse, workspace_unresolved, suspicious, dead}`; since FH.26 `producers` / `client_reach` leave ORIGIN `test_fixture` producers out and each mechanism row gains `test_site_producers` (after `external_producers`; table column `test sites`) | optional for `orient` (section 5.4) |
| 26 | FH.7b / FH.7d / FH.24 contract-breaks names (`7e6902a8`, `90fb4d55`, `c1f603d0`) | contract-breaks JSON gains `names` (NameBreak rows, absent when empty); a shared-schema change across N operations is one schema row with `operations` (`breaking` still counts each); `advisory` counts non-blocking name rows; `--models-min-tier` / `models_min_tier=` accepts `heuristic` (name rows block); review gains `name_breaks`, `counts.name_breaks`, `### Name breaks (advisory)`. FH.7d: a generic or over-cap name is one aggregate row, position `folded`, keys `folded` (`generic` \| `cap`), `client_sites`, `client_files`, `sample_files`: one row stands for N sites. FH.24: `orphaned_clients` rows may carry category `EVENT_FLOWS` (a stale EVM event subscription) and a review can newly exit 1 on one | no contract-breaks / review tool |
| 27 | FD.25 contract-breaks through `git mv` (`193ad8f4`) | a spec moved with `git mv` is one `moved` row (or nothing), not a false removed + added pair; stderr `[contract-breaks] moved_files=<n> paired_ops=<n>` | none |
| 28 | FD.27 rotted rules (`b2d889f6`) | gaps may gain `rotted_rule` rows (`rule: no violation output (..)`); check stderr `[check] transitive edge_levels=<e> rules=<r>`; a reflexion evaluation over budget is a check error `reflexion: rule evaluation stopped ..` | none |
| 29 | FD.69 one rule-violation renderer (`444a68fa`) | `glia check` markdown: `_violation k: ..` / `_path k into ..` -> `_subject: <subj> - tier <t> at <file:line>_`, unindented warning lines (`⚠ <cat> (<lang>): ..`), `|---|` alignment, `_(<shown> of <total> caveats)_`; review unchanged | a script parsing check markdown reads `_subject:` lines |
| 30 | FA.22 / FA.23 org routing (`31385a5d`, `3df0ee91`) | multi-repo builds and layout merges gain cross-repo IMPORTS (rule `org_import`, npm / Go / cargo / pypi) and CALLS / USES / INJECTS / HANDLED_BY (rules `org_call` / `org_ref`), Medium (derived), stamped `resolver:org_packages`; `[passes] domain=code resolve=18 post=9 finalize=2` (was 17). Cross-repo impact / trace / tests-for now follow them. npm PROJECT ORIGIN cells gain `entry` / `subpaths`; `glia coverage` gains a typescript / IMPORTS caveat row | single-repo: nothing; with `--with` repos `impact` crosses repos |
| 31 | FE.7 the skills move (`1d17d689`) | glia owns `skills/glia-{orient,find,debug,impact,trace,init}` (renamed from `repo-graph-<verb>`), plus `glia` and `glia-overlay`. Ruling FE-2: the copies follow glia's LICENSE, James permits repo-graph's plugin to ship them, no notice is written into repo-graph | **TL;DR item 3**: replace `skills/` and `claude-plugin/skills/`, `tests/test_skills.py`, the Makefile `skills` target (`Makefile:32-34`) and the README skill list; `/repo-graph:repo-graph-<verb>` -> `glia-<verb>` |
| 32 | FH.23 `abi_partial` (`871bf428`) | resolver:evm edges gain EVIDENCE rule `abi_partial` (heuristic, Weak; advisory in check / contract-breaks), `[evm-link] .. abi_partial= stale_entries=` | a why / tier mapping that lists evm rules adds it as heuristic |
| 33 | FD.22 checkout-independent ties (`e43ea02a`) | on a tie, seed resolution (`pick_primary`), find's exact tier, overlay binding, declared anchors, cochange ties and test-report picks follow (qname, kind, graph index), never NodeId: an answer on a tie may name the other candidate once | none |
| 34 | FD.23b help text (`f4f7f939`) | `glia contracts --help` for `--fields` names `graphql_selection`; several help strings wrap `<placeholder>` in backticks | none (help prose only) |

## 3. The 0.5.3 handoff, carried forward

`dev-notes/repo-graph-handoff-0.5.3.md` (ranking: co-change first, calibrated selection, `find_files`,
`history_sync` messages) was never applied. Apply it with this one; its sections stand as follows.

| 0.5.3 section | at 0.5.4 |
|---|---|
| 0 TL;DR | **superseded**: the wrapper no longer runs on the new glia without a code change (TL;DR above). Its items 1-3 (rows can reorder on a repo with a history snapshot, `files` / `selection` keys, the ranking cache's memory) stand |
| 1 The pin | superseded by section 1 here. Its mixed-version notes stand (history snapshot v2, overlay `[ids]`, the BUILD_STAMP-bound calibration record) |
| 2 rows 1, 4, 6 (blast radius ranked, kwargs, selection) | stand, amended by rows 20-22 here: `files` and `selection` are left out when empty / null, the row cap is 25, and `blast_radius` / `diff_impact` / `diff_impact_vs_rev` end `.., top_files=10, full=False, offset=0` |
| 2 rows 2, 7 (pack) | stand, amended by rows 11, 12, 14 here (`semantic=`, notes, conventions) |
| 2 rows 10, 11 (review intent) | stand, amended by rows 22-23 (`review_vs_rev(.., title=None, full=False, offset=0)`, `max_tests` / `max_impact` 25, `intent.files` cut at `max_impact`) |
| 2 rows 12-14 (`find_files`, SELf2t, `history_calibrate`) | stand, amended by rows 8-10 (`semantic=`, `sem`, the 13-candidate SELf2t row, `no_vectors`) |
| 2 rows 3, 5, 8, 9 | stand unchanged |
| 3 What the answers show differently | stands; its "no graph content change" (3.4) is 0.5.3's only: 0.5.4 changes content (section 4 here) |
| 4 New primitives (history sync + calibrate on refresh, `find_files`, review title, render `files` / `selection`) | stands; section 5 here adds to it |
| 5 Needs no change, 6 Re-test | superseded by sections 6-7 here |
| 7 Done vs pending, 8, 9 | superseded by section 8; the 0.5.3 release record (the rank gate) stands, extended in section 9 |

## 4. Graph content (no code change; answers change)

The 0.5.4 precision group (the edge-precision audit `bench/edge-audit/`, FD.2-FD.3d, judged 503 samples on
glia and four public repos; its under-floor clusters became FD.73-FD.81) and the self-graph hygiene (FD.4a-FD.6, the
zero-phantom gate `engine/tests/self_scan.rs`) remove phantom nodes and edges; the TH track adds what real
repos showed missing. Nothing is renamed by hand: a removed node's qname simply stops appearing. Per area:

| area | removed (precision) | added or moved |
|---|---|---|
| every language | DOCUMENTS (pass:doclink) from a lone-word, registry-name or placeholder mention, or to a test / bench candidate from a doc outside its tree (FD.79 `d22aeaad`; glia's own tree 830 -> 344 edges); every node under an in-repo directory symlink, a second link to an already-walked outside directory or a link cycle (FD.78 `43cb576d`, **qnames change**: the same files are read once at the target's path; `[walk] symlinks ..`); ACCESSES_DATA and the DATA_SOURCE / DATABASE / CACHE nodes only they reached, read from a JNI type descriptor or a needle running on into a longer word such as `Redistribution` (FD.73 `98e0dfd8`; a Java / Kotlin Redisson row added); DATA_ENTITY / ACCESSES_DATA from a statement literal that is file-write content, a `query_gql` argument or a Rust `tests/` / `benches/` file (FD.74 `e00d1263`); gRPC GRPC_SERVER -HANDLED_BY-> the bootstrap function holding the registration (FD.80 `836d5170`) | an ambiguous doc mention binds the copy under the doc's own project root (FD.79); gRPC registrations reach the handlers they name (rule `register_impl` for a Go impl in another file, FD.80); a ROUTE / ENDPOINT tie may name the other candidate once (FD.22) |
| Rust, Python | CRON_JOB from k8s text outside yaml / json and from non-schedule Celery `"schedule":` values, CLI_INVOCATION from literals and comments (FD.4a `784193cf`); DATA_ENTITY from a SQL / Cypher literal that is not a call argument (const / let / field / list), from nested literals, comments, migration-DSL needles in literals (FD.4b `056f6843`); Rust ROUTEs read from literals or comments (FD.4c `9888e2b8`); statement literals in Rust `#[cfg(test)]` / test items, string-embedded GraphQL literals, Rust data-source needles that are not paths (FD.6 `9298185e`); READS_CONFIG for `os.environ[..] = v` / `del` (FD.75 `e7ddaee7`) | |
| Ruby, PHP, Dart, Elixir | nodes read from comments and non-interpolated strings (FD.5a `bb9e08d7`) | |
| Go, TS / JS, Java, Kotlin, Scala, C#, Swift, C / C++ | nodes read from comments and non-interpolated strings; `clap::Command::new` is no CLI_INVOCATION (FD.5b `76c74d49`) | |
| WebSocket | `ws_client:ws` from a bare `io(` in a file binding its own `io`; a non-Ratchet `->route(` WS_HANDLER (FD.4d `53cc6574`) | a Ratchet double-quoted path **re-keys** `ws:/ws/$x` -> `ws:/ws/{x}` (FD.4d) |
| Go | implicit IMPLEMENTS between a type and an interface in different go.mod modules (FD.81 `ebf41c7b`; microservices-demo IMPLEMENTS 501 -> 333; `[iface] .. cross_module=`) | |
| TS / JS, Python, Go HTTP | data: / blob: / mailto: / javascript: URL endpoints (FH.4a `0a4bc52c`); phantom inferred wrappers (FH.17 `f3829dba`) | ENDPOINTs from any call with a path-shaped URL and a method (rule `call_shape`, FH.4a); inferred in-repo HTTP wrappers: ORIGIN `inferred:wrapper`, EVIDENCE `pass:inferred_wrapper` rule `wrapper_call` (FH.4b `6dee2449`, FH.17b `02798199`); a test-file wrapper site is ORIGIN `test_fixture` (keys `rule` / `def`) and its ENDPOINT_HIT ends `"test_site":true`, read like `"external":true` (FH.17) |
| HTTP pairing | a host-less client onto a gRPC service's lone HTTP route (FH.14 `07b09f6c`) or another project's catch-all route (FH.14b `f046fceb`) | those clients read `unpaired_endpoint` in gaps |
| TS / NestJS | | enum / const route prefixes fold (FH.3 `478d7bec`); `@nestjs/swagger` op keys under a symbolic prefix **re-key** to the folded path (FH.3b `c7236c39`); decorated handlers get HANDLED_BY (FH.19 `a2c737b0`); workspace-package imports bind (rule `workspace_package`, FH.5 `bdfc4948`); webpack / vite / vitest aliases bind (FH.16 `2fef09fa`, FH.16b `0ef6d8b1`); object-shaped type aliases are INTERFACE nodes with SCHEMA_FIELDS (FH.20 `896c3bed`); `process.env.X = v` / `delete` read nothing (FD.75) |
| Vue, Svelte, Astro | | Vue POSITION lines move to the file's real rows when the first `<script>` does not open the file, a second `<script>` block yields nodes, `.svelte` / `.astro` are parsed (lang tag `vue`) (FH.6 `312d1e00`) |
| Java | Javalin / Ktor / WebFlux ROUTEs in a file importing none of them (FH.15 `362018a5`) | |
| JVM, Dart, Elixir, .NET manifests | | `package:maven:<g>:<a>`, `package:pub:<n>`, `package:hex:<n>`, `package:nuget:<n>` PACKAGE_DEP nodes; synthetic MODULEs `<dir>::pom.xml`, `<dir>::build.gradle(.kts)`, `<dir>::<Name>.csproj`; identity classes over them (FD.31 `0f599ac3`; **new node ids**, nothing removed) |
| Cargo, Poetry | PACKAGE_DEP / DEPENDS_ON from array-of-tables keys (`package:cargo:name`, `package:pypi:url` ..) (FD.77 `6542bb7a`; `[packages] eco=cargo\|pypi .. array_tables=`) | |
| YAML config | CONFIG_KEY `config:env:<k>` and DEFINES_CONFIG from an `environment:` block in a pubspec.yaml, a `.github/workflows/*.y(a)ml` or a `.gitlab-ci.yml` (FD.76 `834bee60`; `[config] yaml environment not_env=<kind> keys=<n> path=<p>` (kind `pubspec`, `gha_workflow` or `gitlab_ci`)) | compose / serverless unchanged |
| Vault | `config:secret:vault/<path>` from a generic `.read(` / `.kv(` in a file naming no Vault client (FD.75) | |
| Solidity / EVM | | `abi_partial` pairs (FH.23, row 32) |
| `[[decision]]` overlay | | a sub-scoped decision with no `anchor` anchors on the deepest enclosing PROJECT, else the least-qname MODULE (was dropped) (FD.65 `bf325da4`) |

The audit's report is `dev-notes/edge-precision-0.5.4.md`.

## 5. New primitives worth adopting (all optional)

### 5.1 Embeddings, then recalibrate

```
glia_py.embed(repo)                 # writes .glia/vectors.jsonl (t2, GPU if present, else CPU)
glia_py.history_sync(repo)          # 0.5.3: .glia/history-snapshot/ with messages
glia_py.history_calibrate(repo)     # records the 13-candidate SELf2t row when vectors exist
# then a NEW PyGraph
```

Embedding is a snapshot step: run it in the background, never on an MCP request path (FB.5b measured a
full bge-small CPU embed of glia's 36,133 nodes at 37:43 wall and 10.2 GiB RSS before FB.14's GPU path).
After an embed, recalibrate (row 10), or `find_files` falls back with reason `candidate_set`.

### 5.2 `find_files` as the text-to-files tool, now fused

The 0.5.3 handoff's section 4.2 stands; with vectors the order is the fusion the gate passed
(`dev-notes/fusion-gate-0.5.4.md`, `VERDICT: PASS`, R1 8/9, R2 8/9). The semantic tier **alone** failed its
gate (`dev-notes/embedding-gate-0.5.4.md`, `VERDICT: FAIL`): similarity ranks only inside the fused
`find --files` and as pack's fallback seeds, never in `find`, never seeding blast radius.

### 5.3 `vocab_sync` before `find`

`glia_py.vocab_sync(repo)` writes the identifier vocabulary; `find`'s empty answer then says where the
query's identifier occurs though no node carries it (`named_in`, row 16), which `_render_absence` can show.

### 5.4 `health` in `orient`, `blind` in answers

`PyGraph.health()` (row 25) says per mechanism whether the graph can see it (BLIND / DEGRADED / OK) and the
repo's role; `orient`'s blind-spot footer (`coverage()`, `server.py:1143`) can add it. `blind` (row 24) on a
`blast_radius` / `cross_stack_trace` / `entry_flows` answer is the same caveat per answer.

### 5.5 The zero-install CLI and the use-signal proposal

- `uvx --from glia-cli glia <cmd>` runs the `glia` binary from PyPI (FE.5 `ef8fefa9`, FE.6 `78a5af40`;
  `.github/workflows/wheels-cli.yml`). Published only once James adds the PyPI pending publisher and
  confirms the name `glia-cli`; the six skills already name it in their Transports section.
- `dev-notes/use-signal-registered-test-0.5.4.md` (FE.8 `4a3e94d5`): a joint proposal for a registered
  test of a use signal. Sending it is James's call; nothing is registered until repo-graph acknowledges.

### 5.6 Not in 0.5.4

The goal layer (`goal_why`, the clarification queue as an MCP conversation), `find --flows` / concept
flows, `gh sync`, `review --pr` and placement did not ship (ruling OPTION-3). Their slots are empty and
have no pyo3 or CLI surface; there is nothing to adopt until 0.5.5.

## 6. Needs no change (checked)

- `find` (`graph.py:155`): rows unchanged; the absence may carry `named_in` (row 16) and lowercase `tier`
  (row 18).
- `cross_stack_trace` (`server.py:587`, `:676`) and `entry_flows` (`graph.py:69`): gain `blind` only (absent
  when every mechanism is OK); a trace hop's shape is unchanged.
- `activate`, `resolve`, `node_cells`, `governing_docs`, `coverage`, `bfs` / `predecessors` /
  `shortest_path`, the counts, `generate`, `load_from_gmap`, `default_gmap_dir`, `version`, `WatchSession`
  / `poll` / `snapshot` / `persist`: no signature or shape change (`py/api_surface/` diff, section 2).
- The registries: decoded by name (row 1).
- The watcher: vectors and vocab writes no longer wake it (row 4); no other watch change shipped (T8 did
  not ship).
- Engine-internal packets with no wrapper-visible effect: F0.3-F0.5, F0.7, FB.1, FB.4, FB.5a, FB.6,
  FB.6b, FB.7c, FB.13a, FB.13d, FD.2, FD.3a-FD.3d, FD.23a, FD.24, FD.28, FD.34, FD.34b, FE.1-FE.4,
  FH.1a-FH.1d, FH.2a, FH.7a, FH.7c, FH.10-FH.13b, FH.18, FH.21, FH.22, FH.25.

## 7. Re-test

```
pip install glia-py==0.5.4        # after the publish; or the leap wheel before it
python -c "import glia_py; print(glia_py.build_stamp())"
pytest tests/
```

- `tests/test_mcp_tools.py:206` fails until it reads lowercase tiers (TL;DR item 2); grep `tests/` for
  `FACT` (also `tests/test_mcp_e2e.py:143`, a comment).
- An `impact` test that counts rows or reads `name` moves with TL;DR item 1; with `full=True` the dict is the
  0.5.3 shape, plus `blind` when a mechanism is BLIND / DEGRADED.
- `tests/test_skills.py` against the copied `glia-*` skills (TL;DR item 3).
- `read` on a Python script MODULE shows `entry point: <file>:<row> (__main__ guard)`; an EVM client
  `dials: contract via ethers, ABI .. (evm)`.

## 8. Done vs pending

- **Done, glia:** W0-W26, each close-out green (`cargo test --workspace` 7050 passing at W26; substrate
  bench 458 fixtures, blind 0; matrix 346/482; `[engram-export] check: ok`; `[rank-gate] check: ok` at
  the waves touching a ranked path).
- **Pending, James:** the 0.5.3 -> 0.5.4 bump, the `v0.5.4` tag, the `glia-py` 0.5.4 publish; the PyPI
  pending publisher and name for `glia-cli` (FE.5, FE.6); whether to send the use-signal proposal (FE.8).
- **Pending, repo-graph:** commit the 0.5.2 port; then sections 0-2 (pin, `impact` rows, the tier test,
  the skills) and optionally section 5 and the 0.5.3 handoff's section 4.
- **Done in repo-graph's working tree, uncommitted (the 0.5.2 waves' wrapper fixes, routed by DT.13 /
  DT.1p and DT.14):** `_dial_text` returns None for an HTTP call-site payload with `method` and renders
  `via=evm` hits by library / ABI; `_cell_text` renders SCHEMA_FIELDS as `name: type` pairs; a `main_guard`
  ENTRYPOINT is labelled `entry point`, not `declared entry point`. Nothing left open there.
- **Followups the landed packets named for repo-graph:** F0.1 (the four names), F0.6 (one recalibration),
  FA.21 (IMPORT_BINDINGS), FA.22 / FA.23 (cross-repo edges, `resolve=18`), FB.2, FB.3, FB.5b / FB.5c,
  FB.7a, FB.7b, FB.7d, FB.8, FB.11, FB.12a, FB.12b, FB.13b, FB.13c, FB.14, FD.7b, FD.7d, FD.25, FD.27,
  FD.69, FE.7, FE.8, FH.2b, FH.7b, FH.7d, FH.8-FH.8d, FH.9, FH.17, FH.23, FH.24, FH.26: all in sections
  1-5. The graph-content packets (FD.4a-FD.6, FD.31, FD.73-FD.81, FH.3b, FH.4a, FH.4b, FH.6, FH.14b, FH.15)
  are section 4.
- **Open, not repo-graph's:** FH.13b's g054 reading rule waits on FH.13's measured agent run (ruling FE-3's
  setup-token); FE.4's live agent run has not run.

## 9. Engram, neuropil and the release record

Engram: `dev-notes/engram-handoff-0.5.4.md` (vectors, vocab and corrections contracts). neuropil:
`dev-notes/neuropil-handoff-0.5.4.md` (0.5.1 -> 0.5.4, a compile check with `new=0`).

The 0.5.4 release record, no wrapper change: the rank gate (`bash scripts/rank-gate.sh check`) now
measures the fused `find --files` (bench/rank-gate/README.md, "The fused find (FB.7c)"; the marker
`[rank-parity] label=<l> shape=find ranking=LX[IDR,FUSE[T1s,SEMp:t2]] queries=<q> key_mismatch=0
order_mismatch=0`); it builds `rank_eval` with `--features sem-eval` plus the `glia-embed-worker`
(`gpu-webgpu`) and keeps `~/.cache/glia/fastembed` and `$GLIA_RANK_GATE_DIR/sem` between runs. FD.79's
doclink precision costs glia's own snapshot ANS:impact r10 0.2594 -> 0.2550, accepted by James
(2026-10-30, recorded in `bench/rank-gate/gate.json` `accepted`). FH.1d: the release's full cohort run reads
review with `--full`, so `files_named` / `truth_named` may rise against the baseline (gains). Integration
tests run as one binary per crate (FH.18): `cargo test -p <pkg> --test <crate>_tests <file>::`.

## Release-docs addendum (FZ.1, 1ac10500)

- README.md is install / quickstart / CLI only. The long prose moved to docs/overview.md, the release history to docs/history.md and the license rationale to docs/license.md. A link into an old README section now points at one of those files.
- PARSER_STAMP moves once more: FZ.1 gave the 16 reserved slot files a `//!` line in hashed roots, so every parse cache re-parses once after the upgrade. No graph content changes.
