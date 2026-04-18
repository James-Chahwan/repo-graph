---
name: v0.4.6a — HttpStackResolver prefix stripping + sequence renumber
description: API prefix stripping in resolver (7→28 cross edges on quokka); task sequence renumbered after 0.4.6 pyo3 absorbed into 0.4.10
type: project
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**2026-04-17.** Pre-HippoRAG fix batch.

### HttpStackResolver prefix stripping
- Problem: TS endpoints use `protected/activities/city` but Go routes are `/activities/city`. 20 of 26 endpoints failed to match.
- Fix: `lookup_route_with_prefix_strip()` in `rust/graph/src/lib.rs` — when direct lookup misses, strips up to 2 leading segments if they're in `API_PREFIXES` list.
- `API_PREFIXES = ["protected", "api", "public", "internal", "v1", "v2", "v3"]`
- Result: cross edges 7→28 on quokka (26 unique endpoint→route matches; 2 dupes from `user/2fa` matching both prefixed and unprefixed).
- **Open question:** user flagged hardcoded prefixes concern: *"now hold on you made hard coded prefixes that could be for anycode bose though right ?"* — awaiting decision on prefix list vs pure strip-first-segment-on-miss approach.

### Task sequence renumbered
Old → New (after absorbing pyo3 into text loop step):
- ~~v0.4.6 pyo3~~ → deleted (absorbed)
- v0.4.7 HippoRAG → **v0.4.6**
- v0.4.8 multicellular → **v0.4.7** (+ text compression added per user: *"add the compression in multi cell as you said thats when text is gonna blow the fuck up and graph shines hard"*)
- v0.4.9 mempalace → **v0.4.8**
- v0.4.10 parsers + sweep → **v0.4.9**
- v0.4.11 text loop + pyo3 → **v0.4.10** (combined)
- v0.4.12 PyPI publish → **v0.4.11**

### Quokka dump after fix
- 1,350 nodes, 2,556 edges (2,528 intra + 28 cross)
- cross_stack.gmap grew from 320→824 bytes
- All 26 non-unresolved endpoints now link to backend routes
