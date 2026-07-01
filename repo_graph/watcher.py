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

# Directories we never rebuild on: the engine's own skip set plus our cache dir.
# `.ai` is critical — the rebuild writes the .gmap/parse cache under it, and
# watching that would loop forever.
SKIP_DIRS = {
    ".git", ".ai", "target", "node_modules", ".venv", "venv", "env",
    "__pycache__", "dist", "build", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".idea", ".vscode", ".tox", ".next", ".nuxt", ".angular", ".gradle", ".svelte-kit",
}

DEBOUNCE_SEC = 0.3


def is_ignored(path: str) -> bool:
    """True if `path` lies inside any skipped directory (so edits there don't
    trigger a rebuild — most importantly our own `.ai/` cache writes)."""
    return bool(set(Path(path).parts) & SKIP_DIRS)


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

    debouncer = Debouncer(delay, on_change)

    class _Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            if getattr(event, "is_directory", False):
                return
            src = getattr(event, "dest_path", "") or event.src_path
            if is_ignored(src):
                return
            debouncer.trigger()

    observer = Observer()
    observer.schedule(_Handler(), repo_path, recursive=True)
    observer.daemon = True
    observer.start()
    return observer
