---
name: Validation sweeps should use external GitHub/GitLab repos
description: When user asks for N-repo validation, clone a diverse assortment from GitHub/GitLab — local /home/ivy/Code repos are not representative
type: feedback
originSessionId: e18af0c7-26eb-409e-8c0d-89cbaf6550d0
---
User corrected 2026-04-15 mid-validation: "not local repos go test other repos from github and gitlab" when I started iterating over `/home/ivy/Code/*/`.

**Why:** local repos skew heavily to user's own work (quokka-stack, splorts, webplatform) and don't cover all 20 supported languages with realistic codebases. External open-source repos give representative cross-language coverage and are what third-party users' repos will look like.

**How to apply:** when user asks to validate on N repos (especially >20), build a language-diverse list from GitHub/GitLab — cover every supported language with at least one well-known repo per language. Clone `--depth=1` into `/tmp/rg-val/repos/`, run the generator, collect stats. Run in parallel batches (e.g. 6-wide) via background bash. Local repos only belong in quick smoke tests, not release-validation sweeps.

Corollary: user also said "don't ask me for permission while testing for commands input" — during validation sweeps, run autonomously; don't block on each clone/scan. Reserve confirmation for the irreversible publish step itself.

**Depth + breadth mix (confirmed 2026-04-17, v0.4.11 sweep):** user said "yeah look for depth projects but also some breadth projects too." For 50-100 scale sweeps, mix ~40% depth (full-stack monorepos, cross-stack wiring — HTTP/queues/gRPC/GraphQL/WS/CLI) with ~60% breadth (≥2-3 real projects per supported language). Depth repos validate resolvers; breadth validates parsers.

**Report-only first, fixes after review (confirmed 2026-04-17):** user said "just report and collate issues and enough context to understand all the collated issues together." During validation sweeps, do NOT silently patch bugs mid-sweep. Collate every anomaly into one document with reproduction context; let user pick which to fix. Prevents hidden scope creep on supposed-to-be-pre-publish checkpoints.
