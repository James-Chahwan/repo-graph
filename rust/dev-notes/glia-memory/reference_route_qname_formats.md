---
name: Route qname formats + resolver compat shim
description: Two ROUTE qname conventions currently coexist in the code parsers; HttpStackResolver accepts both via index_route_node().
type: reference
originSessionId: 5d22b623-66cd-4680-a7b3-62cb185a9f5d
---
Two Route node shapes live in the tree as of v0.4.11:

**Shape A (canonical, parser-go + ts_routes):**
- qname: `route:<path>` — one Node per path
- cells: stacked ROUTE_METHOD cells, JSON payload `{"method":"GET","handler":...,"file":...,"line":...,"col":...}`
- nav.name: the path itself

**Shape B (legacy, parser-java + parser-csharp + parser-php + parser-rust):**
- qname: `<METHOD> <path>` — one Node per (method, path)
- cells: single ROUTE_METHOD cell, plain `CellPayload::Text(method)`
- nav.name: `<METHOD> <path>`

`rust/graph/src/lib.rs::index_route_node()` indexes both shapes into the same `(METHOD, normalised_path) → Vec<RouteTarget>` map so HttpStackResolver sees them uniformly.

**Migration target:** migrate shape-B parsers to shape A when the other cross-stack resolvers (Queue, GraphQL, WS, etc.) need per-path aggregation. Not urgent — shape B is correct for HTTP but blocks richer cell stacking per path (e.g., attaching handler-specific cells). File: `rust/parsers/code/{java,csharp,php,rust}/src/lib.rs` — look for `format!("{method} {path}")` and the matching `Text(method)` cell.

**Why both shapes exist:** parser-go was the first parser to emit routes (v0.4.3/0.4.4) and established shape A. The later parsers in v0.4.9 copied a different template that happened to use shape B. The v0.4.11 sweep exposed the mismatch because shape-B routes were invisible to HttpStackResolver.
