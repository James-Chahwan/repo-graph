---
name: repo-graph generalization to multi-language
description: Major refactor completed 2026-04-13 — ripped out all quokka/turps hardcoding, replaced with pluggable analyzer architecture
type: project
originSessionId: 6408138d-8c57-417e-b3fa-73a15b35a7bf
---
repo-graph was fully generalized from a quokka/turps-specific tool to a language-agnostic MCP server.

**Why:** User wants to "shove this onto anthropic" and use it as a general-purpose tool for any codebase, not just their quokka project. Verbatim: "the main problem right now for this code base is the hardcoded fragility for quokka but this needs to become an mcp tool to work better and complete the features so it works with you seamlessly"

**How to apply:** All future work should treat repo-graph as a general-purpose tool. No project-specific logic in core files — language-specific behavior belongs in `repo_graph/analyzers/<language>.py`.
