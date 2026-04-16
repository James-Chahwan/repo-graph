"""
Test → code edge detection.

Runs as a post-pass after all language analyzers. For each test file matched
by two-factor check (filename pattern + framework import/signal), creates a
`test_file` node and — best effort — parses its imports to emit `tests` edges
back to existing graph nodes.

Two-factor confirmation: filename alone is ambiguous (a `test_utils.py` might
be a utility module), so every language also requires a framework-level
signal (import of testing lib, test-decorator, test-function shape, etc).

Coverage:
  Python      test_*.py, *_test.py
  JS/TS       *.test.*, *.spec.*
  Go          *_test.go
  Ruby        *_spec.rb, *_test.rb
  Java        *Test.java, *Tests.java, *IT.java
  Kotlin      *Test.kt, *Tests.kt
  Scala       *Spec.scala, *Test.scala, *Suite.scala
  Clojure     test_*.clj(c|s), *_test.clj(c|s), files under /test/
  C#          *.Tests.cs, *Tests.cs, *Test.cs
  PHP         *Test.php
  Swift       *Tests.swift, *Test.swift
  C/C++       *_test.cc, *_tests.cc, test_*.cc, *_unittest.cc (+ cpp, cxx, c)
  Dart        *_test.dart
  Elixir      *_test.exs
  Rust        files under tests/ directory
"""

from __future__ import annotations

import re
from pathlib import Path

from .discovery import FileIndex


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------
_PY_TEST_RE = re.compile(r"(?:^test_.*\.py$|_test\.py$)")
_PY_FROM_IMPORT_RE = re.compile(r"^from\s+(\S+)\s+import", re.MULTILINE)
_PY_FRAMEWORK_RE = re.compile(
    r"""(?:^|\n)\s*(?:
        import\s+(?:pytest|unittest|nose|nose2|hypothesis|doctest)\b
        |from\s+(?:pytest|unittest|nose|nose2|hypothesis|doctest)\b
        |def\s+test_\w+\s*\(
        |class\s+Test\w+\s*\(
        |@pytest\.
    )""",
    re.VERBOSE,
)

# ---------------------------------------------------------------------------
# JavaScript / TypeScript
# ---------------------------------------------------------------------------
_JS_TEST_RE = re.compile(r"\.(?:test|spec)\.[mc]?[jt]sx?$")
_JS_IMPORT_RE = re.compile(
    r"""(?:import[^'"`]+from\s+|require\s*\(\s*)['"`](\.{1,2}/[^'"`]+)['"`]""",
    re.MULTILINE,
)
_JS_FRAMEWORK_RE = re.compile(
    r"""(?:
        from\s+['"`](?:jest|vitest|mocha|@jest/globals|@testing-library/[\w-]+|node:test|chai|sinon)['"`]
        |require\s*\(\s*['"`](?:jest|vitest|mocha|@jest/globals|node:test|chai|sinon)['"`]
        |(?:^|\s|;)(?:describe|it|test|suite|bench)\s*(?:\.\w+)?\s*\(
        |(?:^|\s|;)(?:beforeAll|beforeEach|afterAll|afterEach)\s*\(
    )""",
    re.VERBOSE,
)

# ---------------------------------------------------------------------------
# Go
# ---------------------------------------------------------------------------
_GO_TEST_RE = re.compile(r"_test\.go$")
_GO_FRAMEWORK_RE = re.compile(
    r"""(?:\"testing\"|func\s+(?:Test|Benchmark|Example|Fuzz)\w*\s*\(|\*testing\.[TBFM]\b)""",
)

# ---------------------------------------------------------------------------
# Ruby
# ---------------------------------------------------------------------------
_RB_TEST_RE = re.compile(r"(?:_spec\.rb$|_test\.rb$)")
_RB_REQUIRE_RE = re.compile(
    r"""^\s*require(?:_relative)?\s+['"]([^'"]+)['"]""", re.MULTILINE
)
_RB_FRAMEWORK_RE = re.compile(
    r"""(?:
        require\s+['"](?:rspec|minitest|test_helper|test/unit|spec_helper|rails_helper)
        |RSpec\.describe\b
        |class\s+\w+\s*<\s*(?:Minitest::Test|Test::Unit::TestCase|ActiveSupport::TestCase)
        |(?:^|\s)(?:describe|context|it|specify)\s*(?:['"]|\s*do\b)
    )""",
    re.VERBOSE,
)

# ---------------------------------------------------------------------------
# Java / Kotlin
# ---------------------------------------------------------------------------
_JAVA_TEST_RE = re.compile(r"(?:Test|Tests|IT)\.java$")
_KOTLIN_TEST_RE = re.compile(r"(?:Test|Tests)\.kt$")
_JAVA_IMPORT_RE = re.compile(r"^\s*import\s+([\w.]+);", re.MULTILINE)
_KOTLIN_IMPORT_RE = re.compile(r"^\s*import\s+([\w.]+)", re.MULTILINE)
_JAVA_FRAMEWORK_RE = re.compile(
    r"""(?:
        import\s+org\.junit
        |import\s+org\.testng
        |import\s+io\.cucumber
        |@Test\b
        |@ParameterizedTest\b
        |@RepeatedTest\b
        |extends\s+TestCase\b
    )""",
    re.VERBOSE,
)
_KOTLIN_FRAMEWORK_RE = re.compile(
    r"""(?:
        import\s+org\.junit
        |import\s+kotlin\.test
        |import\s+io\.kotest
        |import\s+io\.mockk
        |@Test\b
        |class\s+\w+\s*:\s*(?:\w*Spec|\w*StringSpec|\w*FunSpec|\w*BehaviorSpec|\w*WordSpec)\b
    )""",
    re.VERBOSE,
)

# ---------------------------------------------------------------------------
# Scala
# ---------------------------------------------------------------------------
_SCALA_TEST_RE = re.compile(r"(?:Spec|Test|Suite)\.scala$")
_SCALA_IMPORT_RE = re.compile(r"^\s*import\s+([\w.]+)", re.MULTILINE)
_SCALA_FRAMEWORK_RE = re.compile(
    r"""(?:
        import\s+org\.scalatest
        |import\s+munit
        |import\s+org\.specs2
        |extends\s+(?:AnyFunSuite|AnyFlatSpec|AnyWordSpec|AnyFreeSpec|FunSuite|FlatSpec)
        |extends\s+munit\.FunSuite
        |class\s+\w+\s+extends\s+\w*Spec\b
    )""",
    re.VERBOSE,
)

# ---------------------------------------------------------------------------
# Clojure
# ---------------------------------------------------------------------------
_CLJ_TEST_RE = re.compile(r"(?:^test_.*\.cljc?s?$|_test\.cljc?s?$)")
_CLJ_REQUIRE_RE = re.compile(r"\[([\w.-]+)(?:\s+:as\b)?", re.MULTILINE)
_CLJ_FRAMEWORK_RE = re.compile(
    r"""(?:
        clojure\.test
        |\(deftest\b
        |midje\.sweet
        |expectations
    )""",
    re.VERBOSE,
)

# ---------------------------------------------------------------------------
# C# / .NET
# ---------------------------------------------------------------------------
_CS_TEST_RE = re.compile(r"(?:\.Tests\.cs$|Tests\.cs$|Test\.cs$)")
_CS_USING_RE = re.compile(r"^\s*using\s+([\w.]+)\s*;", re.MULTILINE)
_CS_FRAMEWORK_RE = re.compile(
    r"""(?:
        using\s+Xunit\b
        |using\s+NUnit\.Framework\b
        |using\s+Microsoft\.VisualStudio\.TestTools
        |\[Fact\]
        |\[Theory\]
        |\[Test\]
        |\[TestMethod\]
        |\[TestFixture\]
    )""",
    re.VERBOSE,
)

# ---------------------------------------------------------------------------
# PHP
# ---------------------------------------------------------------------------
_PHP_TEST_RE = re.compile(r"Test\.php$")
_PHP_USE_RE = re.compile(r"^\s*use\s+([\w\\]+)\s*;", re.MULTILINE)
_PHP_FRAMEWORK_RE = re.compile(
    r"""(?:
        use\s+PHPUnit\\Framework
        |PHPUnit\\Framework\\TestCase
        |extends\s+TestCase\b
        |use\s+Pest\\
        |use\s+Codeception\\
    )""",
    re.VERBOSE,
)

# ---------------------------------------------------------------------------
# Swift
# ---------------------------------------------------------------------------
_SWIFT_TEST_RE = re.compile(r"(?:Tests?\.swift$)")
_SWIFT_IMPORT_RE = re.compile(r"^\s*(?:@testable\s+)?import\s+(\w+)", re.MULTILINE)
_SWIFT_FRAMEWORK_RE = re.compile(
    r"""(?:
        import\s+XCTest\b
        |import\s+Testing\b
        |import\s+Quick\b
        |import\s+Nimble\b
        |:\s*XCTestCase\b
        |@Test\b
    )""",
    re.VERBOSE,
)

# ---------------------------------------------------------------------------
# C / C++
# ---------------------------------------------------------------------------
_CPP_TEST_RE = re.compile(
    r"(?:_test|_tests|_unittest)\.(?:c|cc|cpp|cxx)$|^test_.*\.(?:c|cc|cpp|cxx)$"
)
_CPP_INCLUDE_RE = re.compile(r'^\s*#include\s+"([^"]+)"', re.MULTILINE)
_CPP_FRAMEWORK_RE = re.compile(
    r"""(?:
        \#include\s*<gtest/gtest\.h>
        |\#include\s*<gmock/gmock\.h>
        |\#include\s*<catch2/
        |\#include\s*<doctest/
        |\#include\s*<boost/test/
        |(?:^|\s)TEST(?:_F|_P)?\s*\(
        |(?:^|\s)CATCH_TEST_CASE\s*\(
        |BOOST_AUTO_TEST_CASE\s*\(
    )""",
    re.VERBOSE,
)

# ---------------------------------------------------------------------------
# Dart / Flutter
# ---------------------------------------------------------------------------
_DART_TEST_RE = re.compile(r"_test\.dart$")
_DART_IMPORT_RE = re.compile(r"""^\s*import\s+['"]([^'"]+)['"]""", re.MULTILINE)
_DART_FRAMEWORK_RE = re.compile(
    r"""(?:
        package:test/test\.dart
        |package:flutter_test/flutter_test\.dart
        |(?:^|\s)test\s*\(
        |(?:^|\s)group\s*\(
        |(?:^|\s)testWidgets\s*\(
    )""",
    re.VERBOSE,
)

# ---------------------------------------------------------------------------
# Elixir
# ---------------------------------------------------------------------------
_EX_TEST_RE = re.compile(r"_test\.exs$")
_EX_ALIAS_RE = re.compile(r"^\s*(?:alias|import)\s+([\w.]+)", re.MULTILINE)
_EX_FRAMEWORK_RE = re.compile(
    r"""(?:
        use\s+ExUnit\.Case
        |defmodule\s+\w+Test\s+do
        |(?:^|\s)test\s+"[^"]+"\s+do
        |(?:^|\s)describe\s+"[^"]+"\s+do
    )""",
    re.VERBOSE,
)

# ---------------------------------------------------------------------------
# Rust (integration tests in tests/ directory)
# ---------------------------------------------------------------------------
_RS_INTEG_FRAMEWORK_RE = re.compile(
    r"""(?:
        \#\[test\]
        |\#\[tokio::test\]
        |\#\[async_std::test\]
        |\#\[cfg\(test\)\]
    )""",
    re.VERBOSE,
)
_RS_USE_RE = re.compile(r"^\s*use\s+([\w:]+)", re.MULTILINE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _test_node_id(rel: str) -> str:
    return "test_" + rel.replace("/", "_").replace("\\", "_").replace(".", "_").replace("-", "_")


_FILE_LEVEL_TYPE_SUFFIXES = ("_module", "_file", "_namespace", "_package")


def _file_level_priority(node_type: str) -> int:
    """Prefer container nodes (module/file/package) over member nodes (class/function)."""
    if any(node_type.endswith(s) for s in _FILE_LEVEL_TYPE_SUFFIXES):
        return 0
    if node_type in {
        "react_module", "vue_module", "py_module", "ts_module", "go_package",
        "java_class", "cs_class", "scala_class", "swift_type",
    }:
        return 0
    return 1


def add_test_edges(
    nodes: list[dict],
    edges: list[dict],
    index: FileIndex,
) -> None:
    """Mutate nodes/edges in place: add test_file nodes + `tests` edges."""
    node_by_path: dict[str, dict] = {}
    for n in nodes:
        fp = n.get("file_path")
        if not fp:
            continue
        incumbent = node_by_path.get(fp)
        if incumbent is None or _file_level_priority(n["type"]) < _file_level_priority(incumbent["type"]):
            node_by_path[fp] = n
    existing_ids = {n["id"] for n in nodes}

    # Pre-build name indexes for qualified-name resolution (Java, C#, Scala...)
    # Map simple name → list of nodes with that name
    name_to_nodes: dict[str, list[dict]] = {}
    for n in nodes:
        nm = n.get("name", "")
        if nm and n.get("file_path"):
            name_to_nodes.setdefault(nm, []).append(n)

    def _resolve_relative(
        from_file: Path, import_path: str, exts: list[str]
    ) -> str | None:
        clean = import_path.split("?")[0].split("#")[0]
        base = (from_file.parent / clean).resolve()
        candidates: list[Path] = [base]
        for ext in exts:
            candidates.append(Path(str(base) + ext))
            candidates.append(base / ("index" + ext))
        for cand in candidates:
            try:
                rel = str(cand.relative_to(index.repo_root))
            except ValueError:
                continue
            if rel in node_by_path:
                return rel
        return None

    def _resolve_qualified(qualified: str) -> list[str]:
        """Resolve `com.foo.Bar` or `Foo.Bar` to node ids by simple-name + path match."""
        parts = qualified.replace("\\", ".").split(".")
        if not parts:
            return []
        simple = parts[-1]
        candidates = name_to_nodes.get(simple, [])
        if not candidates:
            return []
        if len(parts) == 1:
            return [c["id"] for c in candidates if c.get("type") != "test_file"]
        # Prefer candidates whose file_path contains the package path
        pkg_path = "/".join(parts[:-1]).lower()
        matches = [
            c for c in candidates
            if pkg_path in c.get("file_path", "").lower().replace("\\", "/")
            and c.get("type") != "test_file"
        ]
        return [c["id"] for c in (matches or candidates) if c.get("type") != "test_file"]

    def _resolve_siblings(test_file: Path, exts: tuple[str, ...]) -> list[str]:
        """Fallback: match test_file to sibling production files in same directory."""
        out = []
        for ext in exts:
            for sib in test_file.parent.glob(f"*{ext}"):
                if sib == test_file:
                    continue
                try:
                    rel = str(sib.relative_to(index.repo_root))
                except ValueError:
                    continue
                node = node_by_path.get(rel)
                if node and node.get("type") != "test_file":
                    out.append(node["id"])
        return out

    def _emit(test_file: Path, targets: list[str]) -> None:
        """Emit test_file node (always) + tests edges (when targets exist)."""
        try:
            rel = str(test_file.relative_to(index.repo_root))
        except ValueError:
            return
        tid = _test_node_id(rel)
        if tid not in existing_ids:
            existing_ids.add(tid)
            nodes.append({
                "id": tid,
                "type": "test_file",
                "name": test_file.stem,
                "file_path": rel,
                "confidence": "weak",
            })
        seen_edge = set()
        for target_id in targets:
            key = (tid, target_id)
            if key in seen_edge or target_id == tid:
                continue
            seen_edge.add(key)
            edges.append({"from": tid, "to": target_id, "type": "tests"})

    # --- Python ---
    for py in index.files_with_ext(".py"):
        if not _PY_TEST_RE.search(py.name):
            continue
        content = _read(py)
        if not _PY_FRAMEWORK_RE.search(content):
            continue
        targets: list[str] = []
        for m in _PY_FROM_IMPORT_RE.finditer(content):
            mod = m.group(1)
            if not mod.startswith("."):
                continue
            resolved = _resolve_relative(py, mod.lstrip(".").replace(".", "/"), [".py"])
            if resolved and (node := node_by_path.get(resolved)):
                targets.append(node["id"])
        _emit(py, targets)

    # --- JS/TS ---
    for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
        for f in index.files_with_ext(ext):
            if not _JS_TEST_RE.search(f.name):
                continue
            content = _read(f)
            if not _JS_FRAMEWORK_RE.search(content):
                continue
            targets = []
            for m in _JS_IMPORT_RE.finditer(content):
                imp = m.group(1)
                resolved = _resolve_relative(
                    f, imp, [".ts", ".tsx", ".js", ".jsx", ".mjs", ".vue"],
                )
                if resolved and (node := node_by_path.get(resolved)):
                    targets.append(node["id"])
            _emit(f, targets)

    # --- Go ---
    for go in index.files_with_ext(".go"):
        if not _GO_TEST_RE.search(go.name):
            continue
        content = _read(go)
        if not _GO_FRAMEWORK_RE.search(content):
            continue
        targets = _resolve_siblings(go, (".go",))
        _emit(go, targets)

    # --- Ruby ---
    for rb in index.files_with_ext(".rb"):
        if not _RB_TEST_RE.search(rb.name):
            continue
        content = _read(rb)
        if not _RB_FRAMEWORK_RE.search(content):
            continue
        targets = []
        for m in _RB_REQUIRE_RE.finditer(content):
            req = m.group(1)
            if not req.startswith("."):
                req = "./" + req
            resolved = _resolve_relative(rb, req, [".rb"])
            if resolved and (node := node_by_path.get(resolved)):
                targets.append(node["id"])
        _emit(rb, targets)

    # --- Java ---
    for jf in index.files_with_ext(".java"):
        if not _JAVA_TEST_RE.search(jf.name):
            continue
        content = _read(jf)
        if not _JAVA_FRAMEWORK_RE.search(content):
            continue
        targets = []
        for m in _JAVA_IMPORT_RE.finditer(content):
            targets.extend(_resolve_qualified(m.group(1)))
        if not targets:
            targets = _resolve_siblings(jf, (".java",))
        _emit(jf, targets)

    # --- Kotlin ---
    for kt in index.files_with_ext(".kt"):
        if not _KOTLIN_TEST_RE.search(kt.name):
            continue
        content = _read(kt)
        if not _KOTLIN_FRAMEWORK_RE.search(content):
            continue
        targets = []
        for m in _KOTLIN_IMPORT_RE.finditer(content):
            targets.extend(_resolve_qualified(m.group(1)))
        if not targets:
            targets = _resolve_siblings(kt, (".kt",))
        _emit(kt, targets)

    # --- Scala ---
    for sc in index.files_with_ext(".scala"):
        if not _SCALA_TEST_RE.search(sc.name):
            continue
        content = _read(sc)
        if not _SCALA_FRAMEWORK_RE.search(content):
            continue
        targets = []
        for m in _SCALA_IMPORT_RE.finditer(content):
            targets.extend(_resolve_qualified(m.group(1)))
        if not targets:
            targets = _resolve_siblings(sc, (".scala",))
        _emit(sc, targets)

    # --- Clojure ---
    for cl_ext in (".clj", ".cljc", ".cljs"):
        for cl in index.files_with_ext(cl_ext):
            rel = str(cl.relative_to(index.repo_root)) if cl.is_absolute() else str(cl)
            fname_match = bool(_CLJ_TEST_RE.search(cl.name))
            in_test_dir = "/test/" in rel.replace("\\", "/") or rel.startswith("test/")
            if not (fname_match or in_test_dir):
                continue
            content = _read(cl)
            if not _CLJ_FRAMEWORK_RE.search(content):
                continue
            targets = []
            for m in _CLJ_REQUIRE_RE.finditer(content):
                targets.extend(_resolve_qualified(m.group(1).replace("-", "_")))
            _emit(cl, targets)

    # --- C# ---
    for cs in index.files_with_ext(".cs"):
        if not _CS_TEST_RE.search(cs.name):
            continue
        content = _read(cs)
        if not _CS_FRAMEWORK_RE.search(content):
            continue
        targets = []
        for m in _CS_USING_RE.finditer(content):
            targets.extend(_resolve_qualified(m.group(1)))
        if not targets:
            targets = _resolve_siblings(cs, (".cs",))
        _emit(cs, targets)

    # --- PHP ---
    for php in index.files_with_ext(".php"):
        if not _PHP_TEST_RE.search(php.name):
            continue
        content = _read(php)
        if not _PHP_FRAMEWORK_RE.search(content):
            continue
        targets = []
        for m in _PHP_USE_RE.finditer(content):
            targets.extend(_resolve_qualified(m.group(1)))
        if not targets:
            targets = _resolve_siblings(php, (".php",))
        _emit(php, targets)

    # --- Swift ---
    for sw in index.files_with_ext(".swift"):
        if not _SWIFT_TEST_RE.search(sw.name):
            continue
        content = _read(sw)
        if not _SWIFT_FRAMEWORK_RE.search(content):
            continue
        targets = []
        for m in _SWIFT_IMPORT_RE.finditer(content):
            # Swift imports are module names — match by name
            targets.extend(_resolve_qualified(m.group(1)))
        if not targets:
            targets = _resolve_siblings(sw, (".swift",))
        _emit(sw, targets)

    # --- C/C++ ---
    for cpp_ext in (".c", ".cc", ".cpp", ".cxx"):
        for cpp in index.files_with_ext(cpp_ext):
            if not _CPP_TEST_RE.search(cpp.name):
                continue
            content = _read(cpp)
            if not _CPP_FRAMEWORK_RE.search(content):
                continue
            targets = []
            for m in _CPP_INCLUDE_RE.finditer(content):
                inc = m.group(1)
                resolved = _resolve_relative(cpp, inc, [""])
                if resolved and (node := node_by_path.get(resolved)):
                    targets.append(node["id"])
            if not targets:
                targets = _resolve_siblings(cpp, (".c", ".cc", ".cpp", ".cxx", ".h", ".hpp"))
            _emit(cpp, targets)

    # --- Dart ---
    for dart in index.files_with_ext(".dart"):
        if not _DART_TEST_RE.search(dart.name):
            continue
        content = _read(dart)
        if not _DART_FRAMEWORK_RE.search(content):
            continue
        targets = []
        for m in _DART_IMPORT_RE.finditer(content):
            imp = m.group(1)
            if imp.startswith("package:"):
                # package:myapp/foo.dart — try simple name match on "foo"
                pkg_part = imp.replace("package:", "").split("/", 1)
                if len(pkg_part) == 2:
                    simple = Path(pkg_part[1]).stem
                    for c in name_to_nodes.get(simple, []):
                        if c.get("type") != "test_file":
                            targets.append(c["id"])
            elif imp.startswith("."):
                resolved = _resolve_relative(dart, imp, [".dart"])
                if resolved and (node := node_by_path.get(resolved)):
                    targets.append(node["id"])
        if not targets:
            targets = _resolve_siblings(dart, (".dart",))
        _emit(dart, targets)

    # --- Elixir ---
    for ex in index.files_with_ext(".exs"):
        if not _EX_TEST_RE.search(ex.name):
            continue
        content = _read(ex)
        if not _EX_FRAMEWORK_RE.search(content):
            continue
        targets = []
        for m in _EX_ALIAS_RE.finditer(content):
            targets.extend(_resolve_qualified(m.group(1)))
        if not targets:
            targets = _resolve_siblings(ex, (".ex", ".exs"))
        _emit(ex, targets)

    # --- Rust (integration tests under tests/ directory) ---
    for rs in index.files_with_ext(".rs"):
        rel = str(rs.relative_to(index.repo_root)) if rs.is_absolute() else str(rs)
        norm = rel.replace("\\", "/")
        in_tests_dir = (
            norm.startswith("tests/")
            or "/tests/" in norm
            or norm.endswith("_test.rs")
            or "_test_" in norm
        )
        if not in_tests_dir:
            continue
        content = _read(rs)
        if not _RS_INTEG_FRAMEWORK_RE.search(content):
            continue
        targets = []
        for m in _RS_USE_RE.finditer(content):
            path = m.group(1).replace("::", ".")
            targets.extend(_resolve_qualified(path))
        if not targets:
            targets = _resolve_siblings(rs, (".rs",))
        _emit(rs, targets)
