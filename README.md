# repo-graph

[![repo-graph MCP server](https://glama.ai/mcp/servers/James-Chahwan/repo-graph/badges/card.svg)](https://glama.ai/mcp/servers/James-Chahwan/repo-graph)

**Structural graph memory for AI coding assistants.** Map your codebase. Navigate by structure. Read only what matters.

repo-graph gives LLMs a map of your codebase — entities, relationships, and flows — so they can navigate to the right files without reading everything first.

Instead of flooding an LLM's context window with your entire codebase (or hoping it guesses right), repo-graph builds a lightweight graph of what exists, how things connect, and where the entry points are. The LLM queries the graph, finds the minimal set of files it needs, and reads only those.

It pays off most where that's hardest to do by hand: **large repos, monorepos that span several languages, and multi-service systems** where a feature's path crosses files, stacks, and service boundaries. On a small single-language project a model can just read the files — see [Where it fits best](#where-it-fits-best) for the honest sweet spot.

**Install in one click:**

[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white)](https://vscode.dev/redirect/mcp/install?name=repo-graph&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22mcp-repo-graph%22%2C%22--repo%22%2C%22.%22%5D%7D)
[![Install in VS Code Insiders](https://img.shields.io/badge/VS_Code_Insiders-Install-24bfa5?style=flat-square&logo=visualstudiocode&logoColor=white)](https://insiders.vscode.dev/redirect/mcp/install?name=repo-graph&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22mcp-repo-graph%22%2C%22--repo%22%2C%22.%22%5D%7D&quality=insiders)
[![Add to Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/install-mcp?name=repo-graph&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtY3AtcmVwby1ncmFwaCIsIi0tcmVwbyIsIi4iXX0%3D)

Or one command in your terminal wires up every agent you have: `uvx mcp-repo-graph install` (see [Install](#install)).

## Demo

https://github.com/user-attachments/assets/a1e4171b-b225-40d4-9210-39453e14b76a

https://github.com/user-attachments/assets/fc3191e5-fc35-4bd7-8372-72af55995883

Same bug, same model, same prompt — the only difference is whether repo-graph is installed.

**The task:** fix a reversed comparison operator in a Go + Angular monorepo (566 nodes, 620 edges).

| | Without repo-graph | With repo-graph |
|---|---|---|
| **Tokens used** | 75,308 | 29,838 |
| **Time to fix** | 4m 36s | ~30s |
| **Files explored** | ~15 (grep, read, grep, read...) | 2 (trace lookup + handler file) |
| **Outcome** | Found and fixed the bug | Found and fixed the bug |

**2.5x fewer tokens. ~9x faster. Same correct fix.**

### How the test was run

Both runs used identical conditions to keep the comparison fair:

- **Same model**: Claude Opus, 100% (no Haiku routing)
- **Same prompt**: *"Groups that were created recently are showing as closed, and old groups show as open. This is backwards — new groups should be open for members to join. Find and fix the bug."*
- **Fresh context**: each run started from `/clear` with no prior conversation
- **No other tools**: CLAUDE.md, plugins, hooks, and all other MCP servers were removed for both runs — the only variable was whether repo-graph was installed
- **No hints**: the prompt describes the symptom, not the location — Claude has to find `group_controller.go:57` on its own

Without repo-graph, Claude greps for keywords, reads files, greps again, reads more files, and eventually narrows down to the bug. With repo-graph, Claude calls `trace("groups")`, gets back the exact handler function and file, reads it, and fixes it.

> Browse [pre-generated examples](examples/) for [FastAPI](examples/fastapi/), [Gin](examples/gin/), [Hono](examples/hono/), and [NestJS](examples/nestjs/) — real graph output you can inspect without installing anything.

## The problem

LLMs working on code waste most of their context on orientation:

- Reading files that turn out to be irrelevant
- Missing connections between components in different languages
- Not knowing where a feature starts or what it touches
- Loading 50 files when 5 would do

This is expensive, slow, and gets worse as codebases grow.

## How repo-graph solves it

repo-graph scans your codebase once and builds a graph of:

- **Entities**: modules, packages, classes, functions, routes, services, components
- **Relationships**: imports, calls, handles, defines, contains, cross-stack HTTP
- **Flows**: end-to-end paths from entry point to data layer

Then it exposes 6 MCP tools that let the LLM:

1. **Orient** — "What languages are in this repo? What are the main features? Where is the graph blind?"
2. **Navigate** — "Trace the login flow from route to database" / "What's the shortest path between UserService and the payments API?"
3. **Scope** — "Which nodes matter for this bug?" / "Give me just the files I need for this fix"
4. **Assess** — "What's the blast radius of changing this function?" / "What here is dead code?"

The LLM gets structural context in a few hundred tokens instead of reading thousands of lines.

## Where it fits best

repo-graph earns its keep when a codebase is bigger or more tangled than the model can hold in its head at once. The payoff scales with three things:

- **Size** — enough files that reading the relevant ones blows the context budget.
- **Complexity** — rules, indirection, and layers, so "just read it" stops working.
- **Cross-boundary reach** — the answer spans files, languages, or services that a text search can't link.

Strong fits:

- **Monorepos** — a frontend calling a backend across a language boundary. repo-graph links the HTTP call to the route it hits and the handler behind it — the one thing grep structurally can't do. Point `--repo` at the monorepo root and a single graph spans every project. *(The demo above is exactly this: Go + Angular in one repo.)*
- **Multi-service / polyrepo systems** — drop the services under one directory and point `--repo` at it; the graph traces a feature across service boundaries in one call.
- **Large single codebases** — thousands of files where orientation itself is the cost.
- **Unfamiliar or legacy code** — where you don't yet know what touches what.

Where it *doesn't* pull its weight: a **small, single-language repo with a clear task**. The model can just read the files — grep wins and the graph is overhead. Don't reach for it to shave tokens, either: the MCP layer is a fixed per-turn cost, so on easy tasks it can cost *more*. The token win shows up only when it heads off a grep-read-grep spiral (like the demo above). What it reliably buys you is **correct, complete, cross-boundary answers in a few calls** on code too big or too interconnected to fit in context — yours or the model's. (Don't want the MCP layer at all? [Skip it](#use-it-without-mcp) and call the engine directly.)

## Use it without MCP

The MCP server is the zero-config path, but the graph isn't tied to it. The engine ships as a plain Python wheel — `pip install repo-graph-py` — so you can build the graph and call the same answer primitives directly, from a script or your own tooling, with **none of the per-turn MCP cost**:

```python
import repo_graph_py as rg

g = rg.generate(".")                            # or rg.load_from_gmap(rg.default_gmap_dir("."))
print(g.blast_radius("checkout", "both"))       # ranked, located, live-filtered — JSON
print(g.cross_stack_trace("notifications"))     # feature path across the stack, mechanism-labelled
print(g.resolve(open("error.log").read()))      # stacktrace / test / diff → the nodes that matter
print(g.coverage())                             # where extraction is partial (grep those)
```

Same graph, same answers — just without the tool schemas in your context. It's the same Rust engine ([glia](https://github.com/James-Chahwan/glia)) the MCP server wraps; `repo-graph-py` is its published wheel. Good for CI checks, batch analysis, or wiring the graph into your own agent.

## Supported languages

| Language | Detection | What it extracts |
|----------|-----------|-----------------|
| **Go** | `go.mod` | Packages, functions, HTTP routes (gin/echo/chi/stdlib), imports |
| **Rust** | `Cargo.toml` | Crates, modules, structs, traits, functions, routes (Actix/Rocket/Axum) |
| **TypeScript** | `tsconfig.json` / `package.json` | Modules, classes, functions, import relationships |
| **React** | `react` in `package.json` | Components, hooks, context providers, React Router routes, fetch/axios calls, flows |
| **Angular** | `@angular/core` in `package.json` | Components, services, guards, DI injection, HTTP calls, feature flows |
| **Vue** | `vue` in `package.json` | SFCs, composables, Vue Router routes, fetch/axios calls |
| **Python** | `pyproject.toml` / `setup.py` / `requirements.txt` | Packages, modules, classes, functions, routes (Flask/FastAPI/Django) |
| **Java/Kotlin** | `pom.xml` / `build.gradle` | Packages, classes, routes (Spring/JAX-RS/Ktor/WebFlux/Micronaut) |
| **Scala** | `build.sbt` | Packages, objects/classes/traits, routes (Play/Akka HTTP/http4s) |
| **Clojure** | `project.clj` / `deps.edn` | Namespaces, defn/defprotocol/defrecord, routes (Compojure/Reitit) |
| **C#/.NET** | `.csproj` / `.sln` | Namespaces, classes, routes (ASP.NET/Minimal API) |
| **Ruby** | `Gemfile` / `.gemspec` | Files, classes, modules, Rails routes |
| **PHP** | `composer.json` | Namespaces, classes, interfaces, routes (Laravel/Symfony) |
| **Swift** | `Package.swift` / `.xcodeproj` | Files, types (class/struct/enum/protocol/actor), Vapor routes |
| **C/C++** | `CMakeLists.txt` / `Makefile` / `meson.build` | Sources, headers, classes, structs, enums, namespaces, includes |
| **Dart/Flutter** | `pubspec.yaml` | Modules, classes, widgets, go_router/shelf routes |
| **Elixir/Phoenix** | `mix.exs` | Modules, functions, Phoenix router scopes + routes |
| **Solidity** | `.sol` files / `foundry.toml` / `hardhat.config.*` | Contracts, interfaces, libraries, events, inheritance |
| **Terraform** | `.tf` files | Modules, resources, variables, outputs, module sources |
| **SCSS** | `.scss` files present | File-level bloat analysis |

Cross-cutting extractors (work across all languages):

- **Data sources** — DB/cache/queue/blob/search/email client detection
- **CLI entrypoints** — Python click, JS commander/yargs, Go cobra, Rust clap
- **gRPC** — service/method definitions from `.proto` files
- **Queue consumers** — Celery, Dramatiq, BullMQ, Sidekiq, Oban, NATS
- **Cross-stack HTTP** — frontend `fetch`/`axios` calls linked to backend routes

Multiple languages can match one repo (e.g., Go backend + Angular frontend + SCSS). Each contributes its nodes and edges into a single unified graph.

## Install

### One command

```bash
uvx mcp-repo-graph install
```

This detects the AI coding agents you have installed (Claude Code, Claude Desktop,
Cursor, Windsurf, VS Code, Codex, Gemini CLI, opencode, Kiro), writes each one's
MCP config, and adds a short usage block to its instructions file so the agent
reaches for the graph before it greps. Where the agent supports it, it also grants
auto-allow so repo-graph tools don't prompt on every call.

It's safe to re-run, and `uvx mcp-repo-graph uninstall` reverses everything
(config, instructions, permissions) while leaving your graph data in place.

```bash
uvx mcp-repo-graph install --agents all          # every supported agent, not just detected
uvx mcp-repo-graph install --scope user          # your global config, not this project
uvx mcp-repo-graph install --dry-run             # show what it would write, change nothing
uvx mcp-repo-graph install --yes                 # no prompt (scripts and CI)
uvx mcp-repo-graph install --print-config cursor # print one agent's config, write nothing
```

### Manual, per client

If you'd rather wire it up yourself, the package name **is** the run command.
`uvx mcp-repo-graph` just works. No prior `pip install`, nothing to keep on
`PATH`. This is the same command VS Code, Cursor, and the MCP registry use under
the hood.

**Requirements:** Python 3.11+, and [`uv`](https://docs.astral.sh/uv/) if you use the
`uvx` path. Prebuilt wheels ship for the Rust engine on Linux (x86_64, aarch64),
macOS (Intel + Apple Silicon), and Windows (x86_64) — no Rust toolchain needed.

### Claude Code

```bash
claude mcp add repo-graph -- uvx mcp-repo-graph --repo .
```

(`--repo .` points the graph at the current project; use an absolute path to pin it.)

### VS Code

One command — adds the server to your user config:

```bash
code --add-mcp '{"name":"repo-graph","command":"uvx","args":["mcp-repo-graph","--repo","${workspaceFolder}"]}'
```

Or click **Install** on the [MCP gallery](https://code.visualstudio.com/mcp) entry,
or add it to `.vscode/mcp.json` manually (see below).

### Cursor / any MCP client — manual config

Add this to your client's MCP config (`.mcp.json`, `.cursor/mcp.json`,
`.vscode/mcp.json`, or `~/.claude.json`):

```json
{
  "mcpServers": {
    "repo-graph": {
      "command": "uvx",
      "args": ["mcp-repo-graph", "--repo", "/path/to/your/project"]
    }
  }
}
```

Prefer a persistent install? `pip install mcp-repo-graph` (or `uv tool install
mcp-repo-graph`) puts a `mcp-repo-graph` / `repo-graph` command on your `PATH`; then
use `"command": "mcp-repo-graph"` in the config above.

**`--repo` also accepts a git URL.** Point it at any public repo without cloning
first — it shallow-clones and maps it (requires `git`):

```bash
uvx mcp-repo-graph --repo https://github.com/org/repo
```

## Quick start

### 1. Initialise the target repo (optional)

```bash
uvx --from mcp-repo-graph repo-graph-init --repo /path/to/your/project
# or, if installed:  repo-graph-init --repo /path/to/your/project
```

This generates the graph, writes `.mcp.json` and CLAUDE.md instructions, and gets your
AI assistant ready to use repo-graph. If you used the one-liners above, you can skip
this — the server builds the graph on first connect.

### 2. Use it

The AI assistant now has access to all 6 tools. Example queries it can answer:

- *"What does this codebase do?"* → `orient` tool
- *"Trace the checkout flow"* → `trace` tool
- *"What would break if I change UserService?"* → `impact` tool
- *"Which nodes are relevant to this bug?"* / *"Here's a stacktrace — where do I look?"* → `find` tool
- *"Show me that function's source"* → `read` tool
- *"Give me the full graph context cheaply"* → `orient full=true`
- *"Rebuild after a big refactor"* → `refresh` tool

### 3. Freshness (automatic)

The graph stays current on its own. While the server is running it watches the repo
and does an incremental rebuild a moment after you save, so a structural question
right after an edit reflects the change with no manual `refresh`. On top of that, the
graph refreshes on cold start whenever the source tree changed since the cached
`.gmap` was written, so it's never stale when your assistant connects.

The watcher is on by default. Set `REPO_GRAPH_WATCH=0` to disable it (the cold-start
refresh still applies). It needs the `watchdog` package, which ships as a dependency.

Want the cache pre-built and committed so teammates and CI get it too? Add the
pre-commit hook automatically:

```bash
uvx mcp-repo-graph install --agents none --git-hook
```

That installs a marker-fenced `pre-commit` hook that refreshes the graph and stages
`.ai/repo-graph/` on every commit. `uvx mcp-repo-graph uninstall` removes it again.

> **Tip:** If you don't want graph data in version control, add `.ai/repo-graph/` to `.gitignore` and skip the hook — the watcher and cold-start refresh keep it fresh locally.

## MCP tools reference

repo-graph exposes **6 tools** — one natural verb each, backed by a Rust engine primitive.

| Tool | Parameters | Description |
|------|-----------|-------------|
| `orient` | `seed` *(optional)*, `full`, `budget` | The first call on a repo: node/edge counts, detected kinds, entry points, and a **blind-spots** note flagging which languages/edges are under-linked (so you grep those deliberately). `seed=<node>` → scoped map; `full=true` → whole-repo dense map |
| `find` | `query`, `expand`, `kind`, `top_k`, `budget` | Turn any text into the ranked nodes that matter — a symbol/keyword, or a pasted stacktrace / failing-test id / diff (resolved to the code it implicates). `expand=true` fans out to the surrounding neighbourhood. Every row carries `path:line` |
| `impact` | `nodes` *(comma-separated)*, `direction`, `depth`, `live_only`, `top_k`, `budget` | Blast radius: what a change affects (`forward`) or depends on / is used by (`backward`), as a ranked, located closure — each row with the edge `via` reason and a `⊘` when the engine finds it unreachable (likely dead). Pass several nodes for a whole-diff radius |
| `trace` | `from_node`, `to_node` *(optional)*, `depth`, `budget` | One arg: a feature end-to-end across the stack, each hop labelled with its mechanism (call / HTTP / queue / event) and cross-service hops marked. Two args: the shortest path between two nodes |
| `read` | `node` *(comma-separated)*, `context_lines`, `budget` | A node's exact source, sliced from its file by the graph's line span, plus a `context:` footer (HTTP method, cross-stack callers, covering tests, governing docs). Comma-separate to batch-read a ranked set |
| `refresh` | `repo_path` *(optional)*, `full` | Rebuild the graph (incremental by default — only changed files re-parse). `repo_path` retargets a different path or git URL; `full=true` forces a clean reparse. Routine edits are auto-picked-up by the file watcher |

Most tools also take a `budget` (max chars) so a result fits a small-model context window.

> These 6 collapsed from an earlier 13 once the engine (v0.4.18) grew answer-shaped primitives — `blast_radius`, `cross_stack_trace`, `resolve`, `coverage` — that return complete, ranked, located, live-filtered results in one call. Fewer tools = less fixed per-turn overhead and less agent confusion.

## How it works

`mcp-repo-graph` is a thin Python MCP server that wraps **glia**, a Rust engine.

1. **Parse** — per-language tree-sitter parsers extract raw nodes and unresolved references
2. **Extract** — cross-cutting extractors layer on HTTP routes, data sources, CLI entrypoints, gRPC services, queue consumers
3. **Resolve** — graph builder resolves intra-repo references; cross-graph resolvers link stacks (frontend HTTP calls → backend routes, etc.)
4. **Store** — merged graph lands in `.ai/repo-graph/` as a zero-copy `.gmap` (rkyv + mmap) plus JSON projections for portability
5. **Serve** — the MCP server loads the graph into memory and exposes the 6 tools

The Rust engine lives in its own [`glia`](https://github.com/James-Chahwan/glia) repo; `mcp-repo-graph` is the MCP-facing thin wrapper.

## Config (optional escape hatch)

If auto-detection misses a weird layout, drop `.ai/repo-graph/config.yaml` in the target repo:

```yaml
skip:
  - legacy       # directory basenames excluded from the walk
  - scratch

roots:           # explicit roots heuristics miss — added on top of auto-detection
  - path: apps/weird-layout
    kind: python
  - path: services/custom
    kind: go
```

`kind` values: `go`, `rust`, `python`, `typescript`, `react`, `vue`, `angular`, `java`, `scala`, `clojure`, `csharp`, `ruby`, `php`, `swift`, `c_cpp`, `dart`, `elixir`, `solidity`, `terraform`. `config.json` works too if you prefer.

## Graph data format

Generated files live in `.ai/repo-graph/` inside the target repo:

- **`nodes.json`** — `[{id, type, name, file_path, confidence, ...}, ...]`
- **`edges.json`** — `[{from, to, type}, ...]`
- **`flows/*.yaml`** — named feature flows with ordered step sequences and `kind` (`http`/`page`/`cli`/`grpc`/`queue`)
- **`state.md`** — human-readable snapshot for quick orientation

Common edge types: `imports`, `defines`, `contains`, `uses`, `calls`, `handles`, `handled_by`, `exports`, `includes`, `tests`, cross-stack HTTP links.

## Privacy Policy

repo-graph runs on your machine and is built to keep your code there. Full text: [PRIVACY.md](PRIVACY.md).

- **Telemetry / analytics:** None. No tracking, no update checks, no phone-home.
- **Data collection & sharing:** None. Your source code and graph data are never sent to repo-graph, its author, or any third party.
- **Local processing & storage:** Scanning and graph-building happen locally; the graph is cached in your project's `.ai/repo-graph/` directory and stays on your device.
- **Network access — only two cases, both user-initiated:**
  1. *Installation* — `uvx`/`pip` downloads the package and its prebuilt engine wheel from PyPI.
  2. *Git-URL targets* — if you pass a git URL to `--repo`, repo-graph runs `git clone` against the URL **you** specified; nothing is sent to repo-graph or its author. A local `--repo` path (the default) makes zero network calls.
- **Data retention:** The local cache persists until you delete it — fully under your control.
- **Contact:** [GitHub issues](https://github.com/James-Chahwan/repo-graph/issues)

## License

MIT

## Support

If repo-graph saved you time, consider buying me a coffee.

<p align="center">
  <a href="https://buymeacoffee.com/polycrisis">
    <img src="docs/bmc-qr.png" alt="Buy Me a Coffee" width="200">
  </a>
  <br>
  <a href="https://buymeacoffee.com/polycrisis">buymeacoffee.com/polycrisis</a>
</p>

<!-- mcp-name: io.github.James-Chahwan/repo-graph -->
