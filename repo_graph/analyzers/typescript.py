"""
TypeScript analyzer.

Detects TS projects via tsconfig.json, scans for modules,
classes, functions, and import relationships.
"""

import json
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

# Class/interface definitions
_CLASS_PATTERN = re.compile(
    r"^(?:export\s+)?(?:abstract\s+)?(?:class|interface)\s+(\w+)", re.MULTILINE
)

# Function/const exports
_EXPORT_FUNC_PATTERN = re.compile(
    r"^export\s+(?:async\s+)?(?:function|const)\s+(\w+)", re.MULTILINE
)

# Import statements
_IMPORT_PATTERN = re.compile(
    r"""from\s+['"](\.[^'"]+)['"]""", re.MULTILINE
)


def _has_framework(d: Path) -> bool:
    """Check if a directory is an Angular or React project (handled by dedicated analyzers)."""
    pkg_json = d / "package.json"
    if not pkg_json.exists():
        return False
    try:
        pkg = json.loads(read_safe(pkg_json))
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        return "@angular/core" in deps or "react" in deps
    except (json.JSONDecodeError, TypeError):
        return False


def _find_ts_roots(index) -> list[Path]:
    """Directories with tsconfig.json that are NOT Angular/React projects, plus
    any config-declared `kind: typescript` roots."""
    auto = [d for d in index.dirs_with_file("tsconfig.json") if not _has_framework(d)]
    return sorted(set(auto) | set(index.extra_roots("typescript")))


class TypeScriptAnalyzer(LanguageAnalyzer):

    @staticmethod
    def detect(index) -> bool:
        return bool(_find_ts_roots(index))

    def scan(self) -> AnalysisResult:
        nodes: list[Node] = []
        edges: list[Edge] = []
        seen_ids: set[str] = set()

        all_state: dict[str, str] = {}
        for ts_root in _find_ts_roots(self.index):
            src_root = self._find_src_root(ts_root)

            for ts_file in self.index.files_with_ext({".ts", ".tsx"}, under=src_root):
                if ts_file.suffix == ".tsx":
                    continue
                if self._should_skip(ts_file):
                    continue

                file_rel = rel_path(self.repo_root, ts_file)
                module_id = self._file_to_id(ts_file)

                if module_id in seen_ids:
                    continue
                seen_ids.add(module_id)

                nodes.append(Node(
                    id=module_id,
                    type="ts_module",
                    name=ts_file.stem,
                    file_path=file_rel,
                ))

                content = read_safe(ts_file)

                # Extract classes
                for m in _CLASS_PATTERN.finditer(content):
                    class_name = m.group(1)
                    class_id = f"ts_class_{module_id}_{class_name}"
                    if class_id not in seen_ids:
                        seen_ids.add(class_id)
                        nodes.append(Node(
                            id=class_id,
                            type="ts_class",
                            name=class_name,
                            file_path=file_rel,
                        ))
                        edges.append(Edge(from_id=module_id, to_id=class_id, type="defines"))

                # Extract exported functions
                for m in _EXPORT_FUNC_PATTERN.finditer(content):
                    func_name = m.group(1)
                    func_id = f"ts_func_{module_id}_{func_name}"
                    if func_id not in seen_ids:
                        seen_ids.add(func_id)
                        nodes.append(Node(
                            id=func_id,
                            type="ts_function",
                            name=func_name,
                            file_path=file_rel,
                        ))
                        edges.append(Edge(from_id=module_id, to_id=func_id, type="exports"))

                # Extract relative imports → edges
                for m in _IMPORT_PATTERN.finditer(content):
                    imp_path = m.group(1)
                    resolved = self._resolve_import(ts_file, imp_path)
                    if resolved:
                        target_id = self._file_to_id(resolved)
                        if target_id in seen_ids:
                            edges.append(Edge(from_id=module_id, to_id=target_id, type="imports"))

            all_state.update(self._state_section(src_root))

        return AnalysisResult(
            nodes=nodes,
            edges=edges,
            state_sections=all_state,
        )

    def _find_src_root(self, project_root: Path) -> Path:
        """Find the main source directory."""
        candidates = [
            project_root / "src",
            project_root / "lib",
            project_root,
        ]
        for c in candidates:
            if c.exists() and self.index.files_with_ext(".ts", under=c):
                return c
        return project_root

    def _should_skip(self, ts_file: Path) -> bool:
        name = ts_file.name
        parts = str(ts_file)
        return (
            ".spec." in name
            or ".test." in name
            or ".d.ts" in name
            or "node_modules" in parts
            or "/dist/" in parts
            or "/build/" in parts
        )

    def _file_to_id(self, ts_file: Path) -> str:
        rel = rel_path(self.repo_root, ts_file)
        # Strip extension and clean
        stem = re.sub(r"\.tsx?$", "", rel)
        return "ts_mod_" + stem.replace("/", "_").replace("-", "_").replace(".", "_")

    def _resolve_import(self, from_file: Path, imp_path: str) -> Path | None:
        """Resolve a relative import to a file path."""
        base = from_file.parent / imp_path
        for ext in [".ts", ".tsx", "/index.ts", "/index.tsx"]:
            candidate = base.parent / (base.name + ext)
            if candidate.exists():
                return candidate
        if base.is_dir() and (base / "index.ts").exists():
            return base / "index.ts"
        return None

    def _state_section(self, src_root: Path) -> dict[str, str]:
        ts_files = self.index.files_with_ext(".ts", under=src_root)
        ts_files = [f for f in ts_files if not self._should_skip(f)]
        if not ts_files:
            return {}
        return {
            "TypeScript": f"{len(ts_files)} source files in `{rel_path(self.repo_root, src_root)}`\n"
        }

    # -- File-level analysis -----------------------------------------------

    def supported_extensions(self) -> set[str]:
        return {".ts", ".tsx"}

    def analyze_file(self, file_path: Path) -> dict | None:
        if not file_path.is_file() or file_path.suffix not in (".ts", ".tsx"):
            return None

        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        total = len(lines)

        # Find methods
        method_pattern = re.compile(
            r"^\s+(?:async\s+)?(\w+)\s*\([^)]*\)\s*[:{]", re.MULTILINE
        )
        skip = {
            "if", "for", "while", "switch", "catch", "else", "return",
            "throw", "try", "finally", "case", "default", "constructor",
        }

        methods = []
        for m in method_pattern.finditer(content):
            name = m.group(1)
            if name not in skip and not name.startswith("_"):
                start_line = content[: m.start()].count("\n") + 1
                methods.append({"name": name, "line": start_line})

        for i, method in enumerate(methods):
            if i + 1 < len(methods):
                method["approx_lines"] = methods[i + 1]["line"] - method["line"]
            else:
                method["approx_lines"] = total - method["line"]

        methods.sort(key=lambda m: m["approx_lines"], reverse=True)

        # Find classes
        classes = [m.group(1) for m in _CLASS_PATTERN.finditer(content)]

        return {
            "type": "ts",
            "file": file_path.name,
            "total_lines": total,
            "class_count": len(classes),
            "classes": classes,
            "method_count": len(methods),
            "methods": methods,
        }

    def format_bloat_report(self, analysis: dict) -> str | None:
        if analysis.get("type") != "ts":
            return None
        lines = [
            f"Bloat report: {analysis['file']} ({analysis['total_lines']} lines, "
            f"{analysis['class_count']} classes, {analysis['method_count']} methods)\n",
            "Methods (largest first):",
        ]
        for m in analysis["methods"][:15]:
            bar = "█" * (m["approx_lines"] // 3)
            lines.append(
                f"  ~{m['approx_lines']:>3} lines  {bar:30s}  {m['name']} (L{m['line']})"
            )
        return "\n".join(lines)
