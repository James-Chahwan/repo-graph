---
name: Cross-stack endpoint→route linking implemented
description: Generator now matches dangling frontend endpoint_* edges to backend route_* nodes by normalizing URL paths. 18 edges linked on quokka-stack.
type: project
originSessionId: 98a759e1-c796-41c8-93e9-e2059d06aae8
---
Implemented cross-stack endpoint→route linking in `generator.py` (2026-04-13).

**The problem:** Angular analyzer creates `calls` edges from services to `endpoint_ANY_protected_groups` nodes. Go analyzer creates `route_GET_groups` nodes. Different ID schemes — 34 dangling edges, zero cross-stack connections. Flows were frontend-only.

**The fix:** `_link_endpoints_to_routes()` runs after deduplication:
1. Builds lookup of route nodes by normalized URL path (strips `protected/`, `api/`, collapses params)
2. Finds dangling edges targeting `endpoint_*` IDs
3. Extracts path from endpoint ID, normalizes, matches to route nodes
4. Rewires edges to point at actual route nodes

**Also changed:** Flows are now always rebuilt by `_auto_flows()` after cross-stack linking, not conditionally. This ensures flows include backend nodes even when frontend analyzers provided their own flows.

**Results on quokka-stack:** 18 cross-stack edges linked, 64 flows (up from 11). `group_controller.go` now appears in groups flow.

**Go handler linking (FIXED 2026-04-13):** Go routes now link to specific handler functions via regex capture of handler names from `.GET("/path", HandlerFunc)` patterns. Two-pass approach: collect all functions first, then resolve handler references. Cross-package qualified names (`controllers.MetricsHandler`) are handled by suffix matching. Inline `func(...)` handlers fall back to the package.

**Flow fuzzy matching (FIXED 2026-04-13):** `server.py` flow matching now prefers the shortest matching key instead of first alphabetical. `flow("groups")` → `get__groups` instead of `delete__groups_activities_groupid_inviteid`.

**Files changed:** `repo_graph/generator.py`, `repo_graph/analyzers/go.py`, `repo_graph/server.py`.
