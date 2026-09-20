# Measurement 1: does a structured absence change agent behaviour?

**Result: it makes answers ~3x cheaper and does not make them safer.**

## The claim being tested

repo-graph returns a structured *absence* when a query comes back empty: the reason, a FACT or
HEURISTIC tag, and which extractions are partial. The marketing claim was that a bare empty result
reads as "nothing uses this", so an assistant deletes live code. That claim is **not supported by
this experiment.**

## Design

14 symbols across FastAPI, Gin, Hono and NestJS, none of them ours. Each is a case where repo-graph
honestly has no edge **but real callers exist**, so `NOT SAFE` is correct every time and any `SAFE`
verdict is an error.

Two arms, differing in exactly one thing:

| arm | what the agent sees when the graph is empty |
|---|---|
| `bare` | `No results.` |
| `full` | `No answer (no_edges, FACT)...` plus blind spots plus `searched N nodes` |

Same engine, same graph, same ranking, same `path:line` on every row.

Two tool conditions, because the first smoke showed the agent could sidestep the graph entirely:

| condition | tools |
|---|---|
| `graph_only` | the six MCP tools |
| `with_grep` | plus Grep and Bash |

56 runs, claude-sonnet-5, $2.10.

## Results

Correctness, where ground truth is `NOT SAFE` in every case:

| | bare | full |
|---|---|---|
| graph only | 0/14 wrong | 0/14 wrong |
| with grep | 0/14 wrong | 0/14 wrong |

Cost on identical tasks:

| | bare | full | |
|---|---|---|---|
| graph only | $0.0589 | $0.0202 | 2.9x cheaper |
| with grep | $0.0535 | $0.0172 | 3.1x cheaper |

**28 of 28 matched pairs were cheaper with the absence payload**, at the same turn count (2.9 vs 2.9)
and the same wall time. The agent isn't taking fewer steps, it's taking cheaper ones: told why the
answer is empty, it stops re-querying and re-reasoning about what it might have missed.

## Limits, stated plainly

- **n=14, one model.** Sonnet 5 is cautious. A weaker or cheaper model is exactly where the bare arm
  would plausibly fail, and that run hasn't been done.
- **The design leaks.** Only the empty answer was stripped. `find` and `read` still worked, so even
  the bare arm could confirm the symbol existed and reason carefully from that.
- **The prompt primes caution.** "Decide whether it is safe to delete" invites care in a way a real
  refactor mid-flow does not.
- **Self-run harness.** The repos are not ours and the arms differ in one variable, but we wrote the
  scoring. Read the code before believing the number.

## Reproduce

```bash
python3 bench/absence/run.py --cases 2    # smoke, prints cost
python3 bench/absence/run.py              # full matrix
```

Cases are built from live graphs; the curated set used here is committed as `cases.json`.
