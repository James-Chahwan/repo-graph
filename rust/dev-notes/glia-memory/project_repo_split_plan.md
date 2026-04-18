---
name: Repo split plan — glia + repo-graph
description: Mechanics for splitting rust/ into its own glia repo, agreed 2026-04-18. Executes before v0.4.12 publish.
type: project
originSessionId: 5d22b623-66cd-4680-a7b3-62cb185a9f5d
---
**Decision (2026-04-18):** split `rust/` out of the repo-graph monorepo into its own `glia` repo. Executes before v0.4.12 publish.

User verbatim on splitting: *"well im still gonna split the repos just cause i mean the name is sick cmon bro"*.

## Post-split layout

- **glia repo** — contents of today's `rust/` directory. Rust workspace, all ~30 crates, all parsers + extractors + core + graph + store + projection-text + activation + py bindings.
- **repo-graph repo** — slimmed: `repo_graph/*.py`, `pyproject.toml`, `server.json`, MCP skills, examples, README, CLAUDE.md. Thin Python MCP wrapper. Depends on `repo-graph-py` via PyPI (already does today).

## Mechanics (~30 min)

1. `git filter-repo --subdirectory-filter rust/` on a clone → new repo, rust/ history preserved.
2. Create `James-Chahwan/glia` on GitHub + gitlab mirror. Push.
3. In repo-graph: `git rm -r rust/`, clean any top-level Cargo refs. Commit: "chore: extract rust workspace to glia repo".
4. Rewrite repo-graph's CLAUDE.md Architecture section to point at the glia repo instead of documenting rust/ module layout inline.
5. Add a README to glia.

**No PyPI changes in this move.** Packages stay named `repo-graph-py` and `mcp-repo-graph` through v0.4.12. Rename to `glia-py` at v0.5.0 (per `project_naming_glia.md`).

**Don't push the split until v0.4.12 manual builds succeed** — per user rule this session: stage the split locally + commit, push only after the wheel build is confirmed working. Matches the "commit after manual builds" pattern.

## Agreed execution order

1. **Split glia repo** (this plan, local).
2. **v0.4.12 publish from slimmed repo-graph** — Linux x86_64 wheel only, server.json 0.2.0 → 0.4.12 bump, CLAUDE.md rewrite ("engine lives at glia"), tag v0.4.12, push both repos to both remotes.
3. **v0.4.13 scratch probe in `glia/rust/scratch/latent_probe/`** — candle + Qwen 2.5 Coder 7B + `forward_input_embed` hello world. First goal: verify the injection hook works end-to-end before designing anything.

Ordering rationale: splitting first makes the v0.4.12 CLAUDE.md rewrite trivial (one sentence pointing at glia), and the narrative for the first public release matches the code.

## What does not change

- PyPI package names (deferred to v0.5.0 rename).
- Wheel build process (maturin from glia/rust/py/).
- MCP server entry points.
- The v0.4.12 publish mechanics (just run from the slimmed repo-graph).
