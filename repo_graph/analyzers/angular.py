"""
Angular analyzer.

Detects Angular projects via @angular/core in package.json.
Extends TypeScript analysis with component/service/guard/DI concepts.
"""

import json
import re
from pathlib import Path

from .base import (
    AnalysisResult,
    Edge,
    LanguageAnalyzer,
    Node,
    camel_to_snake,
    list_dirs,
    read_safe,
    rel_path,
    render_flow_yaml,
    scan_project_dirs,
)


# Constructor injection: private [readonly] fooService: FooService
_INJECT_PATTERN = re.compile(
    r"private\s+(?:readonly\s+)?(\w+)\s*:\s*(\w+)", re.MULTILINE
)

# HTTP calls: this.http.get/post/put/delete/patch('...')
_HTTP_CALL_PATTERN = re.compile(
    r"this\.http\w*\.(get|post|put|delete|patch)\s*(?:<[^>]*>)?\(\s*[`'\"]([^`'\"]+)",
    re.MULTILINE,
)

# URL builder calls: buildApiUrl('path') or buildWsUrl('path')
_URL_BUILDER_PATTERN = re.compile(
    r"build(?:Api|Ws)Url\(\s*['\"]([^'\"]+)['\"]",
)

# Angular types to skip in DI analysis
_ANGULAR_TYPES = {
    "ElementRef", "Renderer2", "ChangeDetectorRef", "NgZone",
    "Injector", "ViewContainerRef", "TemplateRef", "Router",
    "ActivatedRoute", "DomSanitizer", "HttpClient", "FormBuilder",
    "Title", "Location",
}

_SKIP_TYPES = {
    "Map", "Set", "Array", "Object", "MediaStream", "HTMLElement",
    "FormGroup", "FormControl", "Subject", "BehaviorSubject",
    "Subscription", "Observable",
}


def _find_angular_roots(repo_root: Path) -> list[Path]:
    """Find all directories containing an Angular package.json."""
    return [d for d in scan_project_dirs(repo_root) if _is_angular_dir(d)]


def _is_angular_dir(d: Path) -> bool:
    pkg_json = d / "package.json"
    if not pkg_json.exists():
        return False
    try:
        pkg = json.loads(read_safe(pkg_json))
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        return "@angular/core" in deps
    except (json.JSONDecodeError, TypeError):
        return False


class AngularAnalyzer(LanguageAnalyzer):

    @staticmethod
    def detect(repo_root: Path) -> bool:
        return bool(_find_angular_roots(repo_root))

    def scan(self) -> AnalysisResult:
        nodes: list[Node] = []
        edges: list[Edge] = []
        seen_ids: set[str] = set()

        all_flows: dict[str, str] = {}
        all_state: dict[str, str] = {}

        for project_root in _find_angular_roots(self.repo_root):
            src = self._find_app_root(project_root)
            self._scan_one(src, nodes, edges, seen_ids, all_flows)
            all_state.update(self._state_section_for(src))

        return AnalysisResult(
            nodes=nodes,
            edges=edges,
            flows=all_flows,
            state_sections=all_state,
        )

    def _scan_one(
        self,
        src: Path,
        nodes: list[Node],
        edges: list[Edge],
        seen_ids: set[str],
        all_flows: dict[str, str],
    ) -> None:
        """Scan a single Angular project root."""

        # Scan features (pages)
        features_dir = src / "features"
        if not features_dir.exists():
            # Try alternate structures
            for alt in ["pages", "views", "modules"]:
                if (src / alt).exists():
                    features_dir = src / alt
                    break

        features = self._scan_features(features_dir, nodes, edges, seen_ids)

        # Scan services
        svc_dirs = self._find_service_dirs(src)
        service_map = self._scan_services(svc_dirs, nodes, edges, seen_ids)

        # Scan guards
        guard_dirs = self._find_dirs(src, "guards")
        self._scan_guards(guard_dirs, nodes, edges, seen_ids)

        # Scan shared components
        shared_dirs = self._find_dirs(src, "shared")
        self._scan_shared(shared_dirs, nodes, edges, seen_ids)

        # Feature → service edges (from constructor injection in feature files)
        feat_svcs = self._feature_service_usage(features_dir)
        for feat_name, svc_classes in feat_svcs.items():
            feat_id = f"ng_page_{feat_name.replace('-', '_')}"
            for svc_class in svc_classes:
                svc_id = f"ng_svc_{camel_to_snake(re.sub(r'Service$', '', svc_class))}"
                if feat_id in seen_ids and svc_id in seen_ids:
                    edges.append(Edge(from_id=feat_id, to_id=svc_id, type="uses"))

        # Service → endpoint edges
        svc_endpoints = self._service_endpoint_usage(svc_dirs)
        for svc_file, endpoints in svc_endpoints.items():
            svc_id = f"ng_svc_{self._svc_file_to_id(svc_file)}"
            for method, path in endpoints:
                edges.append(Edge(
                    from_id=svc_id,
                    to_id=f"endpoint_{method}_{path.replace('/', '_').strip('_')}",
                    type="calls",
                ))

        # Build flows
        flows = self._build_flows(feat_svcs, svc_endpoints, seen_ids)
        all_flows.update(flows)

    # -- Scanning helpers --------------------------------------------------

    def _find_app_root(self, project_root: Path) -> Path:
        """Find the Angular app root (typically src/app)."""
        candidates = [
            project_root / "src" / "app",
            project_root / "app",
            project_root / "src",
        ]
        for c in candidates:
            if c.exists():
                return c
        return project_root

    def _state_section_for(self, src: Path) -> dict[str, str]:
        components = list(src.rglob("*.component.ts"))
        services = list(src.rglob("*.service.ts"))
        components = [f for f in components if ".spec." not in f.name]
        services = [f for f in services if ".spec." not in f.name]
        return {
            f"Angular ({rel_path(self.repo_root, src)})": (
                f"{len(components)} components, {len(services)} services\n"
            )
        }

    def _scan_features(
        self, features_dir: Path, nodes: list, edges: list, seen: set
    ) -> list[str]:
        """Scan feature directories and create page nodes."""
        found = []
        if not features_dir.exists():
            return found
        for feat_dir in list_dirs(features_dir):
            name = feat_dir.name
            page_id = f"ng_page_{name.replace('-', '_')}"
            if page_id not in seen:
                seen.add(page_id)
                nodes.append(Node(
                    id=page_id,
                    type="ng_page",
                    name=name,
                    file_path=rel_path(self.repo_root, feat_dir),
                ))
                found.append(name)
        return found

    def _find_service_dirs(self, src: Path) -> list[Path]:
        """Find directories containing service files."""
        dirs = []
        for candidate in ["core/services", "services", "core"]:
            d = src / candidate
            if d.exists() and any(d.rglob("*.service.ts")):
                dirs.append(d)
        return dirs

    def _find_dirs(self, src: Path, name: str) -> list[Path]:
        dirs = []
        for candidate in [f"core/{name}", name]:
            d = src / candidate
            if d.exists():
                dirs.append(d)
        return dirs

    def _scan_services(
        self, svc_dirs: list[Path], nodes: list, edges: list, seen: set
    ) -> dict[str, Node]:
        """Scan service files and create service nodes."""
        service_map = {}
        for d in svc_dirs:
            for f in sorted(d.rglob("*.service.ts")):
                if ".spec." in f.name:
                    continue
                svc_id = f"ng_svc_{self._svc_file_to_id(f.name)}"
                if svc_id not in seen:
                    seen.add(svc_id)
                    node = Node(
                        id=svc_id,
                        type="ng_service",
                        name=f.name,
                        file_path=rel_path(self.repo_root, f),
                    )
                    nodes.append(node)
                    service_map[svc_id] = node
        return service_map

    def _scan_guards(
        self, guard_dirs: list[Path], nodes: list, edges: list, seen: set
    ) -> None:
        for d in guard_dirs:
            for f in sorted(d.rglob("*.guard.ts")):
                if ".spec." in f.name:
                    continue
                gid = f"ng_guard_{re.sub(r'.guard.ts$', '', f.name).replace('-', '_')}"
                if gid not in seen:
                    seen.add(gid)
                    nodes.append(Node(
                        id=gid,
                        type="ng_guard",
                        name=f.name,
                        file_path=rel_path(self.repo_root, f),
                    ))

    def _scan_shared(
        self, shared_dirs: list[Path], nodes: list, edges: list, seen: set
    ) -> None:
        for d in shared_dirs:
            for sub in list_dirs(d):
                cid = f"ng_shared_{sub.name.replace('-', '_')}"
                if cid not in seen:
                    seen.add(cid)
                    nodes.append(Node(
                        id=cid,
                        type="ng_shared",
                        name=sub.name,
                        file_path=rel_path(self.repo_root, sub),
                    ))

    # -- Relationship extraction -------------------------------------------

    def _feature_service_usage(self, features_dir: Path) -> dict[str, list[str]]:
        """Map features to injected service class names."""
        result: dict[str, list[str]] = {}
        if not features_dir.exists():
            return result
        for feat_dir in list_dirs(features_dir):
            services_found: set[str] = set()
            for ts_file in feat_dir.rglob("*.ts"):
                if ".spec." in ts_file.name:
                    continue
                content = read_safe(ts_file)
                for m in _INJECT_PATTERN.finditer(content):
                    type_name = m.group(2)
                    if (
                        type_name.endswith("Service")
                        and type_name not in _ANGULAR_TYPES
                        and type_name not in _SKIP_TYPES
                    ):
                        services_found.add(type_name)
            if services_found:
                result[feat_dir.name] = sorted(services_found)
        return result

    def _service_endpoint_usage(
        self, svc_dirs: list[Path]
    ) -> dict[str, list[tuple[str, str]]]:
        """Map service files to HTTP endpoints they call."""
        result: dict[str, list[tuple[str, str]]] = {}
        for d in svc_dirs:
            for f in sorted(d.rglob("*.service.ts")):
                if ".spec." in f.name:
                    continue
                content = read_safe(f)
                endpoints: list[tuple[str, str]] = []
                # Direct HTTP calls: this.http.get('/path')
                for m in _HTTP_CALL_PATTERN.finditer(content):
                    method = m.group(1).upper()
                    path = m.group(2)
                    endpoints.append((method, path))
                # URL builder calls: buildApiUrl('path') — method unknown
                for m in _URL_BUILDER_PATTERN.finditer(content):
                    path = m.group(1)
                    endpoints.append(("ANY", path))
                if endpoints:
                    result[f.name] = sorted(set(endpoints))
        return result

    def _build_flows(
        self,
        feat_svcs: dict[str, list[str]],
        svc_endpoints: dict[str, list[tuple[str, str]]],
        seen_ids: set[str],
    ) -> dict[str, str]:
        flows: dict[str, str] = {}
        for feat_name, svc_classes in feat_svcs.items():
            feat_id = f"ng_page_{feat_name.replace('-', '_')}"
            paths = []
            for svc_class in svc_classes:
                svc_slug = camel_to_snake(re.sub(r"Service$", "", svc_class))
                svc_id = f"ng_svc_{svc_slug}"
                steps = [
                    {"id": feat_id, "type": "ng_page"},
                    {"id": svc_id, "type": "ng_service", "edge": "uses"},
                ]
                paths.append({"name": f"via-{svc_slug}", "steps": steps})
            if paths:
                flows[feat_name] = render_flow_yaml(feat_name, paths)
        return flows

    def _svc_file_to_id(self, filename: str) -> str:
        base = re.sub(r"\.service\.ts$", "", filename)
        return base.replace("-", "_").replace(".", "_")

    # -- File-level analysis -----------------------------------------------

    def supported_extensions(self) -> set[str]:
        return {".ts", ".tsx"}

    def analyze_file(self, file_path: Path) -> dict | None:
        if not file_path.is_file() or file_path.suffix not in (".ts", ".tsx"):
            return None

        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        total = len(lines)

        # Injected services
        services = []
        for m in _INJECT_PATTERN.finditer(content):
            field_name, type_name = m.group(1), m.group(2)
            if (
                type_name[0].isupper()
                and type_name not in _ANGULAR_TYPES
                and type_name not in _SKIP_TYPES
            ):
                services.append({"field": field_name, "type": type_name})

        # Methods
        method_pattern = re.compile(
            r"^\s+(?:async\s+)?(\w+)\s*\([^)]*\)\s*[:{]", re.MULTILINE
        )
        lifecycle = {
            "ngOnInit", "ngOnDestroy", "ngAfterViewChecked", "ngOnChanges",
            "constructor", "ngAfterViewInit",
        }
        skip = {
            "if", "for", "while", "switch", "catch", "else", "return",
            "throw", "try", "finally", "case", "default",
        }
        methods = []
        for m in method_pattern.finditer(content):
            name = m.group(1)
            if name not in lifecycle and name not in skip and not name.startswith("_"):
                start_line = content[: m.start()].count("\n") + 1
                methods.append({"name": name, "line": start_line})

        for i, method in enumerate(methods):
            if i + 1 < len(methods):
                method["approx_lines"] = methods[i + 1]["line"] - method["line"]
            else:
                method["approx_lines"] = total - method["line"]

        methods.sort(key=lambda m: m["approx_lines"], reverse=True)

        return {
            "type": "angular",
            "file": file_path.name,
            "total_lines": total,
            "services_injected": services,
            "service_count": len(services),
            "method_count": len(methods),
            "methods": methods,
        }

    def suggest_splits(self, file_path: Path, analysis: dict) -> list[dict] | None:
        if analysis.get("type") != "angular":
            return None
        services = analysis.get("services_injected", [])
        methods = analysis.get("methods", [])
        if not services or not methods:
            return None

        source_lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()

        # Build service field → cluster mapping
        svc_field_to_cluster: dict[str, str] = {}
        cluster_to_type: dict[str, list[str]] = {}
        for svc in services:
            field = svc["field"]
            type_name = svc["type"]
            if type_name in _ANGULAR_TYPES:
                continue
            cluster = re.sub(r"Service$", "", type_name)
            cluster = re.sub(r"([a-z])([A-Z])", r"\1-\2", cluster).lower()
            svc_field_to_cluster[field] = cluster
            cluster_to_type.setdefault(cluster, []).append(type_name)

        if not svc_field_to_cluster:
            return None

        # Map methods to clusters by service reference
        assignments: dict[str, list[dict]] = {}
        assigned: set[str] = set()

        for method in methods:
            start = method.get("line", 0) - 1
            end = start + method.get("approx_lines", 20)
            body = "\n".join(source_lines[start:end])

            refs: dict[str, int] = {}
            for field_name, cluster in svc_field_to_cluster.items():
                count = len(re.findall(rf"\bthis\.{re.escape(field_name)}\b", body))
                if count > 0:
                    refs[cluster] = refs.get(cluster, 0) + count

            if refs:
                dominant = max(refs, key=refs.get)
                assignments.setdefault(dominant, []).append(method)
                assigned.add(method["name"])

        component_name = file_path.stem.replace(".component", "")
        clusters = []
        for cluster, cluster_methods in sorted(assignments.items(), key=lambda x: -len(x[1])):
            total_lines = sum(m.get("approx_lines", 0) for m in cluster_methods)
            clusters.append({
                "suggested_name": f"{component_name}-{cluster}",
                "methods": [m["name"] for m in cluster_methods],
                "method_count": len(cluster_methods),
                "approx_lines": total_lines,
                "related_services": cluster_to_type.get(cluster, []),
            })

        remaining = [m for m in methods if m["name"] not in assigned]
        if remaining:
            clusters.append({
                "suggested_name": f"{component_name} (shell/orchestrator)",
                "methods": [m["name"] for m in remaining],
                "method_count": len(remaining),
                "approx_lines": sum(m.get("approx_lines", 0) for m in remaining),
                "related_services": [],
            })

        return clusters

    def format_bloat_report(self, analysis: dict) -> str | None:
        if analysis.get("type") != "angular":
            return None
        lines = [
            f"Bloat report: {analysis['file']} ({analysis['total_lines']} lines, "
            f"{analysis['service_count']} services, {analysis['method_count']} methods)\n"
        ]
        if analysis["services_injected"]:
            lines.append("Injected services:")
            for s in analysis["services_injected"]:
                lines.append(f"  {s['field']}: {s['type']}")

        lines.append("\nMethods (largest first):")
        for m in analysis["methods"][:15]:
            bar = "█" * (m["approx_lines"] // 3)
            lines.append(
                f"  ~{m['approx_lines']:>3} lines  {bar:30s}  {m['name']} (L{m['line']})"
            )
        return "\n".join(lines)

    def format_split_plan(self, file_path: str, analysis: dict, splits: list[dict]) -> str | None:
        if analysis.get("type") != "angular":
            return None
        lines = [f"Split plan for {file_path} ({analysis['total_lines']} lines):\n"]
        for i, cluster in enumerate(splits, 1):
            lines.append(f"  {i}. {cluster['suggested_name']} (~{cluster['approx_lines']} lines)")
            if cluster["related_services"]:
                lines.append(f"     Services: {', '.join(cluster['related_services'])}")
            lines.append(f"     Methods: {', '.join(cluster['methods'][:10])}")
            if len(cluster["methods"]) > 10:
                lines.append(f"     ... and {len(cluster['methods']) - 10} more")

        largest = max(c["approx_lines"] for c in splits) if splits else analysis["total_lines"]
        lines.append(f"\n  Context savings: {analysis['total_lines']} -> max ~{largest} per task touch")
        return "\n".join(lines)
