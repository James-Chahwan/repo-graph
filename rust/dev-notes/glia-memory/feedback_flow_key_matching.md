---
name: Flow key matching — no underscore-to-dash conversion
description: Never convert _ to - when matching flow keys — flow keys like get__ping would break as get--ping
type: feedback
originSessionId: 6408138d-8c57-417e-b3fa-73a15b35a7bf
---
Flow keys in flows/*.yaml can contain underscores and double underscores (e.g., `get__ping`, `post__login_access-token`). Do NOT normalize underscores to dashes when matching.

**Why:** The `flow` tool and `_render_feature_tree` were both doing `.replace("_", "-")` which turned `get__ping` into `get--ping`, failing to match the actual key. Fixed by using raw `.lower().strip()` for matching.

**How to apply:** Any code that looks up flow keys should use the literal lowercase input, then fall back to substring match. Never mangle the key with character replacements.
