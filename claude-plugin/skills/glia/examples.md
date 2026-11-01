# glia worked examples

Read this file when the command table in SKILL.md is not enough: each example is a real run, input and output.


Every example below was run from the root of the repo its comment names. Most are glia's test fixtures (`bench/substrate-gap/fixtures/<name>`). The rest are small git repos built to show a change or a rule. Outputs are trimmed: `…` marks dropped fields and rows.

- `xstack-go-http`: `client/client.go` `FetchUsers` does `http.Get(".../users")`, and `server/main.go` serves `GET /users` with chi.
- `loop`: `orders/` emits `order.placed`, `billing/` handles it and emits `payment.settled`, and `orders/` handles that. The change adds `audit()` to `billing/billing.ts` and calls it from `settle()`.
- `orders-proto`: `proto/orders.proto` declares `message OrderCreated { string order_id = 1; int64 total_cents = 2; repeated string sku = 3; }` on `main`. The change makes `total_cents` a `string` and adds `string currency = 4`.
- `shop`: a Python git repo whose `orders/service.py` and `orders/models.py` changed together in all five of their commits, and `util/money.py` together with `billing/charge.py` in three of its four. `glia history sync . --blame` has been run.
- `identity-proto-diverged`: `orders/`, `billing/` and `shipping/` each hold `proto/orders.proto` with `message OrderCreated`; shipping's copy has an extra field.
- `shop-ranked`: a Python git repo of ten commits: `orders/models.py` and `orders/service.py` changed together in six (one subject is `SHOP-12 orders: round totals`), `util/money.py` and `billing/charge.py` in four, and `docs/tasks.md` holds `- [ ] SHOP-12 round order totals in \`orders/models.py\` and \`orders/service.py\``. `glia history sync . --blame` has been run.
- `models-http-contract`: an Angular `portal/` reads `GET /api/plans/:id` as its `Plan` interface (id, name, priceCents, trialDays); the gin handler in `billing/` writes `planBody` (id, name, priceCents), and the `swagger.json` op documenting the route declares the same three.

```bash
# arch-monorepo-flows: api/ gateway/ web/ worker/ in one repo; one service per top-level dir
glia arch . --json
{"keying":"top_level_dir","services":[{"id":"api","languages":["go","typescript"],"files":4,"nodes":20,"routes":1,"inbound":3,"outbound":1,…},…],
 "links":[{"from":"gateway","to":"api","mechanism":"GRPC_CALLS","channel":"UserService","count":1,"confidence":"medium","example_from_qname":"grpc_client:UserService","example_to_qname":"grpc:user.UserService"},…]}

# xstack-go-http; match tiers run exact_qname > exact_name > … > subsequence
glia find . users --kind FUNCTION --json
{"results":[{"qname":"server::main::listUsers","kind":"FUNCTION","live":true,"file":"server/main.go","line":9,"match":"name_word",…},
            {"qname":"client::client::FetchUsers","live":false,"file":"client/client.go","line":8,…}],"absence":null}

# xstack-go-http; panic.txt is a Go panic whose frame is main.listUsers() at /src/server/main.go:9
# resolve takes signals (a stacktrace, test id or diff; --kind forces one), find takes names
glia resolve . "$(cat panic.txt)" --json
{"results":[{"qname":"server::main::listUsers","kind":"FUNCTION","score":0.571,"live":true,"file":"server/main.go","line":9,…}],"absence":null}

# xstack-go-http; "text" is the pack to paste (without --json, stdout is that text alone); fidelity is full, preview, outline or qname
glia pack . users --budget 4000 --json
{"query":"users","text":"# context for users\n\n### server::main::listUsers (FUNCTION server/main.go:9-9)\n…","budget_tokens":4000,"used_tokens":377,…,"candidates":7,
 "nodes":[{"qname":"GET /users","kind":"ROUTE","file":"server/main.go","line":13,"fidelity":"outline","tokens":11,"rank":1,"tier":"heuristic","reason":"seed",…},
          {"qname":"server::main::listUsers","kind":"FUNCTION","file":"server/main.go","line":9,"fidelity":"full","tokens":35,"rank":3,…,"reason":"seed",…},
          {"qname":"server::main","kind":"MODULE","file":"server/main.go","line":1,"fidelity":"full","tokens":77,"rank":5,"tier":"derived","reason":"neighbour",…},…],"dropped":0,"rerenders":0,"absence":null}

# xstack-go-http; a row names its seed by index into "seeds" ("seed_index"; --full writes "seed", the qname, and "name")
glia blast-radius . client::client::FetchUsers --direction forward --json
{"seeds":[{"query":"client::client::FetchUsers","kind":"FUNCTION","file":"client/client.go","line":8,…}],"unresolved":[],
 "results":[{"qname":"endpoint:GET:/users","kind":"ENDPOINT","reason":"CALLS","depth":1,"score":0.267,"live":false,"file":"client/client.go","line":9,"seed_index":0},
            {"qname":"GET /users","kind":"ROUTE","reason":"HTTP_CALLS","depth":2,"file":"server/main.go","line":13,…},
            {"qname":"server::main::listUsers","reason":"HANDLED_BY","depth":3,"file":"server/main.go","line":9,…}],"absence":null}

# shop-ranked, after `glia history sync .`: the calibration step; one row per (set, shape), the record under .glia/calibration-snapshot/
glia history calibrate . --json
{"dir":"./.glia/calibration-snapshot","history_head":"318a924af42f…","commits":10,"test_commits":9,"messages":true,"ms":36,
 "sets":[{"set":"SELf2t","shape":"find","pick":"H18x","last_online_pick":"H18x","fallback":"LX[IDR,T1s]","test_commits":9,"queries":9,"selection_recall10":1.0,"fallback_recall10":1.0,"delta_recall10":0.0,"ci_low":0.0,"ci_high":0.0},
         {"set":"SELh0","shape":"k1","pick":"H10","last_online_pick":"H10","fallback":"H10","test_commits":9,"queries":20,…},…]}
# SELh0 ranks blast-radius / diff-impact / review's impact (SELs0 under --no-cochange; pack never reads the record), SELt2 review's intent, SELf2t find --files;
# a pick whose online recall@10 falls below its fallback's is refused and recorded as the fallback

# shop-ranked, calibrated: "files" ranks co-changed files first; "selection" names the ranking the answer used
glia blast-radius . orders::models::Order --json
{"seeds":[{"qname":"orders::models::Order","kind":"CLASS","file":"orders/models.py","line":1,…}],"unresolved":[],
 "results":[{"qname":"orders::service::place","kind":"FUNCTION","reason":"CALLS","depth":1,"score":0.201,"file":"orders/service.py","line":4,…}],
 "files":[{"rank":1,"file":"orders/service.py","repo":"shop","cochange":0.857,"ppr":0.116,"depth":null,"rows":1},
          {"rank":2,"file":"billing/charge.py","repo":"shop","cochange":0.143,"ppr":0.0,"depth":null,"rows":0},…],
 "selection":{"set":"SELh0","shape":"k1","pick":"H10","source":"calibrated","reason":null,"test_commits":9},"absence":null}

# shop-ranked: the files a ticket is about; SHOP-12 routes through docs/tasks.md's row (idr), the words through past subjects (text)
glia find . "SHOP-12 round totals" --files --json
{"results":[{"rank":1,"file":"orders/models.py","idr":1.0,"text":8.628,"degree":9.0,"ids":["SHOP-12"]},
            {"rank":2,"file":"orders/service.py","idr":1.0,"text":8.628,"degree":5.0,"ids":["SHOP-12"]},
            {"rank":3,"file":"util/money.py","idr":0.0,"text":1.874,"degree":5.0,"ids":[]}],
 "absence":null,"selection":{"set":"SELf2t","shape":"find","pick":"H18x","source":"calibrated","reason":null,"test_commits":9}}

# org-packages-npm as a one-commit git repo: the embedding snapshot step (the deterministic test-hash model here;
# the default is bge-small, downloaded once into the user cache, never into the repo). Writes .glia/vectors.jsonl,
# re-embeds only nodes whose text changed ("cached" on a rerun); --check counts what needs embedding and writes nothing.
# With vectors, find --files adds a "sem" score and ranks by LX[IDR,FUSE[T1s,SEMp:t2]]; --no-semantic ranks without them
glia embed . --model test-hash --json
{"repo":"demo","model":"glia-test-hash-v1/64","recipe":"t2","dims":64,"nodes":5,"cached":0,"reused":0,"embedded":5,
 "ambiguous":0,"deferred":0,"stale_dropped":0,"foreign_kept":0,"rows_written":5,"ms":4}

# the same repo: the identifier vocabulary of one commit (default HEAD) into .glia/vocab-snapshot/; afterwards an empty
# find names the tracked files a query identifier occurs in (absence.named_in) and gaps lists named_not_modelled rows
glia vocab sync . --json
{"rev":"13f25257aab2161e0edbd48fcad680e25dd57675","files":4,"tokens":13,"common":0,"skipped_binary":0,"skipped_large":0,"ms":5}

# shop-ranked with orders/models.py edited: the PR's intent; without --title it is the newest commit subject of <base>..HEAD
glia review . --title "SHOP-12 round order totals" --json
{…,"intent":{"title":"SHOP-12 round order totals","title_source":"arg","fusion":"H18s[PT*]",
   "ids":[{"id":"SHOP-12","ns":"docs/tasks.md","tier":"derived","route":"unique","defined_at":["docs/tasks.md",3],"state":"pending","named_files":2,"cited_files":0}],
   "files":[{"rank":1,"file":"orders/service.py","idr":1.0,"text":11.908,"ppr":0.116,"ids":["SHOP-12"],"in_impact":false},…],"text":"present"},
 "selection_intent":{"set":"SELt2","shape":"k1","pick":"H18s[PT*]","source":"calibrated","reason":null,"test_commits":9}}

# loop, with the audit() change uncommitted
glia diff-impact . --json
{"base":"HEAD","changed":[{"qname":"billing::billing::audit","file":"billing/billing.ts","line":5,"change":"added","seed":true},{"qname":"billing::billing::settle","change":"modified","seed":true,…},…],
 "edges_added":[{"from_qname":"billing::billing::settle","to_qname":"billing::billing::audit","category":"CALLS","site_file":"billing/billing.ts","site_line":4,…},…],
 "impact":{"seeds":[…],"results":[{"qname":"event_emit:payment.settled","reason":"USES","depth":1,"seed_index":0,…},
                                  {"qname":"event_handle:payment.settled","reason":"EVENT_FLOWS","depth":2,"file":"orders/orders.ts","line":4,…},…]}}
git diff | glia diff-impact . --diff - --json
{"changed":[{"qname":"billing::billing::settle","change":"diff_hit","seed":true,…},…],…}

# a large Go monorepo, a change reaching 6,157 rows: the default answer is the overview, about 20 KB (--full: about 2 MB).
# Read "areas" first, then ask for one area; "truncated.next" names the largest area and the next page
glia diff-impact . --base HEAD^ --json
{"base":"HEAD^","changed":[…],"changed_truncated":114,
 "impact":{"seeds":[…],"results":[{"qname":"internal::entity::auth_session::Session::Abort","kind":"METHOD","reason":"CALLS","depth":1,"score":0.01705,"live":true,"file":"internal/entity/auth_session.go","line":1007,"seed_index":3},…],
  "files":[…],
  "areas":[{"area":"internal/entity","rows":1651,"files":300,"top_file":"internal/entity/auth_session.go","scope":"internal/entity"},
           {"area":"internal/config","rows":875,"files":86,"top_file":"internal/config/config_features.go","scope":"internal/config"},…],
  "truncated":{"results":6132,"seeds":110,"areas":24,"next":{"scope":"internal/entity","offset":25}}}}
# one area, ranked within it
glia diff-impact . --base HEAD^ --scope internal/entity --json
# or the next 25 rows of the whole answer (rows 26-50); --top-k 200 asks for more at once
glia diff-impact . --base HEAD^ --offset 25 --json

# xstack-go-http with client/ and server/ as two repos; the feature word is a name, a qname or a flows key
glia trace client FetchUsers --with server --json
{"seed":{"qname":"client::FetchUsers","file":"client.go","line":8,…},"resolved_by":"name",
 "paths":[{"rank":1,"hops":[{"depth":1,"mechanism":"CALLS","to_qname":"endpoint:GET:/users","to_file":"client.go","to_line":9,…},
                            {"depth":2,"mechanism":"HTTP_CALLS","cross_service":true,"cross_repo":true,"to_qname":"GET /users","to_file":"main.go","to_line":13,…},
                            {"depth":3,"mechanism":"HANDLED_BY","to_qname":"main::listUsers","to_file":"main.go","to_line":9,…}],
           "cross_service_hops":1,"mechanisms":["CALLS","HTTP_CALLS","HANDLED_BY"],"length":3}],"truncated":false,"absence":null}
glia trace . client::client::FetchUsers --to server::main::listUsers --json

# xstack-go-http; "key" is the word trace takes; --features --json groups flows per feature
glia flows . --json
[{"key":"get_/users","entry":{"qname":"GET /users","kind":"ROUTE","file":"server/main.go","line":13,…},"reach":1,"cross_service":false,"mechanisms":["HANDLED_BY"],"hops":[…],…}]

# xstack-go-http; with no direct edge: "found":false, exit 1, and "path" is a shortest witness
glia why . "GET /users" server::main::listUsers --json
{"found":true,"edges":[{"category":"HANDLED_BY","confidence":"strong","tier":"fact","emitter":"graph:refs","rule":"module_symbol","site":{"file":"server/main.go","line":13},…}],"path":[],"absence":null,…}

# xstack-go-http
glia serves . "GET /users" --json
{"results":[{"qname":"GET /users","kind":"ROUTE","file":"server/main.go","line":13,"match":"exact","confidence":"strong",
             "handlers":[{"qname":"server::main::listUsers","file":"server/main.go","line":9,…}],…}],"absence":null}
# xcut-queue-queue_flows: a topic's QUEUE_CONSUMER with its handlers; an unserved channel is an absence with caveats
glia serves . orders --json

# java-iface-extends: interface Catalog extends Readable, class PgCatalog implements Catalog; --up walks to supertypes
glia implementors . Readable --json
{"results":[{"qname":"Catalog","kind":"INTERFACE","file":"Catalog.java","line":3,"relation":"INHERITS_FROM","depth":1,"via":null,"tier":"fact",…},
            {"qname":"PgCatalog","kind":"CLASS","file":"PgCatalog.java","line":3,"relation":"IMPLEMENTS","depth":2,"via":"Catalog","tier":"fact",…}],"absence":null}

# go-sql-call-args: store.Upsert runs INSERT INTO prefs … ON CONFLICT; --cross-service follows a send into its receiver
glia effects . store::Upsert --json
{"seeds":["store::Upsert"],"effects":[{"class":"db","qname":"data_entity:sql:prefs","file":null,"line":null,"mode":"write","depth":1,"tier":"derived",
  "path":[{"from_qname":"store::Upsert","to_qname":"data_entity:sql:prefs","category":"ACCESSES_DATA","site_file":"store.go","site_line":18}],…}],
 "counts":{"db":1,"queue_produce":0,"http_call":0,…},"writes":1,"unresolved":[],"absence":null}

# py-tests: test_calc.py test_add calls calc.add; --files-only prints just the files, for a runner
glia tests-for . calc::add --json
{"seeds":["calc::add"],"tests":[{"qname":"test_calc::test_add","file":"test_calc.py","line":5,"tier":"fact","reason":"tests_edge","covers":["calc::add"],…},
                                {"qname":"test_calc","kind":"MODULE","tier":"heuristic",…}],"test_files":["test_calc.py"],"untested":[],"unresolved":[],"absence":null}
# a git copy of py-tests with calc.py edited: the test files for the working tree's change
glia tests-for . --base main --files-only
test_calc.py

# loop, with the audit() change uncommitted; --base <rev> compares against another rev
glia delta . --json
{"base":"HEAD","counts":{"nodes_added":1,"nodes_modified":2,"edges_added":2,"edges_removed":0,…},
 "nodes":[{"change":"added","qname":"billing::billing::audit","kind":"FUNCTION","file":"billing/billing.ts","line":5,…},…],
 "edges":[{"change":"added","from_qname":"billing::billing::settle","to_qname":"billing::billing::audit","category":"CALLS","site_file":"billing/billing.ts","site_line":4,…},…]}

# loop, with the audit() change uncommitted; without --json it prints markdown for a PR comment; "blocking" is true (exit 1) only when the change adds a blocking rule violation
glia review . --base main --json
{"base":"main","counts":{"nodes_changed":3,"seeds":2,"edges_added":2,"edges_removed":0,"impact":8,"tests":0,"untested_seeds":2,"new_violations":0,"resolved_violations":0,"model_breaks":0,"edges_by_tier":{"fact":2}},
 "changed":[{"qname":"billing::billing::audit","kind":"FUNCTION","file":"billing/billing.ts","line":5,"change":"added","seed":true},…],"impact":{"seeds":[…],…,"results":[…],…},
 "tests":{"seeds":[…],"tests":[],…,"untested":["billing::billing::audit","billing::billing::settle"],…,"absence":{"tier":"fact","reason":"no_edges",…}},
 "edges":[{"change":"added","from_qname":"billing::billing::settle","to_qname":"billing::billing::audit","category":"CALLS","tier":"fact","site_file":"billing/billing.ts","site_line":4,…},…],
 "new_violations":[],"resolved_violations":[],"model_breaks":[],"check_errors":[],"blocking":false}

# orders-proto, with the change uncommitted; "producer" is the base side, "consumer" the working tree; exit 1: a change is breaking
glia contract-breaks . --base main --json
{"base":"main","schemas":[{"kind":"message","key":"shop.v1.OrderCreated","format":"proto","before":{…},"after":{"qname":"message:proto:shop.v1.OrderCreated","file":"proto/orders.proto","line":5,…},"status":"breaking","change":"modified","tier":"fact",…,
  "changes":[{"section":"fields","field":"total_cents","change":"type","producer":"int64","consumer":"string","rule":"proto_wire_type","breaking":true},
             {"section":"fields","field":"currency","change":"consumer_only","producer":null,"consumer":"string","rule":"proto_unknown_field","breaking":false}],…}],
 "models":[],"orphaned_clients":[],"breaking":1,"advisory":0,"absence":null}
# "models" judges the inferred client / server models the same way (a JSON rename, a field removed or now optional, a new required
# request field), one row per model pair with both field lines; advisory unless --models-min-tier derived, as the 0.5.2 pairs are derived.
# "names" lists the client sites still using a name the change removed or renamed server-side (advisory; they block only under
# --models-min-tier heuristic, which contract-breaks takes and review does not: review lists them under "### Name breaks (advisory)");
# a schema change several operations share is one "schemas" row whose "operations" lists their keys
glia contract-breaks . --base main --models-min-tier heuristic --json

# models-http-contract; a client field the server never writes is json_field_missing (breaking); "producer" is the server side
glia contracts portal --with billing --fields --json
{"topics":[],"fields":[{"pairing":"client_contract","key":"GET /api/plans/{id} response","producer":{"qname":"contract::docs::swagger::GET:/api/plans/{id}","format":"openapi","file":"docs/swagger.json","line":6,…},
  "consumer":{"qname":"src::app::plan.service::Plan","format":"ts","file":"src/app/plan.service.ts","line":4,…},"status":"breaking","tier":"derived","note":null,
  "changes":[{"section":"response:200","field":"trialDays","change":"consumer_only","producer":null,"consumer":"number","rule":"contract_field_undeclared","breaking":true}]},
 {"pairing":"http_model","key":"GET /api/plans/:id response","producer":{"qname":"handlers::plans::planBody","format":"go","file":"handlers/plans.go","line":9,…},
  "consumer":{"qname":"src::app::plan.service::Plan","format":"ts","file":"src/app/plan.service.ts","line":4,…},"status":"breaking","tier":"derived","note":null,
  "changes":[{"section":"response","field":"trialDays","change":"consumer_only","producer":null,"consumer":"number","rule":"json_field_missing","breaking":true}]}]}
# a GraphQL operation's selection against its schema type is pairing graphql_selection (a selected field the type lacks: graphql_field_undefined)

# shop, with orders/service.py edited; confidence is per mille of the antecedent's own commits; "link":"none" (no static edge) marks a blind spot
glia cochange . --base main --json
{"query_files":["orders/service.py"],"unmapped":[],
 "rows":[{"file":"orders/models.py","module_qname":"orders::models","antecedent":["orders/service.py"],"support":5,"antecedent_commits":5,"confidence_permille":1000,"link":"direct","source":"pairwise","tier":"heuristic",…}],"absence":null}

# loop; kinds are event_loop, call_loop, possible_loop and import_cycle (--kind event|import|all)
glia cycles . --json
[{"kind":"event_loop","tier":"derived","services":["billing","orders"],"channels":["order.placed","payment.settled"],"size":9,"members":[…],
  "witness":[{"from_qname":"event_emit:order.placed","to_qname":"event_handle:order.placed","category":"EVENT_FLOWS","channel":"order.placed","file":"orders/orders.ts","line":3},…]}]

# a repo with web/ and services/api/ (a pyproject.toml each) whose web/app.py imports and calls services/api/internal.py;
# .glia/overlay.toml has a [[constraint]] kind = "forbid_edge" from "web" to "services/api", categories IMPORTS + CALLS; exit 1
glia check . --json
{"rules":1,"checked":1,"unchecked":[],"errors":[],"violations":[{"rule_id":"web-no-api-internals","rule_kind":"forbid_edge","decl":".glia/overlay.toml:3","severity":"VIOLATION","tier":"fact","blocking":true,"count":2,
  "evidence":[{"from_qname":"web::app","to_qname":"services::api::internal","category":"IMPORTS","file":"web/app.py","line":1,"emitter":"graph:imports",…},…]}],"reflexion":null}
# The same file can declare a reflexion model: [[component]] stanzas (a name and its paths), [[layer]] stanzas ranking them top
# first, and [[constraint]] kind = "allow" from one component to another. check then judges every dependency between two
# components: a convergence, a divergence (a violation, exit 1), or an absence (an allow no edge realises, with caveats).
# The table output prints this as a `## reflexion model` section; --json puts it under "reflexion" (matrix, absences, unmapped).
# With version = 2 a [[constraint]] can also take transitive = true (a path through any third scope counts; via = [..] names
# allowed facades), kind = "invariant" with a Datalog rule = '...' whose violation/N rows are its violations, and
# min_tier = "fact" | "derived" (default derived): a violation weaker than min_tier, and every heuristic one, is listed as
# advisory and leaves the exit code at 0. The stderr line `[check] gate blocking=<b> advisory=<a>` counts them.
# A rule that checks nothing (a misspelt scope, a stanza the loader dropped) is an "unanchored" row with "reason" and "fix",
# printed under "## Rules that check nothing"; --strict makes it a rule error (exit 2). A rule scoped to a directory inside a
# project anchors on that project.

# xcut-flag-read-fn: svc/checkout.py reads LaunchDarkly flags, new-checkout inside checkout() and promo-banner at module scope
glia flags . --json
{"flags":[{"key":"new-checkout","providers":["launchdarkly"],"definitions":[],"reads":[{"qname":"svc::checkout::checkout","kind":"FUNCTION","file":"svc/checkout.py","line":8}],"readers":1,"last_read_change":null,
           "findings":[{"status":"single_site","tier":"fact","note":"read only in svc::checkout::checkout (svc/checkout.py:8)"}]},…],
 "definitions_in_graph":0,"quiet_evaluated":false,"history_now":null,"quiet_days":90,"counts":{"dead":0,"quiet":0,"single_site":2,"undefined":0},"absence":null}

# shop; churn_rank and centrality_rank rank the same "ranked" rows (there is no blended score); symbol rows need blame span changes
glia hotspots . --json
{"modules":[{"level":"module","qname":"orders::models","kind":"MODULE","file":"orders/models.py","line":1,"churn":5,"lines_changed":8,"last_change":1788566400,"churn_rank":2,"centrality_rank":1,"ranked":4,"tier":"heuristic"},
            {"level":"module","qname":"orders::service","kind":"MODULE","file":"orders/service.py","line":1,"churn":5,…,"churn_rank":1,"centrality_rank":3,"ranked":4,…},…],
 "symbols":[],"history_head":1789430400,"absence":null}

# arch-monorepo-flows; a label is the top members' shared qname prefix; cohesion is internal weight over internal + boundary
glia communities . --json
{"method":"leiden","seed":42,"resolution":1.0,"modularity":0.7299382716049383,"total":5,"nodes":33,"isolated":4,
 "communities":[{"id":0,"size":8,"label":"api::orders","tier":"heuristic","cohesion":1.0,"files":2,"kinds":[["FUNCTION",3],["MODULE",2],…],
                 "top_members":[{"qname":"worker::notify::registerHandlers","kind":"FUNCTION","file":"worker/notify.ts","line":4,"weight":9},…],
                 "entries":[{"qname":"event_handle:orderPlaced","kind":"EVENT_HANDLER","file":"worker/notify.ts","line":5,…}],"services":[["api",4],["worker",4]],"sinks":[["event_emit",1]],"links":[]},…],"absence":null}

# channel-monorepo-owner: one repo, eleven services; services/orders and services/returns both publish orders.created,
# which services/audit and services/billing consume; a node with callers or callees in two services is cross_service
glia hubs . --json
{"fan_in":[],"fan_out":[],
 "cross_service":[{"qname":"queue_consumer:orders.created @services/audit","kind":"QUEUE_CONSUMER","file":"services/audit/consume.py","line":5,"label":"connector","fan_in":2,"fan_out":1,
                   "by_category":[["QUEUE_FLOWS",2,0],["HANDLED_BY",0,1]],"caller_services":["services/orders","services/returns"],"callee_services":["services/audit"],…,"live":true,"tier":"derived"},…],
 "nodes":63,"edges":23,"p99_in":2,"p99_out":2,"absence":null}

# xstack-go-http
glia coverage . --json
[{"language":"*","edge_category":"CALLS",…,"edges_found":1},
 {"language":"*","edge_category":"HTTP_CALLS","note":"URLs built dynamically (string concat / variables / base-url config) may not pair to a route","verify":"grep the path literal or base URL","edges_found":1},…,
 {"language":"*","edge_category":"DOCUMENTS","note":"repo markdown is ingested only from: the well-known files (README*.md, …) at the repo root and at each PROJECT root, a docs/ tree at the repo root or at a PROJECT root, a top-level .ai/ tree, ADR directories (…), SDD feature docs (…) and synced external docs (`glia docs sync`); … A doc section DOCUMENTS a symbol only when it names it in a single-backtick span …",…,"edges_found":0},…,
 {"language":"go","edge_category":"IMPLEMENTS","note":"implicit interface satisfaction is inferred (Medium, DERIVED) from method names and, where the parser read both, signatures (parameter and result types, with a type alias declared in the repo resolved through the method's package and imports; …); a one-method interface pairs only across an import path (…), and a pair with a side in a _test.go file only when that test file imports the other side's package directly (or both share a package); …; methods promoted through embedded fields count (…); …","verify":"check the method signatures and receivers against the interface","edges_found":0},…]

# xstack-go-http; Datalog from -e (or a file, or stdin): the routes and their handlers. Without --json, one table per output
glia query . -e 'served(r, h) :- handles(r, h), node(r, "ROUTE").' --json
{"language":"datalog","outputs":[{"predicate":"served","arity":2,"columns":["r","h"],"total":1,"shown":1}],
 "results":[{"predicate":"served","values":[{"node":{"qname":"GET /users","kind":"ROUTE","file":"server/main.go","line":13}},
                                            {"node":{"qname":"server::main::listUsers","kind":"FUNCTION","file":"server/main.go","line":9}}],"tier":"fact","file":"server/main.go","line":13}],"absence":null}
# a negation reads an absence, so its rows carry the coverage caveats of what it negated
glia query . -e 'uncalled(f) :- node(f, "FUNCTION"), !calls(_, f).' --json
{…,"results":[{"predicate":"uncalled","values":[{"node":{"qname":"client::client::FetchUsers",…,"line":8}}],"tier":"fact",…,
  "caveats":[{"language":"*","edge_category":"CALLS","note":"calls through reflection, dynamic dispatch, or higher-order indirection are not resolved",…}]},…],"absence":null}
# the same evaluator behind a GQL read query; the client-to-route hop is resolver-paired, so the row is derived
glia query . --gql -e 'MATCH (f:FUNCTION)-[:CALLS]->(e:ENDPOINT)-[:HTTP_CALLS]->(r:ROUTE) RETURN f, r' --json
{"language":"gql","outputs":[{"predicate":"result","arity":2,"columns":["f","r"],"total":1,"shown":1}],
 "results":[{"predicate":"result","values":[{"node":{"qname":"client::client::FetchUsers","kind":"FUNCTION","file":"client/client.go","line":8}},
                                             {"node":{"qname":"GET /users","kind":"ROUTE","file":"server/main.go","line":13}}],"tier":"derived",…}],"absence":null}
# The predicates (node, edge, qname, file, in_scope, reaches, ...), the prelude (handles, calls, unreached, effect, ...) and the GQL subset:
# https://github.com/James-Chahwan/glia/blob/main/docs/rules.md. A query that matches nothing exits 1 with the absence.

# identity-proto-diverged; one message in three repos is one class; variant 1 is shipping's copy with the extra field
glia identity orders --with billing --with shipping --json
{"counts":{"classes":1,"members":3,"fact":1,"derived":0,"heuristic":0,"diverged":1,"by_rule":[["package_name",0],["manifest_name",0],["message_fqname",1],…]},
 "classes":[{"key":"message:proto:shop.v1.OrderCreated","tier":"fact","rules":["message_fqname"],"collapses":true,"walks":true,"diverged":true,"variants":2,
             "members":[{"repo":"orders","qname":"message:proto:shop.v1.OrderCreated","kind":"MESSAGE_TYPE","file":"proto/orders.proto","line":5,"variant":0},
                        {"repo":"billing",…,"variant":0},{"repo":"shipping",…,"variant":1}]}],"omitted":0,"absence":null}

# xstack-go-http; "suggest" names the .glia/overlay.toml section that could repair the row
glia gaps . --json
{"counts":{"dead_symbol":1,"unpaired_endpoint":0,"tag_only_queue":0,…},"skipped":[],
 "rows":[{"category":"dead_symbol","qname":"client::client::FetchUsers","file":"client/client.go","line":8,"detail":"no entrypoint reaches it; no incoming call or use","suggest":"entrypoints","tier":"heuristic"}]}

# docs-adr-decision: the Decision section of doc/adr/0001-use-flask-for-orders.md names list_orders
glia docs-for . list_orders --json
{"results":[{"qname":"docs::doc::adr::0001-use-flask-for-orders::decision","kind":"DOC_SECTION","file":"doc/adr/0001-use-flask-for-orders.md","line":11,…}],"absence":null}
```

