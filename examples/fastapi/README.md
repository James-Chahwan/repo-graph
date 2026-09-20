# FastAPI — what repo-graph sees

[https://github.com/fastapi/fastapi](https://github.com/fastapi/fastapi) · Python · routes → handlers → data

Real output from the six tools, captured against the current engine. This is what your assistant gets **before it opens a single file**.

| | |
|---|---|
| Nodes | 19,025 |
| Edges | 20,854 |
| Cross-stack edges | 3,999 |
| Entry points | 3,045 |
| Feature flows | 1,816 |
| Cold build (full reparse) | 0.5s |
| Warm load (cached graph) | 0.18s |

## `orient()`

```
  repo-graph
  ========================================

  19025 nodes, 20854 edges, 3999 cross-stack
  Engine: glia-py 0.5.0 (Rust + tree-sitter)

  Confidence: 12194 strong, 541 medium, 6248 weak

  Node kinds:
     9429 ██████████████████████████████ ● doc_section
     4563 ██████████████████████████████ ƒ function
     1610 ██████████████████████████████ ⌗ attribute
     1150 ██████████████████████████████ ◇ module
      629 ██████████████████████████████ □ class
      609 ██████████████████████████████ ⟁ route
      518 ██████████████████████████████ ↗ endpoint
      313 ██████████████████████████████ ƒ method
       78 ███████████████                ● state_var
       36 ███████                        ⟁ cli_command
       22 ████                           ⟁ ws_handler
        7 █                              ⏲ cron_job
        5 █                              ⊕ package_dep
        4 ▏                              ↗ cli_invocation
        3 ▏                              ⊟ database

  Entry points (1816 flows):
    ⟁ /  [ws_handler]  ·3 reached
    ⟁ /broken_scope  [ws_handler]  ·1 reached
    ⟁ /custom_error/  [ws_handler]  ·2 reached
    ⟁ /depends_err/  [ws_handler]  ·2 reached
    ⟁ /depends_validate/  [ws_handler]  ·2 reached
    ⟁ /function_scope  [ws_handler]  ·1 reached
    ⟁ /items/{item_id}  [ws_handler]  ·1 reached
    ⟁ /items/{item_id}/ws  [ws_handler]  ·5 reached
    ⟁ /named_function_scope  [ws_handler]  ·1 reached
    ⟁ /regular_function_scope  [ws_handler]  ·1 reached
    ⟁ /request_scope  [ws_handler]  ·1 reached
    ⟁ /router  [ws_handler]  ·1 reached
    ⟁ /router/{pathparam:path}  [ws_handler]  ·1 reached
    ⟁ /router2  [ws_handler]  ·1 reached
    ⟁ /router_ws_depends/  [ws_handler]  ·2 reached
    ⟁ /sub  [ws_handler]  ·1 reached
    ⟁ /two_scopes  [ws_handler]  ·1 reached
    ⟁ /ws  [ws_handler]  ·9 reached
    ⟁ /ws/{client_id}  [ws_handler]  ·1 reached
    ⟁ /ws/{item_id}  [ws_handler]  ·2 reached
    ... and 1796 more

  Blind spots (verify these with grep — the graph may under-link them):
    ⚠ CALLS (*): calls through reflection, dynamic dispatch, or higher-order indirection are not resolved
    ⚠ HTTP_CALLS (*): URLs built dynamically (string concat / variables / base-url config) may not pair to a route
    ⚠ QUEUE_FLOWS (*)  [0 found]: topics passed as parameters, runtime variables or env vars - and constants that are ambiguous, or lower-case bindings in another file - are extracted as an unresolved framework tag and never paired; literal constants the repo table resolves are folded
    ⚠ QUEUE_FLOWS (*)  [0 found]: GCP Pub/Sub subscriptions are named independently of their topic, so publisher and subscriber pair only when both name the topic
    ⚠ QUEUE_FLOWS (*)  [0 found]: SNS→SQS fan-out is declared in infrastructure, not code — a producer to an SNS topic will not pair with the SQS consumers it feeds
    ⚠ DOCUMENTS (*): contract JSON (OpenAPI/Swagger, AsyncAPI, Pact) over 512 KB is not read, and one whose format key is outside its first and last 8 KB is not recognised
    ⚠ GRAPHQL_CALLS (*)  [0 found]: GraphQL SDL embedded in code is read only from a GraphQL-marked literal: a gql / graphql tag or call, a buildSchema / MustParseSchema / ParseSchema / from_definition argument, a /* GraphQL */ or #graphql literal, a GRAPHQL / GQL heredoc, or a literal bound to a variable or key named typeDefs / type_defs. SDL kept unmarked in a differently named variable (a plain template in `const schema = ...`, a Go string passed to MustParseSchema by name) is not read: its root types and fields mint no GRAPHQL_RESOLVER, so its clients' operations pair with nothing. `.graphql` / `.gql` files are read whole.
    ⚠ WS_CONNECTS (*): a WebSocket upgrade whose route is registered more than one call away from the upgrading function, or through a router glia does not extract, stays unpaired; a client whose URL has no static path is not paired

  Next: `find <symbol|stacktrace|diff>` to jump to nodes, `impact <node>` for blast radius, `trace <feature>` for flows, `orient <node>` / `orient full=true` for the map.
```

## `find("test_path_operations")`

```
  4 node(s) matching 'test_path_operations':

    ƒ test_path_operations  [function]  tests::test_response_model_sub_types::test_path_operations  tests/test_response_model_sub_types.py:37
    ƒ test_path_operations  [function]  tests::test_tutorial::test_metadata::test_tutorial004::test_path_operations  tests/test_tutorial/test_metadata/test_tutorial004.py:9
    ƒ test_app_path_operation_overrides_generate_unique_id  [function]  tests::test_generate_unique_id_function::test_app_path_operation_overrides_generate_unique_id  tests/test_generate_unique_id_function.py:1160
    ƒ test_router_path_operation_overrides_generate_unique_id  [function]  tests::test_generate_unique_id_function::test_router_path_operation_overrides_generate_unique_id  tests/test_generate_unique_id_function.py:947
```

## `impact("read_item")`

```
  Impact (both) from docs_src::additional_responses::tutorial001_py310::read_item — depth 3

    0.240  ⟁ GET /items/{item_id}  [route]  docs_src/additional_responses/tutorial001_py310.py:19  via HANDLED_BY  ·1
    0.008  □ HTTPException  [class]  fastapi/exceptions.py:17  via CALLS  ·3
    0.003  ↗ GET /items/${…}  [endpoint]  tests/test_tutorial/test_path_params/test_tutorial001.py:18  via HTTP_CALLS  ·2
    0.003  ƒ get_item  [function]  docs_src/dependencies/tutorial008c_an_py310.py:20  via HANDLED_BY  ·2
    0.003  ƒ get_item  [function]  docs_src/dependencies/tutorial008d_an_py310.py:21  via HANDLED_BY  ·2
    0.003  ƒ get_item  [function]  docs_src/dependencies/tutorial008b_an_py310.py:26  via HANDLED_BY  ·2
    0.003  ƒ get_item  [function]  docs_src/dependencies/tutorial008d_py310.py:19  via HANDLED_BY  ·2
    0.003  ƒ get_item  [function]  docs_src/dependencies/tutorial008c_py310.py:18  via HANDLED_BY  ·2

  -- 8 nodes in blast radius
```

## `trace("test_path_operations")`

```
  Trace: test_path_operations  (seed tests::test_response_model_sub_types::test_path_operations)  [resolved by name]

  path 1  (3 hops)
      tests::test_response_model_sub_types::test_path_operations
        → [CALLS] endpoint:GET:/valid1  [endpoint]  tests/test_response_model_sub_types.py:38
      endpoint:GET:/valid1
        ⇒ [HTTP_CALLS] GET /valid1  [route]  tests/test_response_model_sub_types.py:15
      GET /valid1
        ⇒ [HANDLED_BY] tests::test_response_model_sub_types::valid1  [function]  tests/test_response_model_sub_types.py:15

  path 2  (3 hops)
      tests::test_response_model_sub_types::test_path_operations
        → [CALLS] endpoint:GET:/valid2  [endpoint]  tests/test_response_model_sub_types.py:40
      endpoint:GET:/valid2
        ⇒ [HTTP_CALLS] GET /valid2  [route]  tests/test_response_model_sub_types.py:20
      GET /valid2
        ⇒ [HANDLED_BY] tests::test_response_model_sub_types::valid2  [function]  tests/test_response_model_sub_types.py:20

  path 3  (3 hops)
      tests::test_response_model_sub_types::test_path_operations
        → [CALLS] endpoint:GET:/valid3  [endpoint]  tests/test_response_model_sub_types.py:42
      endpoint:GET:/valid3
        ⇒ [HTTP_CALLS] GET /valid3  [route]  tests/test_response_model_sub_types.py:25
      GET /valid3
        ⇒ [HANDLED_BY] tests::test_response_model_sub_types::valid3  [function]  tests/test_response_model_sub_types.py:25

  path 4  (3 hops)
      tests::test_response_model_sub_types::test_path_operations
        → [CALLS] endpoint:GET:/valid4  [endpoint]  tests/test_response_model_sub_types.py:44

[... trace truncated: 255 of 1852 chars omitted to fit budget=1600. Narrow the query or raise budget.]
```

---

## Reproduce

```bash
git clone --depth 1 https://github.com/fastapi/fastapi.git /tmp/fastapi
uvx mcp-repo-graph --repo /tmp/fastapi
```

The graph is cached in `/tmp/fastapi/.glia/graph/` — a sharded binary `.gmap`, rebuilt automatically when the source changes.
