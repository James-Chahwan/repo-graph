"""
Python language analyzer.

Uses stdlib `ast` for structural extraction + call/import resolution.
Detects Python projects via pyproject.toml, setup.py, or requirements.txt.

0.3.0 limitations (see dev-notes/0.3.0-decisions.md):
  - Files with syntax errors are dropped whole (item 13, SCOPE-DRIVEN).
  - Call resolution is best-effort; unresolvable sites drop silently (item 3, PRINCIPLED).
  - Import edges are module→module only (item 6, SCOPE-DRIVEN).
  - Routes remain regex-based (item 8, SCOPE-DRIVEN).
"""

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .base import (
    AnalysisResult,
    Edge,
    LanguageAnalyzer,
    Node,
    read_safe,
    rel_path,
)


# ---------------------------------------------------------------------------
# AST helpers — plain data + pure functions
# ---------------------------------------------------------------------------


@dataclass
class FuncInfo:
    name: str
    lineno: int
    node: ast.AST  # FunctionDef | AsyncFunctionDef


@dataclass
class ClassInfo:
    name: str
    lineno: int
    methods: list[FuncInfo] = field(default_factory=list)
    node: ast.ClassDef | None = None


@dataclass
class ImportInfo:
    kind: Literal["import", "from"]
    module: str | None
    names: list[tuple[str, str]]  # (imported_name, alias)
    level: int


@dataclass
class CallInfo:
    kind: Literal["name", "attr", "self_attr"]
    parts: tuple[str, ...]
    lineno: int


def parse_module(path: Path) -> ast.Module | None:
    """Parse a file to ast.Module. Returns None on read error or SyntaxError."""
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    try:
        return ast.parse(source, filename=str(path))
    except SyntaxError:
        return None


def find_module_functions(tree: ast.Module) -> list[FuncInfo]:
    """Top-level def/async def. Nested defs are not returned (0.3.0 item 9)."""
    out: list[FuncInfo] = []
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(FuncInfo(name=stmt.name, lineno=stmt.lineno, node=stmt))
    return out


def find_classes(tree: ast.Module) -> list[ClassInfo]:
    """Top-level class defs with methods populated from class body."""
    out: list[ClassInfo] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.ClassDef):
            methods: list[FuncInfo] = []
            for m in stmt.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(FuncInfo(name=m.name, lineno=m.lineno, node=m))
            out.append(ClassInfo(name=stmt.name, lineno=stmt.lineno, methods=methods, node=stmt))
    return out


def find_imports(tree: ast.Module) -> list[ImportInfo]:
    out: list[ImportInfo] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Import):
            names = [(n.name, n.asname or n.name) for n in stmt.names]
            out.append(ImportInfo(kind="import", module=None, names=names, level=0))
        elif isinstance(stmt, ast.ImportFrom):
            names = [(n.name, n.asname or n.name) for n in stmt.names]
            out.append(ImportInfo(
                kind="from",
                module=stmt.module,
                names=names,
                level=stmt.level or 0,
            ))
    return out


def find_calls(fn_node: ast.AST) -> list[CallInfo]:
    """Walk a function body for call sites. Skips nested def/class bodies
    (item 9: nested functions are not nodes in 0.3.0, so their call sites
    don't bubble up as calls from the enclosing function)."""
    calls: list[CallInfo] = []

    class _Walker(ast.NodeVisitor):
        def visit_FunctionDef(self, node):  # noqa: N802
            pass  # don't recurse into nested def

        def visit_AsyncFunctionDef(self, node):  # noqa: N802
            pass

        def visit_ClassDef(self, node):  # noqa: N802
            pass

        def visit_Call(self, node: ast.Call):  # noqa: N802
            info = _call_info(node)
            if info is not None:
                calls.append(info)
            # Still recurse into args/kwargs for nested calls
            for a in node.args:
                self.visit(a)
            for kw in node.keywords:
                self.visit(kw.value)

    walker = _Walker()
    body = getattr(fn_node, "body", None)
    if body is None:
        return calls
    for stmt in body:
        walker.visit(stmt)
    return calls


def _call_info(call: ast.Call) -> CallInfo | None:
    """Characterise a call's func expression as name / attr / self_attr."""
    func = call.func
    if isinstance(func, ast.Name):
        return CallInfo(kind="name", parts=(func.id,), lineno=call.lineno)
    if isinstance(func, ast.Attribute):
        attrs: list[str] = []
        cur: ast.AST = func
        while isinstance(cur, ast.Attribute):
            attrs.append(cur.attr)
            cur = cur.value
        attrs.reverse()  # outermost attr last
        if isinstance(cur, ast.Name):
            if cur.id == "self" and len(attrs) == 1:
                return CallInfo(kind="self_attr", parts=(attrs[0],), lineno=call.lineno)
            parts = (cur.id, *attrs)
            return CallInfo(kind="attr", parts=parts, lineno=call.lineno)
    # Chained calls like f()() or subscript calls — not characterisable
    return None


# ---------------------------------------------------------------------------
# Regex patterns — routes (item 8: decorator AST is 0.4.0 work, carry over 0.2.0)
# ---------------------------------------------------------------------------

_ROUTE_DECORATOR = re.compile(
    r'@\w+\.(get|post|put|delete|patch|route)\(\s*[\'"]([^\'"]+)[\'"]',
    re.MULTILINE,
)
_DJANGO_PATH = re.compile(
    r'(?:path|re_path)\(\s*[\'"]([^\'"]+)[\'"]', re.MULTILINE
)

# For bloat_report — regex preserved from 0.2.0 for file-level analysis
_CLASS_PATTERN = re.compile(r"^class\s+(\w+)\s*[\(:]", re.MULTILINE)


# ---------------------------------------------------------------------------
# PythonAnalyzer
# ---------------------------------------------------------------------------


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

        # Per-scan state (rebuilt on every scan)
        self._qname_to_id: dict[str, str] = {}

        packages = self._find_packages()

        # parsed: list[(py_file, tree, mod_id, mod_qname, pkg_qname)]
        parsed: list[tuple[Path, ast.Module, str, str, str]] = []

        # --- Pass 1: structural nodes + symbol table -----------------------
        for pkg_root in packages:
            pkg_name = pkg_root.name
            pkg_id = f"py_pkg_{pkg_name}"
            pkg_qname = pkg_name

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

                tree = parse_module(py_file)
                if tree is None:
                    continue

                file_rel = rel_path(self.repo_root, py_file)
                mod_id = self._file_to_id(py_file)
                mod_qname = self._file_to_qname(py_file, pkg_root, pkg_qname)

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
                self._qname_to_id[mod_qname] = mod_id

                # Module-level functions
                for fn in find_module_functions(tree):
                    func_id = f"py_func_{mod_id}_{fn.name}"
                    if func_id in seen_ids:
                        continue
                    seen_ids.add(func_id)
                    nodes.append(Node(
                        id=func_id,
                        type="py_function",
                        name=fn.name,
                        file_path=file_rel,
                    ))
                    edges.append(Edge(from_id=mod_id, to_id=func_id, type="defines"))
                    self._qname_to_id[f"{mod_qname}.{fn.name}"] = func_id

                # Classes + methods
                for cls in find_classes(tree):
                    class_id = f"py_class_{mod_id}_{cls.name}"
                    if class_id not in seen_ids:
                        seen_ids.add(class_id)
                        nodes.append(Node(
                            id=class_id,
                            type="py_class",
                            name=cls.name,
                            file_path=file_rel,
                        ))
                        edges.append(Edge(from_id=mod_id, to_id=class_id, type="defines"))
                    self._qname_to_id[f"{mod_qname}.{cls.name}"] = class_id

                    for m in cls.methods:
                        method_id = f"py_method_{class_id}_{m.name}"
                        if method_id in seen_ids:
                            continue
                        seen_ids.add(method_id)
                        nodes.append(Node(
                            id=method_id,
                            type="py_method",
                            name=m.name,
                            file_path=file_rel,
                        ))
                        edges.append(Edge(from_id=class_id, to_id=method_id, type="defines"))
                        self._qname_to_id[f"{mod_qname}.{cls.name}.{m.name}"] = method_id

                # Routes (regex — unchanged from 0.2.0)
                content = read_safe(py_file)
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

                parsed.append((py_file, tree, mod_id, mod_qname, pkg_qname))

        # --- Pass 2: imports + calls ---------------------------------------
        for py_file, tree, mod_id, mod_qname, pkg_qname in parsed:
            locals_map = self._build_locals(tree, mod_qname)

            # Import edges (module → module)
            for imp in find_imports(tree):
                for target_id in self._resolve_import_targets(imp, mod_qname):
                    if target_id != mod_id:
                        edges.append(Edge(from_id=mod_id, to_id=target_id, type="imports"))

            # Calls from module-level functions
            for fn in find_module_functions(tree):
                source_id = f"py_func_{mod_id}_{fn.name}"
                if source_id not in seen_ids:
                    continue
                for call in find_calls(fn.node):
                    tid = self._resolve_call(call, locals_map, current_class_qname=None)
                    if tid and tid != source_id:
                        edges.append(Edge(from_id=source_id, to_id=tid, type="calls"))

            # Calls from class methods
            for cls in find_classes(tree):
                class_id = f"py_class_{mod_id}_{cls.name}"
                current_class_qname = f"{mod_qname}.{cls.name}"
                for m in cls.methods:
                    source_id = f"py_method_{class_id}_{m.name}"
                    if source_id not in seen_ids:
                        continue
                    for call in find_calls(m.node):
                        tid = self._resolve_call(
                            call, locals_map,
                            current_class_qname=current_class_qname,
                        )
                        if tid and tid != source_id:
                            edges.append(Edge(from_id=source_id, to_id=tid, type="calls"))

        return AnalysisResult(
            nodes=nodes,
            edges=edges,
            state_sections=self._state_section(packages),
        )

    # -- Package discovery --------------------------------------------------

    def _find_packages(self) -> list[Path]:
        """Find Python packages (directories with __init__.py)."""
        _skip = {"venv", "env", ".venv", "node_modules", "dist", "build", "__pycache__"}
        packages: list[Path] = []
        seen: set[Path] = set()
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
        for extra in self.index.extra_roots("python"):
            if extra not in seen:
                seen.add(extra)
                packages.append(extra)
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
        if stem.endswith("/__init__"):
            stem = stem[: -len("/__init__")]
        return "py_mod_" + stem.replace("/", "_").replace("-", "_").replace(".", "_")

    def _file_to_qname(self, py_file: Path, pkg_root: Path, pkg_qname: str) -> str:
        """Build dotted qname for a file relative to its package root.

        myapp/__init__.py → myapp
        myapp/users.py    → myapp.users
        myapp/auth/login.py → myapp.auth.login
        """
        try:
            rel = py_file.relative_to(pkg_root)
        except ValueError:
            return py_file.stem
        parts = list(rel.parts)
        if parts and parts[-1] == "__init__.py":
            parts = parts[:-1]
        elif parts:
            parts[-1] = re.sub(r"\.py$", "", parts[-1])
        if not parts:
            return pkg_qname
        return pkg_qname + "." + ".".join(parts)

    # -- Symbol resolution --------------------------------------------------

    def _build_locals(self, tree: ast.Module, mod_qname: str) -> dict[str, str]:
        """local_name → qname for module-scope names (imports + top-level defs)."""
        locals_map: dict[str, str] = {}

        for imp in find_imports(tree):
            if imp.kind == "import":
                for imported, alias in imp.names:
                    locals_map[alias] = imported
                continue
            # `from` import
            if imp.level == 0:
                base = imp.module or ""
            else:
                base = self._resolve_relative_base(mod_qname, imp.level, imp.module)
            for imported, alias in imp.names:
                if imported == "*":
                    continue
                locals_map[alias] = f"{base}.{imported}" if base else imported

        # Module's own top-level defs (override imports if names collide)
        for fn in find_module_functions(tree):
            locals_map[fn.name] = f"{mod_qname}.{fn.name}"
        for cls in find_classes(tree):
            locals_map[cls.name] = f"{mod_qname}.{cls.name}"

        return locals_map

    def _resolve_relative_base(
        self,
        mod_qname: str,
        level: int,
        module: str | None,
    ) -> str:
        """Resolve a relative import's base qname.

        mod_qname = "myapp.sub.current"
          level=1, module="x" → "myapp.sub.x"
          level=2, module="x" → "myapp.x"
          level=1, module=None → "myapp.sub"
        """
        parts = mod_qname.split(".")
        parts = parts[:-1]  # drop current module
        for _ in range(level - 1):
            if parts:
                parts.pop()
        if module:
            parts.extend(module.split("."))
        return ".".join(parts)

    def _resolve_import_targets(self, imp: ImportInfo, mod_qname: str) -> list[str]:
        """Return module node ids this import emits edges to.

        0.3.0: module → module only. If an imported name is a submodule,
        emit edge to the submodule; if it's a symbol, emit edge to the
        containing module.
        """
        targets: list[str] = []

        if imp.kind == "import":
            for imported, _alias in imp.names:
                tid = self._qname_to_id.get(imported)
                if tid and tid.startswith("py_mod_"):
                    targets.append(tid)
                elif "." in imported:
                    # import x.y.z → try x.y, then x
                    parts = imported.split(".")
                    for depth in range(len(parts) - 1, 0, -1):
                        q = ".".join(parts[:depth])
                        tid = self._qname_to_id.get(q)
                        if tid and tid.startswith("py_mod_"):
                            targets.append(tid)
                            break
        else:
            # from X import Y1, Y2, ...
            if imp.level == 0:
                base = imp.module or ""
            else:
                base = self._resolve_relative_base(mod_qname, imp.level, imp.module)

            base_tid = self._qname_to_id.get(base) if base else None
            base_is_module = bool(base_tid and base_tid.startswith("py_mod_"))

            for imported, _alias in imp.names:
                if imported == "*":
                    if base_is_module:
                        targets.append(base_tid)  # type: ignore[arg-type]
                    continue
                full = f"{base}.{imported}" if base else imported
                tid = self._qname_to_id.get(full)
                if tid and tid.startswith("py_mod_"):
                    targets.append(tid)  # submodule import
                elif base_is_module:
                    targets.append(base_tid)  # type: ignore[arg-type]

        # Dedupe preserving order
        seen: set[str] = set()
        out: list[str] = []
        for t in targets:
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out

    def _resolve_call(
        self,
        call: CallInfo,
        locals_map: dict[str, str],
        current_class_qname: str | None,
    ) -> str | None:
        """Resolve a call site to a target node id, or None if ambiguous.

        Rules (0.3.0):
          - `name`: look up bare name in locals_map, then qname → id
          - `attr` starting with an import alias or known symbol: concat parts
          - `self_attr` inside a class: resolve to same-class method
          - Everything else drops silently
        """
        if call.kind == "name":
            qname = locals_map.get(call.parts[0])
            if qname is None:
                return None
            return self._qname_to_id.get(qname)

        if call.kind == "attr":
            head = call.parts[0]
            head_qname = locals_map.get(head)
            if head_qname is None:
                return None
            full = head_qname + "." + ".".join(call.parts[1:])
            return self._qname_to_id.get(full)

        if call.kind == "self_attr":
            if current_class_qname is None:
                return None
            qname = f"{current_class_qname}.{call.parts[0]}"
            return self._qname_to_id.get(qname)

        return None

    # -- State section ------------------------------------------------------

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

    # -- File-level analysis (unchanged from 0.2.0 — regex-based) ----------

    def supported_extensions(self) -> set[str]:
        return {".py"}

    def analyze_file(self, file_path: Path) -> dict | None:
        if not file_path.is_file() or file_path.suffix != ".py":
            return None

        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        total = len(lines)

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

        for j, func in enumerate(functions):
            if j + 1 < len(functions):
                func["end"] = functions[j + 1]["start"] - 1
            else:
                func["end"] = total
            func["lines"] = func["end"] - func["start"] + 1

        functions.sort(key=lambda f: f["lines"], reverse=True)

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
