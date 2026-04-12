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

    # Injected services
    svc_pattern = re.compile(
        r'private\s+(?:readonly\s+)?(\w+)\s*:\s*(\w+)', re.MULTILINE
    )
    services = []
    for m in svc_pattern.finditer(content):
        field, type_name = m.group(1), m.group(2)
        if type_name[0].isupper() and type_name != "ElementRef":
            services.append({"field": field, "type": type_name})

    # Methods
    method_pattern = re.compile(r'^\s+(?:async\s+)?(\w+)\s*\([^)]*\)\s*[:{]', re.MULTILINE)
    lifecycle = {"ngOnInit", "ngOnDestroy", "ngAfterViewChecked", "ngOnChanges",
                 "constructor", "ngAfterViewInit"}
    methods = []
    for m in method_pattern.finditer(content):
        name = m.group(1)
        if name not in lifecycle and not name.startswith("_"):
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


def suggest_splits(component_name: str, ts_analysis: dict, scss_analysis: dict | None = None) -> list[dict]:
    """
    Suggest component splits based on service clustering.

    Groups methods by which service they likely use (heuristic: method name
    contains service-related keywords). Returns proposed child components.
    """
    services = ts_analysis.get("services_injected", [])
    methods = ts_analysis.get("methods", [])

    if not services or not methods:
        return []

    # Build keyword clusters from service names
    # e.g., ChatClientService -> ["chat", "message", "typing", "send"]
    clusters: list[dict] = []
    service_keywords = {
        "chat": ["chat", "message", "typing", "send", "stream", "ws"],
        "group": ["group", "select", "filter", "panel", "sidebar"],
        "auth": ["auth", "login", "user", "token", "session"],
        "activity": ["activity", "activities", "rsvp", "join", "event"],
        "matching": ["match", "swipe", "recommend", "feedback", "rating"],
        "notification": ["notif", "alert", "badge"],
        "friend": ["friend", "request", "pending"],
        "profile": ["profile", "avatar", "bio", "edit"],
    }

    # Map methods to clusters
    for cluster_name, keywords in service_keywords.items():
        # Check if any injected service relates to this cluster
        has_service = any(
            cluster_name.lower() in s["type"].lower()
            for s in services
        )
        if not has_service:
            continue

        cluster_methods = [
            m for m in methods
            if any(kw in m["name"].lower() for kw in keywords)
        ]
        if cluster_methods:
            total_lines = sum(m.get("approx_lines", 0) for m in cluster_methods)
            clusters.append({
                "suggested_name": f"{component_name}-{cluster_name}",
                "methods": [m["name"] for m in cluster_methods],
                "method_count": len(cluster_methods),
                "approx_lines": total_lines,
                "related_services": [
                    s["type"] for s in services
                    if cluster_name.lower() in s["type"].lower()
                ],
            })

    # Catch unclustered methods as the "shell" remainder
    clustered_names = set()
    for c in clusters:
        clustered_names.update(c["methods"])

    remaining = [m for m in methods if m["name"] not in clustered_names]
    if remaining:
        clusters.append({
            "suggested_name": f"{component_name} (shell/orchestrator)",
            "methods": [m["name"] for m in remaining],
            "method_count": len(remaining),
            "approx_lines": sum(m.get("approx_lines", 0) for m in remaining),
            "related_services": [],
        })

    return clusters
