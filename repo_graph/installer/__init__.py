"""repo-graph installer — one command to wire repo-graph into every AI coding
agent (config + usage instructions + auto-allow permissions), reversibly.

Public surface:
    main(argv)                      CLI entry (`repo-graph install` / `uninstall`)
    install(repo, targets, ...)     programmatic install
    uninstall(repo, targets, ...)   programmatic uninstall
    resolve_targets(spec)           map an --agents spec to Target objects
    REGISTRY, all_targets, detected_targets
"""

from .core import (
    install,
    uninstall,
    resolve_targets,
    format_report,
    main,
)
from .targets import Change, Target, REGISTRY, all_targets, detected_targets

__all__ = [
    "main",
    "install",
    "uninstall",
    "resolve_targets",
    "format_report",
    "Change",
    "Target",
    "REGISTRY",
    "all_targets",
    "detected_targets",
]
