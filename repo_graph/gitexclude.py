"""Keep the `.ai/repo-graph/` cache out of `git status`.

The engine writes its `.gmap` shards + parse cache inside the target repo, which
shows up as a pile of untracked files. On every cache write we add the cache dir
to the repo's local `.git/info/exclude` (never the shared `.gitignore`).

Skipped when the user has opted into committing the cache — the repo-graph
pre-commit hook is installed, or the cache is already tracked — so teams that
share a pre-built graph keep working. Best-effort throughout: no git, a
read-only `.git`, or an odd layout just means nothing is written.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

HOOK_MARKER = "# >>> repo-graph pre-commit >>>"
_COMMENT = "# repo-graph cache (added by repo-graph; local only)"

# Worktree roots already handled this process — the watcher rebuilds often.
_done: set[str] = set()


def find_worktree(start: Path) -> tuple[Path, Path] | None:
    """Walk up from `start` to the enclosing worktree. Returns
    (worktree_root, git_dir); `.git` may be a dir or a `gitdir:` file
    (linked worktrees, submodules)."""
    for d in (start, *start.parents):
        git = d / ".git"
        if git.is_dir():
            return d, git
        if git.is_file():
            try:
                line = git.read_text(encoding="utf-8").strip()
            except OSError:
                return None
            if not line.startswith("gitdir:"):
                return None
            return d, (d / line.split(":", 1)[1].strip()).resolve()
    return None


def common_dir(git_dir: Path) -> Path:
    """Where `info/exclude` and `hooks/` live. Linked worktrees point at the main
    repo via a `commondir` file; normal repos and submodules are their own."""
    try:
        rel = (git_dir / "commondir").read_text(encoding="utf-8").strip()
    except OSError:
        return git_dir
    return (git_dir / rel).resolve()


def _cache_tracked(root: Path, rel: str) -> bool:
    try:
        res = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--", rel],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return res.returncode == 0 and bool(res.stdout.strip())


def ensure_cache_excluded(cache_dir: str | Path) -> str:
    """Add `cache_dir` to the enclosing repo's `info/exclude`.

    Returns what happened: "added", "present", "skipped-hook",
    "skipped-tracked", "no-git", or "error". Never raises.
    """
    try:
        cache = Path(cache_dir).resolve()
        found = find_worktree(cache.parent)
        if found is None:
            return "no-git"
        root, git_dir = found
        key = f"{root}::{cache}"
        if key in _done:
            return "present"
        try:
            rel = cache.relative_to(root.resolve()).as_posix()
        except ValueError:
            return "no-git"
        common = common_dir(git_dir)

        for hooks in {common / "hooks", git_dir / "hooks"}:
            hook = hooks / "pre-commit"
            if hook.is_file() and HOOK_MARKER in hook.read_text(encoding="utf-8", errors="replace"):
                _done.add(key)
                return "skipped-hook"
        if _cache_tracked(root, rel):
            _done.add(key)
            return "skipped-tracked"

        pattern = f"/{rel}/"
        exclude = common / "info" / "exclude"
        text = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
        if any(ln.strip() in (pattern, pattern.rstrip("/"), rel, rel + "/") for ln in text.splitlines()):
            _done.add(key)
            return "present"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        sep = "" if not text or text.endswith("\n") else "\n"
        exclude.write_text(f"{text}{sep}{_COMMENT}\n{pattern}\n", encoding="utf-8")
        _done.add(key)
        return "added"
    except Exception:
        return "error"
