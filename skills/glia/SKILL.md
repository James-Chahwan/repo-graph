---
name: glia
description: Answer structural questions about a codebase with the glia CLI, no MCP server needed. Use it for where X is defined, what changing X (or a diff) affects, how feature Y flows across services, what calls, serves or implements X, what X writes or sends, which tests cover a change, what a change did to the graph, a PR review of a change, whether a change breaks an API client, whether a frontend's model of an API matches what the backend sends, what usually changes with a change, which files a task, ticket or PR title is about, the context for a task packed to a token budget, where the churning, load-bearing or tightly coupled code is, what is one thing across repos, and any structural question a Datalog or GQL query can ask. Reach for it before grep when the question is about structure, not text.
---

# glia from the command line

glia parses a repo into one cross-language graph and answers questions from it. The graph holds calls, imports, the HTTP / gRPC / GraphQL / queue / event / WebSocket links between services, data access, tests and docs. Each answer is one `glia <command> <repo> ...` call. Add `--json` for structured output (progress lines go to stderr). Open the `file:line` an answer gives and read it there rather than grepping for it.

On a repo you have not seen before, run `glia health <repo> --json` first. It says, per boundary mechanism (HTTP, gRPC, RPC, GraphQL, queues, WebSocket), how much of the client and server side the graph pairs, with a verdict `OK`, `DEGRADED` or `BLIND`, plus the code files no parser read and the workspace imports left unbound. Where a mechanism is `BLIND`, an answer that depends on it ("0 breaking", "nothing calls this route") means glia could not see, not that nothing is there: grep for that part instead.

## Which command

| Question | Command |
|---|---|
| Can I trust glia's answers on this repo? Which boundaries can it not see? | `glia health <repo> --json` |
| What services are there, and how do they talk? | `glia arch <repo> --json` |
| Where is X? (a name, qname or fragment) | `glia find <repo> X --json` |
| Which files is this task, ticket or PR title about? | `glia find <repo> "<text>" --files --json` |
| What should I read for task T, within a token budget? | `glia pack <repo> "<T>" --budget 4000 --json` |
| What does this stacktrace / failing test id / diff point at? | `glia resolve <repo> "<signal>" --json` |
| What does changing X affect? | `glia blast-radius <repo> X --json` |
| What does my uncommitted change affect? A pasted diff? | `glia diff-impact <repo> --json`, `glia diff-impact <repo> --diff <file> --json` |
| How does feature Y flow, end to end? | `glia trace <repo> Y --json` |
| What are the entry points, and where does each go? | `glia flows <repo> --json` |
| Which flows touch a concept (a word, not a name: `refund`, `cache`, `webhook`)? | `glia flows <repo> --concept refund --json` |
| Which entry flows pass through X, and how deep? | `glia find <repo> X --flows --json` |
| What starts this code (a Dockerfile, compose service, k8s container, Procfile, systemd unit)? | `glia query <repo> -e 'out(H, T) :- starts(H, T).' --json` |
| Why are A and B connected? | `glia why <repo> A B --json` |
| Who serves `GET /path`, or consumes topic T? | `glia serves <repo> "GET /path" --json` |
| Who implements, extends or overrides X? | `glia implementors <repo> X --json` |
| What does X write, send or call outside the process? | `glia effects <repo> X --json` |
| Which tests cover X, or my change? | `glia tests-for <repo> X --json`, `glia tests-for <repo> --base main --json` |
| What did my change do to the graph? | `glia delta <repo> --json` |
| My change as one PR report: impact, tests, edges, new rule violations? | `glia review <repo> --base main --json` |
| Did my change break a client of an API or message contract? | `glia contract-breaks <repo> --base main --json` |
| Does the frontend's model of an API response or request match the backend's (or the OpenAPI op, or the GraphQL schema)? | `glia contracts <repo> --with <backend> --fields --json` |
| What usually changes along with my change? | `glia cochange <repo> --base main --json` |
| Are there loops between services, or import cycles? | `glia cycles <repo> --json` |
| Does the code break the repo's declared rules or architecture? | `glia check <repo> --json` |
| Which feature flags are dead, undefined, read in one place, or quiet? | `glia flags <repo> --json` |
| What changes often and has much depending on it? | `glia hotspots <repo> --json` |
| What are the tightly coupled clusters? | `glia communities <repo> --json` |
| What carries the most load: utilities, orchestrators, cross-service connectors? | `glia hubs <repo> --json` |
| A structural question no command answers (every route with no handler, every call from `web/` into `api/`)? | `glia query <repo> -e '<datalog>' --json`, `glia query <repo> --gql -e "MATCH ..." --json` |
| Which packages, messages, contract ops or client / server models are one thing across these repos, and which copies diverged? | `glia identity <repo> --with <other> --json` |
| Where is glia blind in this repo? | `glia coverage <repo> --json` |
| What could glia not pair? What looks dead? | `glia gaps <repo> --json` |
| Which docs govern X? | `glia docs-for <repo> X --json` |

`hotspots`, `cochange` and the `quiet` finding of `flags` read git history from a snapshot, never from git itself: run `glia history sync <repo> --blame` once first (it writes `<repo>/.glia/history-snapshot/`). Without one, `hotspots` and `cochange` come back empty with the absence reason `no_history` (exit 1), and `flags` reports `quiet_evaluated: false`.

The ranked answers read the same snapshot. With one, `blast-radius`, `diff-impact`, `review` and `pack` put the files that usually change with the seeds' files first (co-change first, then PageRank), and `review` / `find --files` rank by past commit messages too. Then `glia history calibrate <repo> --json` replays the repo's own history and records, per answer and seed shape, which ranking predicted its past commits best (`<repo>/.glia/calibration-snapshot/`); each ranked answer then uses that pick and says so in `selection` (`source: calibrated`, or `fallback` with the reason, e.g. `absent` before any calibration, `build_stamp` after a glia upgrade: calibrate again). `pack` is the exception: it never reads the record (calibration changes no pack), and its `selection` reads `fallback` with reason `pack_uncalibrated` for the default ranking. So, once per repo and again after an upgrade: `glia history sync <repo>`, then `glia history calibrate <repo>`. Neither runs inside a build, and without them every answer keeps its structural order. `--ranking ppr|ppr-wide|bfs` forces one ranking instead of the calibrated pick (for `pack`, the ranking itself, default `ppr`), `--no-cochange` drops the co-change tier, and `--top-files <N>` (blast-radius, diff-impact) sizes the ranked `files` list.

The rest of the CLI:
- `glia pages <repo>`: frontend router pages and dead links.
- `glia contracts <repo>`: producer vs consumer message types per queue topic; `--fields` diffs fields (schema copies, OpenAPI vs Pact, and the client / server models in the table above).
- `glia spec-status <repo>`: OpenAPI / feature.yaml operations implemented or missing.
- `glia projects <repo>`: the labels `--scope` takes.
- `glia impact <repo> X`: plain reachability, unranked.
- `glia patterns <repo>`: each service's route-handler convention and the handlers off it.
- `glia splits <repo>`: where a scope splits into services at the least coupling (a suggestion, tier heuristic).
- `glia duplicate-flows <repo>`: entry points whose flows reach the same nodes (an aliased route, a v1 / v2 pair, copies drifting apart).
- `glia timeline build <repo>`, then `glia timeline history <repo> <qname>`: when each edge of a node appeared and went, over the last 20 commits.
- `glia scip import <repo> <index.scip>`: load a compiler-grade SCIP index; the next answer reads its references as FACT-tier CALLS / USES / IMPLEMENTS / INHERITS_FROM.
- `glia embed <repo> --json`: embed every node's text with a local model (bge-small, on the GPU when one works, else the CPU) into `<repo>/.glia/vectors.jsonl`. A snapshot step like `history sync`: run it once, and again after big changes (it re-embeds only nodes whose text changed). With vectors, `find --files` blends their similarity into its text key and `pack` seeds from that order when no name matches the query; `--no-semantic` on either ranks without them. Vectors never add, hide or seed a row anywhere else.
- `glia vocab sync <repo> --json`: record every identifier the tracked files hold (`<repo>/.glia/vocab-snapshot/`). Then an empty `find` names the files a query identifier occurs in although no node is named so (`absence.named_in`), and `gaps` lists identifiers the docs cite that no node models (`named_not_modelled`).
- `glia watch <repo>`: keep the build open in the foreground and print one NDJSON line per change saying what it did to the graph (a ready line first); it rewrites `<repo>/.glia/graph/` on exit and every 60 s. For a long session, not for one question. `--with <other> --out <dir>` watches several repos as one build (the joint layout goes to `<dir>`, never into a repo), `--memory-budget-mb <MB>` caps what the session keeps cached, `--embed` keeps `.glia/vectors.jsonl` current after each update.

`flows --concept` matches a word against each flow's entry name, the names and qnames of its hops, node kinds, mechanisms, data entities, external hosts and doc headings, best tier first, and exits 1 with a `no_match` absence when none does; with vectors (`glia embed`) a word that matches nothing lexically answers at tier `semantic` (heuristic, each row with its `similarity`), and `--no-semantic` never reads them. `glia trace <repo> <word>` falls back to the same search when the word names no node, or only a dead end (`resolved_by: concept`). In `find --flows`, each row's `flows` lists the entry flows through it with the row's `depth` in the flow (0: the row is the entry).

The host graph: a start a Dockerfile (`ENTRYPOINT` / `CMD` of the final stage, or of a stage a compose / k8s file targets), compose, k8s, a Procfile, a systemd unit or a supervisord program declares is a `HANDLED_BY` edge from its INFRA_RESOURCE to the code it runs (through `npm run` / `yarn` scripts, entry shell scripts and a compiled `dist/` path back to its TypeScript source), and that code is an entry. So are the commands, events and callbacks a plugin registers with its host (Neovim, VS Code, Obsidian, webpack, Flask, pytest, LÖVE, WezTerm, nginx / OpenResty). `starts(H, T)`, `host_handles(H, T, E)` and `runs_in(N, H)` (every node a start reaches) are prelude predicates for `glia query`.

`glia <command> --help` lists every flag.

Flags most commands share:
- `--with <repo>` (repeatable) merges more repos in, so links pair across them. With one service per repo, pass the others this way. Each row's file stays relative to its own repo's root.
- `--scope <path-or-label>` narrows the answer within a repo.
- The ranked walks also take `--top-k`, `--depth` and `--direction forward|backward|both`.
- `blast-radius`, `diff-impact` and `review` answer with an overview by default: the ranked `files`, `areas` (every row grouped by sub-project or directory, with `rows`, `files`, `top_file` and the exact `scope` that selects it) and the top 25 rows. Read `areas` first, then ask for one area with `--scope <area's scope>` (`review` takes no `--scope`: ask `diff-impact` for the area), or page the whole answer with `--offset 25`; `truncated.next` names both. `--top-k <N>` sets the rows, `--full` returns every row and field whole.
- `--no-collapse` (on `find`, `blast-radius`, `trace`, `flows`, `tests-for`, `serves` and `arch`) shows one row per copy instead of one per identity class.


Drop `--json` when you only read the answer: the table form is about half the size. Use `--json` when you parse it.

## Reading an answer

- `file` / `line` are 1-based and relative to the repo; open the file there instead of grepping for it.
- `tier`: `fact` (read in the source), `derived` (paired by a resolver) or `heuristic` (a name match). Weigh the answer by it.
- An empty answer carries `absence` with the reason and the edge kinds glia is known to miss; grep for those.
- `live: false` (`⊘`) means no entry point reaches the node.
- In the overview rows, `seed_index` points into `seeds` (a row whose seed is past the 25 shown keeps `seed`), and `name` is left out when it is the qname's last `::` segment.

Every field, exit code and what each command writes: [reference.md](reference.md). Worked runs of every command, input and output: [examples.md](examples.md). Read them only when this page is not enough.

## Before you finish a change

grep finds what is named; glia also finds what is connected under another name. After editing, run one of these and fix what it lists before you stop:

- `glia diff-impact <repo>`: what your uncommitted change reaches across files, services and languages.
- `glia contract-breaks <repo> --base HEAD`: API, schema and client / server model drift your change leaves behind (`--base <rev>` for a committed change).
- `glia review <repo> --base HEAD`: the PR view of the same, with the tests to run.

## Install

1. Put `glia` on PATH: `pipx install glia-cli`, or run it with nothing installed as `uvx --from glia-cli glia <command> ..`; from a glia checkout, `cargo build --release -p glia-cli`, then `cp target/release/glia ~/.local/bin/`. Check it with `glia --version`.
2. Copy this directory (SKILL.md, reference.md, examples.md) to `~/.claude/skills/glia/` (every project) or to `<repo>/.claude/skills/glia/` (one repo).

For an always-on MCP server over the same graph, see repo-graph: https://github.com/James-Chahwan/repo-graph
