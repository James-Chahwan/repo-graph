---
name: glia-debug
description: Turn a stacktrace, failing test id or diff into the code it implicates, ranked and located, then read it. Use when a test fails, an error or traceback shows up, or you need to know where to start on a bug.
---

# Debug from a failure

Start from the error, not a filename. glia matches the frames, test id or changed paths in a failure to nodes in its graph, then ranks the code around them.

## Transports

Use whichever is available, in this order: the repo-graph MCP tools when loaded (`mcp__repo-graph__<tool>`, or `mcp__plugin_repo-graph_repo-graph__<tool>` from the Claude Code plugin; they may be deferred, so search your tool list first); the `glia` CLI when on PATH; else `uvx --from glia-cli glia <command> ..` (no install; the first run downloads the wheel); else `uvx mcp-repo-graph <verb>`. The MCP tools and `uvx mcp-repo-graph` print the same text; the glia CLI answers the same question with `--json` rows (`file`, `line`, tier). Run any of them at the repo root (`.` below).

| Want | MCP tool call | glia CLI | uvx mcp-repo-graph |
|---|---|---|---|
| Code a stacktrace points at | `find query=<failure> kind=stacktrace` | `glia resolve . "<signal>" --kind stacktrace --json` | `uvx mcp-repo-graph find - --kind stacktrace` |
| Code a failing test id points at | `find query=<test id> kind=test` | `glia resolve . "<test id>" --kind test --json` | `uvx mcp-repo-graph find "<test id>" --kind test` |
| What a diff touches | `find query=<diff> kind=diff` | `glia diff-impact . --diff <file> --json` | `uvx mcp-repo-graph find - --kind diff` |
| The tests to run | `impact nodes=<node>` | `glia tests-for . <node> --json` | `uvx mcp-repo-graph impact "<node>"` |

## Steps

1. Give the raw failure. Don't trim it to one line: the frames are the signal. `--kind` is `auto` (sniff, the default), `stacktrace`, `test` or `diff`.

   ```bash
   glia resolve . "$(pytest -x 2>&1 | tail -n 80)" --kind stacktrace --json
   glia resolve . "tests/test_cart.py::test_total" --kind test --json
   git diff > /tmp/d.diff && glia diff-impact . --diff /tmp/d.diff --json
   pytest -x 2>&1 | uvx mcp-repo-graph find - --kind stacktrace
   ```

2. Read the top hits: open each row's `file:line` (over MCP, `read node=<a>,<b>` slices them in one call with a `context:` footer of callers and covering tests).
3. Find the tests that cover the suspect: `glia tests-for . <node> --json`, or for the whole change `glia tests-for . --base main --json`. Run those first.
4. Widen only if the cause isn't there: `glia blast-radius . <node> --direction both --depth 1 --json` lists the direct callers and callees.

An empty answer says why: an `absence` with its reason and tier, plus the caveats of what it read. When every frame points outside the repo (site-packages, node_modules), run `glia find . <name> --json` on the deepest in-repo function name as a plain keyword.

Siblings: `glia-orient`, `glia-find`, `glia-debug`, `glia-impact`, `glia-trace`, `glia-init`; `glia` is the full CLI reference (every command, flag and answer shape).
