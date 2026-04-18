---
name: v0.4.6 pyo3 merged into v0.4.11
description: pyo3 bindings absorbed into text loop + interceptor skill milestone — no Python caller exists between 0.4.6 and 0.4.11, so landing bindings early was wasteful
type: project
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**Decision 2026-04-17.** User confirmed: *"okay i guess we move 0.4.6 into 0.4.11 then"*

**Why:** v0.4.6 (pyo3 + maturin bindings) would land Python-callable wrappers that nothing uses until v0.4.11 (text loop + interceptor skill). Everything between them (HippoRAG, multicellular, mempalace, more parsers) is pure Rust tested via `cargo test`. The bindings sit idle through four milestones. Merging removes a hollow milestone.

**How to apply:** The sequence after v0.4.5 needs renumbering. Old v0.4.7–v0.4.12 slide down one slot each, with the combined pyo3+skill step landing right before PyPI publish. Renumbering scheme not yet confirmed — user was asked whether to renumber or mark 0.4.6 as "absorbed."

**Pending:** user hasn't confirmed whether to renumber the sequence (v0.4.6→HippoRAG, v0.4.7→multicellular, etc.) or keep old numbers with a gap.
