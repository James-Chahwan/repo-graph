"""`repo-graph install` / `repo-graph uninstall` — orchestration and CLI.

Resolves which agents to target, then runs each target's config write, instruction
injection, and permission grant (or their reverse). Everything is idempotent and
marker-fenced, so re-running install is a no-op and uninstall is a clean reversal.
Non-interactive by design: `--yes`, a non-TTY stdin (CI, or running inside the MCP
stdio wrapper), or `--dry-run` all skip the prompt.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .constants import SERVER_NAME
from .targets import (
    Change,
    Codex,
    REGISTRY,
    Target,
    all_targets,
    detected_targets,
)


# ── target resolution ─────────────────────────────────────────────────────────


def resolve_targets(spec: str) -> list[Target]:
    """Map an --agents spec to targets.

    ``auto`` = detected-installed (falls back to Claude Code so a bare install
    always does something), ``all`` = every target, ``none`` = [], otherwise a
    comma-separated list of target ids (raises on an unknown id).
    """
    spec = (spec or "auto").strip().lower()
    if spec == "auto":
        return detected_targets() or [REGISTRY["claude-code"]]
    if spec == "all":
        return all_targets()
    if spec == "none":
        return []
    out: list[Target] = []
    for raw in spec.split(","):
        tid = raw.strip()
        if not tid:
            continue
        if tid not in REGISTRY:
            known = ", ".join(REGISTRY)
            raise ValueError(f"unknown agent '{tid}'. Known: {known}")
        out.append(REGISTRY[tid])
    return out


# ── install / uninstall ───────────────────────────────────────────────────────


def install(
    repo: Path,
    targets: list[Target],
    *,
    scope: str = "project",
    permissions: bool = True,
    instructions: bool = True,
    dry: bool = False,
) -> list[Change]:
    changes: list[Change] = []
    for t in targets:
        changes += t.write_mcp(repo, scope, permissions, dry)
        if instructions:
            changes += t.write_instructions(repo, scope, dry)
        if permissions:
            changes += t.write_permissions(repo, scope, dry)
    return changes


def uninstall(repo: Path, targets: list[Target], *, dry: bool = False) -> list[Change]:
    changes: list[Change] = []
    for t in targets:
        changes += t.remove_mcp(repo, dry)
        changes += t.remove_instructions(repo, dry)
        changes += t.remove_permissions(repo, dry)
    return changes


# ── reporting ─────────────────────────────────────────────────────────────────

_SYMBOL = {
    "created": "+",
    "updated": "~",
    "unchanged": "=",
    "removed": "-",
    "not-found": " ",
}


def format_report(changes: list[Change], targets: list[Target], dry: bool) -> str:
    by_id = {t.id: t.label for t in targets}
    lines: list[str] = []
    if dry:
        lines.append("[dry-run] no files written. Would apply:")
    grouped: dict[str, list[Change]] = {}
    for c in changes:
        grouped.setdefault(c.target, []).append(c)
    if not grouped:
        lines.append("  nothing to do.")
    for tid, items in grouped.items():
        lines.append(f"  {by_id.get(tid, tid)}:")
        for c in items:
            sym = _SYMBOL.get(c.action, "?")
            lines.append(f"    {sym} {c.kind:<12} {c.action:<9} {c.path}")
    touched = sum(1 for c in changes if c.action in ("created", "updated", "removed"))
    lines.append("")
    verb = "would change" if dry else "changed"
    lines.append(f"  {touched} file(s) {verb}.")
    return "\n".join(lines)


def _print_config(agent_id: str, repo: Path) -> str:
    """Emit the exact config snippet for one agent without writing anything."""
    if agent_id not in REGISTRY:
        return f"unknown agent '{agent_id}'. Known: {', '.join(REGISTRY)}"
    t = REGISTRY[agent_id]
    if isinstance(t, Codex):
        from .fileio import render_toml_table

        entry = {"command": "uvx", "args": ["mcp-repo-graph", "--repo", "."]}
        return f"# ~/.codex/config.toml\n{render_toml_table(f'mcp_servers.{SERVER_NAME}', entry)}"
    entry = t.build_entry(str(repo), "project", permissions=True)
    return json.dumps({t.config_key: {SERVER_NAME: entry}}, indent=2)


# ── confirmation ──────────────────────────────────────────────────────────────


def _confirm(assume_yes: bool) -> bool:
    if assume_yes or not sys.stdin.isatty():
        return True
    try:
        return input("Proceed? [Y/n] ").strip().lower() in ("", "y", "yes")
    except EOFError:
        return True


# ── CLI ───────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="repo-graph",
        description="Install or remove repo-graph across your AI coding agents.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    ins = sub.add_parser("install", help="wire repo-graph into detected agents")
    ins.add_argument("--agents", default="auto",
                     help="auto | all | none | comma-separated ids (default: auto). "
                          f"ids: {', '.join(REGISTRY)}")
    ins.add_argument("--scope", choices=["project", "user"], default="project",
                     help="write project-local config (default) or user/global config")
    ins.add_argument("--repo", default=".", help="repository to map (default: cwd)")
    ins.add_argument("--no-instructions", action="store_true",
                     help="skip injecting the usage block into agent instructions files")
    ins.add_argument("--no-permissions", action="store_true",
                     help="skip granting auto-allow permissions")
    ins.add_argument("--yes", "-y", action="store_true", help="do not prompt for confirmation")
    ins.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    ins.add_argument("--print-config", metavar="AGENT", default=None,
                     help="print one agent's config snippet and exit (writes nothing)")

    un = sub.add_parser("uninstall", help="remove repo-graph from agents")
    un.add_argument("--agents", default="all",
                    help="auto | all | none | comma-separated ids (default: all)")
    un.add_argument("--repo", default=".", help="repository the graph was mapped for (default: cwd)")
    un.add_argument("--yes", "-y", action="store_true", help="do not prompt for confirmation")
    un.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    args = parser.parse_args(argv)
    repo = Path(args.repo).expanduser().resolve()

    if args.command == "install":
        if args.print_config:
            print(_print_config(args.print_config, repo))
            return 0
        try:
            targets = resolve_targets(args.agents)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        if not targets:
            print("No agents selected.")
            return 0
        preview = install(
            repo, targets,
            scope=args.scope,
            permissions=not args.no_permissions,
            instructions=not args.no_instructions,
            dry=True,
        )
        print(f"repo-graph install -> {repo}")
        print(format_report(preview, targets, dry=True))
        if args.dry_run:
            return 0
        if not _confirm(args.yes):
            print("Aborted.")
            return 1
        applied = install(
            repo, targets,
            scope=args.scope,
            permissions=not args.no_permissions,
            instructions=not args.no_instructions,
            dry=False,
        )
        print(format_report(applied, targets, dry=False))
        print("\nDone. Restart your agent(s) to pick up the new server.")
        return 0

    if args.command == "uninstall":
        try:
            targets = resolve_targets(args.agents)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        preview = uninstall(repo, targets, dry=True)
        print(f"repo-graph uninstall -> {repo}")
        print(format_report(preview, targets, dry=True))
        if args.dry_run:
            return 0
        if not _confirm(args.yes):
            print("Aborted.")
            return 1
        applied = uninstall(repo, targets, dry=False)
        print(format_report(applied, targets, dry=False))
        return 0

    parser.print_help()
    return 1
