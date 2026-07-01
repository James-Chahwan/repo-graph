"""Config file IO for JSON, JSONC, and TOML.

Writes preserve the user's other content: other MCP servers, unrelated keys, and
(for TOML) surrounding comments. JSON is re-serialised via ``json.dumps``, so
``//`` and ``/* */`` comments in a JSONC file (VS Code, opencode) are NOT
round-tripped back — only keys and values survive. Comment-bearing JSONC is
parsed with a string-aware scanner so comment/trailing-comma stripping never
corrupts a string value.

Safety contract: ``load_json`` distinguishes "file missing or empty" (returns
``{}``) from "file present but unparseable" (raises ``ConfigError``). Callers must
never overwrite a config they could not parse — doing so would silently drop the
user's other servers. TOML (Codex) is text-spliced, never re-serialised.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    """A config file exists and is non-empty but could not be parsed."""


# ── JSON / JSONC ──────────────────────────────────────────────────────────────


def _scan_strip_comments(text: str) -> str:
    """Remove // line and /* */ block comments, skipping string literals."""
    out: list[str] = []
    i, n = 0, len(text)
    in_str = False
    quote = ""
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == quote:
                in_str = False
            i += 1
            continue
        if c in ('"', "'"):
            in_str, quote = True, c
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            if j == -1:
                break
            i = j
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = (j + 2) if j != -1 else n
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _scan_strip_trailing_commas(text: str) -> str:
    """Drop commas that are immediately followed by } or ], skipping strings."""
    out: list[str] = []
    i, n = 0, len(text)
    in_str = False
    quote = ""
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == quote:
                in_str = False
            i += 1
            continue
        if c in ('"', "'"):
            in_str, quote = True, c
            out.append(c)
            i += 1
            continue
        if c == ",":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in "}]":
                i += 1  # drop the trailing comma
                continue
        out.append(c)
        i += 1
    return "".join(out)


def strip_jsonc(text: str) -> str:
    """String-aware strip of JSONC comments and trailing commas.

    Only content outside string literals is touched, so a value like
    ``"file:///x"`` or ``"a, ]"`` is left intact.
    """
    return _scan_strip_trailing_commas(_scan_strip_comments(text))


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON/JSONC file into a dict.

    Returns ``{}`` for a missing or whitespace-only file. Raises ``ConfigError``
    if the file exists, is non-empty, and cannot be parsed even after stripping
    JSONC comments — so a caller never mistakes "unparseable" for "empty" and
    overwrites the user's config. Tolerates a UTF-8 BOM.
    """
    if not path.is_file():
        return {}
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as e:
        raise ConfigError(f"could not read {path}: {e}") from e
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        try:
            return json.loads(strip_jsonc(raw))
        except json.JSONDecodeError as e:
            raise ConfigError(f"could not parse {path}: {e}") from e


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Serialise `data` as indented JSON with a trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# ── TOML (read to detect, text-splice to write) ───────────────────────────────


def load_toml(path: Path) -> dict[str, Any]:
    """Load a TOML file into a dict; ``{}`` if missing or unparseable."""
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _toml_value(v: Any) -> str:
    """Render a scalar or flat list as a TOML value."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v)  # JSON string escaping is valid TOML basic-string
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    raise TypeError(f"unsupported TOML value: {v!r}")


def render_toml_table(table: str, entries: dict[str, Any]) -> str:
    """Render ``[table]`` with scalar/list `entries` and nested-dict sub-tables."""
    scalars = {k: v for k, v in entries.items() if not isinstance(v, dict)}
    subtables = {k: v for k, v in entries.items() if isinstance(v, dict)}
    lines = [f"[{table}]"]
    for k, v in scalars.items():
        lines.append(f"{k} = {_toml_value(v)}")
    out = "\n".join(lines) + "\n"
    for name, sub in subtables.items():
        out += "\n" + render_toml_table(f"{table}.{name}", sub)
    return out


_TOML_HEADER_RE = re.compile(r"^\s*\[\[?([^\]]+)\]\]?\s*$")


def remove_toml_table(text: str, table: str) -> tuple[str, bool]:
    """Remove ``[table]`` and any ``[table.sub]`` blocks from TOML `text`.

    Returns ``(new_text, removed)``. Blank/comment lines that trail the removed
    table but precede the *next* table belong to that next table and are
    preserved (re-emitted); the table's own key/value lines are dropped. Only the
    excised region is touched, so unrelated user spacing is left alone.
    """
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    removed = False
    skipping = False
    buf: list[str] = []  # blank/comment lines that may belong to the next table
    for line in lines:
        m = _TOML_HEADER_RE.match(line)
        if m:
            name = m.group(1).strip()
            if name == table or name.startswith(table + "."):
                skipping = True
                removed = True
                buf = []
                continue
            if skipping:  # foreign header ends the skip; its leading comments survive
                out.extend(buf)
                buf = []
                skipping = False
            out.append(line)
            continue
        if skipping:
            s = line.strip()
            if s == "" or s.startswith("#"):
                buf.append(line)  # might precede the next table
            else:
                buf = []  # a key/value line of our table -> drop, reset
            continue
        out.append(line)
    return "".join(out), removed
