"""Idempotent marker-fenced section upsert/removal for instructions files.

The one primitive behind instruction injection: given a file's text and a fenced
block (``<!-- repo-graph:start -->`` ... ``<!-- repo-graph:end -->``), insert it,
replace it in place if already present, or strip it out — always leaving the
user's surrounding content untouched. Same engine drives install and uninstall.
"""

from __future__ import annotations

import re

from .constants import MARKER_START, MARKER_END

# Matches the whole fenced region, markers included, across lines. Non-greedy so
# only the first block is taken; a trailing newline is swallowed if present so
# repeated upserts don't accumulate blank lines.
_SECTION_RE = re.compile(
    re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END) + r"\n?",
    re.DOTALL,
)


def upsert_section(content: str, block: str) -> tuple[str, str]:
    """Insert or replace the fenced block in `content`.

    Returns ``(new_content, status)`` where status is ``created`` (appended for
    the first time), ``updated`` (an existing block was replaced with different
    text), or ``unchanged`` (the block was already present and identical).
    """
    if _SECTION_RE.search(content):
        replaced = _SECTION_RE.sub(lambda _: block + "\n", content, count=1)
        # Normalise: strip a doubled trailing newline the sub may introduce.
        if replaced.endswith("\n\n") and not content.endswith("\n\n"):
            replaced = replaced[:-1]
        if replaced == content:
            return content, "unchanged"
        return replaced, "updated"

    if content and not content.endswith("\n"):
        content += "\n"
    prefix = content + "\n" if content else ""
    return prefix + block + "\n", "created"


def remove_section(content: str) -> tuple[str, str]:
    """Strip the fenced block from `content`.

    Returns ``(new_content, status)`` with status ``removed`` or ``not-found``.
    Collapses the blank line left behind so uninstall is a clean reversal.
    """
    if not _SECTION_RE.search(content):
        return content, "not-found"
    stripped = _SECTION_RE.sub("", content, count=1)
    # Tidy up a doubled blank line where the block used to sit.
    stripped = re.sub(r"\n{3,}", "\n\n", stripped)
    return stripped, "removed"


def has_section(content: str) -> bool:
    """True if the fenced block is present in `content`."""
    return bool(_SECTION_RE.search(content))
