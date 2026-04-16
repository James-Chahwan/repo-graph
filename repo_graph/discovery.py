"""
File discovery for repo-graph.

Single walk of the repo root at generation start. All analyzers share one
FileIndex and query it for files/directories, rather than each running its
own rglob. Centralises the skip list so build artefacts, vendored deps, and
language-specific caches stay out of the graph.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path


# Directories whose contents are never indexed.
_DEFAULT_SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn",
    "node_modules", "bower_components",
    "vendor",
    "target", "build", "out", "dist",
    ".next", ".nuxt", ".output", ".svelte-kit",
    "__pycache__", ".venv", "venv", "env",
    ".cpcache", ".shadow-cljs", ".lsp",
    ".idea", ".vscode", ".vs",
    ".cargo", ".gradle", ".m2", ".mvn",
    ".bundle", ".terraform", ".terragrunt-cache", ".serverless",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    "coverage", ".nyc_output",
    "dist-newstyle", ".stack-work",
    ".dart_tool",
    ".bloop", ".metals", "_build", "deps",
})


@dataclass
class FileIndex:
    """One-shot file index. Built once per generate, shared across analyzers."""

    repo_root: Path
    all_files: list[Path] = field(default_factory=list)
    files_by_ext: dict[str, list[Path]] = field(default_factory=lambda: defaultdict(list))
    files_by_dir: dict[Path, list[Path]] = field(default_factory=lambda: defaultdict(list))
    config_roots: dict[str, list[Path]] = field(default_factory=dict)

    def extra_roots(self, kind: str) -> list[Path]:
        """User-declared roots from .ai/repo-graph/config.yaml for a language kind."""
        return self.config_roots.get(kind, [])

    def roots_for(self, kind: str, markers) -> list[Path]:
        """Directories containing any marker file/glob, unioned with config-supplied
        roots for the given kind. `markers` can be a single name or a list."""
        if isinstance(markers, str):
            markers = [markers]
        return sorted(set(self.dirs_with_any(markers)) | set(self.extra_roots(kind)))

    def rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.repo_root))
        except ValueError:
            return str(path)

    def files_with_ext(
        self, exts, under: Path | None = None,
    ) -> list[Path]:
        """Files matching any of the given extensions, optionally under a dir."""
        if isinstance(exts, str):
            exts = {exts}
        collected: list[Path] = []
        for ext in exts:
            collected.extend(self.files_by_ext.get(ext, []))
        if under is not None:
            collected = [p for p in collected if _is_under(p, under)]
        return sorted(collected)

    def files_with_name(
        self, name: str, under: Path | None = None,
    ) -> list[Path]:
        """Files whose basename exactly matches."""
        collected = [p for p in self.all_files if p.name == name]
        if under is not None:
            collected = [p for p in collected if _is_under(p, under)]
        return sorted(collected)

    def files_matching(
        self, pattern: str, under: Path | None = None,
    ) -> list[Path]:
        """Files whose basename matches the given glob pattern (e.g. '*.csproj')."""
        collected = [p for p in self.all_files if fnmatch(p.name, pattern)]
        if under is not None:
            collected = [p for p in collected if _is_under(p, under)]
        return sorted(collected)

    def dirs_with_file(self, name: str) -> list[Path]:
        """Directories containing a file with the exact name."""
        return sorted({
            d for d, files in self.files_by_dir.items()
            if any(f.name == name for f in files)
        })

    def dirs_with_glob(self, pattern: str) -> list[Path]:
        """Directories with at least one file matching the glob."""
        return sorted({
            d for d, files in self.files_by_dir.items()
            if any(fnmatch(f.name, pattern) for f in files)
        })

    def dirs_with_any(self, markers) -> list[Path]:
        """Directories containing any of the named files or glob patterns."""
        result: set[Path] = set()
        for marker in markers:
            if any(c in marker for c in "*?["):
                result.update(self.dirs_with_glob(marker))
            else:
                result.update(self.dirs_with_file(marker))
        return sorted(result)


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _should_skip_dir(d: Path, extra_skip: set[str]) -> bool:
    name = d.name
    if name in _DEFAULT_SKIP_DIRS or name in extra_skip:
        return True
    if name.startswith(".") and name != ".ai":
        return True
    return False


def build_index(
    repo_root: Path,
    extra_skip: set[str] | None = None,
    config_roots: dict[str, list[Path]] | None = None,
) -> FileIndex:
    """Walk repo_root once, returning a populated FileIndex."""
    extra_skip = set(extra_skip or ())
    index = FileIndex(repo_root=repo_root, config_roots=dict(config_roots or {}))
    _walk(repo_root, index, extra_skip)
    return index


def _walk(current: Path, index: FileIndex, extra_skip: set[str]) -> None:
    try:
        entries = list(current.iterdir())
    except (PermissionError, OSError):
        return
    for entry in entries:
        if entry.is_symlink():
            continue
        if entry.is_dir():
            if _should_skip_dir(entry, extra_skip):
                continue
            _walk(entry, index, extra_skip)
        elif entry.is_file():
            index.all_files.append(entry)
            index.files_by_ext[entry.suffix].append(entry)
            index.files_by_dir[entry.parent].append(entry)
