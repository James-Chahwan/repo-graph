---
name: Workspace layout — parsers nested by domain
description: Rust workspace layout decision at v0.4.3b. Parsers live under parsers/<domain>/<language>/ (e.g., parsers/code/python). Domain-shared crates sit at workspace root alongside core (e.g., code-domain). Keeps the tree tidy as the v0.5.0 domain-agnostic vision lands.
type: project
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
Decided 2026-04-17 during v0.4.3b when adding parser-go. Initially I went flat (`rust/parser-go/`). User pushed back twice:

Round 1: *"hey why don't we move the parsers to a mambers to just handle the workspace better ? like yeh ?"* → agreed, moved to `rust/parsers/<language>/`.

Round 2: *"wait it should parsers/code/specific lanaguage parser this makes it easier for domain configuration later"* → nested deeper. Final shape:

```
rust/
  core/                      universal graph primitives (Node, Edge, NodeId, ...)
  code-domain/               shared code-language types (CodeNav, FileParse, ...)
  parsers/
    code/                    code domain grouping
      python/                repo-graph-parser-python
      go/                    repo-graph-parser-go
      typescript/            repo-graph-parser-typescript (pending v0.4.3b.3)
    (future: chemistry/, video/, policy/, ...)
  graph/                     per-repo graph construction + resolver
  scratch/                   throwaway experiments
```

**Crate name convention:** `repo-graph-parser-<language>` (kebab-case, language at end). The on-disk path differs from the crate name — that's fine, Cargo doesn't enforce a match.

**Path deps:** parsers reach three levels up for workspace siblings: `{ path = "../../../core" }`, `{ path = "../../../code-domain" }`. Graph crate at `rust/graph/` reaches down: `{ path = "../parsers/code/python" }`.

**Rationale for nested-by-domain:**
- Scales: v0.5.0 will bring parsers for chemistry (molecule trees), video (frame graphs), policy (legal doc structure), climate (sensor streams). Flat layout would mean 30+ sibling dirs. Domain grouping caps the breadth at ~5-8 domains.
- Mirrors the registry architecture: every code-language parser shares `code-domain` (u32 NodeKind/EdgeCategory slots, CodeNav shape). `parsers/code/*` files depend on `code-domain`; `parsers/chemistry/*` will depend on a future `chemistry-domain` crate. Directory structure matches dependency structure.
- Aligns with the v0.5.0 domain-agnostic framing: code isn't a special case, it's the first domain.

**Fixture-path gotcha for parser tests:** `env!("CARGO_MANIFEST_DIR")` at `rust/parsers/code/<lang>/` is **four** `parent()` calls from the repo root, not two. Fixtures (shared across languages) live at `tests/fixtures/`. Graph crate tests at `rust/graph/` only need two `parent()` calls — still at the old depth.
