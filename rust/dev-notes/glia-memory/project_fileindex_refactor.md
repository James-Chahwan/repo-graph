---
name: FileIndex refactor (completed 2026-04-15)
description: Centralized repo walk — one FileIndex shared by all 20 analyzers, replacing per-analyzer rglob walks. Completed and validated.
type: project
originSessionId: e18af0c7-26eb-409e-8c0d-89cbaf6550d0
---
## Goal

Replace per-analyzer `rglob` walks with a single repo walk. Each analyzer receives a `FileIndex` instance that it queries for files/dirs, rather than walking the tree itself. Consolidates the skip list and (much faster on large repos).

**Why:** 20 analyzers × rglob per `generate` call = N² walks on large monorepos. Single walk is dramatically faster and centralizes skip-dir logic.

**How to apply:** When adding a new analyzer, implement `detect(index)` and `scan()` using `self.index.files_with_ext(...)` / `self.index.dirs_with_file(...)` — never `rglob` directly. `scan_project_dirs` helper was removed — use `index.dirs_with_file("<marker>")` or `index.dirs_with_any([...])` instead.

## Architecture

`repo_graph/discovery.py` — implements `FileIndex` dataclass + `build_index(repo_root)`.

FileIndex API:
- `rel(path)` — relative path string
- `files_with_ext(exts, under=None)` — files by extension
- `files_with_name(name, under=None)` — exact basename match
- `files_matching(pattern, under=None)` — glob pattern match
- `dirs_with_file(name)` — directories containing an exact file
- `dirs_with_glob(pattern)` — directories with glob match
- `dirs_with_any(markers)` — directories with any of the markers (files or globs)

Default skip dirs in `_DEFAULT_SKIP_DIRS` — covers .git, node_modules, vendor, target, build, __pycache__, .venv, .dart_tool, .bloop, _build, etc.

`generator.py` — `index = build_index(repo_root)` built once, passed to `discover_analyzers(repo_root, index)`.

`analyzers/__init__.py` — `discover_analyzers` takes an index. `get_file_analyzer` builds its own index internally.

`analyzers/base.py` — `LanguageAnalyzer.__init__(repo_root, index)`. Abstract `detect(index: FileIndex) -> bool` takes index. `scan_project_dirs` helper removed.

## Validation (completed 2026-04-15)

Sweep of 14 sample repos via `generate()` — all analyzers fire correctly, no crashes:
- quokka-stack: 570 nodes / 626 edges / 64 flows (was 566/620 pre-refactor — minor positive drift from updated skip list)
- grpc-go: 4441 / 4517 — Go monorepo fine
- webplatform: 5627 / 5785 / 390 flows — large C# repo
- Kina: Angular + Go + Solidity all firing in one repo
- splorts-frontend, angular-export, jobhunter, uptalk-api: all clean
