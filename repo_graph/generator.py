#!/usr/bin/env python3
"""
generate-repo-map.py
Generates .ai/repo-graph/ with:
  - nodes.json   — all known entities (handlers, repos, pages, services, DB collections, NATS topics)
  - edges.json   — directed relationships between entities
  - flows/*.yaml — end-to-end request paths per frontend feature
  - state.md     — session-start snapshot: git state, feature coverage, available flows

Heuristics used (all approximate — see inline comments):
  - Backend routes: regex on controller files for router.GET/POST/PUT/DELETE/PATCH
  - Controller→repo: grep for Services.FooRepository() [global-provider] and
    struct field patterns [injected]
  - Feature→service: grep for constructor injection `private fooService: FooService`
  - Service→endpoint: grep for buildApiUrl( and buildWsUrl( calls
  - Repo→collection: regex on NewCollection[T](db, "name") in repository files
  - NATS topics: hardcoded (subjects are config-driven, not statically extractable)
"""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

ROOT      = Path(os.environ.get("REPO_GRAPH_REPO", Path(__file__).resolve().parent.parent))
GRAPH_DIR = ROOT / ".ai" / "repo-graph"
BACKEND   = ROOT / "turps"
FRONT     = ROOT / "quokka_web"

# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def git(repo: Path, cmd: list[str]) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo)] + cmd,
            text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "?"


def submodule_sha(name: str) -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(ROOT), "submodule", "status", name],
            text=True, stderr=subprocess.DEVNULL
        ).strip()
        return out.lstrip("+-U ").split()[0]
    except Exception:
        return "?"


def changed_files(repo: Path) -> str:
    staged   = git(repo, ["diff", "--cached", "--name-only"])
    unstaged = git(repo, ["diff", "--name-only"])
    # git() returns "?" on error (e.g. detached HEAD in submodule) — treat as empty
    if staged == "?":   staged = ""
    if unstaged == "?": unstaged = ""
    combined = sorted(set((staged + "\n" + unstaged).strip().splitlines()))
    return "\n".join(f"  {f}" for f in combined) if combined else "  (none)"


def recent_commits(repo: Path, n: int = 5) -> str:
    lines = git(repo, ["log", "--oneline", f"-{n}"]).splitlines()
    return "\n".join(f"  {l}" for l in lines) if lines else "  (none)"


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------

def list_go_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(p for p in directory.iterdir()
                  if p.suffix == ".go" and not p.name.endswith("_test.go"))


def list_ts_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(p for p in directory.iterdir() if p.suffix == ".ts")


def list_dirs(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(p for p in directory.iterdir() if p.is_dir())


def read_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Backend analysis
# ---------------------------------------------------------------------------

def backend_controllers() -> list[str]:
    d = BACKEND / "Server" / "Controllers"
    files = list_go_files(d)
    names = []
    for f in files:
        name = f.name
        # strip _controller.go suffix
        name = re.sub(r"_controller\.go$", "", name)
        names.append(name)
    return names



def backend_repositories() -> list[str]:
    d = BACKEND / "Services" / "Repositories"
    files = list_go_files(d)
    names = []
    for f in files:
        name = f.name
        # skip collection.go — it's a generic helper, not a domain repo
        if name == "collection.go":
            continue
        name = re.sub(r"_repository\.go$", "", name)
        names.append(name)
    return names


def backend_tasks() -> list[str]:
    d = BACKEND / "Tasks"
    files = list_go_files(d)
    return [f.name for f in files]


def backend_models() -> list[str]:
    d = BACKEND / "models"
    return [sub.name for sub in list_dirs(d)]



def controller_repo_usage() -> dict[str, dict[str, list[str]]]:
    """
    Heuristic: for each controller file, find repo access patterns.
    - 'global-provider': Services.FooRepository() calls
    - 'injected': struct field patterns like `fooRepo FooRepository` or
      constructor param `fooRepo *repositories.FooRepository`
    Accuracy ~80% — misses repos accessed via local variable aliases.
    """
    d = BACKEND / "Server" / "Controllers"
    result = {}
    global_pattern = re.compile(r'Services\.(\w+Repository)\(\)')
    inject_pattern = re.compile(r'\b(\w+(?:Repo|Repository))\s+(?:\*?repositories\.)?\w+Repository')

    for f in list_go_files(d):
        content = read_safe(f)
        controller = re.sub(r"_controller\.go$", "", f.name)
        global_repos = sorted(set(global_pattern.findall(content)))
        injected_repos = sorted(set(inject_pattern.findall(content)))
        # filter injected to avoid false positives — must look like a real field
        injected_repos = [r for r in injected_repos if r not in global_repos]
        if global_repos or injected_repos:
            result[controller] = {
                "global-provider": global_repos,
                "injected": injected_repos,
            }
    return result


# ---------------------------------------------------------------------------
# Frontend analysis
# ---------------------------------------------------------------------------

def frontend_features() -> list[tuple[str, str]]:
    """Returns (feature_name, main_component_file_or_label)."""
    d = FRONT / "src" / "app" / "features"
    results = []
    for feature_dir in list_dirs(d):
        name = feature_dir.name
        # find main component — prefer <name>.component.ts
        component_file = feature_dir / f"{name}.component.ts"
        if not component_file.exists():
            candidates = sorted(feature_dir.glob("*.component.ts"))
            if candidates:
                component_file = candidates[0]
            elif any((feature_dir / sub).exists() for sub in ["shell", "pages"]):
                # shell/landing page — no single root component
                results.append((name, "(shell)"))
                continue
            else:
                component_file = None
        results.append((name, component_file.name if component_file else "?"))
    return results


def frontend_services() -> list[str]:
    d = FRONT / "src" / "app" / "core" / "services"
    # index.ts = barrel export; auth-http-context.ts = HTTP context token; system.service.ts = orphaned
    skip = {"index.ts", "auth-http-context.ts", "system.service.ts"}
    return [f.name for f in list_ts_files(d)
            if ".spec." not in f.name and f.name not in skip]


def frontend_guards() -> list[str]:
    d = FRONT / "src" / "app" / "core" / "guards"
    skip = {"index.ts"}
    return [f.name for f in list_ts_files(d)
            if ".spec." not in f.name and f.name not in skip]


def frontend_shared() -> list[str]:
    d = FRONT / "src" / "app" / "shared"
    return [sub.name for sub in list_dirs(d)]



def feature_service_usage() -> dict[str, list[str]]:
    """
    Heuristic: for each feature component, find injected services via
    constructor parameter patterns: `private fooService: FooService`.
    Accuracy ~85% — misses renamed injections and non-constructor injection.
    """
    d = FRONT / "src" / "app" / "features"
    result = {}
    # match: private [readonly] fooService: FooService
    pattern = re.compile(
        r'private\s+(?:readonly\s+)?(\w+Service)\s*:\s*(\w+Service)',
        re.MULTILINE
    )
    for feature_dir in list_dirs(d):
        services_found = set()
        for ts_file in feature_dir.rglob("*.ts"):
            if ".spec." in ts_file.name:
                continue
            content = read_safe(ts_file)
            for match in pattern.finditer(content):
                # use the type name (second group) — more stable than field name
                services_found.add(match.group(2))
        if services_found:
            result[feature_dir.name] = sorted(services_found)
    return result


def service_endpoint_usage() -> dict[str, list[str]]:
    """
    Heuristic: for each service file, find buildApiUrl( and buildWsUrl( calls
    and extract the path argument.
    Accuracy ~90% — misses dynamically constructed paths.
    """
    d = FRONT / "src" / "app" / "core" / "services"
    result = {}
    # match buildApiUrl('...') or buildApiUrl("/...") with optional concatenation
    pattern = re.compile(r'build(?:Api|Ws)Url\([\'"]([^\'"]+)[\'"]')

    # api-url-builder.service.ts is the URL utility itself, not a service that calls endpoints
    skip = {"api-url-builder.service.ts"}
    for f in list_ts_files(d):
        if ".spec." in f.name or f.name in skip:
            continue
        content = read_safe(f)
        endpoints = sorted(set(pattern.findall(content)))
        if endpoints:
            result[f.name] = endpoints
    return result


# ---------------------------------------------------------------------------
# Feature coverage
# ---------------------------------------------------------------------------

def feature_coverage() -> list[dict]:
    features_dir = ROOT / "features"
    if not features_dir.exists():
        return []
    rows = []
    for feature_dir in sorted(features_dir.iterdir()):
        if not feature_dir.is_dir():
            continue
        name = feature_dir.name
        rows.append({
            "name": name,
            "backend_spec": "yes" if (feature_dir / "backend.md").exists() else "—",
            "ui_spec":      "yes" if (feature_dir / "ui.md").exists() else "—",
            "state":        "yes" if (feature_dir / "current-state.md").exists() else "—",
        })
    return rows


# ---------------------------------------------------------------------------
# Graph helpers — node/edge/flow extraction
# ---------------------------------------------------------------------------

def camel_to_snake(name: str) -> str:
    s1 = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)
    return re.sub(r'([a-z\d])([A-Z])', r'\1_\2', s1).lower()


def normalize_repo_id(class_name: str) -> str:
    """'GroupActivityInviteRepository' -> 'group_activity_invite'"""
    return camel_to_snake(re.sub(r"Repository$", "", class_name))


def normalize_svc_class_id(class_name: str) -> str:
    """'UserProfileService' -> 'user_profile'"""
    return camel_to_snake(re.sub(r"Service$", "", class_name))


def svc_file_to_id(filename: str) -> str:
    """'user-profile.service.ts' -> 'user_profile'"""
    base = re.sub(r"\.service\.ts$", "", filename)
    return base.replace("-", "_").replace(".", "_")


def path_to_slug(path: str) -> str:
    """'/groups/:id/activities' -> 'groups_id_activities'"""
    return re.sub(r"[^a-zA-Z0-9]", "_", path.lstrip("/")).strip("_")


def repo_collection_map() -> dict[str, str]:
    """
    Parses each repository file for NewCollection[T](db, "name").
    Returns {repo_name: collection_name}, e.g. {'group': 'groups'}.
    """
    d = BACKEND / "Services" / "Repositories"
    pattern = re.compile(r'NewCollection\[.*?\]\(\s*\w+,\s*\w+,\s*"([^"]+)"')
    result = {}
    for f in list_go_files(d):
        if f.name == "collection.go":
            continue
        content = read_safe(f)
        m = pattern.search(content)
        if m:
            repo_name = re.sub(r"_repository\.go$", "", f.name)
            result[repo_name] = m.group(1)
    return result


def backend_routes_by_controller() -> list[tuple[str, str, str]]:
    """
    Same logic as backend_routes() but also returns the controller name.
    Returns list of (method, path, controller_name).
    """
    d = BACKEND / "Server" / "Controllers"
    pattern = re.compile(
        r'\.(GET|POST|PUT|DELETE|PATCH|OPTIONS)\(\s*"([^"]+)"',
        re.MULTILINE
    )
    routes = []
    seen: set[tuple[str, str, str]] = set()
    for f in list_go_files(d):
        content = read_safe(f)
        ctrl = re.sub(r"_controller\.go$", "", f.name)
        for method, path in pattern.findall(content):
            key = (method, path, ctrl)
            if key not in seen:
                seen.add(key)
                routes.append(key)
    return sorted(routes, key=lambda x: x[1])


def _route_index(routes_with_ctrl: list[tuple[str, str, str]]):
    """
    Pre-computes a lookup list from routes_with_ctrl.
    Each entry: (ep_base, clean_path, method, slug, ctrl)
    ep_base = path stripped of leading / and :param segments, for prefix matching.
    """
    index = []
    for method, path, ctrl in routes_with_ctrl:
        clean = path.lstrip("/")
        slug = path_to_slug(path)
        ep_base = re.split(r"/:", clean)[0]
        index.append((ep_base, clean, method, slug, ctrl))
    return index


def _ep_path(endpoint: str) -> str:
    """
    Strip the first URL-builder prefix segment from a frontend endpoint string.
    e.g. 'protected/groups/user' -> 'groups/user', 'auth/login' -> 'login'
    """
    parts = endpoint.split("/")
    return "/".join(parts[1:]) if len(parts) > 1 else endpoint


def build_nodes(
    controllers, repos, tasks, models, features,
    fe_services, guards, shared, routes_with_ctrl, coll_map,
) -> list[dict]:
    nodes: list[dict] = []

    for ctrl in controllers:
        nodes.append({
            "id": f"handler_{ctrl}", "type": "handler", "name": ctrl,
            "file_path": f"turps/Server/Controllers/{ctrl}_controller.go",
        })

    for repo in repos:
        nodes.append({
            "id": f"repo_{repo}", "type": "repository", "name": repo,
            "file_path": f"turps/Services/Repositories/{repo}_repository.go",
        })

    for task in tasks:
        tid = re.sub(r"\.go$", "", task)
        nodes.append({
            "id": f"task_{tid}", "type": "task", "name": task,
            "file_path": f"turps/Tasks/{task}",
        })

    for model in models:
        nodes.append({
            "id": f"model_{model.lower()}", "type": "model_domain", "name": model,
            "file_path": f"turps/models/{model}/",
        })

    seen_routes: set[str] = set()
    for method, path, ctrl in routes_with_ctrl:
        rid = f"route_{method}_{path_to_slug(path)}"
        if rid not in seen_routes:
            seen_routes.add(rid)
            nodes.append({
                "id": rid, "type": "backend_route", "name": f"{method} {path}",
                "file_path": f"turps/Server/Controllers/{ctrl}_controller.go",
            })

    seen_colls: set[str] = set()
    for coll in coll_map.values():
        if coll not in seen_colls:
            seen_colls.add(coll)
            nodes.append({
                "id": f"db_{coll}", "type": "db_collection", "name": coll,
                "file_path": "turps/Services/Repositories/",
            })

    # NATS topics — hardcoded; subjects are config-driven, not statically extractable
    nodes.extend([
        {"id": "nats_chat_room", "type": "nats_topic", "name": "chat.room.{roomId}",
         "file_path": "turps/Services/chat/nats.go"},
        {"id": "nats_notif",     "type": "nats_topic", "name": "notif.{userId}",
         "file_path": "turps/Services/chat/notifications.go"},
    ])

    for name, _ in features:
        page_id = name.replace("-", "_")
        nodes.append({
            "id": f"fe_page_{page_id}", "type": "frontend_page", "name": name,
            "file_path": f"quokka_web/src/app/features/{name}/",
        })

    for svc_file in fe_services:
        sid = svc_file_to_id(svc_file)
        nodes.append({
            "id": f"fe_svc_{sid}", "type": "frontend_service", "name": svc_file,
            "file_path": f"quokka_web/src/app/core/services/{svc_file}",
        })

    for guard in guards:
        gid = re.sub(r"\.guard\.ts$", "", guard).replace("-", "_")
        nodes.append({
            "id": f"fe_guard_{gid}", "type": "frontend_guard", "name": guard,
            "file_path": f"quokka_web/src/app/core/guards/{guard}",
        })

    for comp in shared:
        cid = comp.replace("-", "_")
        nodes.append({
            "id": f"fe_shared_{cid}", "type": "shared_component", "name": comp,
            "file_path": f"quokka_web/src/app/shared/{comp}/",
        })

    return nodes


def build_edges(
    ctrl_repos, feat_svcs, svc_eps, routes_with_ctrl, coll_map,
) -> list[dict]:
    edges: list[dict] = []
    seen: set[tuple] = set()

    def add(e: dict) -> None:
        key = (e["from"], e["to"], e["type"])
        if key not in seen:
            seen.add(key)
            edges.append(e)

    # handler → repository (uses)
    for ctrl, repo_groups in ctrl_repos.items():
        all_repos = (
            repo_groups.get("global-provider", []) +
            repo_groups.get("injected", [])
        )
        for repo_class in all_repos:
            add({"from": f"handler_{ctrl}",
                 "to":   f"repo_{normalize_repo_id(repo_class)}",
                 "type": "uses"})

    # frontend_page → frontend_service (uses)
    for feature, class_names in feat_svcs.items():
        fid = feature.replace("-", "_")
        for cls in class_names:
            add({"from": f"fe_page_{fid}",
                 "to":   f"fe_svc_{normalize_svc_class_id(cls)}",
                 "type": "uses"})

    ridx = _route_index(routes_with_ctrl)

    # frontend_service → backend_route (calls)
    # ~70% accurate — URL builder prefixes don't map 1:1 to route segments
    for svc_file, endpoints in svc_eps.items():
        sid = svc_file_to_id(svc_file)
        for endpoint in endpoints:
            ep = _ep_path(endpoint)
            for ep_base, clean_route, method, slug, _ in ridx:
                if ep_base == ep or clean_route == ep:
                    add({"from": f"fe_svc_{sid}",
                         "to":   f"route_{method}_{slug}",
                         "type": "calls"})

    # backend_route → handler (handled_by)
    for method, path, ctrl in routes_with_ctrl:
        add({"from": f"route_{method}_{path_to_slug(path)}",
             "to":   f"handler_{ctrl}",
             "type": "handled_by"})

    # repository → db_collection (reads_from)
    for repo, coll in coll_map.items():
        add({"from": f"repo_{repo}",
             "to":   f"db_{coll}",
             "type": "reads_from"})

    # NATS publish edges (hardcoded from static analysis)
    for from_id in ["handler_friends", "handler_group_activity_invite",
                    "task_group_matching_tasks"]:
        add({"from": from_id, "to": "nats_notif", "type": "publishes_to"})

    return edges


def build_flows(
    features, feat_svcs, svc_eps, ctrl_repos, routes_with_ctrl, coll_map,
) -> dict[str, str]:
    """
    Returns {feature_name: yaml_string}.
    One path per unique (service, handler) pair within each feature.
    """
    ridx = _route_index(routes_with_ctrl)

    ctrl_to_repos: dict[str, list[str]] = {
        ctrl: [normalize_repo_id(r)
               for r in rg.get("global-provider", []) + rg.get("injected", [])]
        for ctrl, rg in ctrl_repos.items()
    }

    flows: dict[str, str] = {}

    for feat_name, _ in features:
        if feat_name not in feat_svcs:
            continue

        feat_id = feat_name.replace("-", "_")
        paths: list[dict] = []
        seen_pairs: set[tuple[str, str]] = set()

        for svc_class in feat_svcs[feat_name]:
            svc_id   = normalize_svc_class_id(svc_class)
            svc_file = next((sf for sf in svc_eps if svc_file_to_id(sf) == svc_id), None)
            if not svc_file:
                continue

            for endpoint in svc_eps[svc_file]:
                ep = _ep_path(endpoint)

                for ep_base, _, method, slug, ctrl in ridx:
                    if ep_base != ep and ep_base.split("/")[0] != ep.split("/")[0]:
                        continue

                    pair = (svc_id, ctrl)
                    if pair in seen_pairs:
                        break
                    seen_pairs.add(pair)

                    steps: list[dict] = [
                        {"id": f"fe_page_{feat_id}",         "type": "frontend_page"},
                        {"id": f"fe_svc_{svc_id}",           "type": "frontend_service", "edge": "uses"},
                        {"id": f"route_{method}_{slug}",     "type": "backend_route",    "edge": "calls"},
                        {"id": f"handler_{ctrl}",            "type": "handler",          "edge": "handled_by"},
                    ]
                    for repo_id in ctrl_to_repos.get(ctrl, []):
                        steps.append({"id": f"repo_{repo_id}", "type": "repository", "edge": "uses"})
                        if repo_id in coll_map:
                            steps.append({"id": f"db_{coll_map[repo_id]}",
                                          "type": "db_collection", "edge": "reads_from"})

                    paths.append({"name": f"{svc_id}-to-{ctrl}", "steps": steps})
                    break

        if paths:
            flows[feat_name] = _render_flow_yaml(feat_name, paths)

    return flows


def _render_flow_yaml(feat_name: str, paths: list[dict]) -> str:
    lines = [f"flow: {feat_name}", "paths:"]
    for p in paths:
        lines.append(f"  - name: {p['name']}")
        lines.append("    steps:")
        for step in p["steps"]:
            edge_part = f", edge: {step['edge']}" if "edge" in step else ""
            lines.append(f"      - {{id: {step['id']}, type: {step['type']}{edge_part}}}")
    return "\n".join(lines) + "\n"


_GRAPH_README = """\
# Repo Graph

Generated by `scripts/generate-repo-map.py`. Do not edit manually.

## Files

- `nodes.json` — all known entities (handlers, repos, pages, services, collections, NATS topics)
- `edges.json` — directed relationships between entities
- `flows/<feature>.yaml` — end-to-end request paths per feature for fast AI navigation

## How to use (AI agent guide)

1. **Start from the feature** — load `flows/<feature>.yaml` for the feature you are working on.
2. **Follow the path** — each flow shows: page → service → route → handler → repo → DB collection.
3. **Use edges.json for neighbours** — find related nodes not in the flow (e.g. sibling repos, NATS topics).
4. **Read file_path** — each node has a `file_path`; open only those files. Do not scan the whole repo.
5. **Do not load nodes.json / edges.json wholesale** — filter by node ID or type as needed.

## Node types

| type             | description                                          |
|------------------|------------------------------------------------------|
| handler          | HTTP controller (turps/Server/Controllers/)          |
| repository       | Data access layer (turps/Services/Repositories/)    |
| task             | Background/cron job (turps/Tasks/)                  |
| model_domain     | Model package (turps/models/)                       |
| backend_route    | HTTP route — method + path                          |
| db_collection    | MongoDB collection                                  |
| nats_topic       | NATS subject pattern                                |
| frontend_page    | Angular feature page (quokka_web/src/app/features/) |
| frontend_service | Angular core service (quokka_web/src/app/core/)     |
| frontend_guard   | Angular route guard                                 |
| shared_component | Angular shared component                            |

## Edge types

| type         | meaning                                  |
|--------------|------------------------------------------|
| uses         | handler → repo  /  page → service       |
| calls        | frontend_service → backend_route        |
| handled_by   | backend_route → handler                 |
| reads_from   | repo → db_collection                    |
| publishes_to | handler / task → nats_topic             |

## Regenerate

    python3 scripts/generate-repo-map.py
"""


def write_graph_outputs(nodes: list[dict], edges: list[dict], flows: dict[str, str]) -> None:
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    flows_dir = GRAPH_DIR / "flows"
    flows_dir.mkdir(exist_ok=True)

    (GRAPH_DIR / "nodes.json").write_text(json.dumps(nodes, indent=2), encoding="utf-8")
    (GRAPH_DIR / "edges.json").write_text(json.dumps(edges, indent=2), encoding="utf-8")

    for feat_name, yaml_content in flows.items():
        (flows_dir / f"{feat_name}.yaml").write_text(yaml_content, encoding="utf-8")

    (GRAPH_DIR / "README.md").write_text(_GRAPH_README, encoding="utf-8")


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def render_coverage(rows: list[dict]) -> str:
    if not rows:
        return "  (none)"
    header = "  | Feature | Backend spec | UI spec | Current state |"
    sep    = "  | --- | --- | --- | --- |"
    lines  = [header, sep]
    for r in rows:
        lines.append(
            f"  | {r['name']} | {r['backend_spec']} | {r['ui_spec']} | {r['state']} |"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    backend_sha  = submodule_sha("turps")
    frontend_sha = submodule_sha("quokka_web")
    be_branch    = git(BACKEND, ["branch", "--show-current"]) or "(detached)"
    fe_branch    = git(FRONT,   ["branch", "--show-current"]) or "(detached)"

    controllers  = backend_controllers()
    repos        = backend_repositories()
    tasks        = backend_tasks()
    models       = backend_models()
    ctrl_repos   = controller_repo_usage()

    features     = frontend_features()
    fe_services  = frontend_services()
    guards       = frontend_guards()
    shared       = frontend_shared()
    feat_svcs    = feature_service_usage()
    svc_eps      = service_endpoint_usage()

    coverage     = feature_coverage()

    # Graph outputs
    routes_with_ctrl = backend_routes_by_controller()
    coll_map         = repo_collection_map()
    nodes = build_nodes(
        controllers, repos, tasks, models, features,
        fe_services, guards, shared, routes_with_ctrl, coll_map,
    )
    edges = build_edges(ctrl_repos, feat_svcs, svc_eps, routes_with_ctrl, coll_map)
    flows = build_flows(features, feat_svcs, svc_eps, ctrl_repos, routes_with_ctrl, coll_map)
    write_graph_outputs(nodes, edges, flows)
    print(f"Generated repo graph — {len(nodes)} nodes, {len(edges)} edges, {len(flows)} flows")

    # state.md — session-start snapshot (replaces REPO_MAP for AI context loading)
    flows_list = ", ".join(sorted(flows.keys()))
    state_content = f"""# Repo State

*Generated by `scripts/generate-repo-map.py`. Regenerate: `python3 scripts/generate-repo-map.py`*

---

## Git State

Backend:  turps      @ {backend_sha}
Frontend: quokka_web @ {frontend_sha}

Backend branch:  {be_branch}
Frontend branch: {fe_branch}

### Backend — uncommitted changes
{changed_files(BACKEND)}

### Backend — recent commits
{recent_commits(BACKEND)}

### Frontend — uncommitted changes
{changed_files(FRONT)}

### Frontend — recent commits
{recent_commits(FRONT)}

---

## Feature Coverage

{render_coverage(coverage)}

---

## Available Flows

{flows_list}
"""
    (GRAPH_DIR / "state.md").write_text(state_content, encoding="utf-8")
    print(f"Generated state.md  — {len(coverage)} features, flows: {flows_list}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate repo graph data")
    parser.add_argument("--repo", default=None, help="Path to the target repository")
    args = parser.parse_args()
    if args.repo:
        os.environ["REPO_GRAPH_REPO"] = args.repo
        # Re-resolve paths
        ROOT = Path(args.repo)
        GRAPH_DIR = ROOT / ".ai" / "repo-graph"
        BACKEND = ROOT / "turps"
        FRONT = ROOT / "quokka_web"
    main()
