# repo-graph handoff — glia 0.5.4 -> 0.5.5

For: repo-graph (the MCP server wrapping glia-py). Pin: `glia-py==0.5.5`. Apply after the 0.5.4 handoff (`dev-notes/repo-graph-handoff-0.5.4.md`).

0.5.5 is additive: Lua, from Brian Ealdwine's glia PR #3 (plan `dev-notes/next-leap-0.5.5.md`). No API, keyword,
dict key, CLI flag, registry id, FORMAT_VERSION or MANIFEST_VERSION change.

## Declared changes

1. **Graph contents (`.lua` files are parsed).** A repo with Lua gains MODULE / FUNCTION / METHOD / CLASS nodes, IMPORTS
   (`require`), CALLS, INHERITS_FROM (metatables), TESTS (busted `it` blocks, FUNCTIONs named `<describe ..> <it>`),
   ROUTEs (Lapis) and ENDPOINTs (`socket.http` / `resty.http`). Answers over such a repo grow accordingly; a repo with
   no Lua builds the same graph as 0.5.4. Lua qnames are `<path::module>::<key>` with dotted keys (`M.setup`,
   `Dog.bark`, a nested local `M.setup.helper`); a key may contain spaces (a busted test, a Lapis handler
   `GET /users/:id`).
2. **`health()` / `glia health`.** `.lua` files no longer count in `unparsed`.
3. **PARSER_STAMP / BUILD_STAMP move** (a new parser crate): cached parse caches and layouts rebuild once, and a
   calibration record (`glia history calibrate`) is read only by the build that wrote it, so recalibrate.
4. **stderr.** New `[lua]`, `[imports] lua requires`, `[lua-classes]` and `[lua-calls]` lines (CLAUDE.md, "The 0.5.5
   markers").

## Nothing to change unless

- you filter files by extension before calling glia, and want Lua: add `.lua`;
- you test against a fixed `unparsed` count for a repo holding Lua.
