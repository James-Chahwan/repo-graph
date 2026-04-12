"""
Analyzer registry — discovery and dispatch.

Discovers which language analyzers apply to a given repo,
and provides file-level analyzer lookup for bloat_report / split_plan.
"""

from pathlib import Path

from .base import LanguageAnalyzer


def _analyzer_classes() -> list[type[LanguageAnalyzer]]:
    """All known analyzer classes, ordered by specificity (most specific first)."""
    from .angular import AngularAnalyzer
    from .react import ReactAnalyzer
    from .go import GoAnalyzer
    from .typescript import TypeScriptAnalyzer
    from .python_lang import PythonAnalyzer
    from .rust import RustAnalyzer
    from .java import JavaAnalyzer
    from .csharp import CSharpAnalyzer
    from .ruby import RubyAnalyzer
    from .php import PhpAnalyzer
    from .swift import SwiftAnalyzer
    from .c_cpp import CppAnalyzer
    from .scss import ScssAnalyzer

    return [
        AngularAnalyzer,       # before React/TS (most specific)
        ReactAnalyzer,         # before TS (more specific)
        GoAnalyzer,
        RustAnalyzer,
        JavaAnalyzer,
        CSharpAnalyzer,
        SwiftAnalyzer,
        RubyAnalyzer,
        PhpAnalyzer,
        CppAnalyzer,
        TypeScriptAnalyzer,
        PythonAnalyzer,
        ScssAnalyzer,          # last — supplements, no graph nodes
    ]


def discover_analyzers(repo_root: Path) -> list[LanguageAnalyzer]:
    """Return instantiated analyzers for all detected languages/frameworks."""
    matched = []
    for cls in _analyzer_classes():
        if cls.detect(repo_root):
            matched.append(cls(repo_root))
    return matched


def get_file_analyzer(repo_root: Path, file_path: Path) -> LanguageAnalyzer | None:
    """Find the best analyzer for a specific file (for bloat_report / split_plan)."""
    ext = file_path.suffix
    for cls in _analyzer_classes():
        if cls.detect(repo_root):
            instance = cls(repo_root)
            if ext in instance.supported_extensions():
                return instance
    return None
