# NestJS — what repo-graph sees

[https://github.com/nestjs/nest](https://github.com/nestjs/nest) · TypeScript · modules / DI

Real output from the six tools, captured against the current engine. This is what your assistant gets **before it opens a single file**.

| | |
|---|---|
| Nodes | 7,829 |
| Edges | 14,961 |
| Cross-stack edges | 362 |
| Entry points | 469 |
| Feature flows | 24 |
| Cold build (full reparse) | 0.4s |
| Warm load (cached graph) | 0.09s |

## `orient()`

```
  repo-graph
  ========================================

  7829 nodes, 14961 edges, 362 cross-stack
  Engine: glia-py 0.5.0 (Rust + tree-sitter)

  Confidence: 6031 strong, 663 medium, 1092 weak

  Node kinds:
     2745 ██████████████████████████████ ƒ method
     1924 ██████████████████████████████ ◇ module
     1055 ██████████████████████████████ □ class
      371 ██████████████████████████████ ƒ function
      350 ██████████████████████████████ ⟁ route
      329 ██████████████████████████████ ◊ interface
      281 ██████████████████████████████ ⌗ attribute
      161 ██████████████████████████████ ⊕ package_dep
      134 ██████████████████████████     ⚙ service
       94 ██████████████████             ● state_var
       66 █████████████                  ⟁ graphql_resolver
       51 ██████████                     ● project
       46 █████████                      ↗ endpoint
       34 ██████                         ▣ enum
       23 ████                           ⚿ config_key

  Entry points (24 flows):
    ⟁ addrecipe  [graphql_resolver]  ·3 reached
    ⟁ catcreated  [graphql_resolver]  ·1 reached
    ⟁ create  [graphql_resolver]  ·3 reached
    ⟁ delete  [graphql_resolver]  ·3 reached
    ⟁ findonebyid  [graphql_resolver]  ·2 reached
    ⟁ findpost  [graphql_resolver]  ·2 reached
    ⟁ getcats  [graphql_resolver]  ·2 reached
    ⟁ getposts  [graphql_resolver]  ·2 reached
    ⟁ getuser  [graphql_resolver]  ·2 reached
    ƒ main  [function]  ·16 reached
    ⟁ owner  [graphql_resolver]  ·2 reached
    ⟁ post  [graphql_resolver]  ·2 reached
    ⟁ postcreated  [graphql_resolver]  ·1 reached
    ⟁ posts  [graphql_resolver]  ·2 reached
    ⟁ recipe  [graphql_resolver]  ·2 reached
    ⟁ recipeadded  [graphql_resolver]  ·1 reached
    ⟁ recipes  [graphql_resolver]  ·2 reached
    ⟁ removerecipe  [graphql_resolver]  ·2 reached
    ⟁ unresolved:kafka  [queue_consumer]  ·3 reached
    ⟁ unresolved:mqtt  [queue_consumer]  ·18 reached
    ... and 4 more

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

## `find("unresolved:mqtt")`

```
  2 node(s) matching 'unresolved:mqtt':

    ⟁ unresolved:mqtt  [queue_consumer]  queue_consumer:unresolved:mqtt @packages/microservices  packages/microservices/client/client-mqtt.ts:286
    ↗ unresolved:mqtt  [queue_producer]  queue_producer:unresolved:mqtt @packages/microservices  packages/microservices/client/client-mqtt.ts:278
```

## `impact("getWebhooks")`

```
  Impact (both) from integration::discovery::src::webhooks.explorer::WebhooksExplorer::getWebhooks — depth 3

    0.140  ƒ getMetadataByDecorator  [method]  packages/core/discovery/discovery-service.ts:131 ⊘  via CALLS  ·1
    0.076  ƒ getAllMethodNames  [method]  packages/core/metadata-scanner.ts:78 ⊘  via CALLS  ·1
    0.071  ƒ getProviders  [method]  packages/core/discovery/discovery-service.ts:84 ⊘  via CALLS  ·1
    0.017  ƒ getProvidersByMetaKey  [method]  packages/core/discovery/discoverable-meta-host-collection.ts:101 ⊘  via CALLS  ·2
    0.008  ◇ discoverable-meta-host-collection.spec  [module]  packages/core/test/discovery/discoverable-meta-host-collection.spec.ts:1 ⊘  via CALLS  ·3
    0.006  ↗ GET <unresolved>  [endpoint]  packages/core/discovery/discoverable-meta-host-collection.ts:105 ⊘  via CALLS  ·2
    0.006  ƒ reflectInjectables  [method]  packages/core/scanner.ts:299 ⊘  via CALLS  ·2
    0.005  ƒ scanForPaths  [method]  packages/core/router/paths-explorer.ts:26 ⊘  via CALLS  ·2

  -- 8 nodes in blast radius  (8 marked ⊘ are not reachable from a known entry point — likely dead, or an entry kind the engine doesn't yet recognise; re-run with live_only=true to drop them)
```

## `trace("unresolved:mqtt")`

```
  Trace: unresolved:mqtt  (seed queue_consumer:unresolved:mqtt @packages/microservices)  [resolved by name]

  path 1  (5 hops)
      queue_consumer:unresolved:mqtt @packages/microservices
        ⇒ [HANDLED_BY] packages::microservices::server::server-mqtt::ServerMqtt::bindEvents  [method]  packages/microservices/server/server-mqtt.ts:107
      packages::microservices::server::server-mqtt::ServerMqtt::bindEvents
        → [CALLS] packages::microservices::server::server-mqtt::ServerMqtt::getMessageHandler  [method]  packages/microservices/server/server-mqtt.ts:145
      packages::microservices::server::server-mqtt::ServerMqtt::getMessageHandler
        → [CALLS] packages::microservices::server::server-mqtt::ServerMqtt::handleMessage  [method]  packages/microservices/server/server-mqtt.ts:156
      packages::microservices::server::server-mqtt::ServerMqtt::handleMessage
        → [CALLS] packages::microservices::server::server-mqtt::ServerMqtt::getPublisher  [method]  packages/microservices/server/server-mqtt.ts:192
      packages::microservices::server::server-mqtt::ServerMqtt::getPublisher
        → [USES] queue_producer:unresolved:mqtt @packages/microservices  [queue_producer]  packages/microservices/client/client-mqtt.ts:278

  path 2  (5 hops)
      queue_consumer:unresolved:mqtt @packages/microservices
        ⇒ [HANDLED_BY] packages::microservices::server::server-mqtt::ServerMqtt::bindEvents  [method]  packages/microservices/server/server-mqtt.ts:107
      packages::microservices::server::server-mqtt::ServerMqtt::bindEvents

[... trace truncated: 7246 of 8799 chars omitted to fit budget=1600. Narrow the query or raise budget.]
```

---

## Reproduce

```bash
git clone --depth 1 https://github.com/nestjs/nest.git /tmp/nestjs
uvx mcp-repo-graph --repo /tmp/nestjs
```

The graph is cached in `/tmp/nestjs/.glia/graph/` — a sharded binary `.gmap`, rebuilt automatically when the source changes.
