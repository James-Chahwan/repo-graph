---
name: Push back on sequence slips when dependencies would break
description: If the user says "move to N" but N has a dependency on a skipped step, flag it and ask — don't just proceed. They'd rather be corrected than watch me build on unstable ground.
type: feedback
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
Rule: when the user names a next step by number, check whether the numbering list has an intermediate item. If yes, push back — even if they phrased it confidently.

**Why:** 2026-04-17 after v0.4.3 shipped, user said "move on to 0.4.4" but 0.4.4 depends on 0.4.3b (Go + TS parsers) to fully test the cross-repo HTTP resolver. I flagged it as a two-option question, which was the right move. User verbatim: *"oh yeah shit sorry 0.4.3b first i mean literally the number in a list, you should push back on that lol"* — they wanted me to push back harder, not present as optional.

**How to apply:**
- When the user names a version/step by number, re-read the sequence list and check for intermediate items.
- If there is one, state the dependency explicitly: "0.4.4 needs 0.4.3b first because [reason]. Doing 0.4.3b now." — then proceed.
- Don't frame as "option A vs option B" when the dependency is clear. That pushes the decision back on them for something I should catch.
- User-named numbers are often shorthand for "next in line", not literal sequence skipping. Default to respecting the list order unless they explicitly say "skip".
