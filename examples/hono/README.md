# Hono — what repo-graph sees

[https://github.com/honojs/hono](https://github.com/honojs/hono) · TypeScript · edge routes

Real output from the six tools, captured against the current engine. This is what your assistant gets **before it opens a single file**.

| | |
|---|---|
| Nodes | 2,062 |
| Edges | 4,967 |
| Cross-stack edges | 204 |
| Entry points | 581 |
| Feature flows | 10 |
| Cold build (full reparse) | 0.2s |
| Warm load (cached graph) | 0.04s |

## `orient()`

```
  repo-graph
  ========================================

  2062 nodes, 4967 edges, 204 cross-stack
  Engine: glia-py 0.5.0 (Rust + tree-sitter)

  Confidence: 1445 strong, 615 medium, 2 weak

  Node kinds:
      597 ██████████████████████████████ ƒ function
      442 ██████████████████████████████ ⟁ route
      365 ██████████████████████████████ ◇ module
      138 ███████████████████████████    ƒ method
      123 ████████████████████████       ◊ interface
      100 ████████████████████           ⬡ component
       69 █████████████                  ● state_var
       52 ██████████                     ↗ endpoint
       49 █████████                      ⊕ package_dep
       48 █████████                      □ class
       32 ██████                         ● doc_section
       24 ████                           ⌗ attribute
        6 █                              ● project
        3 ▏                              ↗ event_emitter
        3 ▏                              ▣ enum

  Entry points (10 flows):
    ƒ app  [function]  ·1 reached
    ƒ child  [function]  ·1 reached
    ƒ component  [function]  ·1 reached
    ƒ errorboundary  [function]  ·25 reached
    ⟁ get_/named  [route]  ·1 reached
    ƒ main  [function]  ·1 reached
    ƒ nested  [function]  ·3 reached
    ƒ redtheme  [function]  ·1 reached
    ƒ showcount  [function]  ·1 reached
    ƒ suspense  [function]  ·19 reached

  Blind spots (verify these with grep — the graph may under-link them):
    ⚠ CALLS (*): calls through reflection, dynamic dispatch, or higher-order indirection are not resolved
    ⚠ HTTP_CALLS (*): URLs built dynamically (string concat / variables / base-url config) may not pair to a route
    ⚠ QUEUE_FLOWS (*)  [0 found]: topics passed as parameters, runtime variables or env vars - and constants that are ambiguous, or lower-case bindings in another file - are extracted as an unresolved framework tag and never paired; literal constants the repo table resolves are folded
    ⚠ QUEUE_FLOWS (*)  [0 found]: GCP Pub/Sub subscriptions are named independently of their topic, so publisher and subscriber pair only when both name the topic
    ⚠ QUEUE_FLOWS (*)  [0 found]: SNS→SQS fan-out is declared in infrastructure, not code — a producer to an SNS topic will not pair with the SQS consumers it feeds
    ⚠ DOCUMENTS (*): contract JSON (OpenAPI/Swagger, AsyncAPI, Pact) over 512 KB is not read, and one whose format key is outside its first and last 8 KB is not recognised
    ⚠ GRAPHQL_CALLS (*)  [0 found]: GraphQL SDL embedded in code is read only from a GraphQL-marked literal: a gql / graphql tag or call, a buildSchema / MustParseSchema / ParseSchema / from_definition argument, a /* GraphQL */ or #graphql literal, a GRAPHQL / GQL heredoc, or a literal bound to a variable or key named typeDefs / type_defs. SDL kept unmarked in a differently named variable (a plain template in `const schema = ...`, a Go string passed to MustParseSchema by name) is not read: its root types and fields mint no GRAPHQL_RESOLVER, so its clients' operations pair with nothing. `.graphql` / `.gql` files are read whole.
    ⚠ WS_CONNECTS (*)  [0 found]: a WebSocket upgrade whose route is registered more than one call away from the upgrading function, or through a router glia does not extract, stays unpaired; a client whose URL has no static path is not paired

  Next: `find <symbol|stacktrace|diff>` to jump to nodes, `impact <node>` for blast radius, `trace <feature>` for flows, `orient <node>` / `orient full=true` for the map.
```

## `find("ErrorBoundary")`

```
  2 node(s) matching 'ErrorBoundary':

    ⬡ ErrorBoundary  [component]  src::jsx::components::ErrorBoundary  src/jsx/components.ts:57
    ● ErrorBoundary  [state_var]  src::jsx::dom::components::ErrorBoundary  src/jsx/dom/components.ts:7 ⊘
```

## `impact("getAppTemplate")`

```
  Impact (both) from benchmarks::http-server::benchmark::getAppTemplate — depth 3

    0.263  ƒ buildVersion  [function]  benchmarks/http-server/benchmark.ts:93  via CALLS  ·1
    0.069  ƒ runCommand  [function]  benchmarks/http-server/benchmark.ts:56  via CALLS  ·2
    0.049  ◇ benchmark  [module]  benchmarks/http-server/benchmark.ts:1 ⊘  via CALLS  ·3
    0.034  ƒ main  [function]  benchmarks/http-server/benchmark.ts:234  via CALLS  ·2
    0.021  ƒ sleep  [function]  benchmarks/http-server/benchmark.ts:54  via CALLS  ·2
    0.016  ƒ runBenchmark  [function]  benchmarks/http-server/benchmark.ts:180  via CALLS  ·3
    0.009  ↗ POST /json  [endpoint]  benchmarks/http-server/benchmark.ts:148  via CALLS  ·2
    0.009  ↗ GET /  [endpoint]  benchmarks/http-server/benchmark.ts:137  via CALLS  ·2

  -- 8 nodes in blast radius  (1 marked ⊘ are not reachable from a known entry point — likely dead, or an entry kind the engine doesn't yet recognise; re-run with live_only=true to drop them)
```

## `trace("ErrorBoundary")`

```
  Trace: ErrorBoundary  (seed src::jsx::components::ErrorBoundary)  [resolved by name]

  path 1  (6 hops)
      src::jsx::components::ErrorBoundary
        → [CALLS] src::jsx::base::jsx  [function]  src/jsx/base.ts:358
      src::jsx::base::jsx
        → [CALLS] src::jsx::base::jsxFn  [function]  src/jsx/base.ts:373
      src::jsx::base::jsxFn
        → [CALLS] src::jsx::context::createContext  [function]  src/jsx/context.ts:213
      src::jsx::context::createContext
        → [CALLS] src::jsx::base::renderChildren  [function]  src/jsx/base.ts:176
      src::jsx::base::renderChildren
        → [CALLS] src::jsx::base::childrenToStringToBuffer  [function]  src/jsx/base.ts:139
      src::jsx::base::childrenToStringToBuffer
        → [CALLS] src::utils::html::escapeToBuffer  [function]  src/utils/html.ts:90

  path 2  (6 hops)
      src::jsx::components::ErrorBoundary
        → [CALLS] src::jsx::base::jsx  [function]  src/jsx/base.ts:358
      src::jsx::base::jsx
        → [CALLS] src::jsx::base::jsxFn  [function]  src/jsx/base.ts:373
      src::jsx::base::jsxFn
        → [CALLS] src::jsx::context::createContext  [function]  src/jsx/context.ts:213
      src::jsx::context::createContext
        → [CALLS] src::jsx::base::renderChildren  [function]  src/jsx/base.ts:176
      src::jsx::base::renderChildren
        → [CALLS] src::jsx::context::runWithRenderContext  [function]  src/jsx/context.ts:161
      src::jsx::context::runWithRenderContext
        → [CALLS] src::jsx::context::getCurrentStore  [function]  src/jsx/context.ts:69

  path 3  (6 hops)

[... trace truncated: 5818 of 7386 chars omitted to fit budget=1600. Narrow the query or raise budget.]
```

---

## Reproduce

```bash
git clone --depth 1 https://github.com/honojs/hono.git /tmp/hono
uvx mcp-repo-graph --repo /tmp/hono
```

The graph is cached in `/tmp/hono/.glia/graph/` — a sharded binary `.gmap`, rebuilt automatically when the source changes.
