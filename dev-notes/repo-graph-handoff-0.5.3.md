# repo-graph handoff - glia 0.5.3, the ranking release (0.5.2 -> 0.5.3)

**Status: written at glia HEAD `5639697b` (the W15 close-out), before the bump.** glia 0.5.3 is complete
on glia's local `main` but not tagged: the version bump, the `v0.5.3` tag and the `glia-py` 0.5.3 publish
are James's release steps after these docs. Every pin below is the pin to take **once James tags
`v0.5.3`**. Until then a wheel built from `main` reports `0.5.2+p<stamp>` from `glia_py.build_stamp()`
(the W15 leap wheel reads `0.5.2+pd640454f26e4ce00`).

The sixth glia -> repo-graph handoff, after `repo-graph-handoff-0.5.2.md`. 0.5.3 is the ranking
release: 43 packets in `dev-notes/leap-053-packets.json` (plan: `dev-notes/next-leap-0.5.3.md`,
evidence `dev-notes/ranking-scoreboard.md`), waves W0-W16 since `v0.5.2` (`9837b1ff`). Each ranking
packet ports a mechanism that the 2026-10-18..19 experiments measured in
`engine/examples/rank_eval.rs` into a shipped answer. Groups: EA structural ranking (a held PPR index,
the candidate file space, co-change first, PPR d0.85 + sum pooling, BFS; in blast radius,
diff-impact, review and pack), EB intent (commit messages in the history snapshot, BM25 over them, the
`[ids]` vocabulary, typed id routing, `review --title`, `find --files`), EC per-repo calibrated
selection (`.glia/calibration-snapshot/`, `glia history calibrate`, the selection in every ranked
answer), EG the rank gate, the DE.5 removal and the wheels CI fix, EZ these docs. Breaks were allowed
when a packet declared them, and **consumers pin the release exactly**.

Sources, in order of authority:
- the landed code at glia HEAD `5639697b` and the pyo3 / CLI surface snapshots, diffed
  `v0.5.2..HEAD -- py/api_surface/ cli/surface/` (section 2 lists that diff, row by row);
- each packet's landed commit body (its `Declared breaks` paragraph). Where a body differs from its
  spec, the body wins;
- the routed handoff paragraphs in `dev-notes/leap-053-corrections.json` (EZ.2's entry);
- this packet's own measurements on a clone of glia at `5639697b` under `~/.cache/glia-EZ.2/` (deleted
  afterwards), with the W15 leap wheel (`~/.venvs/glia-leap`, build `0.5.2+pd640454f26e4ce00`): marked
  "measured here".

Every wrapper `file:line` was read read-only in repo-graph's working tree: HEAD `0f8ecfa` plus the
uncommitted 0.5.2 port (18 modified, 5 untracked paths: `pyproject.toml:31` already pins
`glia-py==0.5.2`, the watcher holds a `WatchSession`). `server.py`, `graph.py` live in `repo_graph/`.
Packet ids are glossed in words; the hash after an id is the glia commit that landed it.

---

## 0. TL;DR

**The wrapper runs on 0.5.3 without a code change.** Of the pyo3 calls it makes, only
`PyGraph.blast_radius` changed signature, and its three new keywords are LAST (`..., collapse=True,
ranking=None, cochange=True, top_files=10`), so `server.py:503`
`g.pygraph.blast_radius(names, dir_engine, depth, None, live_only)` binds as before. `find`
(`graph.py:155`), `cross_stack_trace`, `entry_flows`, `activate`, `resolve`, `node_cells`, the
traversal calls, `WatchSession` and its `poll` / `snapshot` / `persist` are unchanged in
`py/api_surface/`. No registry id, no `.gmap` format change (FORMAT_VERSION 3), no graph-content
change.

What changes under the wrapper:
1. **`impact` rows can reorder** on a repo that holds `.glia/history-snapshot/` (written by
   `glia history sync`): rows in files that historically change with the seeds' files come first
   (co-change first, "H10"), the rest keep their PPR order. Rows keep their `score`, so the `impact`
   output's score column is no longer always descending. With no snapshot the rows are byte-identical
   to 0.5.2 (section 3).
2. **The `blast_radius` dict gains two keys**: `files` (a ranked file list, after `results`) and
   `selection` (which ranking was used and why). The wrapper reads neither, so nothing breaks.
3. **Memory:** each live PyGraph holds a ranking cache: measured here +7 MB VmRSS on glia's own
   38k-node graph on the first ranked call (section 3.3).

What repo-graph can adopt (section 4, all optional):
1. `glia_py.history_sync(repo)` then `glia_py.history_calibrate(repo)` on the refresh path, then a
   **new** PyGraph: answers then use the repo's measured pick. A PyGraph (and every
   `WatchSession.snapshot()`) reads the calibration record once, so a graph opened before the
   calibration keeps the fallback (measured here, section 4.1).
2. `PyGraph.find_files(query, top_k=20)`: the files a free-text query (an issue title, a ticket id) is
   about. A candidate mode of `find`.
3. `review_vs_rev(..., title=...)`: the PR's intent, if the wrapper grows a review mode.
4. Render `files` / `selection` in `impact`; update its docstring ("Personalized-PageRank-ranked").

Bump order:
1. **glia (James):** `[workspace.package].version` (`Cargo.toml`), `py/pyproject.toml` and the excluded
   `engram-export/Cargo.toml` move 0.5.2 -> 0.5.3 in the release commit; James pushes, tags `v0.5.3`
   and lets `wheels-py.yml` publish `glia-py` 0.5.3.
2. **repo-graph:** pin `glia-py==0.5.3` (section 1), run section 6 against a local wheel, then
   release after glia-py 0.5.3 is on PyPI.

## 1. The pin

| file:line (working tree) | now | change to |
|---|---|---|
| `pyproject.toml:31` | `"glia-py==0.5.2",  # glia pins consumers exactly per release ...` | `"glia-py==0.5.3",` |
| `CLAUDE.md:28` | runtime deps `glia-py==0.5.2` | the same pin |
| `CLAUDE.md:82` | "consumes the published `glia-py` wheel (`==0.5.2`)" | `==0.5.3` |
| `CLAUDE.md:127-138` | "glia 0.5.2 boundary notes" | add a 0.5.3 boundary note from sections 2-4 |
| `CLAUDE.md:228` | "glia 0.5.3 follows with its own 0.5.2 -> 0.5.3 handoff" | point at this file |

**Mixed versions until both sides move.** Three 0.5.3 writes are unreadable to a 0.5.2 engine:
- `glia history sync` (0.5.3 CLI or `history_sync`) writes **history snapshot version 2** (EB.1,
  `3fbe3e8f`): `meta.json` gains `messages` / `messages_hash`, `messages.jsonl` appears. A 0.5.2
  reader rejects a v2 meta, so a 0.5.2 MCP build of that repo loses what it read from the snapshot
  (the history cells, ATTN and CO_CHANGES edges) until it moves to 0.5.3.
- `.glia/overlay.toml` with an `[ids]` table (EB.4, `44380ddc`): a 0.5.2 glia rejects the unknown
  table and **ignores the whole file** (entrypoints, wrappers, edges, constraints). glia's own repo
  commits one since `9612f68e` (EB.9).
- `.glia/calibration-snapshot/` is bound to the BUILD_STAMP that wrote it (ruling EC-2): any other
  glia build, older or newer, reads it as `rejected: build_stamp` and falls back. Recalibrate after
  every glia upgrade.

And, as at every release, PARSER_STAMP moved (every packet that edits an engine, activation,
code-domain or snapshots source), so the first `load_from_gmap` / `refresh` after the upgrade is a full
reparse, and a 0.5.2 `glia` CLI and a 0.5.3 MCP server rebuild each other's `.glia/graph/` on every
alternation. Reinstall the CLI from the `v0.5.3` tag with the wheel.

## 2. Breaks that reach the wrapper

Every row names the glia packet and commit, what changed (old -> new), and the wrapper site. None asks
for a code edit. The pyo3 surface diff `v0.5.2..HEAD -- py/api_surface/` is exactly rows 1, 4, 6, 7,
10, 11, 12 and 13's signature changes; `cli/surface/` moves for rows 5, 8, 10, 12 and 13.

| # | packet (commit) | old -> new | wrapper site and action |
|---|---|---|---|
| 1 | EA.5 blast radius, diff-impact and review ranked by the selected Ranking (`fe4f23b8`) | every `BlastRadius` (`PyGraph.blast_radius` / `diff_impact` dicts, `diff_impact_vs_rev`, review's impact) gains `files` after `results`: `[{rank, file, repo, cochange, ppr, depth, rows}]`, the first `top_files` (10) ranked files under `scope`, never the seed files, `[]` on an empty answer. With a history snapshot under the cache's repo roots, rows of co-changed files move first (H10), so order and the `top_k` cut change; without one rows are byte-identical to 0.5.2. stderr: `[rank] surface=<s> ranking=<H10|P1|..> seed_files=<s> cochange_files=<c> files=<f> lifted=<l> closure_index=<hit|built>` once per answer | `server.py:503` binds; `_rows(env)` reads `results` only. The rows of `impact` (the loop at `server.py:529`) can come in non-descending `score` order. **Optional:** render `env["files"]` (section 4.4) |
| 2 | EA.6 pack ranked co-change first (`d05b956c`), then **EA.6b pack lifts co-changed files, not their rows** (`c6a2179f`, ruling EA-2b) | with a history snapshot, `pack` / `pack_ids` order their candidates as **each co-changed file's best row (its first in the PPR order) first, in the H10 file order, then every other row in PPR order** (a co-changed file's later rows keep their PPR position); weights stay the PPR profile down the new order. Without a snapshot, or under `ranking="ppr"` with `cochange=False`, the pack is byte-identical to 0.5.2. The marker `[rank] surface=pack .. lifted=<l> lifted_files=<f> max_file_share=<m>/<k>` now means: `lifted` = lifted rows (one per lifted file), `lifted_files` = lifted rows inside the candidates cut, `max_file_share` = the most of the cut any one file holds (EA.6 had meant: the most any co-changed file took) | the wrapper calls no `pack` (grep of `repo_graph/`: 0 hits) |
| 3 | EA.7 PyGraph and WatchSession hold one RankCache (`32922d48`) | a PyGraph holds `rank: Arc<RankCache>` (holder `pygraph`) built from its repo roots and labels, and **reads `.glia/history-snapshot/` under them**: its default blast / diff-impact / pack order is co-change first (H10) where a snapshot exists, and `files` names repos by label (a PyGraph built before 0.5.3 had no roots: `repo#<n>`). It keeps at most 8 PPR indexes plus the file and co-change indexes for its lifetime. `WatchSession.snapshot()` shares the session's cache; a fresh one replaces it after every update that changed the graph (a noop keeps it). A bad `ranking=` string is a `ValueError` (`unknown ranking \`x\`: expected one of ppr, ppr-wide, bfs`) before any work. stderr: `[rank-cache] holder=pygraph source=<quotient|merged> .. index=hit\|built ..`, `[rank-files] ..`, `[rank-cochange] ..` | `_graph = RustGraph(_session.snapshot(), ...)` (`server.py:186`) shares the session's cache, so `impact` after an update rebuilds the indexes once (section 3.3). Memory: section 3.3 |
| 4 | EA.7 (`32922d48`) pyo3 keywords, defaults as moved by EC.8 / EC.9 | `PyGraph.blast_radius(.., collapse=True)` -> `(.., collapse=True, ranking=None, cochange=True, top_files=10)`; `PyGraph.diff_impact(.., scope=None)` and `diff_impact_vs_rev(.., scope=None)` -> `(.., scope=None, ranking=None, cochange=True, top_files=10)`; `review_vs_rev(.., models_min_tier="fact")` -> `(.., models_min_tier="fact", ranking=None, cochange=True, title=None)`; `PyGraph.pack` / `pack_ids(.., scope=None)` -> `(.., scope=None, ranking=None, cochange=True)`. `ranking` takes `ppr` / `ppr-wide` / `bfs`; `cochange=False` turns the co-change tier off | positional calls still bind (`server.py:503`) |
| 5 | EA.8 `--ranking` / `--no-cochange` / `--top-files` on the CLI (`33222db0`) | `glia blast-radius`, `diff-impact`, `review`, `pack` gain `--ranking ppr\|ppr-wide\|bfs` and `--no-cochange`; `blast-radius` / `diff-impact` gain `--top-files <N>` (10) and a **trailing `## files` markdown table** after the rows (rank, file, repo when the build holds several, rows, co-change, ppr; `depth` under bfs) | the wrapper runs no glia CLI. **A CI script that parses `blast-radius` / `diff-impact` markdown sees the new trailing `## files` section** (and EC.8's `ranking:` line, row 6) |
| 6 | EC.8 calibrated selection in blast_radius, diff_impact and review's impact (`096d114b`) | dicts and `--json` gain `selection` {`set`, `shape`, `pick`, `source`, `reason`, `test_commits`}: `set` SELh0 (co-change on) or SELs0 (`cochange=False`), `shape` k1 / k2 / k3 / half from the seeds' distinct files, `source` calibrated / fallback / explicit. **`ranking=None` (the new default) means calibrated**: the repo's `.glia/calibration-snapshot/` picks the ranking, falling back to H10 (P1 with `cochange=False`) with a `reason` (`not_loaded`, `absent`, `rejected:<why>`, `no_set`, `candidate_set`, `no_queries`, `refused`); a string is explicit. Markdown gains one `ranking: <pick> (<source>[: <reason>], shape <k>[, <t> commits])` line under the impact table. stderr: `[select] surface=<s> set=.. shape=.. pick=.. source=.. reason=.. test_commits=..`. Without a record rows are byte-identical to EA.5's | `server.py:503` passes no `ranking`, so `impact` is calibrated once the repo is (section 4.1). **Optional:** show `selection.pick` / `source` in the impact footer |
| 7 | EC.9 calibrated selection in pack / pack_ids (`6b3bfd59`), **taken out by EC.9b (ruling EC-9b, "Pack ignores calibration")** | `selection` in the dict (skipped on an empty pack), `ranking=None` default, `[select] surface=pack`. Since EC.9b pack **never reads the calibration record**: `ranking=None` is the default ranking (H10, co-change first), the order is the same on a calibrated repo and an uncalibrated one, and `history_calibrate` changes no pack. `selection.source` is `fallback` with `reason` `pack_uncalibrated` (`test_commits` 0) for the default ranking, `explicit` for any other; never `calibrated`. `PackArgs.select` (EC.9, unreleased) is gone | the wrapper has no pack tool yet; a future one gets `selection`; it need not calibrate for pack |
| 8 | EB.1 history sync keeps commit messages (`3fbe3e8f`) | `history_sync(.., blame_max_files=300)` -> `(.., blame_max_files=300, messages=True)`; the snapshot moves to **version 2** (`messages.jsonl` beside `commits.jsonl`, meta `messages` / `messages_hash`; a 0.5.2 reader rejects it, section 1); the summary dict gains, last, `messages`, `redacted`, `trailers_dropped`, `branch_labels`; the `[history] sync ..` marker gains `messages= redacted= branch_labels= trailers_dropped=` (or `messages=off`) before `surface=`. Messages pass the untrusted-text redaction, and trailer lines (author identities) are dropped. CLI: `glia history sync --no-messages` | the wrapper calls no `history_sync` today; section 4.1 |
| 9 | EB.4 the `[ids]` id vocabulary in `.glia/overlay.toml` (`44380ddc`) | a `[ids]` table (`patterns`, `local_words`, `markdown`, `[[ids.tracker]]`) is user config like `[walk]` (legal in overlay versions 1 and 2, applied under `--no-overlay`, no graph change); a file holding one was ignored whole before. The `[overlay] loaded ...` stderr line gains `ids=<n>` after `layer=<n>` | the server parses no stderr. Mixed versions: section 1 |
| 10 | EB.7 `review --title` (`378e79fb`) | `review_vs_rev(.., title=None)`, `glia review --title <TEXT>`. With a title, **or with no title when `<base>..HEAD` holds a commit** (the newest non-merge subject is the default title, ruling EB-2), the dict / `--json` gains a last key `intent` {`title`, `title_source` arg / commit / none, `fusion`, `ids`, `files`, `text`} and the markdown gains `### Intent` after the impact table; when a title id routes, impact rows in id-routed files move first by IDR and the rest keep their order; stderr gains `[review-intent] ..` and the intent markers (`[intent] text`, `[ids] vocab`, `[id-defs]`, `[id-ns]`, `[id-paths]`, `[idr]`) | the wrapper does not call review (grep: 0 hits) |
| 11 | EC.11 review's text selection SELt (`182de4f1`), then EC.12 review's set SELt2 (`6ae02bab`) | review gains a top-level `selection_intent` after `intent` (the same six keys as `selection`); `intent.files` order and `intent.fusion` follow the repo's calibrated **SELt2** pick (EC.12 replaced EC.11's SELt; uncalibrated: `LX[IDR,P1]`, EB.7's order); the markdown gains `_ranked by <pick> (calibrated on <t> commits, shape <k>)_` or `(uncalibrated: <reason>)` under `### Intent`; stderr `[select] surface=review_intent set=SELt2 ..`. A row the replay refused (its online pick scored below the fallback, ruling EC-3) answers `reason` **`refused`** (EC.12; was `candidate_set`). A record written before EC.12 answers `no_set` for review until recalibrated | review only |
| 12 | EB.8 `find --files` / `PyGraph.find_files` (`8f9074c2`) | new `PyGraph.find_files(query, top_k=20)` -> `{results, absence, selection}`; each row `{rank, file, idr, text, degree, ids}`, ordered by `LX[IDR,T1s]` (typed id routing of the query, then BM25 over past commit messages, then file degree). An empty answer is a FACT `no_match` absence whose note names the missing input (`no history messages (run glia history sync)` ..). More than one repo raises. CLI `glia find <repo> <query> --files` (conflicts with `--kind` / `--no-collapse` / `--scope`; `--with` exits 2) **exits 0 on an absence**, as `glia find` does. stderr `[find-files] repo=<l> surface=<cli\|py\|lib> fusion=<pick> ids=<n> idr_files=<i> text=<present\|absent> text_files=<t> rows=<r>`. `PyGraph.find` and default `glia find` unchanged | optional adoption, section 4.2 |
| 13 | EC.13 find --files' selection SELf2t (`8e5bba6c`) | `find_files`' order follows the repo's calibrated **SELf2t** pick (uncalibrated `LX[IDR,T1s]`, EB.8's order); the dict gains `selection` after `absence`; the CLI table ends `ranked by <pick> (calibrated on <t> commits \| fallback: <reason>)`; `[select] surface=find_files ..` | with row 12 |
| 14 | EC.6 `glia history calibrate` / `history_calibrate` (`d64c2d0b`), its default groups grown by EC.11 / EC.12 / EC.13 | new `glia_py.history_calibrate(repo_path, max_commits=300, max_seeds=5, sets=None)` -> dict `{dir, history_head, commits, test_commits, messages, ms, sets: [{set, shape, pick, last_online_pick, fallback, test_commits, queries, selection_recall10, fallback_recall10, delta_recall10, ci_low, ci_high}]}`, a `ValueError` on an error (no snapshot names `glia history sync`), the GIL released. Default groups `structure`, `review`, `find`: **13 rows, SELf2t find first**, then SELh0 / SELs0 / SELt2 on k1 / k2 / k3 / half. CLI `glia history calibrate <repo> [--max-commits] [--max-seeds] [--sets <group,..>] [--json]` (exit 0 written, 1 step error, 2 build error). stderr `[calibrate] done surface=<cli\|pyo3> sets=13 test_commits=<t> ms=<ms>`, one `[calibrate] set=..` line per row, one `[idr] replay ..` and one `[rank-cache] holder=calibrate summary lookups=.. built=.. hits=.. build_ms=..` line (EG.7, `b252607e`; was one line per lookup) | optional, section 4.1; nothing breaks if the wrapper never calls it (answers fall back) |

`review::intent_files_with`, `find::find_files_with` and `review::IntentHistory` (EG.7, `b252607e`) are
`#[doc(hidden)]` engine seams for the rank gate: unstable, not pyo3, never call them.
`CalibrateOptions.vocab` (EC.14, `369f748f`) is a new optional engine input (an `[ids]` vocabulary
override for the calibration replay), not exposed through pyo3.

## 3. What the answers show differently

### 3.1 Which ranking an answer uses

The default for blast radius, diff-impact, review's impact and pack is **co-change first** (H10:
the measured C0 co-change score over the history snapshot, then undirected PPR, rulings EA-5 + EC-7).
On top of it, except for pack (ruling EC-9b: pack's order is unchanged by calibration in 0.5.3; the
impact replay's pick lowered pack's recall@10 on every gate snapshot), the repo's calibration record may pick another member of the same set (SELh0 = H10,
H10[PT*] (co-change, then PPR at damping 0.85 with sum pooling), H10[B0] (co-change, then carry BFS
depth); or with `cochange=False` SELs0 = P1, PT*, B0). The pick is per seed shape (one seed file, two,
three, half the files). A pick whose replay recall@10 fell below the fallback's is refused (ruling
EC-3), so a calibrated repo never ranks worse than its fallback on its own history. Without
`.glia/history-snapshot/` there is no co-change, H10 equals P1, and the rows equal 0.5.2's.

### 3.2 Measured on glia's own repo (measured here)

A clone of glia at `5639697b`, `history_sync` (1274 commits, 1274 messages), then
`blast_radius(["radius"], "both", 4, 50, False, "engine/src/answers.rs")`:
`[rank] surface=blast_radius ranking=H10 seed_files=1 cochange_files=134 .. lifted=1188`,
`selection` `{set: SELh0, shape: k1, pick: H10, source: fallback, reason: absent}` before the
calibration and `source: calibrated, test_commits: 300` on a new PyGraph after it. The rank gate's
measured effect on the answers, per public snapshot, is in the round reports and
`bench/rank-gate/README.md`; e.g. ANS:impact MRR on the single-seed shape, 0.5.2 -> co-change first:
glia 0.3825 -> 0.4605, shell 0.5371 -> 0.6567, samples 0.3945 -> 0.4337 (EA.6b's gate proof).

### 3.3 Cost of the held ranking cache

- **Time** (measured here, same call): first ranked call 530.7 ms, then 207.4 / 192.0 ms on the same
  PyGraph (two PPR indexes built, 25.3 + 27.2 ms; `[rank-files]` 148.8 ms once; co-change read 31.7 ms).
  EA.7's own series on a 1231-commit clone: 561.7 ms call 1, 202.5 ms median of calls 2-20, a fresh
  PyGraph per call ~570 ms; every answer equal. Under `WatchSession` the first `impact` after each
  update pays the build again (the session swaps in a fresh cache).
- **Memory** (measured here): VmRSS 629 MB after the build -> 636 MB after the first ranked call
  (+7 MB: two PPR indexes of 263,444 incidences over ~38k nodes, the file index of 2,590 files, the
  co-change index of 32,900 pairs), flat over the next calls. EA.7 recorded no RSS; the spec's bound
  is at most 8 PPR indexes per PyGraph (an index per distinct PPR config).
- **Calibration** (measured here): `history_calibrate` on the same clone, default groups: 133.9 s
  wall, peak RSS 717 MB, 13 rows, 300 test commits. glia's own `.glia/overlay.toml` declares an
  `[ids]` vocabulary, so its review / find replays route ids (`[idr] replay .. routed=300
  resolved=245 .. ms=84600.9`); a repo with no `[ids]` table and no `{U}-{N}` / `T{N3}` ids is
  faster. EC.5 measured the structure group alone at 166 ms (websocket) and 437 ms (shell).

### 3.4 Graph content

No 0.5.3 packet changes what a build extracts or resolves: rankings are query-time and store nothing
in a `.gmap`. The substrate bench stayed at 419 fixtures, matrix 346/482 and blind 0 at every wave
close-out W0-W15, and the engine's `byte_identical` test stayed green. `orient` / `read` / `trace`
output is unchanged.

## 4. New primitives worth adopting

### 4.1 History sync and calibration on the refresh path

```
glia_py.history_sync(repo)          # writes .glia/history-snapshot/ (v2, with messages)
glia_py.history_calibrate(repo)     # writes .glia/calibration-snapshot/ (13 rows)
# then build or load a NEW PyGraph
```

- **A held graph does not see a new record.** A PyGraph reads the calibration record once, on its
  first ranked answer; `WatchSession.snapshot()` shares the session's cache, and the session drops
  `.glia/calibration-snapshot/` from its poll (EC.1), so writing a record triggers no update.
  Measured here: a PyGraph opened before the record answered `reason: absent` both before and after
  the record appeared; a new `load_from_gmap` answered `source: calibrated`. After calibrating, swap in
  a fresh graph: `refresh` builds a new PyGraph (`server.py:948`), and `refresh(full=true)` also
  re-opens the session (`server.py:957-961`); otherwise the record is read at the next update that
  changes the graph. A history sync, by contrast, writes a `.glia/` build input, so the
  session's next poll rebuilds and the new cache reads the new co-change.
- **Recalibrate after every glia upgrade** (the record is bound to the BUILD_STAMP, ruling EC-2) and
  after the snapshot moves far (the record records `history_head`).
- Both write into the repo's `.glia/`; `history-snapshot/` and `calibration-snapshot/` are per-user
  state, not inputs to commit (the wrapper's `ensure_cache_excluded` covers only `.glia/graph/`).
- The calibration takes minutes on a large history (section 3.3): run it in the background, never on
  an MCP request path.

### 4.2 `find_files` as the text-to-files tool

`PyGraph.find_files(query, top_k=20)` answers "which files is this about" for an issue title, a commit
subject or a ticket id: typed id routing (an id the repo's `[ids]` vocabulary or the defaults
`{U}-{N}` / `T{N3}` recognise, resolved through its markdown and tracker definitions to the files
they name), then BM25 over past commit messages. It needs `history_sync` (with messages) for the text
half; with neither signal it returns an absence whose note says what is missing. Measured here on the
glia clone: 0.85 s for a query naming a packet id (`ids=1 idr_files=9 text_files=87`). A candidate
`kind="files"` mode of the `find` tool, or a seed source for `impact`.

### 4.3 `review_vs_rev(title=...)`

If the wrapper adds a review mode: `title=` passes the PR title; with none, the newest commit subject
of `<base>..HEAD` is used. Render `intent.files` (each with its routed `ids`), `selection_intent` and
the `_ranked by .._` line.

### 4.4 Render what `impact` already receives

`env["files"]` is a short ranked file list (the files the change most likely touches, co-change
first), and `env["selection"]` says which ranking ordered the rows. Both are a few lines in the
`impact` footer. The `impact` docstring (`server.py:492`) says "Personalized-PageRank-ranked": on a
repo with a history snapshot the order is co-change first, then PPR.

## 5. Needs no change (checked)

- `find` (`graph.py:155`): `PyGraph.find` is unchanged (`py/api_surface/find.txt` gains only
  `find_files`).
- `cross_stack_trace` (`server.py:587`, `:676`), `entry_flows` (`graph.py:69`), `activate`
  (`server.py:360`, `:459`; the `ActivationConfig` default damping stays 0.5, and EA.1's held index is
  bit-identical to the 0.5.2 computation), `resolve`, `node_cells`, `governing_docs`, `coverage`,
  `bfs` / `predecessors` / `shortest_path`, the counts, the registries, `generate`,
  `load_from_gmap`, `default_gmap_dir`, `version`, `WatchSession(repo)` / `poll` / `snapshot` /
  `persist`: no signature or shape change.
- The registries (`kind_names`, `category_names`, `cell_type_names`, `entry_kinds`): no id
  allocated.
- EA.9 (`e673fd11`), EB.9 (`9612f68e`), EG.1-EG.3, EG.6, EG.7 (harness and gate), EA.1-EA.4,
  EB.2, EB.3, EB.5a-c, EB.6, EC.1-EC.5, EC.10, EC.14: engine internals or additive engine items with
  no pyo3 surface; the wrapper sees them only through rows 1-14.

## 6. Re-test

Against a local wheel of the tag (or the leap wheel before it):

```
pip install glia-py==0.5.3        # after the publish
python -c "import glia_py; print(glia_py.build_stamp())"
pytest tests/                     # the wrapper's own suite
```

- The wrapper's impact tests: a fixture repo without `.glia/history-snapshot/` gives rows
  byte-identical to 0.5.2's; only a test that pins row order on a repo holding a snapshot can move.
- After `history_sync` + `history_calibrate` on a scratch clone, a new graph's `impact` dict carries
  `selection.source == "calibrated"`; stderr shows `[select] surface=blast_radius ..` and
  `[rank] surface=blast_radius ranking=..`.
- The watcher tests (`tests/test_watcher.py`) are unaffected: the session's API did not change.

## 7. Done vs pending

- **Done, glia:** W0-W15 (every packet but EZ.1 / EZ.2), each close-out green
  (`cargo test --workspace` 6556 passing at the W15 close-out, `[rank-gate] check: ok`).
- **Pending, James:** the 0.5.2 -> 0.5.3 bump, the `v0.5.3` tag, the `glia-py` 0.5.3 publish.
- **Pending, repo-graph:** the pin (section 1); optionally sections 4.1-4.4. The 0.5.2 port in the
  working tree is still uncommitted at the time of writing; land it first.
- **Followups named for repo-graph by the packets:** EA.7 (kwargs and the H10 default), EA.6b (pack's
  file-level lift), EA.8 (the `## files` section), EB.1 (history v2, the kwarg, the four keys), EB.7
  (`intent`, the default title), EB.8 (`find_files` as an optional adoption, exit 0 on absence), EC.6
  (call `history_calibrate` after `history_sync`), EC.8 (`selection`, `ranking=None` = calibrated),
  EC.9 / EC.9b (pack's `selection`; pack ignores calibration, ruling EC-9b), EC.11 / EC.12 (`selection_intent`, SELt2, `refused`, recalibrate
  after the upgrade), EC.13 (`find_files`' `selection`, the SELf2t row first): all in sections 1-4.
- **Open question routed to James by EB.7, settled:** the default title is on (ruling EB-2): a branch
  with commits past the base gets an intent without `--title`.

## 8. Engram and neuropil

Engram's only 0.5.3 change is the exporter's DE.5 removal (`dev-notes/engram-handoff-0.5.3.md`).
neuropil skipped 0.5.2 and moves 0.5.1 -> 0.5.3 (`dev-notes/neuropil-handoff-0.5.3.md`).

## 9. The 0.5.3 release record (no consumer change)

Notes the packets routed to the release record; none asks repo-graph for anything.

- **The rank gate** (EG.1-EG.3, EG.6, EG.7; `bench/rank-gate/`, `scripts/rank-gate.sh`): six public
  snapshots (glia at v0.5.2, pop-os/shell, gorilla/websocket, flutter/samples, and by ruling INT-1
  apache/commons-lang and apache/commons-io). `check` judges every gated (shape, ranker, metric) row
  against the 0.5.2 baseline AND against `current`, each pair its own family (rulings EG-1, EG-2).
  The verdict is **Holm over the changed rows, not a per-row CI rule**: one-sided per direction,
  family alpha 0.05, a row's p the share of its paired commit-cluster bootstrap means on the wrong
  side; with one changed row the threshold is p <= 0.05. Unchanged rows are `same`. At EG.3 a whole
  check took about 313 s once rank_eval was built; with EG.6 / EG.7's answers in the gate it takes
  10:25-10:33 wall (glia 454-499 s, of it glia's calibration over three groups with id routing
  116.6 s and the intent pass 84 s), below the close-out's 1800 s threshold. The last recorded check:
  `[rank-gate] check: ok - 1176 rows, 47 gains, 0 drops on 6 snapshots` (EC.14, `369f748f`).
- **The gate's glia snapshot is pinned before `9612f68e`** (EB.9, glia's own `.glia/overlay.toml` with
  `[ids]`), so its parents carry no overlay and the gate supplies glia's vocabulary itself (EC.14's
  `CalibrateOptions.vocab`, `--eng-overlay` / the compiled-in `--pre glia` overlay). When the snapshot
  is re-pinned past `9612f68e`, recheck the glia intent rows literally.
- **rank_eval harness flags** added in 0.5.3: `--ans on` (the shipped answers as rankers), `--ans-leak
  on`, `--engine-parity on`, `--engine on`, `--eng-overlay <file>`, `--gate-check` / `--gate-trim`.
- **EA.7's timing** (section 3.3): one reused PyGraph answers `blast_radius` in 202.5 ms (median of
  calls 2-20) vs 561.7 ms for call 1 on a 1231-commit glia clone, 2.8x on the whole answer; all 40
  answers equal. EA.6's real-repo acceptance was met through EA.7: pack on the glia copy prints
  `[rank] surface=pack ranking=H10 seed_files=1 cochange_files=127 ..`.
- **Wheels CI** (EG.5, `6b03413d`; rehearsal green, PR #1, run 39946342215): every action in
  `.github/workflows/wheels-py.yml` is pinned by full commit SHA with its version tag in a comment
  (Node 24 actions), and the runner images are pinned (`ubuntu-24.04`, `windows-2025-vs2026`).
  `macos-14` is unchanged and **deprecated upstream**: a later packet should move it to `macos-15`
  deliberately.
