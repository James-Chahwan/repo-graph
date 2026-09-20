# Example outputs

Real output from the six MCP tools, run against freshly cloned upstream repos. This is what your
assistant sees **before it opens a single file**. Nothing here is hand-written.

| Repository | Language | Nodes | Edges | Cross-stack | Entry points | Cold build | Warm load |
|---|---|---|---|---|---|---|---|
| [FastAPI](fastapi/) | Python | 19,025 | 20,854 | 3,999 | 3,045 | 0.5s | 0.18s |
| [NestJS](nestjs/) | TypeScript | 7,829 | 14,961 | 362 | 469 | 0.4s | 0.10s |
| [Hono](hono/) | TypeScript | 2,062 | 4,967 | 204 | 581 | 0.3s | 0.05s |
| [Gin](gin/) | Go | 2,037 | 3,809 | 34 | 810 | 0.1s | 0.02s |

Each directory has a `README.md` with the actual `orient`, `find`, `impact` and `trace` transcripts
for that repo, plus the numbers above.

Cold build is a full reparse from a fresh clone. Warm load reads the cached graph from
`.glia/graph/`. Both measured on one machine, so treat them as a shape, not a benchmark.

## Regenerate

```bash
python3 scripts/build_examples.py          # clones into /tmp/exrepos, rewrites examples/
python3 scripts/build_examples.py --keep   # reuse existing clones
```

Run it after an engine release so the published transcripts match what users actually get.
