---
name: graph_view tool — implemented
description: ASCII visual graph tool with 3 modes: overview (bar charts), node view (children/flows/connections), flow view (layered tiers ENTRY→SERVICE→HANDLER→DATA)
type: project
originSessionId: 6408138d-8c57-417e-b3fa-73a15b35a7bf
---
graph_view tool is the 13th MCP tool, implemented in server.py with three render modes:

- **Overview** (`graph_view` no args): bar chart of node types, edge types, flow list. User said "I like the overview you did."
- **Node view** (`graph_view node="X"`): shows flows the node belongs to, children (defines/contains/exports edges), connections (other outbound), and "used by" (inbound). Depth parameter controls sub-children expansion.
- **Flow view** (`graph_view feature="X"`): layered tiers — ENTRY >> SERVICE >> HANDLER >> DATA. Each tier shows items with type icons and file paths.

Tier classification uses _ENTRY_TYPES, _SERVICE_TYPES, _HANDLER_TYPES, _DATA_TYPES sets with heuristic fallback on node name keywords.

Type icons: ⟁ route, ◈ project, ◇ module, ⬡ component, ⚙ service, ƒ function, □ class, ◊ trait/protocol, ⚓ hook, ◎ context, ↗ api_call.

**How to apply:** When modifying graph_view, preserve the three-mode structure. The tier cap is 10 items per tier to prevent output explosion on large packages.
