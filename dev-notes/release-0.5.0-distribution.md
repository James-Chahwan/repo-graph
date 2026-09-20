# 0.5.0 distribution update pack

Every surface repo-graph has been submitted to, what changes for 0.5.0, and the exact action.
Status column verified live on **2026-09-20**.

Two things make this release different from a routine bump:

1. **The engine package is renamed** `repo-graph-py` → `glia-py`. Anything that names the engine is stale.
2. **The tool surface has been 6 for a while, but most listing copy still says 11 or 13.** Every
   directory entry written before v0.4.18 is wrong.

---

## ⚠ Do these two first

**1. `glia-py` is unclaimed on PyPI.** `https://pypi.org/pypi/glia-py/json` returns **404** right now.
Until you claim it, the name the whole 0.5.0 release depends on is sitting there for anyone to take.
Claim it by adding the **pending trusted publisher** before you tag:

> pypi.org → Your projects → Publishing → Add a pending publisher
> PyPI project name `glia-py` · Owner `James-Chahwan` · Repository `glia` · Workflow `wheels-py.yml`

Without it the `wheels-py.yml` publish job fails and the tag is wasted.

**2. Version parity.** `pyproject.toml` and glia's `py/Cargo.toml` **and** `[workspace.package].version`
must move together — the 0.4.17 lesson was that a mismatch makes the publish silently do nothing.

Current live versions: `mcp-repo-graph` **0.4.21** · `repo-graph-py` **0.4.18** · MCP Registry **0.4.21** ·
`glia-py` **absent**.

---

## Release order

```bash
# 0. gate — non-negotiable
pytest && pytest -m perf

# 1. glia: bump py/Cargo.toml + [workspace.package].version + py/pyproject.toml to 0.5.0
#    then (pending publisher already added):
git -C ../glia tag v0.5.0 && git -C ../glia push origin v0.5.0     # wheels-py.yml publishes glia-py
curl -s https://pypi.org/pypi/glia-py/json | python3 -c "import sys,json;[print(f['filename']) for f in json.load(sys.stdin)['urls']]"
#    expect 5 wheels + sdist. A single linux wheel = macOS/Windows installs break.

# 2. repo-graph: only after glia-py is on PyPI (pyproject pins glia-py>=0.5.0)
rm -rf dist/ && python -m build && twine upload dist/* -u __token__ -p <TOKEN>

# 3. MCP Registry
/tmp/mcp-publisher login github && /tmp/mcp-publisher publish

# 4. site
npx wrangler deploy                      # docs/ → repo-graph.com

# 5. tag + release
git tag v0.5.0 && git push github main --tags && git push gitlab main --tags
gh release create v0.5.0 --title "v0.5.0" --notes-file dev-notes/release-notes-0.5.0.md
```

---

## Surfaces

### Automatic — verify only

| Surface | ID | Action |
|---|---|---|
| **PulseMCP** | `james-chahwan-repo-graph` | Auto-fed from the MCP Registry. Check the tool count says 6 a day after publishing. |
| **Glama** | `James-Chahwan/repo-graph` | Re-scans the repo. Confirm score stays A and the profile is still 100%. |
| **cursor.directory** | Open Plugins auto-detect | Reads `.plugin/plugin.json` (bumped to 0.5.0) + root `.mcp.json`. Re-run auto-detect if it doesn't pick up. |
| **VS Code MCP gallery** | via MCP Registry | Follows the registry entry. |

### Manual — needs a push

| Surface | ID | Action |
|---|---|---|
| **PyPI (wrapper)** | `mcp-repo-graph` | `twine upload`. Needs a fresh token — the old one is spent. |
| **PyPI (engine)** | `glia-py` | **Claim the name first** (see above). Published by glia CI, not by hand. |
| **PyPI (old engine)** | `repo-graph-py` | **Decision needed** — see Open questions. |
| **MCP Registry** | `io.github.James-Chahwan/repo-graph` | `mcp-publisher publish`. Token expires each session, so log in fresh. |
| **VS Code Marketplace** | `james-chahwan.repo-graph` | `vsce publish` from `vscode-extension/` (now 0.5.0, CHANGELOG written). **Cosmetic** — the extension just runs `uvx mcp-repo-graph`, so every install auto-pulls the new version off PyPI regardless. Low priority. |
| **Smithery** | `j-r-chahwan/repo-graph` | Rebuild the `.mcpb` **by hand** with an enriched manifest — Smithery requires per-tool `inputSchema`, which `mcpb pack` refuses to emit. See the recipe below. |
| **repo-graph.com** | Cloudflare Worker | `npx wrangler deploy`. Site restyled + examples regenerated this session. |

### Submitted — check state, update copy if live

| Surface | State as of the last check | Action |
|---|---|---|
| **Cline marketplace** | issue [cline/mcp-marketplace#1745](https://github.com/cline/mcp-marketplace/issues/1745) | Check if merged. If live, the listing copy says 13 tools → ask for 6. |
| **awesome-mcp-servers** | PR merged | One-line entry; if it names a tool count, open a small PR. |
| **Claude plugin / claude-community** | in review | Chase or leave. `claude-plugin/.claude-plugin/plugin.json` is at 0.5.0. |
| **MCP Atlas** | submitted 2026-06-08 (11 tools) | Copy is stale whether or not it landed. Resubmit/update. |
| **Stacklok (ToolHive)** | submitting 2026-06-08 | Check for a follow-up. |
| **MCP Server Finder** | emailed 2026-06-08 (11 tools) | Stale copy; email an update to info@mcpserverfinder.com. |
| **mcp.so** | submitted 2026-06-08 | Stale copy. |
| **Claude Desktop MCPB directory** | submitted, Node-leaning | Probably no response; ignore. |

### Parked

Open VSX (Eclipse webmaster never unblocked) · MCP Market paid tier ($29 — not worth it).

---

## Canonical copy — use this everywhere

Everything below replaces the pre-0.4.18 blurb that says 11 or 13 tools.

**Name:** `mcp-repo-graph` (the unambiguous string — bare "repo-graph" collides with
`repo-graphrag-mcp` and `repo-architecture-mcp`)
**Title:** Repo Graph · **Author:** James-Chahwan · **Category:** Developer Tools
**Repo:** https://github.com/James-Chahwan/repo-graph · **Site:** https://repo-graph.com
**Icon:** `https://raw.githubusercontent.com/James-Chahwan/repo-graph/main/docs/logo-400.png`
**Tags:** `mcp, code-graph, ai-coding, code-navigation, developer-tools, tree-sitter`

**Tools (6):** `orient`, `find`, `impact`, `trace`, `read`, `refresh`

**Short description:**

> Structural graph memory for AI coding assistants. repo-graph maps your codebase — entities,
> relationships, and cross-stack flows — so the model navigates to the right files instead of reading
> everything first. Six tools, tree-sitter, 20+ languages, frontend to backend, any MCP client.

**What's new in 0.5.0** (for "release notes" fields):

> Moves onto the glia 0.5.0 engine. Empty answers now explain themselves — you get the reason,
> whether it's a fact or a heuristic, and which extractions are partial — instead of a bare "not
> found". `impact` takes a whole diff in one call and reports names it couldn't resolve. `trace`
> returns ranked distinct cross-stack paths. Declared components and services are labelled as such
> rather than flattened to "class". The engine package is renamed `repo-graph-py` → `glia-py`.

**Config block (unchanged — every client reduces to this):**

```json
{"mcpServers":{"repo-graph":{"command":"uvx","args":["mcp-repo-graph","--repo","."]}}}
```

---

## Smithery rebuild recipe

Smithery's stdio registry **requires** per-tool `inputSchema`; Anthropic's MCPB format **forbids** it,
so `mcpb pack` won't build a publishable bundle. The committed `mcpb/manifest.json` stays MCPB-valid;
the enrichment is a publish-time transform only.

```bash
# 1. enrich a COPY of the manifest with inputSchema pulled from the live registry
python3 - <<'EOF'
import json, asyncio
from repo_graph import server
m = json.load(open("mcpb/manifest.json"))
tools = asyncio.run(server.mcp.list_tools())
by = {t.name: t.inputSchema for t in tools}
for t in m["tools"]:
    t["inputSchema"] = by[t["name"]]
json.dump(m, open("/tmp/mcpb-build/manifest.json", "w"), indent=2)
EOF
# 2. hand-zip (do NOT use `mcpb pack`)
cd /tmp/mcpb-build && zip -r repo-graph-0.5.0.mcpb manifest.json icon.png server/
# 3. publish
npx -y @smithery/cli@latest mcp publish ./repo-graph-0.5.0.mcpb -n j-r-chahwan/repo-graph
```

Honest note: Smithery's hosted playground runs the stdio server in an empty sandbox and can't see the
user's files, so the listing is the only value here.

---

## Open questions for James

1. **What happens to `repo-graph-py` on PyPI?** It sits at 0.4.18 and is now superseded. Options:
   (a) one final 0.4.19 whose description points at `glia-py`, (b) leave it and let the README carry
   the redirect, (c) yank — *don't*, it breaks anyone pinned. The handoff left this open.
2. **Does `mcp-repo-graph` get renamed?** CLAUDE.md's roadmap pencilled it in for 0.5.0. It's the one
   string every listing, the registry slug and the whole SEO story is built on, so renaming means
   re-doing this entire table. Recommendation: **don't**, not in the same release as an engine rename.
3. **Is the VS Code extension worth republishing?** It's display-only — installs auto-pull the new
   PyPI version. Skip it unless you want the changelog visible.

---

## Also fixed this session

- `vscode-extension/package.json` was a release behind (0.4.20 while everything else was 0.5.0).
  Two new tests now guard it: `test_all_distribution_manifests_version_synced` checks all six
  manifests against `pyproject.toml`, and `test_mcpb_manifest_tools_match_server_registry` catches a
  tool-surface change that doesn't reach the MCPB bundle.
- `examples/` regenerated as real tool transcripts (`scripts/build_examples.py`) — they were
  Python-era `nodes.json`/`state.md` dumps in a format the engine no longer produces.
- Site restyled to the quokk4.net design language; `docs/og.png` regenerated to match
  (`scripts/build_og.py`).
