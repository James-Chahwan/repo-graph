# Example Outputs

Pre-generated graph data for popular open-source repositories, so you can see what `repo-graph` produces without running it yourself.

| Repository | Language | Nodes | Edges | Flows |
|---|---|---|---|---|
| [FastAPI](fastapi/) | Python | 1,693 | 1,619 | 95 |
| [Gin](gin/) | Go | 419 | 417 | 2 |
| [Hono](hono/) | TypeScript | 716 | 608 | 0 |
| [NestJS](nestjs/) | TypeScript | 2,805 | 2,237 | 0 |

Each directory contains the full `.ai/repo-graph/` output:

- **`state.md`** -- project overview, git state, detected packages/modules
- **`nodes.json`** -- every entity (functions, classes, routes, modules, etc.)
- **`edges.json`** -- relationships (imports, calls, contains, routes_to)
- **`flows/`** -- auto-generated feature flows from detected routes

## Regenerate

To regenerate any example against the latest version of the repo:

```bash
git clone --depth 1 https://github.com/tiangolo/fastapi.git /tmp/fastapi
repo-graph-generate --repo /tmp/fastapi
```

The output lands in `/tmp/fastapi/.ai/repo-graph/`.
