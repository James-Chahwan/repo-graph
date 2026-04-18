---
name: Dense text projection needs prefix/default compression
description: v0.4.5b text renderer is naively literal — prefix repetition, per-node kind/confidence, and module code dedup waste ~45% of tokens; three compression moves identified
type: project
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**Identified 2026-04-17** during first quokka-stack dump review. User spotted it: *"the dense text output could be super denser, we have so many dupes like server : controllers and repeated text they could just become legends right but thats something for later i guess and kinda a legacy hold over"*

### The problem (451KB merged text for 126 files)

1. **Prefix repetition** — `Server::Controllers::` appears 233× in topology, `src::app::core::chat::chat-client.service::` repeats on every TS chat line. Pure token waste.
2. **Cell defaults** — `:kind Function` and `:confidence strong` appear on 80%+ of 1,350 node blocks. 2,700 lines of near-zero information.
3. **Module code dedup** — Go multi-file packages produce N identical `:code package controllers…` lines. The `[Server::Controllers]` block has 17 of them.

### Three compression moves (all projection-layer, binary format unchanged)

1. **`[SCOPES]` legend** — `SC = Server::Controllers`, `SV = Services`, etc. Topology lines shorten dramatically.
2. **`[DEFAULTS]` section** — `:kind Function`, `:confidence strong`. Only nodes that differ emit those lines.
3. **Module file collapse** — `:files Server/Controllers/{activity,auth,...}_controller.go` instead of N×`:code`+`:position` pairs.

**Estimated savings:** 451KB → ~250KB (rough). Bigger payoff as cell types grow in v0.4.8+.

**How to apply:** Slot into multicellular cell population step (adding more cell types makes compression mandatory). Projection-only change — `render_repo_graph` / `render_merged` in `rust/projection-text/src/lib.rs` get smarter, gmap binary format stays unchanged.

### Also noted: HttpStackResolver path normalization gap
20 of 26 TS endpoints don't cross-link because Angular prepends `protected/` API base path. Routes are `/activities/city`, endpoints are `protected/activities/city`. `normalise_http_path` needs common-prefix stripping. Separate fix from text compression.
