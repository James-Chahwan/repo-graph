---
name: Python implementation never produces the new data format
description: Hard architectural constraint — Python codebase ends at enriched JSON in existing schema; new format is Rust-only from 0.4.0
type: feedback
originSessionId: f5091c3e-4ad2-47ca-be6b-233c911fb6a7
---
**Verbatim:** "python should never make the new data format at all."

**Why:** Avoids the trap of designing a Python-shaped format that the Rust rewrite then has to match (or, worse, diverges from). If Rust is the producer of the new canonical format from day one, Python doesn't need format hooks, projector ABCs, cell envelopes, or schema versioning — it stays a stable JSON v1 producer until end of life.

**How to apply:**
- Reject any 0.3.x proposal that adds new on-disk schema fields, even if they're "just for forward compatibility."
- Capture richer data internally if useful (e.g. `Node.extras: dict` not serialized) but never write it.
- 0.3.x snapshot test fixtures *are* the format spec for the Rust rewrite. Treat them as load-bearing artifacts, not throwaway test infra.
- If something feels like it needs to land in Python because "Rust is far away," push back — that's exactly the trap this rule prevents.
