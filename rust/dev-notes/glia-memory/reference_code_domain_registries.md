---
name: Code-domain registries — u32 contract shared across all code-language parsers
description: Locked u32 values for NodeKindId / EdgeCategoryId / CellTypeId in the code domain, plus qname separator and extraction-vs-resolution split. All code parsers (Python, Go, TS, Rust, ...) must agree.
type: reference
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
Locked 2026-04-17 during v0.4.2 (Python parser). Every future code-language parser (Go + TS at v0.4.3b, remaining languages at v0.4.10) **must** use these same u32 slots so multi-repo merge at v0.4.4 and the container header at v0.4.5 can treat them as one domain.

Source of truth lives in `rust/parser-python/src/lib.rs` (constants in `node_kind`, `edge_category`, `cell_type` modules). When v0.4.3 extracts a shared `repo-graph-code-domain` crate, lift them there verbatim.

## Graph-type tag

`"code"` — passed as the first arg to `NodeId::from_parts`. Any graph produced by a code-language parser uses this.

## NodeKindId (u32)

| id | name     | allocated at |
|----|----------|--------------|
| 1  | Module   | v0.4.1       |
| 2  | Class    | v0.4.1       |
| 3  | Function | v0.4.1       |
| 4  | Method   | v0.4.1       |
| 5  | Route    | v0.4.3b      |
| 6  | Package  | v0.4.3b      |
| 7  | Interface| v0.4.3b      |
| 8  | Struct   | v0.4.3b      |
| 9  | Endpoint | v0.4.3b      |

Semantic notes for v0.4.3b slots:
- **Route** — HTTP backend handler registration. Shared Go (gin/echo/chi/stdlib), TS (Express/Fastify/NestJS), Python (Flask/FastAPI/Django). A Route node represents `METHOD /path → handler_qname` and points to the handler Function/Method via `Defines` or `handled_by` (via `Calls`).
- **Package** — larger-than-module unit. Go: `go.mod` root. Rust: crate. TS/JS: `package.json` root. Python: distribution package (not to be confused with the per-file Module). A Package contains Modules.
- **Interface** — Go interface, TS interface, Rust trait, Java interface. Method-set declaration, no body.
- **Struct** — Go struct, Rust struct, TS type-alias struct shapes when declared as types. (C#/Java classes with no methods go to Class.)
- **Endpoint** — TS/JS/Python frontend **caller-side** HTTP call (fetch, axios, HttpClient.get). Matches to a backend Route at v0.4.4 cross-stack merge. Conceptually symmetrical to Route but on the consumer side.

Future slots still reserved (not yet allocated): 10=Enum, 11=Constant, 12=Component (framework), 13=Service (framework).

**Angular/React framework roles (Component, Service, Guard, Directive, Pipe) do NOT get dedicated NodeKind slots.** They're tagged via cells (Intent cell with `{role: "ng_component"}`) on top of a `Class` node. Rationale: there are dozens of framework roles across the ecosystem — slot allocation doesn't scale, cells do. Confirmed 2026-04-17 during v0.4.3b design.

## EdgeCategoryId (u32)

| id | name       | tier         | allocated at |
|----|------------|--------------|--------------|
| 1  | Defines    | structural   | v0.4.1       |
| 2  | Contains   | structural   | v0.4.1       |
| 3  | Imports    | behavioural  | v0.4.1       |
| 4  | Calls      | behavioural  | v0.4.1       |
| 5  | Uses       | behavioural  | v0.4.1       |
| 6  | Documents  | metadata     | v0.4.1       |
| 7  | Tests      | metadata     | v0.4.1       |
| 8  | Injects    | behavioural  | v0.4.3b      |
| 9  | HandledBy  | behavioural  | v0.4.4a      |
| 10 | HttpCalls  | behavioural  | v0.4.4a      |

**HandledBy semantics:** Route → handler Function/Method. Emitted by parser-go when a route registration's second arg is an identifier or selector; the graph crate's `resolve_refs` pass binds the qualifier through the registering module's import table (v0.4.4a).

**HttpCalls semantics:** Endpoint → Route. Emitted by `HttpStackResolver` (v0.4.4b) when a frontend HTTP call's (METHOD, normalised path) matches a backend route. Cross-repo edge — produced after the per-repo build.

**Injects semantics:** dependency injection via constructor types. Angular (`constructor(private svc: UserService)`), NestJS (same), Spring (`@Autowired`), .NET DI. Direction: `Component → Service` (consumer → provider). Kept separate from `Uses` so queries like "what injects this service" are a single category lookup without filtering on node kinds. `Uses` stays for lower-signal relationships (field reads, type mentions) that v0.4.8 cells will attach.

Tier is load-bearing for v0.4.7 HippoRAG spreading activation and flow-traversal priority (behavioural before structural for function sources). See `dev-notes/0.3.0-decisions.md` item "_auto_flows prefer-calls rule" for the background.

## CellTypeId (u32)

| id | name         | payload variant | notes                                |
|----|--------------|-----------------|--------------------------------------|
| 1  | Code         | Text            | raw source slice for the entity      |
| 2  | Doc          | Text            | docstring, stripped of triple-quotes |
| 3  | Position     | Json            | `{"file": str, "start_line": N, "end_line": N}` |
| 4  | Intent       | Text (stub)     | filled at v0.4.8 when auto-derive or LLM-written |
| 5  | RouteMethod  | Json            | `{method, handler?, file, line, col}` — stacks on a Route node, one per HTTP method registered on that path (v0.4.4a) |
| 6  | EndpointHit  | Json            | `{method, path, file, line, col, confidence}` — stacks on an Endpoint node, one per callsite (v0.4.4a) |

Other code-domain cell types land at v0.4.8: Test, Fail, Constraint, Decision, Env, Conv, Attn, Vector. Allocate new u32s sequentially.

## qname separator

`::` — e.g. `myapp::users::User::login`. Matches Rust idiom and avoids filename-dot collisions (`config.prod.py`).

## Extraction vs resolution split (affects v0.4.3 resolver design)

The parser is **dumb about cross-file references**. It records what it sees syntactically and defers disambiguation.

- `u.login()` and `helpers.hash_password()` are both emitted as `CallQualifier::Attribute { base, name }` — same variant, no type inference at parse time.
- v0.4.3's resolver checks: is `base` in the current module's import table? If yes → resolve to imported symbol. If no → drop (local variable, unknown type).
- Same pattern for bare-name calls: intra-file resolution happens in the parser's own post-sweep; cross-file resolution is the v0.4.3 resolver's job using the import table.

Why: type inference would require scope creep the single-file parser can't afford. The import table is the cheap disambiguation signal and it's always available at v0.4.3.

## Node shape per code-domain entity (v0.4.2 baseline)

Every Module/Class/Function/Method node carries:
- Code cell (always)
- Position cell (always)
- Doc cell (optional — only if docstring exists)

Confidence: `Strong` for anything syntactically resolvable. `Medium`/`Weak` reserved for v0.4.3+ when the resolver might emit uncertain edges (e.g., `super()` calls resolved through hierarchy walk that can't find the parent class).

## Tree-sitter toolchain (pinned 2026-04-17)

- `tree-sitter = "0.26"`
- `tree-sitter-python = "0.25"`
- API: `tree_sitter_python::LANGUAGE.into()` → `tree_sitter::Language`; `parser.set_language(&lang)`; `parser.parse(source, None)` → `Option<Tree>`.
- Node accessors: `.kind()`, `.child_by_field_name("name")`, `.named_children(&mut cursor)`, `.start_position()` / `.end_position()` (row/column, 0-indexed).
- Tree-sitter recovers from syntax errors — partial graph emits correctly, which lets us honour the dev-notes "Rust implication: extract valid structural nodes, record error locations" item without extra ceremony.
