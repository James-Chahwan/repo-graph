---
name: User wants walkthrough before release
description: When about to release, pause and summarise changes + validation — user wants to see what's going out before the irreversible publish
type: feedback
originSessionId: e18af0c7-26eb-409e-8c0d-89cbaf6550d0
---
User said 2026-04-15 right before the 0.2.0 publish: "before release show the validation and changes and walk me through it"

**Why:** PyPI + MCP registry publishes are irreversible. Even after greenlighting feature work with "okay do it", the user still wants a final review gate before public publish. This matches the established "risky actions warrant confirmation" pattern.

**How to apply:** before running `twine upload`, `mcp-publisher publish`, `gh release create`, or git push to remotes, present a walkthrough of: (1) files changed with one-liner each, (2) validation results including real repo stats + fixture smoke tests, (3) the exact shell commands about to run, (4) ask for greenlight. Don't proceed until user confirms.
