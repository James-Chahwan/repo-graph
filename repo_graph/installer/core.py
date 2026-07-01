"""`repo-graph install` / `repo-graph uninstall` — orchestration and CLI.

Resolves which agents to target, then runs each target's config write, instruction
injection, and permission grant (or their reverse). Everything is idempotent and
marker-fenced, so re-running install is a no-op and uninstall is a clean reversal.
Non-interactive by design: `--yes`, a non-TTY stdin (CI, or running inside the MCP
stdio wrapper), or `--dry-run` all skip the prompt. One target failing to write
(read-only dir, permission error) is reported and skipped, never aborting the rest.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .constants import SERVER_NAME, PACKAGE, looks_like_git_url
from .targets import (
    Change,
    Codex,
    REGISTRY,
    Target,
    all_targets,
    detected_targets,
    _pick,
    _uvx,
    _repo_arg,
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


def _dedupe(changes: list[Change]) -> list[Change]:
    """Collapse duplicate writes to the same (path, kind) — e.g. Codex and
    opencode share AGENTS.md — so a dry-run preview matches the applied result
    instead of double-counting the shared file as changed twice."""
    seen: set[tuple[str, str]] = set()
    for c in changes:
        key = (c.path, c.kind)
        if c.path and key in seen and c.action in ("created", "updated"):
            c.action = "unchanged"
        seen.add(key)
    return changes


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
        try:
            changes += t.write_mcp(repo, scope, permissions, dry)
            if instructions:
                changes += t.write_instructions(repo, scope, dry)
            if permissions:
                changes += t.write_permissions(repo, scope, dry)
        except OSError as e:
            changes.append(Change(t.id, "write", f"(error: {e})", "error"))
    return _dedupe(changes)


def uninstall(repo: Path, targets: list[Target], *, dry: bool = False) -> list[Change]:
    changes: list[Change] = []
    for t in targets:
        try:
            changes += t.remove_mcp(repo, dry)
            changes += t.remove_instructions(repo, dry)
            changes += t.remove_permissions(repo, dry)
        except OSError as e:
            changes.append(Change(t.id, "write", f"(error: {e})", "error"))
    return _dedupe(changes)


# ── reporting ─────────────────────────────────────────────────────────────────

_SYMBOL = {
    "created": "+",
    "updated": "~",
    "unchanged": "=",
    "removed": "-",
    "not-found": " ",
    "error": "!",
    "skipped": "s",
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
    errors = sum(1 for c in changes if c.action == "error")
    lines.append("")
    verb = "would change" if dry else "changed"
    lines.append(f"  {touched} file(s) {verb}.")
    if errors:
        lines.append(f"  {errors} target(s) could not be written (see ! above).")
    return "\n".join(lines)


def _print_config(agent_id: str, repo: Path) -> str:
    """Emit the exact config snippet for one agent — matching what install would
    actually write for that target's scope (user-only targets get absolute uvx +
    absolute repo, not a bare `uvx` + `.`)."""
    if agent_id not in REGISTRY:
        return f"unknown agent '{agent_id}'. Known: {', '.join(REGISTRY)}"
    t = REGISTRY[agent_id]
    if isinstance(t, Codex):
        from .fileio import render_toml_table

        _, eff = _pick("project", *t._toml_paths(repo))
        entry = {"command": _uvx(eff), "args": [PACKAGE, "--repo", _repo_arg(str(repo), eff)]}
        where = "~/.codex/config.toml" if eff == "user" else ".codex/config.toml"
        return f"# {where}\n{render_toml_table(f'mcp_servers.{SERVER_NAME}', entry)}"
    _, eff = _pick("project", t._mcp_project(repo), t._mcp_user(repo))
    entry = t.build_entry(str(repo), eff, permissions=True)
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


def _resolve_repo_arg(raw: str) -> Path | None:
    """Resolve the --repo CLI value, or None if it's a git URL (unsupported by
    the installer, which configures agents for a local checkout)."""
    if looks_like_git_url(raw):
        print(
            "error: install/uninstall operate on a local repo path. To map a "
            "remote repo, run the server directly:\n"
            "  uvx mcp-repo-graph --repo <git-url>",
            file=sys.stderr,
        )
        return None
    return Path(raw).expanduser().resolve()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    args = parser.parse_args(argv)

    repo = _resolve_repo_arg(args.repo)
    if repo is None:
        return 2

    if args.command == "install":
        if args.print_config:
            print(_print_config(args.print_config, repo))
            return 0
        if not repo.is_dir():
            print(f"error: --repo path does not exist: {repo}", file=sys.stderr)
            return 2
        try:
            targets = resolve_targets(args.agents)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        if not targets:
            print("No agents selected.")
            return 0
        kw = dict(scope=args.scope,
                  permissions=not args.no_permissions,
                  instructions=not args.no_instructions)
        print(f"repo-graph install -> {repo}")
        print(format_report(install(repo, targets, dry=True, **kw), targets, dry=True))
        if args.dry_run:
            return 0
        if not _confirm(args.yes):
            print("Aborted.")
            return 1
        print(format_report(install(repo, targets, dry=False, **kw), targets, dry=False))
        print("\nDone. Restart your agent(s) to pick up the new server.")
        return 0

    if args.command == "uninstall":
        try:
            targets = resolve_targets(args.agents)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        print(f"repo-graph uninstall -> {repo}")
        print(format_report(uninstall(repo, targets, dry=True), targets, dry=True))
        if args.dry_run:
            return 0
        if not _confirm(args.yes):
            print("Aborted.")
            return 1
        print(format_report(uninstall(repo, targets, dry=False), targets, dry=False))
        return 0

    parser.print_help()
    return 1
