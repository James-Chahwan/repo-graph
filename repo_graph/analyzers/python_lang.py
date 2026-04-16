"""
Python language analyzer.

Detects Python projects via pyproject.toml, setup.py, or requirements.txt.
Scans for modules, classes, functions, and framework routes
(Flask, FastAPI, Django).
"""

import re
from pathlib import Path

from .base import (
    AnalysisResult,
    Edge,
    LanguageAnalyzer,
    Node,
    read_safe,
    rel_path,
)


# Function/method definitions
_DEF_PATTERN = re.compile(r"^(?:async\s+)?def\s+(\w+)\s*\(", re.MULTILINE)

# Class definitions
_CLASS_PATTERN = re.compile(r"^class\s+(\w+)\s*[\(:]", re.MULTILINE)

# Import patterns
_IMPORT_FROM = re.compile(r"^from\s+(\.[\w.]*)\s+import", re.MULTILINE)
_IMPORT_ABS = re.compile(r"^from\s+([\w.]+)\s+import", re.MULTILINE)

# Flask/FastAPI route decorators
_ROUTE_DECORATOR = re.compile(
    r'@\w+\.(get|post|put|delete|patch|route)\(\s*[\'"]([^\'"]+)[\'"]',
    re.MULTILINE,
)

# Django urlpatterns
_DJANGO_PATH = re.compile(
    r'(?:path|re_path)\(\s*[\'"]([^\'"]+)[\'"]', re.MULTILINE
)


class PythonAnalyzer(LanguageAnalyzer):

    _PY_MARKERS = {"pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"}

    @staticmethod
    def detect(index) -> bool:
        return bool(
            index.dirs_with_any(PythonAnalyzer._PY_MARKERS)
            or index.extra_roots("python")
        )

    def scan(self) -> AnalysisResult:
        nodes: list[Node] = []
        edges: list[Edge] = []
        seen_ids: set[str] = set()

        # Find the main package(s)
        packages = self._find_packages()

        for pkg_root in packages:
            pkg_name = pkg_root.name
            pkg_id = f"py_pkg_{pkg_name}"
            if pkg_id not in seen_ids:
                seen_ids.add(pkg_id)
                nodes.append(Node(
                    id=pkg_id,
                    type="py_package",
                    name=pkg_name,
                    file_path=rel_path(self.repo_root, pkg_root),
                ))

            for py_file in self.index.files_with_ext(".py", under=pkg_root):
                if self._should_skip(py_file):
                    continue

                file_rel = rel_path(self.repo_root, py_file)
                mod_id = self._file_to_id(py_file)

                if mod_id in seen_ids:
                    continue
                seen_ids.add(mod_id)

                nodes.append(Node(
                    id=mod_id,
                    type="py_module",
                    name=py_file.stem,
                    file_path=file_rel,
                ))
                edges.append(Edge(from_id=pkg_id, to_id=mod_id, type="contains"))

                content = read_safe(py_file)

                # Extract classes
                for m in _CLASS_PATTERN.finditer(content):
                    class_name = m.group(1)
                    class_id = f"py_class_{mod_id}_{class_name}"
                    if class_id not in seen_ids:
                        seen_ids.add(class_id)
                        nodes.append(Node(
                            id=class_id,
                            type="py_class",
                            name=class_name,
                            file_path=file_rel,
                        ))
                        edges.append(Edge(from_id=mod_id, to_id=class_id, type="defines"))

                # Extract top-level functions
                for m in _DEF_PATTERN.finditer(content):
                    func_name = m.group(1)
                    # Only top-level (no leading whitespace)
                    line_start = content[: m.start()].rfind("\n") + 1
                    if m.start() == line_start or content[line_start : m.start()].strip() in ("", "async"):
                        func_id = f"py_func_{mod_id}_{func_name}"
                        if func_id not in seen_ids:
                            seen_ids.add(func_id)
                            nodes.append(Node(
                                id=func_id,
                                type="py_function",
                                name=func_name,
                                file_path=file_rel,
                            ))
                            edges.append(Edge(from_id=mod_id, to_id=func_id, type="defines"))

                # Extract routes (Flask/FastAPI)
                for m in _ROUTE_DECORATOR.finditer(content):
                    method = m.group(1).upper()
                    if method == "ROUTE":
                        method = "ANY"
                    path = m.group(2)
                    route_id = f"route_{method}_{path.replace('/', '_').strip('_')}"
                    if route_id not in seen_ids:
                        seen_ids.add(route_id)
                        nodes.append(Node(
                            id=route_id,
                            type="route",
                            name=f"{method} {path}",
                            file_path=file_rel,
                        ))
                        edges.append(Edge(from_id=route_id, to_id=mod_id, type="handled_by"))

                # Extract Django URL patterns
                for m in _DJANGO_PATH.finditer(content):
                    path = m.group(1)
                    route_id = f"route_ANY_{path.replace('/', '_').strip('_')}"
                    if route_id not in seen_ids:
                        seen_ids.add(route_id)
                        nodes.append(Node(
                            id=route_id,
                            type="route",
                            name=path,
                            file_path=file_rel,
                        ))
                        edges.append(Edge(from_id=route_id, to_id=mod_id, type="handled_by"))

                # Extract relative imports → edges
                for m in _IMPORT_FROM.finditer(content):
                    imp = m.group(1)
                    resolved = self._resolve_relative_import(py_file, imp)
                    if resolved:
                        target_id = self._file_to_id(resolved)
                        if target_id in seen_ids:
                            edges.append(Edge(from_id=mod_id, to_id=target_id, type="imports"))

        return AnalysisResult(
            nodes=nodes,
            edges=edges,
            state_sections=self._state_section(packages),
        )

    def _find_packages(self) -> list[Path]:
        """Find Python packages (directories with __init__.py)."""
        _skip = {"venv", "env", ".venv", "node_modules", "dist", "build", "__pycache__"}
        packages: list[Path] = []
        seen: set[Path] = set()
        # Every directory with an __init__.py is a package candidate; keep only
        # those whose parent is NOT itself a package (i.e., top-level packages).
        pkg_dirs = set(self.index.dirs_with_file("__init__.py"))
        for pkg_dir in sorted(pkg_dirs):
            if pkg_dir.parent in pkg_dirs:
                continue
            if pkg_dir.name.startswith(".") or pkg_dir.name.startswith("_"):
                continue
            if pkg_dir.name in _skip:
                continue
            if pkg_dir in seen:
                continue
            seen.add(pkg_dir)
            packages.append(pkg_dir)
        # Config-supplied python roots — add any that weren't already captured.
        for extra in self.index.extra_roots("python"):
            if extra not in seen:
                seen.add(extra)
                packages.append(extra)
        # Fallback: single-file scripts at root with a pyproject.toml
        if not packages:
            root_py = [
                f for f in self.index.files_with_ext(".py", under=self.repo_root)
                if f.parent == self.repo_root and f.name != "setup.py"
            ]
            if root_py:
                packages.append(self.repo_root)
        return packages

    def _should_skip(self, py_file: Path) -> bool:
        name = py_file.name
        parts = str(py_file)
        return (
            name.startswith("test_")
            or name.endswith("_test.py")
            or "conftest" in name
            or "/tests/" in parts
            or "/test/" in parts
            or "__pycache__" in parts
            or "/.venv/" in parts
            or "/venv/" in parts
            or "/env/" in parts
            or ".egg-info" in parts
        )

    def _file_to_id(self, py_file: Path) -> str:
        rel = rel_path(self.repo_root, py_file)
        stem = re.sub(r"\.py$", "", rel)
        # __init__ → use parent dir name
        if stem.endswith("/__init__"):
            stem = stem[: -len("/__init__")]
        return "py_mod_" + stem.replace("/", "_").replace("-", "_").replace(".", "_")

    def _resolve_relative_import(self, from_file: Path, imp: str) -> Path | None:
        """Resolve a relative import like '.foo' or '..bar'."""
        dots = len(imp) - len(imp.lstrip("."))
        rest = imp.lstrip(".")
        base = from_file.parent
        for _ in range(dots - 1):
            base = base.parent
        if rest:
            parts = rest.split(".")
            target = base / "/".join(parts)
            if target.with_suffix(".py").exists():
                return target.with_suffix(".py")
            if (target / "__init__.py").exists():
                return target / "__init__.py"
        return None

    def _state_section(self, packages: list[Path]) -> dict[str, str]:
        if not packages:
            return {}
        lines = []
        for pkg in packages:
            all_py = self.index.files_with_ext(".py", under=pkg)
            py_files = [f for f in all_py if not self._should_skip(f)]
            test_files = [
                f for f in all_py
                if f.name.startswith("test_") or f.name.endswith("_test.py")
            ]
            lines.append(
                f"- **{pkg.name}** — {len(py_files)} source files, {len(test_files)} test files"
            )
        return {"Python Packages": "\n".join(lines) + "\n"}

    # -- File-level analysis -----------------------------------------------

    def supported_extensions(self) -> set[str]:
        return {".py"}

    def analyze_file(self, file_path: Path) -> dict | None:
        if not file_path.is_file() or file_path.suffix != ".py":
            return None

        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        total = len(lines)

        # Find all function/method definitions with their indentation level
        functions = []
        for i, line in enumerate(lines, 1):
            m = re.match(r"^(\s*)(?:async\s+)?def\s+(\w+)\s*\(", line)
            if m:
                indent = len(m.group(1))
                functions.append({
                    "name": m.group(2),
                    "start": i,
                    "indent": indent,
                    "is_method": indent > 0,
                })

        # Estimate function sizes
        for j, func in enumerate(functions):
            if j + 1 < len(functions):
                func["end"] = functions[j + 1]["start"] - 1
            else:
                func["end"] = total
            func["lines"] = func["end"] - func["start"] + 1

        functions.sort(key=lambda f: f["lines"], reverse=True)

        # Find classes
        classes = []
        for m in _CLASS_PATTERN.finditer(content):
            class_name = m.group(1)
            line_num = content[: m.start()].count("\n") + 1
            classes.append({"name": class_name, "line": line_num})

        return {
            "type": "python",
            "file": file_path.name,
            "total_lines": total,
            "function_count": len(functions),
            "functions": functions,
            "class_count": len(classes),
            "classes": classes,
        }

    def format_bloat_report(self, analysis: dict) -> str | None:
        if analysis.get("type") != "python":
            return None
        lines = [
            f"Bloat report: {analysis['file']} ({analysis['total_lines']} lines, "
            f"{analysis['function_count']} functions, {analysis['class_count']} classes)\n",
            "Functions (largest first):",
        ]
        for fn in analysis["functions"][:15]:
            bar = "█" * (fn["lines"] // 5)
            kind = "method" if fn.get("is_method") else "func"
            lines.append(
                f"  {fn['lines']:>4} lines  {bar:30s}  {fn['name']} "
                f"[{kind}] (L{fn['start']}-{fn['end']})"
            )
        return "\n".join(lines)

    def suggest_splits(self, file_path: Path, analysis: dict) -> list[dict] | None:
        if analysis.get("type") != "python":
            return None
        functions = analysis.get("functions", [])
        classes = analysis.get("classes", [])

        # Group methods by their class
        if classes:
            groups: dict[str, list[dict]] = {"(module-level)": []}
            class_lines = {c["name"]: c["line"] for c in classes}
            class_names = sorted(class_lines.keys(), key=lambda n: class_lines[n])

            for fn in functions:
                if not fn.get("is_method"):
                    groups["(module-level)"].append(fn)
                    continue
                assigned = False
                for cls_name in reversed(class_names):
                    if fn["start"] > class_lines[cls_name]:
                        groups.setdefault(cls_name, []).append(fn)
                        assigned = True
                        break
                if not assigned:
                    groups["(module-level)"].append(fn)

            return [
                {
                    "suggested_name": f"{file_path.stem}_{group_name.lower()}",
                    "methods": [f["name"] for f in fns],
                    "method_count": len(fns),
                    "approx_lines": sum(f["lines"] for f in fns),
                    "related_services": [],
                }
                for group_name, fns in groups.items()
                if fns
            ]

        if len(functions) < 4:
            return None

        return [{
            "suggested_name": file_path.stem,
            "methods": [f["name"] for f in functions],
            "method_count": len(functions),
            "approx_lines": sum(f["lines"] for f in functions),
            "related_services": [],
        }]

    def format_split_plan(self, file_path: str, analysis: dict, splits: list[dict]) -> str | None:
        if analysis.get("type") != "python":
            return None
        lines = [
            f"Split plan for {file_path} ({analysis['total_lines']} lines, "
            f"{analysis['function_count']} functions):\n"
        ]
        for i, cluster in enumerate(splits, 1):
            lines.append(f"  {i}. {cluster['suggested_name']}.py (~{cluster['approx_lines']} lines)")
            fn_names = cluster["methods"]
            lines.append(f"     Functions: {', '.join(fn_names[:8])}")
            if len(fn_names) > 8:
                lines.append(f"     ... and {len(fn_names) - 8} more")
        return "\n".join(lines)
