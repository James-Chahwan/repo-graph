---
name: Init/bootstrap system design
description: Proposed repo-graph-init command where Claude Code assists with first-run project config — source dirs, frameworks, features
type: project
originSessionId: 6408138d-8c57-417e-b3fa-73a15b35a7bf
---
User asked (2026-04-13): "how do we use you inside repo-graph but using the users context of claude code to answer the questions in repo-graph like with an init script for us do the hard parts first and save that for later usages?"

Proposed design:
1. `repo-graph-init` CLI command (or `init` MCP tool)
2. Runs auto-detection first (existing analyzer detect())
3. Writes `.ai/repo-graph/config.yaml` with discovered settings
4. If running inside Claude Code, asks the LLM follow-up questions: "I found packages at backend/app/ — are there others I missed?", "These look like features: login, users, items — any missing?"
5. LLM answers get saved to config.yaml as overrides
6. Future `generate` runs read config.yaml and use the overrides

User said to "do the hard parts first and save that for later usages" — meaning the init captures project knowledge so subsequent runs don't need LLM interaction.

**Why:** Regex heuristics can't discover everything. Having the LLM fill in gaps on first run makes the graph more complete for all future uses.

**How to apply:** This is a post-submission feature. Save for later. When implementing, keep config.yaml human-readable and editable.
