# repo-graph

[![repo-graph MCP server](https://glama.ai/mcp/servers/James-Chahwan/repo-graph/badges/card.svg)](https://glama.ai/mcp/servers/James-Chahwan/repo-graph)

**Structural graph memory for AI coding assistants.** Map your codebase. Navigate by structure. Read only what matters.

repo-graph gives LLMs a map of your codebase — entities, relationships, and flows — so they can navigate to the right files without reading everything first.

Instead of flooding an LLM's context window with your entire codebase (or hoping it guesses right), repo-graph builds a lightweight graph of what exists, how things connect, and where the entry points are. The LLM queries the graph, finds the minimal set of files it needs, and reads only those.

## Demo

https://github.com/user-attachments/assets/a1e4171b-b225-40d4-9210-39453e14b76a

https://github.com/user-attachments/assets/fc3191e5-fc35-4bd7-8372-72af55995883

Same bug, same model, same prompt — the only difference is whether repo-graph is installed.

**The task:** fix a reversed comparison operator in a Go + Angular monorepo (566 nodes, 620 edges).

| | Without repo-graph | With repo-graph |
|---|---|---|
| **Tokens used** | 75,308 | 29,838 |
| **Time to fix** | 4m 36s | ~30s |
| **Files explored** | ~15 (grep, read, grep, read...) | 2 (flow lookup + handler file) |
| **Outcome** | Found and fixed the bug | Found and fixed the bug |

**2.5x fewer tokens. ~9x faster. Same correct fix.**

### How the test was run

Both runs used identical conditions to keep the comparison fair:

- **Same model**: Claude Opus, 100% (no Haiku routing)
- **Same prompt**: *"Groups that were created recently are showing as closed, and old groups show as open. This is backwards — new groups should be open for members to join. Find and fix the bug."*
- **Fresh context**: each run started from `/clear` with no prior conversation
- **No other tools**: CLAUDE.md, plugins, hooks, and all other MCP servers were removed for both runs — the only variable was whether repo-graph was installed
- **No hints**: the prompt describes the symptom, not the location — Claude has to find `group_controller.go:57` on its own

Without repo-graph, Claude greps for keywords, reads files, greps again, reads more files, and eventually narrows down to the bug. With repo-graph, Claude calls `flow("groups")`, gets back the exact handler function and file, reads it, and fixes it.

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

Then it exposes 13 MCP tools that let the LLM:

1. **Orient** — "What languages are in this repo? What are the main features?"
2. **Navigate** — "Trace the login flow from route to database" / "What's the shortest path between UserService and the payments API?"
3. **Scope** — "How many lines would I need to read to understand this feature?" / "Give me just the files I need for this bug fix"
4. **Assess** — "What's the blast radius of changing this function?" / "Which files are the biggest maintenance risks?"

The LLM gets structural context in a few hundred tokens instead of reading thousands of lines.

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

```bash
pip install mcp-repo-graph
```

Python 3.11+. Installs two packages: `mcp-repo-graph` (the MCP server) and `repo-graph-py` (the Rust engine, as a prebuilt wheel).

## Quick start

### 1. Initialise the target repo

```bash
repo-graph-init --repo /path/to/your/project
```

This generates the graph, writes `.mcp.json` and CLAUDE.md instructions, and gets your AI assistant ready to use repo-graph.

### 2. Connect to your AI assistant

If you skipped `repo-graph-init`, add this to your MCP configuration manually:

**Claude Code** (`~/.claude/claude_code_config.json` or project `.mcp.json`):
```json
{
  "mcpServers": {
    "repo-graph": {
      "command": "repo-graph",
      "args": ["--repo", "/path/to/your/project"]
    }
  }
}
```

**With environment variable:**
```json
{
  "mcpServers": {
    "repo-graph": {
      "command": "repo-graph",
      "env": { "REPO_GRAPH_REPO": "/path/to/your/project" }
    }
  }
}
```

### 3. Use it

The AI assistant now has access to all 13 tools. Example queries it can answer:

- *"What does this codebase do?"* → `status` tool
- *"Trace the checkout flow"* → `flow` tool
- *"What would break if I change UserService?"* → `impact` tool
- *"What files do I need for this bug?"* → `minimal_read` tool
- *"This file is too big, how should I split it?"* → `split_plan` tool
- *"Show me the auth flow visually"* → `graph_view` tool

### 4. Keep it fresh with a git hook (recommended)

Add a call to `generate` via your MCP client to a pre-commit hook so the graph stays up to date automatically — no LLM context spent on regeneration:

```bash
# .git/hooks/pre-commit (or add to your existing hook)
#!/bin/sh
repo-graph --repo . --regenerate
git add .ai/repo-graph/
```

```bash
chmod +x .git/hooks/pre-commit
```

Every commit keeps the graph current. The LLM always has a fresh map without wasting a single token on `generate`.

> **Tip:** If you don't want graph data in version control, add `.ai/repo-graph/` to `.gitignore` and skip the `git add` line — the graph will just live locally.

## MCP tools reference

### Generation

| Tool | Parameters | Description |
|------|-----------|-------------|
| `generate` | *(none)* | Scan the codebase from scratch, rebuild the graph, and reload |
| `reload` | *(none)* | Reload graph data from disk (after external regeneration) |

### Navigation

| Tool | Parameters | Description |
|------|-----------|-------------|
| `status` | *(none)* | Repo overview: git state, detected languages, entity counts, available flows |
| `flow` | `feature` | End-to-end flow for a feature — from entry point through service layer to data |
| `trace` | `from_id`, `to_id` | Shortest path between any two nodes in the graph |
| `impact` | `node_id`, `direction` (`upstream`/`downstream`), `depth` | Fan out from a node to see what it affects or depends on |
| `neighbours` | `node_id` | All direct connections to and from a node |

### Context budgeting

| Tool | Parameters | Description |
|------|-----------|-------------|
| `cost` | `feature` | Total line count for all files in a feature's flow |
| `hotspots` | `top_n` | Files ranked by `size * connections` — maintenance risk indicators |
| `minimal_read` | `feature`, `task_hint` | Smallest file set needed for a specific task within a feature |

### Health analysis

| Tool | Parameters | Description |
|------|-----------|-------------|
| `bloat_report` | `file_path` | Internal structure of a file: functions/methods ranked by size, type counts |
| `split_plan` | `file_path` | Concrete suggestions for splitting an oversized file, grouped by responsibility |
| `graph_view` | `feature` or `node`, `depth` | Visual ASCII map of a feature flow, node neighbourhood, or full graph overview |

## How it works

`mcp-repo-graph` is a thin Python MCP server that wraps **glia**, a Rust engine.

1. **Parse** — per-language tree-sitter parsers extract raw nodes and unresolved references
2. **Extract** — cross-cutting extractors layer on HTTP routes, data sources, CLI entrypoints, gRPC services, queue consumers
3. **Resolve** — graph builder resolves intra-repo references; cross-graph resolvers link stacks (frontend HTTP calls → backend routes, etc.)
4. **Store** — merged graph lands in `.ai/repo-graph/` as a zero-copy `.gmap` (rkyv + mmap) plus JSON projections for portability
5. **Serve** — the MCP server loads the graph into memory and exposes the 13 tools

The Rust engine will split into its own [`glia`](https://github.com/James-Chahwan/repo-graph) repo post-v0.4.12. `mcp-repo-graph` will remain the MCP-facing thin wrapper.

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
