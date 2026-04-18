---
name: Project rename — glia (with gmap as the format)
description: Decided 2026-04-18. repo-graph renames to glia for the domain-agnostic v0.5.0+ identity; gmap stays as the format/interface name.
type: project
originSessionId: 5d22b623-66cd-4680-a7b3-62cb185a9f5d
---
**Decision (2026-04-18):** project renames from `repo-graph` to **glia**. Format name stays **gmap**. Two-name split mirrors Arrow+Parquet, Docker+OCI.

User verbatim: *"glia works also for the fucking retcon you fucking genius cunt, your an ideas man you know that."*

**Why glia:**
- Biological literalism — glia are the non-neuronal substrate that lets neurons communicate. Exactly what the project *is*: the substrate that lets LLMs talk to a cellular graph and to each other.
- Matches the multicellular + activation framing already in the vision memory. "Glia cells" as a phrase is already in the vocabulary.
- gmap retcon: "glia-map" works as a back-derivation. Format name didn't have to change.
- Undercrowded namespace vs synapse (SynapsePy / Matrix Synapse), loom (Weaveworks + meeting tool), prism (prismjs / prisma).
- `repo-graph` was scoped too narrow on both axes for the 0.5.0+ domain-agnostic vision (not just repos, not just graphs).

**When the rename actually happens:** the v0.4.12 wheel still ships under `mcp-repo-graph` on PyPI. The rename is a v0.5.0 move, bundled with the domain-agnostic generalisation. Rushing it before v0.4.12 publish would churn for no gain.

**What gets renamed at v0.5.0:**
- Project identity / repo name / docs
- PyPI package (`mcp-repo-graph` → probably `glia` or `glia-mcp`)
- crates.io crate prefix (`repo-graph-*` → `glia-*`)
- CLI entrypoints (`repo-graph`, `repo-graph-init` → `glia ...`)
- MCP Registry id (`io.github.James-Chahwan/repo-graph` → new slug)

**What stays:**
- `gmap` file format + extension
- gmap binary / gmap text / gmap vectors projection names
- `.gmap` file extension

**Don't name-churn before v0.5.0.** Shipping v0.4.12 as mcp-repo-graph is fine; the rename is one clean cut at v0.5.0.
