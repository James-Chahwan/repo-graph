---
name: Don't invent ceremony (PR counts, phases, ship sequences) when the ask is "simplify"
description: When user asks to simplify scope, keep the scope simple — don't re-package it into a PR plan with phases; that's re-introducing complexity
type: feedback
originSessionId: f5091c3e-4ad2-47ca-be6b-233c911fb6a7
---
**Verbatim:** "where the fuck you get 3-4 pr's lol / where just simplifying what 0.3.0 is"

Context: user asked to simplify 0.3.0 from a multi-release plan with SymbolTable subpackage, fixture-as-spec Rust contract, Node.extras, 30-repo sweep automation. I stripped the architecture but then re-packaged the remainder into "PR 1 / PR 2 / PR 3 / PR 4" with a week-by-week plan. That's still ceremony — just reshuffled.

**Why:** simplifying scope and then repackaging it into a process plan re-introduces the complexity in a different dimension. The user's simplifications are about reducing the size of the thing they're holding in their head, not about getting a cleaner project-management artifact.

**How to apply:**
- When user says "simplify," describe the scope as a flat list of what's in and what's out. Not a PR breakdown.
- Don't propose release sequences (0.3.0 / 0.3.1 / 0.3.2) unless the user explicitly asks for sequencing.
- Don't propose week-by-week timelines unless asked.
- Don't propose "PR 1 does X, PR 2 does Y" unless asked.
- If the user wants execution structure they'll ask. Wait for the ask.
- The planning artifact and the execution artifact are separate. Don't hand them both when only one was requested.
