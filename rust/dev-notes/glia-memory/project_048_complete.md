---
name: v0.4.8 complete — cell write API (was mempalace bridge)
description: v0.4.8 reframed from mempalace bridge to generic cell write API; upsert_cell/remove_cell/read_to_owned/upsert_cell_sharded in store crate; 7 new tests, 89 workspace green
type: project
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**Completed 2026-04-17.**

### Design pivot (user-driven)
Original plan was "mempalace bridge (vendored direct)" — pull mempalace data into repo-graph. User challenged this through a series of questions:
- "but wouldn't we just be pulling from mempalace?" — flipped direction assumption
- "does this work though?" — exposed the join problem (no shared key between mempalace entity names and repo-graph qnames)
- "i mean shouldn't the mempalace info live inside the nodes in a cell?" — pointed to cells as the answer
- "so then we could just write in mempalace info if we wanted to by config? or other types of things by mcp?" — generalized: mempalace is just one possible source, the write surface is the feature

**Result:** v0.4.8 is a generic cell write API. Mempalace, CI logs, conversation history, env context — anything populates cells through this API. Config-driven ingest (declarative, runs on regen) and MCP write tools (imperative, one-shot) are downstream consumers.

### What shipped
- `read_to_owned(path)` — deserialize archived .gmap back to owned Container
- `upsert_cell(path, node_id, cell_type, payload)` — read-modify-write single cell
- `remove_cell(path, node_id, cell_type)` — remove cell by type, returns bool
- `upsert_cell_sharded(dir, node_id, cell_type, payload)` — sharded variant, finds correct shard + updates manifest hash
- `StoreError::NodeNotFound` variant
- 7 new unit tests

### Files modified
- `rust/store/src/lib.rs` — mutation API + tests added

### Not yet done (downstream)
- Config-driven ingest (`config.yaml` cells: section) — needs generate pipeline (v0.4.10+)
- MCP write_cell tool — needs pyo3 (v0.4.10+)
- CLI binary entry point — could land anytime, thin wrapper
