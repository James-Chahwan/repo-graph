"""
File analysis — internal structure, bloat detection, split suggestions.

Reads actual source files to analyze function boundaries, SCSS blocks,
service injection patterns, and propose concrete splits.
"""

import re
from pathlib import Path


def analyze_go_file(file_path: Path) -> dict:
    """Analyze a Go file: functions, their line ranges, and size."""
    if not file_path.is_file():
        return {"error": f"File not found: {file_path}"}

    content = file_path.read_text(encoding="utf-8", errors="ignore")
    lines = content.splitlines()
    total = len(lines)

    # Find function definitions
    func_pattern = re.compile(r'^func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(')
    functions = []
    current_func = None
    brace_depth = 0

    for i, line in enumerate(lines, 1):
        m = func_pattern.match(line)
        if m and brace_depth == 0:
            if current_func:
                current_func["end"] = i - 1
                current_func["lines"] = current_func["end"] - current_func["start"] + 1
                functions.append(current_func)
            current_func = {"name": m.group(1), "start": i, "end": total, "lines": 0}

        brace_depth += line.count("{") - line.count("}")

    if current_func:
        current_func["end"] = total
        current_func["lines"] = current_func["end"] - current_func["start"] + 1
        functions.append(current_func)

    # Find repo/service usage per function
    repo_pattern = re.compile(r'Services\.(\w+Repository)\(\)')
    imports = []
    in_import = False
    for line in lines:
        if 'import (' in line:
            in_import = True
            continue
        if in_import:
            if ')' in line:
                in_import = False
                continue
            stripped = line.strip().strip('"')
            if stripped:
                imports.append(stripped)

    functions.sort(key=lambda f: f["lines"], reverse=True)

    return {
        "file": str(file_path.name),
        "total_lines": total,
        "function_count": len(functions),
        "functions": functions,
        "imports": imports,
    }


def analyze_ts_component(file_path: Path) -> dict:
    """Analyze an Angular TypeScript component: injected services, methods, size."""
    if not file_path.is_file():
        return {"error": f"File not found: {file_path}"}

    content = file_path.read_text(encoding="utf-8", errors="ignore")
    lines = content.splitlines()
    total = len(lines)

    # Injected services — match constructor params: `private fooService: FooService`
    # Only count types ending in Service, Store, or known Angular DI types.
    svc_pattern = re.compile(
        r'private\s+(?:readonly\s+)?(\w+)\s*:\s*(\w+)', re.MULTILINE
    )
    # Types that are injected but not domain services
    angular_types = {"ElementRef", "Renderer2", "ChangeDetectorRef", "NgZone",
                     "Injector", "ViewContainerRef", "TemplateRef"}
    # Non-service types that leak through (native TS / DOM types)
    skip_types = {"Map", "Set", "Array", "Object", "MediaStream", "HTMLElement",
                  "FormGroup", "FormControl", "Subject", "BehaviorSubject",
                  "Subscription", "Observable"}
    services = []
    for m in svc_pattern.finditer(content):
        field, type_name = m.group(1), m.group(2)
        if type_name[0].isupper() and type_name not in angular_types and type_name not in skip_types:
            services.append({"field": field, "type": type_name})

    # Methods — skip control flow keywords and lifecycle hooks
    method_pattern = re.compile(r'^\s+(?:async\s+)?(\w+)\s*\([^)]*\)\s*[:{]', re.MULTILINE)
    lifecycle = {"ngOnInit", "ngOnDestroy", "ngAfterViewChecked", "ngOnChanges",
                 "constructor", "ngAfterViewInit"}
    control_flow = {"if", "for", "while", "switch", "catch", "else", "return",
                    "throw", "try", "finally", "case", "default"}
    methods = []
    for m in method_pattern.finditer(content):
        name = m.group(1)
        if name not in lifecycle and name not in control_flow and not name.startswith("_"):
            start_line = content[:m.start()].count("\n") + 1
            methods.append({"name": name, "line": start_line})

    # Estimate method sizes by distance between starts
    for i, method in enumerate(methods):
        if i + 1 < len(methods):
            method["approx_lines"] = methods[i + 1]["line"] - method["line"]
        else:
            method["approx_lines"] = total - method["line"]

    methods.sort(key=lambda m: m["approx_lines"], reverse=True)

    return {
        "file": str(file_path.name),
        "total_lines": total,
        "services_injected": services,
        "service_count": len(services),
        "method_count": len(methods),
        "methods": methods,
    }


def analyze_scss_file(file_path: Path) -> dict:
    """Analyze SCSS file: top-level rule blocks with line ranges."""
    if not file_path.is_file():
        return {"error": f"File not found: {file_path}"}

    content = file_path.read_text(encoding="utf-8", errors="ignore")
    lines = content.splitlines()
    total = len(lines)

    # Find top-level selectors (lines starting with . or & or : or element names, not indented)
    selector_pattern = re.compile(r'^([.&:@#\w][\w\-.*,\s&:()>+~]*)\s*\{')
    blocks = []
    current_block = None
    depth = 0

    for i, line in enumerate(lines, 1):
        if depth == 0:
            m = selector_pattern.match(line)
            if m:
                if current_block:
                    current_block["end"] = i - 1
                    current_block["lines"] = current_block["end"] - current_block["start"] + 1
                    blocks.append(current_block)
                current_block = {"selector": m.group(1).strip(), "start": i, "end": total, "lines": 0}

        depth += line.count("{") - line.count("}")

    if current_block:
        current_block["end"] = total
        current_block["lines"] = current_block["end"] - current_block["start"] + 1
        blocks.append(current_block)

    blocks.sort(key=lambda b: b["lines"], reverse=True)

    return {
        "file": str(file_path.name),
        "total_lines": total,
        "block_count": len(blocks),
        "blocks": blocks,
    }


def suggest_splits(
    component_name: str,
    ts_analysis: dict,
    scss_analysis: dict | None = None,
    file_path: Path | None = None,
) -> list[dict]:
    """
    Suggest component splits based on which service each method actually references.

    Reads the source file to find which injected service field names appear in
    each method body, then clusters methods by their dominant service. No
    hardcoded keyword dictionaries — derived entirely from the code.
    """
    services = ts_analysis.get("services_injected", [])
    methods = ts_analysis.get("methods", [])

    if not services or not methods:
        return []

    # Read the actual file to map methods → service usage
    source_lines: list[str] = []
    if file_path and file_path.is_file():
        source_lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()

    # Build service field name → cluster name mapping from actual injected services.
    # e.g. "chatClient" (field) → "chat-client" (cluster), type "ChatClientService"
    # Cluster name = service type with "Service" stripped, lowered, hyphenated.
    svc_field_to_cluster: dict[str, str] = {}
    cluster_to_type: dict[str, list[str]] = {}
    for svc in services:
        field = svc["field"]
        type_name = svc["type"]
        # Skip Angular/utility types — not domain services
        if type_name in ("Router", "ActivatedRoute", "DomSanitizer",
                         "HttpClient", "ElementRef", "Renderer2"):
            continue
        # Derive cluster name from type: "ChatClientService" → "chat-client"
        cluster = re.sub(r"Service$", "", type_name)
        cluster = re.sub(r"([a-z])([A-Z])", r"\1-\2", cluster).lower()
        svc_field_to_cluster[field] = cluster
        cluster_to_type.setdefault(cluster, []).append(type_name)

    if not svc_field_to_cluster:
        return []

    # For each method, find which service fields are referenced in its body
    method_clusters: dict[str, dict[str, int]] = {}  # method_name → {cluster: ref_count}

    for i, method in enumerate(methods):
        start = method.get("line", 0) - 1  # 0-indexed
        end = start + method.get("approx_lines", 20)
        body = "\n".join(source_lines[start:end]) if source_lines else ""

        refs: dict[str, int] = {}
        for field, cluster in svc_field_to_cluster.items():
            # Count references like `this.chatClient.` or `this.chatClient,`
            count = len(re.findall(rf'\bthis\.{re.escape(field)}\b', body))
            if count > 0:
                refs[cluster] = refs.get(cluster, 0) + count

        if refs:
            method_clusters[method["name"]] = refs

    # Assign each method to its dominant cluster (most references)
    assignments: dict[str, list[dict]] = {}  # cluster → [methods]
    assigned_names: set[str] = set()

    for method in methods:
        name = method["name"]
        refs = method_clusters.get(name, {})
        if refs:
            dominant = max(refs, key=refs.get)
            assignments.setdefault(dominant, []).append(method)
            assigned_names.add(name)

    # Build cluster output
    clusters: list[dict] = []
    for cluster, cluster_methods in sorted(assignments.items(), key=lambda x: -len(x[1])):
        total_lines = sum(m.get("approx_lines", 0) for m in cluster_methods)
        clusters.append({
            "suggested_name": f"{component_name}-{cluster}",
            "methods": [m["name"] for m in cluster_methods],
            "method_count": len(cluster_methods),
            "approx_lines": total_lines,
            "related_services": cluster_to_type.get(cluster, []),
        })

    # Catch unclustered methods as the "shell" remainder
    remaining = [m for m in methods if m["name"] not in assigned_names]
    if remaining:
        clusters.append({
            "suggested_name": f"{component_name} (shell/orchestrator)",
            "methods": [m["name"] for m in remaining],
            "method_count": len(remaining),
            "approx_lines": sum(m.get("approx_lines", 0) for m in remaining),
            "related_services": [],
        })

    return clusters
