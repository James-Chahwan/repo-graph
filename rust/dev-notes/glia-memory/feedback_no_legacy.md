---
name: No legacy/backwards-compat layers
description: User explicitly rejected preserving quokka/turps as a legacy analyzer — clean break preferred
type: feedback
originSessionId: 6408138d-8c57-417e-b3fa-73a15b35a7bf
---
When planning the generalization, I proposed keeping a `quokka_turps.py` analyzer for backwards compatibility. User rejected: "remove quokka stuff entirely with this plan."

**Why:** User wants a clean general-purpose tool to publish, not one carrying project-specific baggage.

**How to apply:** Don't propose backwards-compat shims or legacy code preservation. When refactoring, prefer clean breaks over migration paths.
