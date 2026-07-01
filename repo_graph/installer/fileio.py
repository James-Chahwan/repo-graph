"""Non-destructive config file IO for JSON, JSONC, and TOML.

Every write here preserves whatever the user already has: other MCP servers,
comments, unrelated keys. JSON/JSONC configs are parsed tolerantly (some clients
— opencode, VS Code — allow ``//`` comments and trailing commas), mutated, and
re-serialised as clean JSON. TOML (Codex) has no stdlib writer, so we read with
``tomllib`` to detect presence and splice the server's table as text.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any


# ── JSON / JSONC ──────────────────────────────────────────────────────────────

# Strip // line comments and /* */ block comments, then trailing commas. Good
# enough for the config files we touch; we never round-trip comments back.
_LINE_COMMENT_RE = re.compile(r'(?<!:)//[^\n"]*')
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def strip_jsonc(text: str) -> str:
    """Best-effort strip of JSONC comments and trailing commas."""
    text = _BLOCK_COMMENT_RE.sub("", text)
    # Only strip // when it's not inside a URL like http:// — the (?<!:) guard
    # above handles the common case; a full lexer is overkill for these files.
    text = _LINE_COMMENT_RE.sub("", text)
    text = _TRAILING_COMMA_RE.sub(r"\1", text)
    return text


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON/JSONC file into a dict; ``{}`` if missing or unparseable."""
    if not path.is_file():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        try:
            return json.loads(strip_jsonc(raw))
        except json.JSONDecodeError:
            return {}


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
        return tomllib.loads(path.read_text(encoding="utf-8"))
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


def remove_toml_table(text: str, table: str) -> tuple[str, bool]:
    """Remove ``[table]`` and any ``[table.sub]`` blocks from TOML `text`.

    Returns ``(new_text, removed)``. Removal spans from a matching header line to
    the next top-level ``[`` header or EOF.
    """
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    removed = False
    skipping = False
    header_re = re.compile(r"^\s*\[\[?([^\]]+)\]\]?\s*$")
    for line in lines:
        m = header_re.match(line)
        if m:
            name = m.group(1).strip()
            if name == table or name.startswith(table + "."):
                skipping = True
                removed = True
                continue
            skipping = False
        if not skipping:
            out.append(line)
    new_text = "".join(out)
    # Collapse blank runs left by the excision.
    new_text = re.sub(r"\n{3,}", "\n\n", new_text)
    return new_text, removed
