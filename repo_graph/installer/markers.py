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
# only the first block is taken; a trailing newline is swallowed if present.
_SECTION_RE = re.compile(
    re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END) + r"\n?",
    re.DOTALL,
)


def upsert_section(content: str, block: str) -> tuple[str, str]:
    """Insert or replace the fenced block in `content`.

    Returns ``(new_content, status)`` where status is ``created`` (appended for
    the first time), ``updated`` (an existing block was replaced with different
    text), or ``unchanged`` (identical, or differing only by a trailing newline —
    so re-install never triggers a redundant write).
    """
    m = _SECTION_RE.search(content)
    if m:
        replaced = content[: m.start()] + block + "\n" + content[m.end():]
        # A block that sat at EOF without a trailing newline is byte-different
        # only by that newline; treat as unchanged and keep the original.
        if replaced == content or replaced.rstrip("\n") == content.rstrip("\n"):
            return content, "unchanged"
        return replaced, "updated"

    if content and not content.endswith("\n"):
        content += "\n"
    prefix = content + "\n" if content else ""
    return prefix + block + "\n", "created"


def remove_section(content: str) -> tuple[str, str]:
    """Strip the fenced block from `content`.

    Returns ``(new_content, status)`` with status ``removed`` or ``not-found``.
    Only the seam left by the block is tidied; blank lines the user authored
    elsewhere are left exactly as they were.
    """
    m = _SECTION_RE.search(content)
    if not m:
        return content, "not-found"
    before = content[: m.start()].rstrip("\n")
    after = content[m.end():].lstrip("\n")
    if before and after:
        joined = before + "\n\n" + after
    elif before:
        joined = before + "\n"
    elif after:
        joined = after if after.endswith("\n") else after + "\n"
    else:
        joined = ""
    return joined, "removed"


def has_section(content: str) -> bool:
    """True if the fenced block is present in `content`."""
    return bool(_SECTION_RE.search(content))
