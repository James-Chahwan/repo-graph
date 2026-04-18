---
name: Positioning — glia is the product, repo-graph is the demo
description: Strategic reframe 2026-04-18 after deciding to split repos; glia carries the value, repo-graph is one MCP use case among many.
type: project
originSessionId: 5d22b623-66cd-4680-a7b3-62cb185a9f5d
---
**Decision (2026-04-18) after the repo split call.** Positioning shift:

- **glia** — the product. Cellular-graph substrate + activation + latent LLM loop. Domain-agnostic. Where future investment goes. Value depends on 0.4.13 working.
- **repo-graph (mcp-repo-graph)** — the demo. MCP server that happens to use glia for code graphs. One of many possible consumers. Stays alive as long as useful for showcase / onboarding.

User verbatim: *"repo-graph is seperate at this point. so if i lose that race (probably) this might actually be something worth something if 0.4.13 works well enough"*.

**Why this matters for decisions going forward:**

- **Investment priority inverts.** Previous frame was "repo-graph is the product, Rust rewrite is an implementation detail." New frame is "glia is the product, repo-graph is proof glia works on one domain." Feature requests that only help the MCP code-graph use case are lower priority than substrate work that strengthens glia.
- **0.4.13 is the defining milestone, not 0.4.12.** 0.4.12 is the commodity ship (get repo-graph into the MCP race at all). 0.4.13 (latent loop + SWE-bench) is what decides whether glia is worth anything.
- **MCP code-graph race is likely lost.** Explicitly acknowledged. Ship 0.4.12 anyway — it's demo infrastructure for glia + low marginal effort from here + probably some users will find it. Don't sink effort into *winning* that race.
- **Other consumers of glia become strategic.** Chemistry / video / policy / climate per the v0.5.0 domain-agnostic plan. Each new domain-primitive is a new "here's another race glia can enter." Diversifies away from code-graph being the only proof point.
- **Mempalace, HippoRAG activation, latent projection, multi-agent loop** — these are the moat items (per `project_competitive_landscape.md`). Spend time here, not on the 20th language parser.

**What this does not change:**
- Release cadence for v0.4.12 is still the next step.
- Code architecture (Rust engine + Python MCP layer) is unchanged — the split just makes the two-product structure explicit in git.
- 0.5.0 generalisation plan is unchanged (still the domain-agnostic move, still the renamed entry point).

**Operational implication:** when prioritising v0.5.0+ work, the question becomes *"does this strengthen glia, or does this strengthen only the repo-graph demo?"* Former wins every time.
