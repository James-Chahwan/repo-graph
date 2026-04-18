---
name: CLAUDE.md must say "trust repo-graph results"
description: Without explicit trust instructions, Claude uses repo-graph then keeps searching anyway, bloating tokens. Key lesson from demo recording.
type: feedback
originSessionId: 98a759e1-c796-41c8-93e9-e2059d06aae8
---
When configuring repo-graph in a project's CLAUDE.md, you MUST include "trust the results" language. Without it, Claude treats repo-graph output as just another signal and continues grepping/exploring — defeating the purpose.

**Why:** During demo recording, the first repo-graph run took 183k tokens (5 min) because Claude found the answer via repo-graph at ~40s but kept exploring cron_tasks, matching pipeline, etc. After adding "Trust repo-graph results: read ONLY the files it identifies" to CLAUDE.md, it dropped to 29,698 tokens (30s).

**How to apply:** When writing README setup instructions or example CLAUDE.md configs, always include language like:
- "Trust repo-graph results: read ONLY the files it identifies"
- "Do not grep, glob, or explore beyond those files unless they don't contain the answer"
- "Fix with minimal file reads"

This is critical for the tool's value proposition. Without it, repo-graph adds overhead instead of saving context.
