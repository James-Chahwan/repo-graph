"""
Config loader for repo-graph.

Reads `.ai/repo-graph/config.yaml` (or `config.json`) if present, letting the
user override auto-detection in unusual monorepos. Config merges with the
built-in heuristics — auto-detected roots are still scanned, config just adds
more.

Schema:
    skip:           # extra directory basenames to skip during the walk
      - legacy
      - scratch
    roots:          # explicit project roots the heuristics miss
      - path: apps/weird-layout
        kind: python
      - path: services/custom
        kind: go

Kinds map one-to-one with analyzer names: go, rust, python, typescript,
react, vue, angular, java, scala, clojure, csharp, ruby, php, swift,
c_cpp, dart, elixir, solidity, terraform.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RepoGraphConfig:
    skip: set[str] = field(default_factory=set)
    roots: dict[str, list[Path]] = field(default_factory=dict)

    def extra_roots(self, kind: str) -> list[Path]:
        return self.roots.get(kind, [])


def load_config(repo_root: Path) -> RepoGraphConfig:
    """Load config from .ai/repo-graph/config.{yaml,json}; return empty if absent."""
    base = repo_root / ".ai" / "repo-graph"
    for name in ("config.yaml", "config.yml", "config.json"):
        path = base / name
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
                raw = json.loads(text) if name.endswith(".json") else _parse_yaml(text)
            except Exception as exc:
                print(f"  [config] failed to parse {path.name}: {exc}")
                return RepoGraphConfig()
            return _build_config(repo_root, raw)
    return RepoGraphConfig()


def _build_config(repo_root: Path, raw: dict) -> RepoGraphConfig:
    skip = {str(s) for s in (raw.get("skip") or []) if s}
    roots: dict[str, list[Path]] = {}
    for entry in (raw.get("roots") or []):
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        path_str = entry.get("path")
        if not kind or not path_str:
            continue
        abs_path = (repo_root / path_str).resolve()
        roots.setdefault(str(kind), []).append(abs_path)
    return RepoGraphConfig(skip=skip, roots=roots)


# ---------------------------------------------------------------------------
# Minimal YAML parser — supports the config schema only.
#
# Handles: top-level scalar keys, top-level keys with a block list of scalars,
# top-level keys with a block list of inline-dict items (2-space indent each).
# # line comments, blank lines, single/double quoted strings.
# Not supported: anchors, references, multi-line strings, flow syntax.
# ---------------------------------------------------------------------------


def _parse_yaml(text: str) -> dict:
    lines: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.split("#", 1)[0].rstrip()
        if stripped.strip():
            lines.append(stripped)

    result: dict = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith(" "):
            i += 1
            continue
        if ":" not in line:
            i += 1
            continue
        key, _, inline = line.partition(":")
        inline = inline.strip()
        key = key.strip()
        if inline:
            result[key] = _scalar(inline)
            i += 1
            continue
        block, consumed = _parse_list(lines, i + 1)
        result[key] = block
        i += 1 + consumed
    return result


def _parse_list(lines: list[str], start: int) -> tuple[list, int]:
    items: list = []
    i = start
    item_indent: int | None = None
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        if not stripped.startswith("- "):
            if item_indent is not None and indent > item_indent and items and isinstance(items[-1], dict):
                key, _, val = stripped.partition(":")
                items[-1][key.strip()] = _scalar(val.strip())
                i += 1
                continue
            break
        if item_indent is None:
            item_indent = indent
        elif indent != item_indent:
            break
        body = stripped[2:].strip()
        if ":" in body:
            key, _, val = body.partition(":")
            items.append({key.strip(): _scalar(val.strip())})
        else:
            items.append(_scalar(body))
        i += 1
    return items, i - start


def _scalar(val: str):
    val = val.strip()
    if not val:
        return ""
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    low = val.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "~"):
        return None
    if val.lstrip("-").isdigit():
        return int(val)
    return val
