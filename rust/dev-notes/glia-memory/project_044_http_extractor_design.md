---
name: v0.4.4 TS HTTP endpoint extractor — syntactic, not framework-specific
description: Design decision for the TypeScript endpoint extractor driving HttpStackResolver; reshaped by quokka_web corpus inspection 2026-04-17
type: project
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**Findings from quokka_web inspection 2026-04-17** (user: *"do a quick check on quokka-stack in directory above this in code quokka-web is angular turps is the go , i know about ws and grpc for go and db etc for later but just check angular"*):

- 52 HTTP calls across 19 files in `quokka_web/src/`. **All Angular HttpClient via DI. Zero fetch. Zero axios.**
- Pattern: `constructor(private readonly http: HttpClient, ...)` + `this.http.post(url, payload, opts)` / `this.http.get(url, opts)` / etc.
- URLs frequently wrapped: `this.apiUrlBuilder.buildApiUrl('auth/login')` → `/api/auth/login`. Sometimes raw string literal.
- `HttpClient` imported from `@angular/common/http`. Identifying it requires either type-aware analysis (DI) or syntactic fallback.

**Implication:** A pure `fetch(url)` / `axios.get(url)` regex extracts zero endpoints from quokka_web. The MVP cross-repo smoke test against the real corpus would be useless.

**Design decision: extractor stays syntactic, ignores framework.**

Match shapes in `parse-typescript`:
1. `this.<name>.(get|post|put|delete|patch)(<first-arg>, ...)` — no type resolution for `<name>` needed. Catches Angular HttpClient + any "service with HTTP client field" pattern generically (ngx-restangular, custom Apollo wrappers, axios-in-a-service, got-in-a-service).
2. `<name>.(get|post|put|delete|patch)(<first-arg>, ...)` where `<name>` is a module-level import alias. Catches direct `axios.get(url)`, `got.get(url)`, `ky.post(url)`.
3. `fetch(<first-arg>, <opts>?)` — method defaults to GET unless opts has `method:`. Standard.

First-arg handling (emits `Endpoint(METHOD, path, confidence)`):
- **String literal** → emit with `confidence=Strong`, path = literal.
- **Template literal with only static parts** → emit with `confidence=Strong`, path = joined text.
- **Template literal with interpolations** → emit with `confidence=Medium`, path = literal prefix + `${…}` placeholder.
- **Call expression** like `this.apiUrlBuilder.buildApiUrl('auth/login')` → pluck innermost string literal as path hint, `confidence=Weak`.
- **Identifier / variable / anything else** → emit with `confidence=Weak`, path = `<unresolved>`, kept for diagnostics.

**Why syntactic over framework-specific.** Angular-specific decorator parsing (`@Injectable`, `@Component`, `providedIn: 'root'`, `@Inject(...)`) stays in 0.4.10 where it joins templates + SCSS. The HTTP call shape is the same across frameworks — a method call on a member holding an HTTP client. Don't need `@Injectable` to know `this.http.post(url)` is an HTTP call.

**Known gap parked for 0.4.10: URL-builder wrapper resolution.** Quokka uses `buildApiUrl('auth/login')` → `/api/auth/login`. The wrapper prepends `/api` or a base URL. To get the full backend-matchable path, need to:
- Detect that `buildApiUrl` is a known URL-builder (by name pattern: `buildUrl`, `buildApiUrl`, `apiUrl`, `endpoint`, etc. OR by locating the fn def and inspecting it).
- Extract the return pattern from the def (e.g. `\`/api/${suffix}\``) and reassemble.
- 0.4.4 smoke test uses literal paths directly to sidestep this. Quokka-stack cross-repo validation is partial until 0.4.10 implements wrapper resolution.

**Go side of HttpStackResolver (parser-go route extraction) — scope for v0.4.4:**
- `net/http` — `http.HandleFunc("/path", handler)`, `mux.HandleFunc("/path", handler)`.
- `chi` — `r.Get("/path", handler)`, `r.Post(...)`, `r.Route("/prefix", func(r Router) {...})`.
- `gin` — `r.GET("/path", handler)`, `r.POST(...)`, `router.Group("/prefix")`.
- Route nodes carry `(METHOD, path)` + `HANDLED_BY` edge to handler fn when the second arg is an identifier. Turps-specific router choice to confirm before final scope.

**HttpStackResolver matching logic:**
- Normalise paths: `/users/:id` == `/users/{id}` == `/users/${x}` — strip leading slash, split on `/`, replace any param-looking segment with `{}`, rejoin.
- Match `Endpoint(METHOD, path)` against `Route(METHOD, path)` with METHOD equal and normalised paths equal.
- Emit `HTTP_CALLS` edge (new EdgeCategory slot, reserved in code-domain registry).
- `confidence` of edge = min(endpoint_confidence, route_confidence).
