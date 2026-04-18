---
name: v0.4.7 in progress — cell registry + text compression
description: v0.4.7 cell types 7-14 registered, text compression implemented (scopes/defaults/module-collapse/compact-position), 452KB→320KB on quokka; not yet committed
type: project
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**Started 2026-04-17, not yet committed.**

### What's done
- Cell types 7-14 registered in `rust/code-domain/src/lib.rs`: TEST(7), ATTN(8), FAIL(9), CONSTRAINT(10), DECISION(11), ENV(12), CONV(13), VECTOR(14)
- Text renderer labels all 14 cell types
- Four compression moves in `rust/projection-text/src/lib.rs`:
  1. `[SCOPES]` — common qname prefix abbreviation (max 25, net-savings scoring, immediate-parent level)
  2. `[DEFAULTS]` — majority kind/confidence declared once, nodes only emit deviations
  3. Module file collapse — multi-file packages render `:files` instead of N×`:code`+`:position`
  4. Compact position — `file:start-end` instead of JSON blob
- 9 new unit tests (scopes, defaults, module collapse, alias collision)
- 82 workspace tests green, clippy clean

### Compression results on quokka
- 452KB → ~320KB (29% reduction)
- `:confidence strong` default saved 1320 lines
- `:kind` not defaultable (no single kind >50%)
- Module file collapse triggered on 9 multi-file Go packages

### Not yet done (deferred per user feedback)
- Auto-populators for TEST and ATTN cells — these are just empty registry slots for now
- Further text compression polish — user said text is legacy, don't over-invest

### Files modified
- `rust/code-domain/src/lib.rs` — cell_type registry expanded to 14
- `rust/projection-text/src/lib.rs` — full rewrite with compression
