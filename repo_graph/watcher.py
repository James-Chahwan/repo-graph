"""Background file watcher — keeps the graph fresh without a manual git hook.

Runs as a daemon thread inside the MCP server (started from ``server.main`` unless
``REPO_GRAPH_WATCH=0``). On a debounced batch of source edits it triggers an
incremental rebuild, so the next tool call sees current structure without the user
running ``reload`` or wiring a commit hook.

Requires the optional ``watchdog`` dependency. If it's unavailable the server runs
fine without live freshness — the cold-start staleness check still refreshes the
graph whenever the source tree changed since the cached ``.gmap`` was written.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Callable

# Directories we never rebuild on: the engine's own skip set. The layout dir is
# NOT in here — it's matched by prefix in `is_ignored`, because `.glia/` also
# holds committed *inputs* (overlay.toml, cells.jsonl, vectors.jsonl) whose edits
# must rebuild. Only `<repo>/.glia/graph` is our own write.
SKIP_DIRS = {
    ".git", ".ai", "target", "node_modules", ".venv", "venv", "env",
    "__pycache__", "dist", "build", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".idea", ".vscode", ".tox", ".next", ".nuxt", ".angular", ".gradle", ".svelte-kit",
}

# Event types that mean the tree actually changed. watchdog >= 6.0 on Linux also
# emits read-only `opened` / `closed_no_write` events, and a rebuild opens every
# source file — so triggering on those makes each rebuild schedule the next one
# (measured: 9161 `opened` events in 6s; ~1.2 TB written in a day, idle).
WRITE_EVENTS = frozenset({"created", "modified", "moved", "deleted", "closed"})

DEBOUNCE_SEC = 0.3


def is_ignored(path: str, layout_dir: str | None = None) -> bool:
    """True if `path` lies inside a skipped directory, or inside our own graph
    layout dir (`<repo>/.glia/graph`) — so our cache writes never trigger a
    rebuild, while edits to `.glia/overlay.toml` and friends still do."""
    if set(Path(path).parts) & SKIP_DIRS:
        return True
    if layout_dir:
        try:
            Path(path).resolve().relative_to(Path(layout_dir).resolve())
            return True
        except (ValueError, OSError):
            pass
    return False


class Debouncer:
    """Trailing debounce: coalesce a burst of triggers into one call of `fn`,
    fired `delay` seconds after the last trigger. Editor save-storms become one
    rebuild."""

    def __init__(self, delay: float, fn: Callable[[], None]):
        self._delay = delay
        self._fn = fn
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def trigger(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._delay, self._fn)
            self._timer.daemon = True
            self._timer.start()

    def cancel(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None


def start_watcher(repo_path: str, on_change: Callable[[], None],
                  delay: float = DEBOUNCE_SEC):
    """Start watching `repo_path`; call `on_change()` (debounced) on source edits.

    Returns the running watchdog Observer, or None if watchdog is unavailable or
    the path isn't a directory. The observer is a daemon thread and dies with the
    process; the caller can keep the handle to stop it explicitly.
    """
    if not Path(repo_path).is_dir():
        return None
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except Exception:
        return None

    try:
        import glia_py
        layout_dir = glia_py.default_gmap_dir(repo_path)
    except Exception:
        layout_dir = str(Path(repo_path) / ".glia" / "graph")

    debouncer = Debouncer(delay, on_change)

    class _Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            if getattr(event, "is_directory", False):
                return
            if getattr(event, "event_type", "") not in WRITE_EVENTS:
                return
            src = getattr(event, "dest_path", "") or event.src_path
            if is_ignored(src, layout_dir):
                return
            debouncer.trigger()

    observer = Observer()
    observer.schedule(_Handler(), repo_path, recursive=True)
    observer.daemon = True
    observer.start()
    return observer
