"""
Base class and data types for language analyzers.
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Node:
    id: str
    type: str
    name: str
    file_path: str  # relative to repo root


@dataclass
class Edge:
    from_id: str
    to_id: str
    type: str


@dataclass
class AnalysisResult:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    flows: dict[str, str] = field(default_factory=dict)
    state_sections: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class LanguageAnalyzer(ABC):
    """Base class for language/framework analyzers."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    @staticmethod
    @abstractmethod
    def detect(repo_root: Path) -> bool:
        """Return True if this analyzer applies to the given repo."""
        ...

    @abstractmethod
    def scan(self) -> AnalysisResult:
        """Scan the repo and return all discovered nodes, edges, and flows."""
        ...

    # -- File-level analysis (optional) ------------------------------------

    def supported_extensions(self) -> set[str]:
        """File extensions this analyzer handles for bloat_report."""
        return set()

    def analyze_file(self, file_path: Path) -> dict | None:
        """Analyze a single file's internal structure. Returns None if unsupported."""
        return None

    def suggest_splits(self, file_path: Path, analysis: dict) -> list[dict] | None:
        """Suggest splits for a large file. Returns None if unsupported."""
        return None

    def format_bloat_report(self, analysis: dict) -> str | None:
        """Format analysis dict into a human-readable bloat report."""
        return None

    def format_split_plan(self, file_path: str, analysis: dict, splits: list[dict]) -> str | None:
        """Format split suggestions into a human-readable string."""
        return None


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------


def read_safe(path: Path) -> str:
    """Read a file, returning empty string on any error."""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def list_files(directory: Path, suffix: str) -> list[Path]:
    """List files with a given suffix in a directory (non-recursive)."""
    if not directory.exists():
        return []
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix == suffix)


def list_dirs(directory: Path) -> list[Path]:
    """List subdirectories of a directory."""
    if not directory.exists():
        return []
    return sorted(p for p in directory.iterdir() if p.is_dir())


# Common monorepo container directories
_MONOREPO_DIRS = {"packages", "apps", "services", "modules", "libs", "projects", "workspace", "src", "crates"}
_SKIP_DIRS = {"node_modules", ".git", "dist", "build", "__pycache__", "vendor", ".venv", "venv"}


def scan_project_dirs(repo_root: Path) -> list[Path]:
    """
    Return candidate project directories to check for marker files.

    Checks: repo root, immediate subdirs, and one level into common
    monorepo container dirs (packages/*, apps/*, services/*, etc.).
    Handles layouts like:
      - root project
      - root/backend, root/frontend
      - packages/api, packages/web
      - apps/server, apps/client
    """
    candidates: list[Path] = [repo_root]
    for d in sorted(repo_root.iterdir()):
        if not d.is_dir() or d.name.startswith(".") or d.name in _SKIP_DIRS:
            continue
        candidates.append(d)
        # One level into monorepo containers
        if d.name in _MONOREPO_DIRS:
            for sub in sorted(d.iterdir()):
                if sub.is_dir() and not sub.name.startswith(".") and sub.name not in _SKIP_DIRS:
                    candidates.append(sub)
    return candidates


def camel_to_snake(name: str) -> str:
    """Convert CamelCase to snake_case."""
    s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s1).lower()


def path_to_slug(path: str) -> str:
    """'/groups/:id/activities' -> 'groups_id_activities'"""
    return re.sub(r"[^a-zA-Z0-9]", "_", path.lstrip("/")).strip("_")


def render_flow_yaml(flow_name: str, paths: list[dict]) -> str:
    """Render a flow as YAML text."""
    lines = [f"flow: {flow_name}", "paths:"]
    for p in paths:
        lines.append(f"  - name: {p['name']}")
        lines.append("    steps:")
        for step in p["steps"]:
            edge_part = f", edge: {step['edge']}" if "edge" in step else ""
            lines.append(
                f"      - {{id: {step['id']}, type: {step['type']}{edge_part}}}"
            )
    return "\n".join(lines) + "\n"


def rel_path(repo_root: Path, absolute: Path) -> str:
    """Return path relative to repo root as a string."""
    try:
        return str(absolute.relative_to(repo_root))
    except ValueError:
        return str(absolute)
