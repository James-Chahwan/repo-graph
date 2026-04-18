---
name: Parser-vs-graph resolution split
description: Design rule for every v0.4.x language parser — where each kind of cross-reference gets resolved. Locked at v0.4.3b across Python/Go/TypeScript.
type: reference
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
Every new language parser in v0.4.10 (Scala/Ruby/Clojure/C#/Java/Swift/etc.) must follow this split. It's not obvious from any single file — the responsibility is spread across `code-domain`, parser crates, and `graph`.

**Parser crate (`parsers/code/<language>/`)** resolves what its own AST gives it for free:
- Intra-file bare calls (same-module top-level defs) — emit as CALLS edge directly.
- Intra-file self-method dispatch **only** when the AST tells you the enclosing class during the same walk that classifies the call (Python's AST does; Go/TS don't cleanly, so they defer).
- Everything else — cross-file, cross-package, anything that depends on knowing what some other file exports — is emitted as `ImportStmt` + `CallSite` + `CallQualifier` for the graph crate to resolve.

**Graph crate (`rust/graph/`)** runs the 4-stage pipeline uniformly:
1. `merge_parses` — collect all per-file parses, dedup nodes by `NodeId` (multi-file packages collapse, cells stack).
2. `build_symbol_table` — index `module_by_qname`, `module_symbols[mod][name]`, `class_methods[class][name]`. STRUCT is treated identically to CLASS here (for Go).
3. `resolve_imports_<lang>` — language-specific, because import semantics differ (Python dotted qnames + relative levels; Go stripped go.mod prefix; TS raw specifier strings via caller-provided closure).
4. `resolve_calls` — **uniform across all languages**. Bare → bindings then module_symbols; Attribute{base,name} → bindings[base] then MODULE module_symbols or CLASS/STRUCT class_methods; SelfMethod → walk `parent_of` to enclosing CLASS/STRUCT then class_methods lookup; ComplexReceiver → unresolved.

**`extra_hook` seam** — `resolve_calls<H>(g, calls, H: Fn(&RepoGraph, &CallSite) -> Option<NodeId>)` takes a closure for language-specific shapes the generic pass can't handle. Unused at v0.4.3b (all three languages pass `|_, _| None`). Reserved for shapes like Go method-on-struct-via-package-alias (`pkg.StructVal.Method()`), Scala implicits, etc. — add only when a real case surfaces, don't speculate.

**Why SelfMethod moved up to graph.** Originally thought each parser would resolve its own self-calls. Dropped that: the walk `parent_of → CLASS/STRUCT → class_methods[name]` is identical regardless of language. Python's parser still resolves `self.x` intra-file (its tree-walk tracks enclosing class naturally), which just means zero SelfMethod emissions reach the graph crate — harmless no-op. Go/TS emit SelfMethod and the graph crate resolves. New language parsers should default to emitting SelfMethod and letting the graph crate handle it — only inline-resolve if it's trivially free from the AST walk.

**Why import resolution stays per-language.** Import semantics are genuinely different:
- Python: dotted qnames with relative levels (`from ..helpers import x`, level=2).
- Go: go.mod prefix strip at parse time → `ImportTarget::Module { path }` with repo-local `::` qname.
- TS: raw source strings (`./user`, `@angular/core`) that only the caller knows how to resolve — hence `Fn(&str, &str) -> Option<String>` closure on `build_typescript`.

Trying to unify these loses information. Three `resolve_imports_<lang>` functions is the right shape.

**Attribute resolution rule.** `CallQualifier::Attribute { base, name }` resolves by:
1. Look up `base` in `module_import_bindings[from_mod]` to get a node id.
2. If that node's kind is MODULE → look name up in its `module_symbols`.
3. If kind is CLASS or STRUCT → look name up in `class_methods`.
4. Otherwise unresolved.

This is why TS namespace imports (`import * as helpers from ...`) work: the namespace alias binds to the MODULE itself, so `helpers.hashPassword` hits case 2.

**Same-NodeId dedup is load-bearing for multi-file packages.** Go packages span multiple files, each emitting a Module node with the same `(GRAPH_TYPE, repo, MODULE, package_qname)`. `merge_parses` keys an index by NodeId and appends cells onto the existing node when a duplicate arrives. Without this, multi-file Go packages would appear as N separate module nodes and cross-file resolution would break.

**Test fixture pattern.** For every new language parser, add `tests/fixtures/<lang>_smoke/` with files that exercise: intra-file bare, cross-file named-import bare, namespace-import attribute, self-method, and one intentionally-unresolved call (receiver of unknown type). Mirror the py_smoke / go_smoke / ts_smoke structure — keeps the smoke tests uniform and the resolver contract visible.
