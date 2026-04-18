---
name: CrossGraphResolver backlog for v0.4.10
description: Stack-boundary resolvers beyond HttpStackResolver — captured at v0.4.4 start to drive the 0.4.10 frontend batch + cross-cutting resolver work
type: project
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**Context.** v0.4.4 ships `CrossGraphResolver` trait + `HttpStackResolver` (fetch/axios → REST route). Every other stack-boundary resolver was deferred. User at v0.4.4 kickoff 2026-04-17: *"make a note of all the graphql grpc etc type stack resolvers we will need for 0.4.10"*.

**Why:** quokka-stack's cross-repo edges are HTTP-only, but real stacks glue together through many other boundaries. The resolver trait must accommodate all of these from day one — if `HttpStackResolver` locks in a shape that doesn't generalise, refactor cost in 0.4.10 is painful.

**Landing order (all in 0.4.10 unless marked):**

- **HttpStackResolver** — v0.4.4 (the baseline). Fetch/axios/`http.Client{}.Get` call sites → route handlers. Needs: route extraction in parser-go (chi/gin/mux/net-http) + parser-typescript (fetch/axios/got/ky). Matches frontend `endpoint_*` → backend `route_*` (quokka produces 18 of these).

- **GraphQLStackResolver** — 0.4.10. Frontend: Apollo client, urql, graphql-request, graphql-tag template literals. Backend: Apollo server, graphql-yoga, Nexus, TypeGraphQL, pothos, gqlgen (Go), strawberry/graphene (Python). Matching axis: operation name + schema location. Shape edge: query `GetUser` → resolver `Query.user` → backing fn.

- **GrpcStackResolver** — 0.4.10. Shared `.proto` files. Client: `NewFooServiceClient` / `FooServiceClient(channel)`. Server: `RegisterFooServiceServer` / `FooServiceServicer`. Matching axis: service + method name via .proto AST. Python 0.2.0 already has `grpc.py` cross-cutting analyzer — port that heuristic.

- **QueueStackResolver** — 0.4.10. Producer publishes (Kafka `Producer.Send`, SQS `SendMessage`, NATS `Publish`, Redis `XADD`, Celery `.delay()`, BullMQ `queue.add`, Sidekiq `perform_async`) → consumer subscribes (Kafka consumer group, SQS long-poll, NATS subscribe, Celery task fn, BullMQ processor, Sidekiq worker). Matching axis: topic/queue name string, shared across producer+consumer. Python 0.2.0 has `queues.py` — port.

- **WebSocketStackResolver** — 0.4.10. Client: `new WebSocket(url)`, `socket.io-client.connect(...)`, `useWebSocket`. Server: `ws.on("connection")`, socket.io server, Phoenix channels, Gorilla WS. Matching axis: URL path + event name.

- **SharedSchemaResolver** — 0.4.10. Zod/Joi/ajv/Yup/pydantic schemas imported by both sides. Matching axis: exported schema symbol referenced across repos. Often the silent connective tissue in typed stacks. Shape edge: frontend validator usage → backend validator usage → shared schema def node.

- **EventBusResolver** — 0.4.10. In-process pub/sub (EventEmitter, RxJS Subject), cross-service event brokers (EventBridge, CloudEvents, NATS JetStream). Often overlaps QueueStackResolver — decide at impl whether to merge or keep separate.

- **DatabaseStackResolver** — 0.4.10 (lower priority). ORM model → migration file → schema table → possibly admin panel. Probably intra-repo most of the time; cross-repo applies when schema packages are vendored.

- **CliInvocationResolver** — 0.4.10 (maybe). `exec.Command("tool", ...)` / `child_process.spawn("tool")` → cobra command in another repo. Niche but real for monorepo tooling stacks.

**Non-HTTP axes (beyond stack resolvers).** These are `CrossGraphResolver` implementations too, they just resolve a different axis:

- **TeamOwnershipResolver** — CODEOWNERS → `OWNED_BY` edges from nodes to Team entities.
- **SecurityZoneResolver** — IAM/policy/service-account boundary crossings.
- **RuntimeZoneResolver** — browser / server / edge-worker / background-worker runtime boundaries (one codebase, multiple runtimes).

**Design implication for v0.4.4 trait shape.** The trait must handle:
1. Name-based matching (HTTP path strings, queue topic names) — the primary use case for HTTP.
2. Shared-symbol matching (same proto message imported both sides, same Zod schema).
3. File-based matching (.proto files, OpenAPI yaml, migration files).

If `HttpStackResolver`'s signature is too tuned to case 1, the others will need adapter shims. Keep the trait generic: `fn resolve(&self, graph: &MergedGraph) -> Vec<Edge>` — resolvers own their own matching heuristics, the merge machinery just exposes nodes and symbols.

**Test corpus plan.** quokka-stack for HTTP. Future resolvers need their own fixture pairs — one frontend caller + one backend handler per resolver type. Store under `tests/fixtures/<resolver>_smoke/`.
