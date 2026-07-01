"""Optional pre-commit hook install — pre-warm the graph on every commit.

The in-server watcher keeps the graph fresh while an agent is connected, and the
cold-start staleness check refreshes it on connect. The git hook is the third
option: regenerate + cache the graph at commit time so the cached `.gmap` can be
committed and teammates/CI get a pre-built graph. Marker-fenced and idempotent,
so `repo-graph uninstall` removes exactly what it added.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from .markers import upsert_section, remove_section
from .targets import Change

_HOOK_START = "# >>> repo-graph pre-commit >>>"
_HOOK_END = "# <<< repo-graph pre-commit <<<"

_HOOK_BODY = f"""{_HOOK_START}
# Refresh and cache the repo-graph before committing, then stage the cache.
uvx --from mcp-repo-graph repo-graph-init --repo . --graph-only >/dev/null 2>&1 || true
git add .ai/repo-graph 2>/dev/null || true
{_HOOK_END}"""

# Reuse the marker engine but with the hook's own sentinels.
import re  # noqa: E402

_HOOK_RE = re.compile(re.escape(_HOOK_START) + r".*?" + re.escape(_HOOK_END) + r"\n?", re.DOTALL)


def _hooks_dir(repo: Path) -> Path | None:
    git = repo / ".git"
    if git.is_dir():
        return git / "hooks"
    # `.git` is a file for worktrees/submodules: `gitdir: <path>`
    if git.is_file():
        try:
            line = git.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if line.startswith("gitdir:"):
            return (repo / line.split(":", 1)[1].strip()).resolve() / "hooks"
    return None


def install_hook(repo: Path, dry: bool = False) -> Change:
    hooks = _hooks_dir(repo)
    if hooks is None:
        return Change("git-hook", "hook", str(repo / ".git"), "not-found")
    path = hooks / "pre-commit"
    content = path.read_text(encoding="utf-8") if path.is_file() else ""
    if not content:
        content = "#!/bin/sh\n"
    if _HOOK_RE.search(content):
        return Change("git-hook", "hook", str(path), "unchanged")
    new = content + ("\n" if not content.endswith("\n") else "") + _HOOK_BODY + "\n"
    if not dry:
        hooks.mkdir(parents=True, exist_ok=True)
        path.write_text(new, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return Change("git-hook", "hook", str(path), "created")


def remove_hook(repo: Path, dry: bool = False) -> Change | None:
    hooks = _hooks_dir(repo)
    if hooks is None:
        return None
    path = hooks / "pre-commit"
    if not path.is_file():
        return None
    content = path.read_text(encoding="utf-8")
    if not _HOOK_RE.search(content):
        return None
    stripped = _HOOK_RE.sub("", content)
    if not dry:
        # If the hook is now just the shebang (we created it), remove it entirely.
        if stripped.strip() in ("", "#!/bin/sh", "#!/bin/bash"):
            path.unlink()
        else:
            path.write_text(stripped, encoding="utf-8")
    return Change("git-hook", "hook", str(path), "removed")
