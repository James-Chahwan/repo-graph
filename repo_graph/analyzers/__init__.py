"""
Analyzer registry — discovery and dispatch.

Discovers which language analyzers apply to a given repo,
and provides file-level analyzer lookup for bloat_report / split_plan.
"""

from pathlib import Path

from ..discovery import FileIndex
from .base import LanguageAnalyzer


def _analyzer_classes() -> list[type[LanguageAnalyzer]]:
    """All known analyzer classes, ordered by specificity (most specific first)."""
    from .angular import AngularAnalyzer
    from .react import ReactAnalyzer
    from .vue import VueAnalyzer
    from .go import GoAnalyzer
    from .typescript import TypeScriptAnalyzer
    from .python_lang import PythonAnalyzer
    from .rust import RustAnalyzer
    from .java import JavaAnalyzer
    from .scala import ScalaAnalyzer
    from .clojure import ClojureAnalyzer
    from .csharp import CSharpAnalyzer
    from .ruby import RubyAnalyzer
    from .php import PhpAnalyzer
    from .swift import SwiftAnalyzer
    from .c_cpp import CppAnalyzer
    from .dart import DartAnalyzer
    from .elixir import ElixirAnalyzer
    from .solidity import SolidityAnalyzer
    from .terraform import TerraformAnalyzer
    from .data_sources import DataSourceAnalyzer
    from .cli import CliEntrypointAnalyzer
    from .grpc import GrpcAnalyzer
    from .queues import QueueConsumerAnalyzer
    from .scss import ScssAnalyzer

    return [
        AngularAnalyzer,       # before React/TS (most specific)
        ReactAnalyzer,         # before TS (more specific)
        VueAnalyzer,           # before TS (more specific)
        GoAnalyzer,
        RustAnalyzer,
        JavaAnalyzer,
        ScalaAnalyzer,         # JVM — before generic
        ClojureAnalyzer,       # JVM — before generic
        CSharpAnalyzer,
        SwiftAnalyzer,
        RubyAnalyzer,
        PhpAnalyzer,
        CppAnalyzer,
        DartAnalyzer,
        ElixirAnalyzer,
        SolidityAnalyzer,
        TerraformAnalyzer,
        TypeScriptAnalyzer,
        PythonAnalyzer,
        DataSourceAnalyzer,    # supplementary — cross-language data source detection
        CliEntrypointAnalyzer, # supplementary — cross-language CLI entrypoints
        GrpcAnalyzer,          # supplementary — .proto service/method definitions
        QueueConsumerAnalyzer, # supplementary — background job / queue consumers
        ScssAnalyzer,          # last — supplements, no graph nodes
    ]


def discover_analyzers(
    repo_root: Path, index: FileIndex,
) -> list[LanguageAnalyzer]:
    """Return instantiated analyzers for all detected languages/frameworks."""
    matched = []
    for cls in _analyzer_classes():
        if cls.detect(index):
            matched.append(cls(repo_root, index))
    return matched


def get_file_analyzer(repo_root: Path, file_path: Path) -> LanguageAnalyzer | None:
    """Find the best analyzer for a specific file (for bloat_report / split_plan)."""
    from ..discovery import build_index
    index = build_index(repo_root)
    ext = file_path.suffix
    for cls in _analyzer_classes():
        if cls.detect(index):
            instance = cls(repo_root, index)
            if ext in instance.supported_extensions():
                return instance
    return None
