---
name: Write surface over data bridge — generic APIs beat bespoke integrations
description: User-driven insight from v0.4.8: don't build a mempalace-specific bridge, build a generic cell write API that any source can use
type: feedback
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
Build generic write surfaces, not bespoke data bridges.

**Why:** During v0.4.8 design, I proposed a mempalace→repo-graph data bridge. User challenged: there's no reliable join key between mempalace entities (human-language names) and repo-graph nodes (qualified names). The real feature is the write API — let any source (mempalace, CI, conversation, env) populate cells. The LLM or config does the mapping, not a Rust crate guessing at string matches.

**How to apply:** When tempted to build integration-specific code (mempalace bridge, CI bridge, etc.), build the generic API instead and let consumers (MCP tools, config, LLM) handle the mapping. The cells are generic containers — the write surface is the feature, not the data source.
