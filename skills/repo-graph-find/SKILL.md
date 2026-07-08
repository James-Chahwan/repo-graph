---
name: repo-graph-find
description: Locate where a feature or symbol lives — match nodes by name, or pull the related cluster from a seed via spreading activation. Use to scope before reading.
---

# repo-graph find

Find the relevant set, not one lucky file.

## When to use

- "Where is the billing code?" / "find the auth handlers."
- You have a couple of keywords and need everything related.

## Steps

1. Exact-ish name: call `find` with `query=<text>` → matching nodes with kind, qname, and `path:line`.
2. A concept or feature: call `find` with `query=<text>` and `expand=true` → the related cluster ranked by relevance (Personalized PageRank from the matches).
3. Pull the source of the best hit with `read`, or run `trace` to see it end to end.

Use the results to scope what you read. Don't read the whole repo to find one thing. (Debugging from an error rather than a keyword? Use the `repo-graph-debug` skill — `find` on the stacktrace, then `read`.)
