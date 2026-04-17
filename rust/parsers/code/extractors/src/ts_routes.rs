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
