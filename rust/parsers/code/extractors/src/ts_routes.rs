//! Backend HTTP route extraction for JS/TS — complements the endpoint
//! (fetch/axios) extraction in the TypeScript parser. Detects:
//!   - Next.js file-based API routes: `pages/api/...` and `app/api/.../route.ts`
//!   - Express / Koa / Hono / Fastify-style: `app.get('/path', ...)`,
//!     `router.post('/path', ...)`.
//!
//! Runs per-file. Output is route nodes that HttpStackResolver can match
//! against endpoint nodes to produce cross-stack HTTP edges.
//!
//! Emits one Route node per path, with stacked ROUTE_METHOD cells — matches
//! the shape parser-go writes and the shape HttpStackResolver reads.
//!
//! Like the other cross-cutting extractors, this is pattern-based. Only called
//! by the pipeline for JS/TS-family languages.

use std::collections::BTreeMap;

use repo_graph_code_domain::{CodeNav, GRAPH_TYPE, cell_type, node_kind};
use repo_graph_core::{Cell, CellPayload, Confidence, Node, NodeId, RepoId};

pub struct RouteNodes {
    pub nodes: Vec<Node>,
    pub nav: CodeNav,
}

const HTTP_METHODS: &[&str] = &["get", "post", "put", "delete", "patch", "options", "head", "all"];

pub fn extract_ts_backend_routes(
    source: &str,
    path: &str,
    module_id: NodeId,
    repo: RepoId,
) -> RouteNodes {
    // path → set of methods (BTreeMap gives stable ordering for deterministic output).
    let mut by_path: BTreeMap<String, Vec<String>> = BTreeMap::new();

    // Shape 1: Express-style `<x>.<method>('/...', ...)` and Hono/Koa routers.
    for line in source.lines() {
        let t = line.trim();
        for method in HTTP_METHODS {
            let needle = format!(".{method}(");
            let Some(idx) = t.find(&needle) else {
                continue;
            };
            let after = &t[idx + needle.len()..];
            let arg_start = after.trim_start();
            let Some((quote, rest)) = arg_start
                .strip_prefix('"')
                .map(|r| ('"', r))
                .or_else(|| arg_start.strip_prefix('\'').map(|r| ('\'', r)))
                .or_else(|| arg_start.strip_prefix('`').map(|r| ('`', r)))
            else {
                continue;
            };
            let Some(end) = rest.find(quote) else { continue };
            let route = &rest[..end];
            if !route.starts_with('/') || route.len() > 256 {
                continue;
            }
            if looks_like_http_client(t) {
                continue;
            }
            add_method(&mut by_path, route, method);
        }
    }

    // Shape 2: Next.js file-based routing — path gives us the route, source
    // gives us the method(s).
    if let Some(route) = nextjs_route_from_path(path) {
        for method in nextjs_methods_from_source(source) {
            add_method(&mut by_path, &route, method);
        }
    }

    // Shape 3: SvelteKit `+server.ts` — path from file path, methods from
    // named exports (same shape as Next.js App Router).
    if let Some(route) = sveltekit_route_from_path(path) {
        for method in nextjs_methods_from_source(source) {
            add_method(&mut by_path, &route, method);
        }
    }

    // Shape 4: NestJS controllers — combine @Controller(prefix) with method
    // decorators @Get/@Post/...(suffix).
    for (method, route) in nestjs_routes(source) {
        add_method(&mut by_path, &route, method);
    }

    let mut nodes = Vec::new();
    let mut nav = CodeNav::default();
    for (route, methods) in by_path {
        let qname = format!("route:{route}");
        let id = NodeId::from_parts(GRAPH_TYPE, repo, node_kind::ROUTE, &qname);
        let cells = methods
            .into_iter()
            .map(|m| Cell {
                kind: cell_type::ROUTE_METHOD,
                payload: CellPayload::Json(format!(
                    r#"{{"method":"{}","handler":"","file":"{}","line":0,"col":0}}"#,
                    m.to_ascii_uppercase(),
                    escape_json(path),
                )),
            })
            .collect();
        nodes.push(Node {
            id,
            repo,
            confidence: Confidence::Medium,
            cells,
        });
        nav.record(id, &route, &qname, node_kind::ROUTE, Some(module_id));
    }

    RouteNodes { nodes, nav }
}

fn add_method(by_path: &mut BTreeMap<String, Vec<String>>, route: &str, method: &str) {
    let entry = by_path.entry(route.to_string()).or_default();
    let m = method.to_ascii_lowercase();
    if !entry.iter().any(|existing| existing == &m) {
        entry.push(m);
    }
}

fn escape_json(s: &str) -> String {
    s.replace('\\', "\\\\").replace('"', "\\\"")
}

fn looks_like_http_client(line: &str) -> bool {
    line.contains("fetch(")
        || line.contains("axios.")
        || line.contains("axios(")
        || line.contains(".request(")
        || line.contains("got(")
        || line.contains("got.")
        || line.contains("ky.")
        || line.contains(".ajax(")
        || line.contains("expect(")
        || line.contains(".resolves")
        || line.contains(".rejects")
}

/// Extract a Next.js route path from a source path, or None if not a Next.js
/// API route file. Handles both Pages Router (`pages/api/foo.ts` → `/api/foo`)
/// and App Router (`app/api/foo/route.ts` → `/api/foo`). Dynamic segments
/// `[id]` become `:id`.
fn nextjs_route_from_path(path: &str) -> Option<String> {
    let norm = path.replace('\\', "/");
    if let Some(rest) = norm.split("pages/api/").nth(1) {
        let without_ext = strip_js_ext(rest)?;
        let cleaned = without_ext.strip_suffix("/index").unwrap_or(without_ext);
        return Some(format!("/api/{}", nextjs_params_to_colon(cleaned)));
    }
    if let Some(rest) = norm.split("app/api/").nth(1) {
        let without_route = rest
            .strip_suffix("/route.ts")
            .or_else(|| rest.strip_suffix("/route.tsx"))
            .or_else(|| rest.strip_suffix("/route.js"))
            .or_else(|| rest.strip_suffix("/route.jsx"))?;
        return Some(format!("/api/{}", nextjs_params_to_colon(without_route)));
    }
    None
}

fn strip_js_ext(s: &str) -> Option<&str> {
    for ext in [".tsx", ".ts", ".jsx", ".js"] {
        if let Some(stripped) = s.strip_suffix(ext) {
            return Some(stripped);
        }
    }
    None
}

fn nextjs_params_to_colon(path: &str) -> String {
    let mut out = String::with_capacity(path.len());
    let mut chars = path.chars().peekable();
    while let Some(c) = chars.next() {
        if c == '[' {
            let mut name = String::new();
            while let Some(&nc) = chars.peek() {
                if nc == ']' {
                    chars.next();
                    break;
                }
                name.push(nc);
                chars.next();
            }
            let cleaned = name.trim_start_matches("...").trim_start_matches("..");
            out.push(':');
            out.push_str(cleaned);
        } else {
            out.push(c);
        }
    }
    out
}

/// Extract a SvelteKit route path from `+server.ts`. Example:
/// `src/routes/api/users/+server.ts` → `/api/users`.
/// `src/routes/api/users/[id]/+server.ts` → `/api/users/:id`.
fn sveltekit_route_from_path(path: &str) -> Option<String> {
    let norm = path.replace('\\', "/");
    let file = ["+server.ts", "+server.js"]
        .iter()
        .find(|ext| norm.ends_with(*ext))?;
    let idx = norm.find("src/routes/").map(|i| i + "src/routes/".len())
        .or_else(|| norm.find("routes/").map(|i| i + "routes/".len()))?;
    let tail = &norm[idx..norm.len() - file.len()];
    let tail = tail.trim_end_matches('/');
    let cleaned = sveltekit_params_to_colon(tail);
    if cleaned.is_empty() {
        Some("/".to_string())
    } else {
        Some(format!("/{}", cleaned))
    }
}

fn sveltekit_params_to_colon(path: &str) -> String {
    // SvelteKit uses `[param]` same as Next.js dynamic segments.
    nextjs_params_to_colon(path)
}

/// Scan a TS source for NestJS @Controller + @Get/@Post/... method decorators.
/// Returns (method, full_path) pairs.
fn nestjs_routes(source: &str) -> Vec<(&'static str, String)> {
    let mut out = Vec::new();
    let mut controller_prefix: Option<String> = None;
    for line in source.lines() {
        let t = line.trim();
        if t.starts_with("@Controller(") {
            controller_prefix = Some(extract_decorator_string(t).unwrap_or_default());
            continue;
        }
        for (deco, method) in &[
            ("@Get(", "get"),
            ("@Post(", "post"),
            ("@Put(", "put"),
            ("@Patch(", "patch"),
            ("@Delete(", "delete"),
            ("@Head(", "head"),
            ("@Options(", "options"),
            ("@All(", "all"),
        ] {
            if t.starts_with(deco) {
                let suffix = extract_decorator_string(t).unwrap_or_default();
                let full = combine_nest_paths(controller_prefix.as_deref().unwrap_or(""), &suffix);
                out.push((*method, full));
                break;
            }
        }
    }
    out
}

fn extract_decorator_string(line: &str) -> Option<String> {
    // Find first quoted literal after the opening paren.
    let open = line.find('(')?;
    let rest = &line[open + 1..];
    let bytes = rest.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        let c = bytes[i];
        if c == b'\'' || c == b'"' || c == b'`' {
            let delim = c;
            let start = i + 1;
            let mut j = start;
            while j < bytes.len() && bytes[j] != delim {
                if bytes[j] == b'\\' && j + 1 < bytes.len() {
                    j += 2;
                } else {
                    j += 1;
                }
            }
            if j < bytes.len() {
                return Some(rest[start..j].to_string());
            }
            return None;
        }
        if c == b')' {
            return None;
        }
        i += 1;
    }
    None
}

fn combine_nest_paths(prefix: &str, suffix: &str) -> String {
    let prefix = prefix.trim_matches('/');
    let suffix = suffix.trim_matches('/');
    let mut out = String::from("/");
    if !prefix.is_empty() {
        out.push_str(prefix);
    }
    if !suffix.is_empty() {
        if !out.ends_with('/') {
            out.push('/');
        }
        out.push_str(suffix);
    }
    // Convert NestJS :param (already :) or express-style. No transform needed;
    // both Nest and Express use :param natively.
    out
}

fn nextjs_methods_from_source(source: &str) -> Vec<&'static str> {
    let mut methods = Vec::new();
    for method in ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"] {
        let needle_async = format!("export async function {method}");
        let needle_sync = format!("export function {method}");
        let needle_const = format!("export const {method}");
        if source.contains(&needle_async)
            || source.contains(&needle_sync)
            || source.contains(&needle_const)
        {
            methods.push(match method {
                "GET" => "get",
                "POST" => "post",
                "PUT" => "put",
                "DELETE" => "delete",
                "PATCH" => "patch",
                "OPTIONS" => "options",
                "HEAD" => "head",
                _ => unreachable!(),
            });
        }
    }
    if methods.is_empty() && source.contains("export default") {
        methods.push("get");
    }
    methods
}

#[cfg(test)]
mod tests {
    use super::*;

    fn repo() -> RepoId {
        RepoId(1)
    }
    fn module_id() -> NodeId {
        NodeId::from_parts(GRAPH_TYPE, repo(), node_kind::MODULE, "test")
    }

    #[test]
    fn detects_express_get() {
        let src = "app.get('/users/:id', handler);";
        let r = extract_ts_backend_routes(src, "server.ts", module_id(), repo());
        assert_eq!(r.nodes.len(), 1);
        assert_eq!(r.nodes[0].cells.len(), 1);
    }

    #[test]
    fn detects_router_post() {
        let src = "router.post('/widgets', createWidget);";
        let r = extract_ts_backend_routes(src, "routes.ts", module_id(), repo());
        assert_eq!(r.nodes.len(), 1);
    }

    #[test]
    fn rejects_fetch_call() {
        let src = "fetch('/api/widgets').then(r => r.json());";
        let r = extract_ts_backend_routes(src, "client.ts", module_id(), repo());
        assert_eq!(r.nodes.len(), 0);
    }

    #[test]
    fn detects_nextjs_pages_router() {
        let src = "export default function handler(req, res) { res.json({}); }";
        let r = extract_ts_backend_routes(src, "pages/api/users.ts", module_id(), repo());
        assert_eq!(r.nodes.len(), 1);
    }

    #[test]
    fn detects_nextjs_app_router_named_exports() {
        let src = "export async function GET() {}\nexport async function POST() {}";
        let r = extract_ts_backend_routes(src, "app/api/widgets/route.ts", module_id(), repo());
        // One Route node per path, with one ROUTE_METHOD cell per method.
        assert_eq!(r.nodes.len(), 1);
        assert_eq!(r.nodes[0].cells.len(), 2);
    }

    #[test]
    fn converts_nextjs_dynamic_segment() {
        let src = "export default function h() {}";
        let r = extract_ts_backend_routes(src, "pages/api/users/[id].ts", module_id(), repo());
        assert_eq!(r.nodes.len(), 1);
        let qname = r.nav.qname_by_id.values().next().unwrap();
        assert!(qname.contains("/api/users/:id"), "qname={qname}");
    }

    #[test]
    fn detects_nestjs_controller_and_methods() {
        let src = r#"
@Controller('users')
export class UsersController {
  @Get()
  list() {}

  @Get(':id')
  getOne() {}

  @Post()
  create() {}

  @Put(':id')
  update() {}

  @Delete(':id')
  destroy() {}
}
"#;
        let r = extract_ts_backend_routes(src, "src/users.controller.ts", module_id(), repo());
        let qnames: Vec<&str> = r.nav.qname_by_id.values().map(|s| s.as_str()).collect();
        assert!(qnames.iter().any(|q| *q == "route:/users"));
        assert!(qnames.iter().any(|q| *q == "route:/users/:id"));
    }

    #[test]
    fn detects_sveltekit_plus_server() {
        let src = "export async function GET() {}\nexport async function POST() {}";
        let r = extract_ts_backend_routes(src, "src/routes/api/widgets/+server.ts", module_id(), repo());
        let qnames: Vec<&str> = r.nav.qname_by_id.values().map(|s| s.as_str()).collect();
        assert!(qnames.iter().any(|q| *q == "route:/api/widgets"));
        let node = r.nodes.iter().find(|n| n.cells.len() == 2).expect("combined node");
        assert_eq!(node.cells.len(), 2);
    }

    #[test]
    fn sveltekit_dynamic_segment() {
        let src = "export function GET() {}";
        let r = extract_ts_backend_routes(src, "src/routes/api/users/[id]/+server.ts", module_id(), repo());
        let qnames: Vec<&str> = r.nav.qname_by_id.values().map(|s| s.as_str()).collect();
        assert!(qnames.iter().any(|q| q.contains("/api/users/:id")));
    }

    #[test]
    fn route_cell_carries_method_json() {
        let src = "app.get('/x', h); app.post('/x', h);";
        let r = extract_ts_backend_routes(src, "server.ts", module_id(), repo());
        assert_eq!(r.nodes.len(), 1);
        assert_eq!(r.nodes[0].cells.len(), 2);
        let payloads: Vec<String> = r.nodes[0]
            .cells
            .iter()
            .map(|c| match &c.payload {
                CellPayload::Json(s) => s.clone(),
                _ => String::new(),
            })
            .collect();
        assert!(payloads.iter().any(|p| p.contains("\"method\":\"GET\"")));
        assert!(payloads.iter().any(|p| p.contains("\"method\":\"POST\"")));
    }
}
