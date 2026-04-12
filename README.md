# repo-graph

**Structural graph memory for AI coding assistants.** Map your codebase. Navigate by structure. Read only what matters.

repo-graph gives LLMs a map of your codebase — entities, relationships, and flows — so they can navigate to the right files without reading everything first.

Instead of flooding an LLM's context window with your entire codebase (or hoping it guesses right), repo-graph builds a lightweight graph of what exists, how things connect, and where the entry points are. The LLM queries the graph, finds the minimal set of files it needs, and reads only those.

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
- **Relationships**: imports, calls, handles, defines, contains
- **Flows**: end-to-end paths from entry point to data layer

Then it exposes 12 MCP tools that let the LLM:

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
| **TypeScript** | `tsconfig.json` | Modules, classes, functions, import relationships |
| **React** | `react` in `package.json` | Components, hooks, context providers, React Router routes, fetch/axios calls, flows |
| **Angular** | `@angular/core` in `package.json` | Components, services, guards, DI injection, HTTP calls, feature flows |
| **Python** | `pyproject.toml` / `setup.py` / `requirements.txt` | Packages, modules, classes, functions, routes (Flask/FastAPI/Django) |
| **Java/Kotlin** | `pom.xml` / `build.gradle` | Packages, classes, routes (Spring/JAX-RS) |
| **C#/.NET** | `.csproj` / `.sln` | Namespaces, classes, routes (ASP.NET/Minimal API) |
| **Ruby** | `Gemfile` / `.gemspec` | Files, classes, modules, routes (Rails) |
| **PHP** | `composer.json` | Namespaces, classes, interfaces, routes (Laravel/Symfony) |
| **Swift** | `Package.swift` / `.xcodeproj` | Files, types (class/struct/enum/protocol/actor), routes (Vapor) |
| **C/C++** | `CMakeLists.txt` / `Makefile` / `meson.build` | Sources, headers, classes, structs, enums, namespaces, includes |
| **SCSS** | `.scss` files present | File-level bloat analysis (selector blocks, sizes) |

Multiple analyzers can match one repo (e.g., Go backend + Angular frontend + SCSS). Each contributes its nodes and edges into a single unified graph.

## Install

```bash
pip install mcp-repo-graph
```

Requires Python 3.11+. Only runtime dependency: `mcp[cli]`.

## Quick start

### 1. Generate the graph

```bash
repo-graph-generate --repo /path/to/your/project
```

This scans the codebase and writes graph data to `.ai/repo-graph/` inside the target repo.

### 2. Connect to your AI assistant

Add to your MCP configuration:

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

The AI assistant now has access to all 12 tools. Example queries it can answer:

- *"What does this codebase do?"* -> `status` tool
- *"Trace the checkout flow"* -> `flow` tool
- *"What would break if I change UserService?"* -> `impact` tool
- *"What files do I need for this bug?"* -> `minimal_read` tool
- *"This file is too big, how should I split it?"* -> `split_plan` tool
- *"Show me the auth flow visually"* -> `graph_view` tool

### 4. Keep it fresh with a git hook (recommended)

Add `repo-graph-generate` to a pre-commit hook so the graph stays up to date automatically — no LLM context spent on regeneration:

```bash
# .git/hooks/pre-commit (or add to your existing hook)
#!/bin/sh
repo-graph-generate --repo .
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
| `reload` | *(none)* | Reload graph data from disk (after external `repo-graph-generate`) |

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

1. **Detect** — `scan_project_dirs()` finds project roots (including monorepo layouts like `packages/*`, `apps/*`, `services/*`, `src/*`). Each analyzer checks for its marker files.
2. **Scan** — matching analyzers extract entities and relationships using regex heuristics. No AST parsing, no external toolchains, no build step required.
3. **Merge** — all analyzer results merge into a single graph. Nodes deduplicate by ID, edges by (from, to, type).
4. **Serve** — the MCP server loads the graph into memory and exposes BFS-based traversal tools.

## Graph data format

Generated files live in `.ai/repo-graph/` inside the target repo:

- **`nodes.json`** — `[{id, type, name, file_path}, ...]`
- **`edges.json`** — `[{from, to, type}, ...]`
- **`flows/*.yaml`** — named feature flows with ordered step sequences
- **`state.md`** — human-readable snapshot for quick orientation

Edge types: `imports`, `defines`, `contains`, `uses`, `calls`, `handles`, `handled_by`, `exports`, `includes`.

## Adding a new analyzer

Create `repo_graph/analyzers/<language>.py`:

```python
from .base import AnalysisResult, Edge, LanguageAnalyzer, Node, scan_project_dirs, rel_path, read_safe

class MyLangAnalyzer(LanguageAnalyzer):

    @staticmethod
    def detect(repo_root):
        # Check for language marker files
        return any(
            (d / "my-marker").exists()
            for d in scan_project_dirs(repo_root)
        )

    def scan(self):
        nodes, edges = [], []
        # ... scan files, extract entities, build relationships ...
        return AnalysisResult(
            nodes=nodes,
            edges=edges,
            state_sections={"MyLang": f"{len(nodes)} entities\n"},
        )

    # Optional: file-level analysis for bloat_report / split_plan
    def supported_extensions(self):
        return {".mylang"}

    def analyze_file(self, file_path):
        # Return dict with function/method sizes, class counts, etc.
        pass

    def format_bloat_report(self, analysis):
        # Format the analysis dict into a human-readable string
        pass
```

Register it in `analyzers/__init__.py` by adding it to `_analyzer_classes()`.

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
