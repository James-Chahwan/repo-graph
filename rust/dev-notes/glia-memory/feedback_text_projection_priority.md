---
name: Text projection is legacy — don't over-invest
description: User said text projection is eventually legacy, don't go hard on optimizing it; binary + activation are the real value
type: feedback
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
Don't over-invest in text projection compression or formatting polish.

**Why:** User verbatim 2026-04-17: "dude text is kinda legacy eventually so you don't have to go so hard". Text projection is a stepping stone — the binary projection and activation (PPR) are the real value. Text is what LLMs read today, but latent vectors (v0.4.13) will replace it.

**How to apply:** When working on projection-text, do the minimum viable compression and move on. Don't iterate on scope alias aesthetics, position format micro-optimizations, or edge-case compression. Ship it functional and focus energy on binary format, activation, and mempalace bridge.
