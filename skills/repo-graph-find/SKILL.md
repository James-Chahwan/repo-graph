---
name: repo-graph-find
description: Locate where a feature or symbol lives — match nodes by name, or pull the related cluster from seed terms via spreading activation. Use to scope before reading.
---

# repo-graph find

Find the relevant set, not one lucky file.

## When to use

- "Where is the billing code?" / "find the auth handlers."
- You have a couple of keywords and need everything related.

## Steps

1. Exact-ish name: call `find` with `query=<text>` → matching nodes with kind and qname.
2. A concept or feature: call `activate` with `seeds=<comma-separated terms>` → the most related nodes ranked by relevance (Personalized PageRank from your seeds).
3. Then run `flow` or `trace` on the best hit to see it end to end.

Use the results to scope what you read. Don't read the whole repo to find one thing.
