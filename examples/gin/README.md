# Gin — what repo-graph sees

[https://github.com/gin-gonic/gin](https://github.com/gin-gonic/gin) · Go · HTTP routing

Real output from the six tools, captured against the current engine. This is what your assistant gets **before it opens a single file**.

| | |
|---|---|
| Nodes | 2,037 |
| Edges | 3,809 |
| Cross-stack edges | 34 |
| Entry points | 810 |
| Feature flows | 570 |
| Cold build (full reparse) | 0.1s |
| Warm load (cached graph) | 0.02s |

## `orient()`

```
  repo-graph
  ========================================

  2037 nodes, 3809 edges, 34 cross-stack
  Engine: glia-py 0.5.0 (Rust + tree-sitter)

  Confidence: 1823 strong, 175 medium, 39 weak

  Node kinds:
      909 ██████████████████████████████ ƒ function
      483 ██████████████████████████████ ƒ method
      157 ██████████████████████████████ ● state_var
      139 ███████████████████████████    ⟁ route
      125 █████████████████████████      □ struct
      103 ████████████████████           ◇ module
       62 ████████████                   ● doc_section
       32 ██████                         ⊕ package_dep
       20 ████                           ◊ interface
        2 ▏                              ⚿ config_key
        2 ▏                              ● message_type
        2 ▏                              ⏲ cron_job
        1 ▏                              ● project

  Entry points (570 flows):
    ⟁ delete_/base/v1/orgs/:id  [route]  ·1 reached
    ⟁ get_/  [route]  ·15 reached
    ⟁ get_/:count  [route]  ·14 reached
    ⟁ get_/base/metrics  [route]  ·1 reached
    ⟁ get_/base/v1/:id/devices  [route]  ·1 reached
    ⟁ get_/base/v1/orgs/:id  [route]  ·1 reached
    ⟁ get_/base/v1/user/:id/groups  [route]  ·1 reached
    ⟁ get_/favicon.ico  [route]  ·1 reached
    ⟁ get_/test/copy/race  [route]  ·1 reached
    ⟁ get_/users  [route]  ·1 reached
    ⟁ get_/users/:id  [route]  ·1 reached
    ⟁ get_/v2/test  [route]  ·14 reached
    ⟁ post_/users/:id  [route]  ·1 reached
    ƒ testaddroute  [function]  ·5 reached
    ƒ testaddroutefails  [function]  ·5 reached
    ƒ testany  [function]  ·2 reached
    ƒ testbadfiledescriptor  [function]  ·5 reached
    ƒ testbadlistener  [function]  ·5 reached
    ƒ testbadtrustedcidrs  [function]  ·5 reached
    ƒ testbadunixsocket  [function]  ·5 reached
    ... and 550 more

  Blind spots (verify these with grep — the graph may under-link them):
    ⚠ CALLS (*): calls through reflection, dynamic dispatch, or higher-order indirection are not resolved
    ⚠ HTTP_CALLS (*)  [0 found]: URLs built dynamically (string concat / variables / base-url config) may not pair to a route
    ⚠ QUEUE_FLOWS (*)  [0 found]: topics passed as parameters, runtime variables or env vars - and constants that are ambiguous, or lower-case bindings in another file - are extracted as an unresolved framework tag and never paired; literal constants the repo table resolves are folded
    ⚠ QUEUE_FLOWS (*)  [0 found]: GCP Pub/Sub subscriptions are named independently of their topic, so publisher and subscriber pair only when both name the topic
    ⚠ QUEUE_FLOWS (*)  [0 found]: SNS→SQS fan-out is declared in infrastructure, not code — a producer to an SNS topic will not pair with the SQS consumers it feeds
    ⚠ DOCUMENTS (*): contract JSON (OpenAPI/Swagger, AsyncAPI, Pact) over 512 KB is not read, and one whose format key is outside its first and last 8 KB is not recognised
    ⚠ GRAPHQL_CALLS (*)  [0 found]: GraphQL SDL embedded in code is read only from a GraphQL-marked literal: a gql / graphql tag or call, a buildSchema / MustParseSchema / ParseSchema / from_definition argument, a /* GraphQL */ or #graphql literal, a GRAPHQL / GQL heredoc, or a literal bound to a variable or key named typeDefs / type_defs. SDL kept unmarked in a differently named variable (a plain template in `const schema = ...`, a Go string passed to MustParseSchema by name) is not read: its root types and fields mint no GRAPHQL_RESOLVER, so its clients' operations pair with nothing. `.graphql` / `.gql` files are read whole.
    ⚠ WS_CONNECTS (*)  [0 found]: a WebSocket upgrade whose route is registered more than one call away from the upgrading function, or through a router glia does not extract, stays unpaired; a client whose URL has no static path is not paired

  Next: `find <symbol|stacktrace|diff>` to jump to nodes, `impact <node>` for blast radius, `trace <feature>` for flows, `orient <node>` / `orient full=true` for the map.
```

## `find("GET /")`

```
  6 node(s) matching 'GET /':

    ⟁ GET /  [route]  GET /  benchmarks_test.go:23
    ⟁ GET /users  [route]  GET /users  gin_test.go:618
    ⟁ GET /:count  [route]  GET /:count  gin_test.go:680
    ⟁ GET /v2/test  [route]  GET /v2/test  gin_test.go:726
    ⟁ GET /users/:id  [route]  GET /users/:id  gin_test.go:619
    ⟁ GET /favicon.ico  [route]  GET /favicon.ico  benchmarks_test.go:115
```

## `impact("searchCredential")`

```
  Impact (both) from auth::authPairs::searchCredential — depth 3

    0.266  ƒ StringToBytes  [function]  internal/bytesconv/bytesconv.go:13  via CALLS  ·1
    0.027  ƒ Render  [method]  render/json.go:94 ⊘  via CALLS  ·2
    0.027  ƒ Render  [method]  render/json.go:117 ⊘  via CALLS  ·2
    0.022  ƒ setWithProperType  [function]  binding/form_mapping.go:323 ⊘  via CALLS  ·2
    0.012  ƒ authorizationHeader  [function]  auth.go:91  via CALLS  ·2
    0.010  ƒ TestStringToBytes  [function]  internal/bytesconv/bytesconv_test.go:81  via CALLS  ·2
    0.009  ƒ WriteString  [function]  render/text.go:33 ⊘  via CALLS  ·2
    0.009  ƒ BenchmarkBytesConvStrToBytes  [function]  internal/bytesconv/bytesconv_test.go:120 ⊘  via CALLS  ·2

  -- 8 nodes in blast radius  (5 marked ⊘ are not reachable from a known entry point — likely dead, or an entry kind the engine doesn't yet recognise; re-run with live_only=true to drop them)
```

## `trace("GET /")`

```
  Trace: GET /  [resolved by qname]

  path 1  (6 hops)
      GET /
        ⇒ [HANDLED_BY] gin::Engine::HandleContext  [method]  gin.go:709
      gin::Engine::HandleContext
        → [CALLS] gin::Engine::handleHTTPRequest  [method]  gin.go:719
      gin::Engine::handleHTTPRequest
        → [CALLS] gin::redirectFixedPath  [function]  gin.go:837
      gin::redirectFixedPath
        → [CALLS] gin::redirectRequest  [function]  gin.go:849
      gin::redirectRequest
        → [CALLS] debug::debugPrint  [function]  debug.go:56
      debug::debugPrint
        → [CALLS] debug::DebugPrintFunc  [state_var]  debug.go:30

  path 2  (6 hops)
      GET /
        ⇒ [HANDLED_BY] gin::Engine::HandleContext  [method]  gin.go:709
      gin::Engine::HandleContext
        → [CALLS] gin::Engine::handleHTTPRequest  [method]  gin.go:719
      gin::Engine::handleHTTPRequest
        → [CALLS] gin::redirectFixedPath  [function]  gin.go:837
      gin::redirectFixedPath
        → [CALLS] gin::redirectRequest  [function]  gin.go:849
      gin::redirectRequest
        → [CALLS] debug::debugPrint  [function]  debug.go:56
      debug::debugPrint
        → [CALLS] debug::IsDebugging  [function]  debug.go:22

  path 3  (6 hops)
      GET /
        ⇒ [HANDLED_BY] gin::Engine::HandleContext  [method]  gin.go:709
      gin::Engine::HandleContext
        → [CALLS] gin::Engine::handleHTTPRequest  [method]  gin.go:719
      gin::Engine::handleHTTPRequest
        → [CALLS] gin::redirectTrailingSlash  [function]  gin.go:810
      gin::redirectTrailingSlash

[... trace truncated: 3614 of 5152 chars omitted to fit budget=1600. Narrow the query or raise budget.]
```

---

## Reproduce

```bash
git clone --depth 1 https://github.com/gin-gonic/gin.git /tmp/gin
uvx mcp-repo-graph --repo /tmp/gin
```

The graph is cached in `/tmp/gin/.glia/graph/` — a sharded binary `.gmap`, rebuilt automatically when the source changes.
