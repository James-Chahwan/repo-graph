---
name: Tree-sitter grammar quirks across languages
description: Known AST structure surprises in tree-sitter grammars that differ from expected node kinds/field names; reference for future parser work
type: reference
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
### Linking conflicts
- `tree-sitter-clojure v0.1` depends on tree-sitter 0.25, conflicts with workspace 0.26. Use `tree-sitter-clojure-orchard v0.2` instead.
- Grammars using `tree-sitter-language` crate (dart, elixir, solidity, hcl, clojure-orchard) avoid native linking conflicts entirely.

### Swift (tree-sitter-swift v0.7.1)
- `class_declaration` used for ALL type declarations: class, struct, enum, actor, protocol
- Distinguish via unnamed keyword child: `"struct"`, `"enum"`, `"actor"`, `"protocol"`
- Body node found by `_body` suffix match (e.g., `class_body`, `enum_class_body`)

### Dart (tree-sitter-dart v0.1)
- Node kind is `class_declaration` (not `class_definition`)
- No field-named `name` — identifier is an unnamed `identifier` child
- Enum is `enum_declaration` with same pattern
- Methods wrapped in `class_member` → `method_signature` → `function_signature`

### Elixir (tree-sitter-elixir v0.3)
- `arguments` is a named child, NOT field-named
- Module names are `alias` nodes (e.g., `MyApp.Users`)
- `def get_user(id)` — function name is inside a nested `call` node within arguments
- `Repo.get` appears as a `dot` target node, not qualified identifier
- Use `find_args()` helper to locate arguments by kind

### HCL/Terraform (tree-sitter-hcl v1.1)
- Root is `config_file` containing `body` containing `block` nodes (extra wrapper)
- `string_lit` has nested structure: `quoted_template_start` → `template_literal` → `quoted_template_end`
- Must extract `template_literal` child to get unquoted string content
- Block body is a named `body` child, not field-named
