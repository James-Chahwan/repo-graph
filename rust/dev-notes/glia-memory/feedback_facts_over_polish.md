---
name: Don't refine on assumptions — validate first, polish second
description: Prioritization rule from 2026-04-18 — before 0.4.13 lights up, every glia design decision is a guess. Defer polish until the loop produces facts.
type: feedback
originSessionId: 5d22b623-66cd-4680-a7b3-62cb185a9f5d
---
Rule: before the v0.4.13 latent loop runs end-to-end against a real LLM, don't invest heavily in refining glia's design. The feedback loop produces facts; refinement without it is speculation.

**Why:** user verbatim 2026-04-18, explaining why the v0.4.12 pre-publish sweep was only 10 repos (not 99): *"yeah thats why i only did 10 for the reasoning, because we could spend all this time refining glia at this point on assumptions but 0.4.13 means facts and interfaces."*

Context: earlier same day user framed glia as the product, repo-graph as the demo. The MCP code-graph race is probably lost; 0.4.13 decides whether glia is worth anything. Given that, polish time spent on v0.4.12 is time not spent discovering what 0.4.13 actually needs.

**How to apply:**
- When a v0.4.12 decision feels like "should we harden X?" — default to "ship it, see what 0.4.13 says X actually needs." 10-repo smoke over 99-repo sweep. Linux-only wheel over full matrix. Bundled commit over polished per-milestone tags.
- When a glia design decision has no concrete consumer yet — don't solve the general case. Wait for 0.4.13 (or the next domain primitive) to show what shape the API actually wants to be.
- Exception: invariants that are *expensive to change after ship* get full attention now (NodeKind ID assignments, .gmap format, schema version). These are irreversible; polish them.
- Reversible polish (CLAUDE.md prose, test coverage on settled paths, doc tone) waits until there's a reason to spend on it.

**Related:** `project_positioning_glia_primary.md` (glia = product, repo-graph = demo), `project_competitive_landscape.md` (moat is latent + activation + loop, not parser count).
