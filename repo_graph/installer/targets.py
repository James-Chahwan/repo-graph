"""Per-agent install targets.

Each agent is a `Target` that knows how to: detect whether it's installed, write
its MCP-server config in that agent's native format/location/wrapper-key, inject
the marker-fenced usage block into its instructions file, and set auto-allow
permissions. Every action is reversible (uninstall) and idempotent (re-running
install is a no-op). The generic `Target` handles the common case — JSON under a
`mcpServers` key, a markdown instructions file, no separate permissions file —
and subclasses override only the parts that differ.

Paths and wrapper keys were verified against official 2026 docs; see
`reference_mcp_client_configs` in memory for the full citation table.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .constants import SERVER_NAME, PACKAGE, TOOL_NAMES, instructions_block
from .fileio import (
    load_json,
    write_json,
    load_toml,
    render_toml_table,
    remove_toml_table,
)
from .markers import upsert_section, remove_section


@dataclass
class Change:
    """One thing the installer did (or would do) to one file."""

    target: str
    kind: str  # "mcp" | "instructions" | "permissions"
    path: str
    action: str  # created | updated | unchanged | removed | not-found


# ── shared helpers ────────────────────────────────────────────────────────────


def _uvx(eff_scope: str) -> str:
    """`uvx` launch command. User/global configs get an absolute path because GUI
    apps (Cursor, VS Code, Claude Desktop, Windsurf) launch with a stripped PATH;
    project configs stay portable with a bare `uvx` for teammates."""
    if eff_scope == "user":
        return shutil.which("uvx") or "uvx"
    return "uvx"


def _repo_arg(repo_abs: str, eff_scope: str) -> str:
    """`--repo` value: portable `.` at project scope, absolute path at user scope
    (a global config has no notion of the current project)."""
    return "." if eff_scope == "project" else repo_abs


def _pick(scope: str, project: Path | None, user: Path | None) -> tuple[Path | None, str]:
    """Choose the config path for the requested scope, falling back to whichever
    scope the target actually supports. Returns (path, effective_scope)."""
    if scope == "project" and project:
        return project, "project"
    if scope == "user" and user:
        return user, "user"
    if project:
        return project, "project"
    if user:
        return user, "user"
    return None, ""


def _both(project: Path | None, user: Path | None) -> list[Path]:
    """Both concrete scope paths a target supports (for uninstall sweeps)."""
    return [p for p in (project, user) if p is not None]


def _is_effectively_empty(content: str) -> bool:
    """True if `content` has nothing but whitespace and a YAML frontmatter block —
    used to delete instruction files repo-graph fully owns after its block is
    stripped."""
    body = content.strip()
    if not body:
        return True
    if body.startswith("---"):
        end = body.find("---", 3)
        if end != -1:
            body = body[end + 3:].strip()
    return not body


def _write_or_unlink_json(path: Path, data: dict) -> None:
    """Write `data`, or delete the file if `data` is now empty — so removing our
    only entry from a config we created leaves no empty ``{}`` behind. A config
    with the user's other content is never deleted, only rewritten."""
    if not data:
        path.unlink(missing_ok=True)
    else:
        write_json(path, data)


# ── base target ───────────────────────────────────────────────────────────────


class Target:
    id: str = ""
    label: str = ""
    config_key: str = "mcpServers"
    entry_type: str | None = None  # "type" field in the MCP entry (VS Code: stdio)
    command_array: bool = False  # opencode: command is one [exe, *args] array
    has_instructions: bool = True
    instr_frontmatter: str | None = None  # Cursor .mdc
    instr_owned: bool = False  # dedicated file repo-graph created (delete if empty)

    # detection knobs
    detect_bins: tuple[str, ...] = ()
    detect_paths: tuple[Path, ...] = ()

    # ── detection ──
    def detect(self) -> bool:
        if any(shutil.which(b) for b in self.detect_bins):
            return True
        return any(p.exists() for p in self.detect_paths)

    # ── path resolution (overridden per target) ──
    def _mcp_project(self, repo: Path) -> Path | None:
        return None

    def _mcp_user(self, repo: Path) -> Path | None:
        return None

    def _instr_project(self, repo: Path) -> Path | None:
        return None

    def _instr_user(self, repo: Path) -> Path | None:
        return None

    # ── MCP entry ──
    def entry_permission_fields(self, permissions: bool) -> dict:
        """Auto-allow fields that live *inside* the server entry (Gemini trust,
        Windsurf alwaysAllow, Kiro autoApprove). Default: none."""
        return {}

    def build_entry(self, repo_abs: str, eff_scope: str, permissions: bool) -> dict:
        args = [PACKAGE, "--repo", _repo_arg(repo_abs, eff_scope)]
        if self.command_array:
            entry: dict = {"type": "local", "command": [_uvx(eff_scope)] + args, "enabled": True}
        else:
            entry = {"command": _uvx(eff_scope), "args": args}
            if self.entry_type:
                entry = {"type": self.entry_type, **entry}
        entry.update(self.entry_permission_fields(permissions))
        return entry

    # ── MCP config write/remove (generic JSON) ──
    def write_mcp(self, repo: Path, scope: str, permissions: bool, dry: bool) -> list[Change]:
        path, eff = _pick(scope, self._mcp_project(repo), self._mcp_user(repo))
        if not path:
            return []
        data = load_json(path)
        existing = data.get(self.config_key, {}).get(SERVER_NAME) if isinstance(data.get(self.config_key), dict) else None
        entry = self.build_entry(str(repo), eff, permissions)
        action = "unchanged" if existing == entry else ("updated" if existing else "created")
        if not dry and action != "unchanged":
            data.setdefault(self.config_key, {})[SERVER_NAME] = entry
            write_json(path, data)
        return [Change(self.id, "mcp", str(path), action)]

    def remove_mcp(self, repo: Path, dry: bool) -> list[Change]:
        changes: list[Change] = []
        for path in _both(self._mcp_project(repo), self._mcp_user(repo)):
            data = load_json(path)
            servers = data.get(self.config_key)
            if isinstance(servers, dict) and SERVER_NAME in servers:
                if not dry:
                    del servers[SERVER_NAME]
                    if not servers:
                        data.pop(self.config_key, None)
                    _write_or_unlink_json(path, data)
                changes.append(Change(self.id, "mcp", str(path), "removed"))
        return changes

    # ── instructions write/remove (generic markdown) ──
    def write_instructions(self, repo: Path, scope: str, dry: bool) -> list[Change]:
        if not self.has_instructions:
            return []
        path, _ = _pick(scope, self._instr_project(repo), self._instr_user(repo))
        if not path:
            return []
        content = path.read_text(encoding="utf-8") if path.is_file() else ""
        if not content and self.instr_frontmatter:
            content = self.instr_frontmatter + "\n"
        new, status = upsert_section(content, instructions_block())
        if not dry and status != "unchanged":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(new, encoding="utf-8")
        return [Change(self.id, "instructions", str(path), status)]

    def remove_instructions(self, repo: Path, dry: bool) -> list[Change]:
        if not self.has_instructions:
            return []
        changes: list[Change] = []
        for path in _both(self._instr_project(repo), self._instr_user(repo)):
            if not path.is_file():
                continue
            content = path.read_text(encoding="utf-8")
            new, status = remove_section(content)
            if status == "not-found":
                continue
            if not dry:
                # Delete the file if nothing of the user's is left (only our block
                # and, for owned .mdc files, YAML frontmatter). Otherwise rewrite.
                if _is_effectively_empty(new):
                    path.unlink()
                else:
                    path.write_text(new, encoding="utf-8")
            changes.append(Change(self.id, "instructions", str(path), "removed"))
        return changes

    # ── permissions (default no-op; relies on read-only tool hints) ──
    def write_permissions(self, repo: Path, scope: str, dry: bool) -> list[Change]:
        return []

    def remove_permissions(self, repo: Path, dry: bool) -> list[Change]:
        return []


# ── platform path helpers ─────────────────────────────────────────────────────


def _home() -> Path:
    return Path.home()


def _claude_desktop_config() -> Path:
    if sys.platform == "darwin":
        return _home() / "Library/Application Support/Claude/claude_desktop_config.json"
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", _home())) / "Claude/claude_desktop_config.json"
    return _home() / ".config/Claude/claude_desktop_config.json"  # unofficial on Linux


def _vscode_user_dir() -> Path:
    if sys.platform == "darwin":
        return _home() / "Library/Application Support/Code/User"
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", _home())) / "Code/User"
    return _home() / ".config/Code/User"


# ── concrete targets ──────────────────────────────────────────────────────────


class ClaudeCode(Target):
    id = "claude-code"
    label = "Claude Code"
    detect_bins = ("claude",)

    @property
    def detect_paths(self):  # type: ignore[override]
        return (_home() / ".claude", _home() / ".claude.json")

    def _mcp_project(self, repo):
        return repo / ".mcp.json"

    def _mcp_user(self, repo):
        return _home() / ".claude.json"

    def _instr_project(self, repo):
        return repo / "CLAUDE.md"

    def _instr_user(self, repo):
        return _home() / ".claude/CLAUDE.md"

    def _settings(self, repo, scope):
        return repo / ".claude/settings.json" if scope == "project" else _home() / ".claude/settings.json"

    def write_permissions(self, repo, scope, dry):
        path = self._settings(repo, scope if scope in ("project", "user") else "project")
        data = load_json(path)
        perms = data.setdefault("permissions", {}) if not dry else dict(data.get("permissions", {}))
        allow = list(perms.get("allow", []))
        rule = f"mcp__{SERVER_NAME}__*"
        if rule in allow:
            return [Change(self.id, "permissions", str(path), "unchanged")]
        if not dry:
            data.setdefault("permissions", {}).setdefault("allow", [])
            data["permissions"]["allow"].append(rule)
            write_json(path, data)
        return [Change(self.id, "permissions", str(path), "created")]

    def remove_permissions(self, repo, dry):
        changes = []
        rule = f"mcp__{SERVER_NAME}__*"
        for path in (_home() / ".claude/settings.json", repo / ".claude/settings.json"):
            data = load_json(path)
            allow = data.get("permissions", {}).get("allow") if isinstance(data.get("permissions"), dict) else None
            if isinstance(allow, list) and rule in allow:
                if not dry:
                    allow.remove(rule)
                    write_json(path, data)
                changes.append(Change(self.id, "permissions", str(path), "removed"))
        return changes


class ClaudeDesktop(Target):
    id = "claude-desktop"
    label = "Claude Desktop"
    has_instructions = False  # Desktop reads no repo instructions file

    @property
    def detect_paths(self):  # type: ignore[override]
        return (_claude_desktop_config().parent,)

    def _mcp_user(self, repo):
        return _claude_desktop_config()  # global only; forces absolute --repo


class Cursor(Target):
    id = "cursor"
    label = "Cursor"
    detect_bins = ("cursor",)
    instr_owned = True
    instr_frontmatter = "---\ndescription: repo-graph structural map usage\nalwaysApply: true\n---"

    @property
    def detect_paths(self):  # type: ignore[override]
        return (_home() / ".cursor",)

    def _mcp_project(self, repo):
        return repo / ".cursor/mcp.json"

    def _mcp_user(self, repo):
        return _home() / ".cursor/mcp.json"

    def _instr_project(self, repo):
        return repo / ".cursor/rules/repo-graph.mdc"  # plain .md is ignored by Cursor


class Windsurf(Target):
    id = "windsurf"
    label = "Windsurf / Devin"
    detect_bins = ("windsurf",)

    @property
    def detect_paths(self):  # type: ignore[override]
        return (_home() / ".codeium/windsurf",)

    def _mcp_user(self, repo):
        return _home() / ".codeium/windsurf/mcp_config.json"  # user-global only

    def _instr_project(self, repo):
        return repo / ".windsurf/rules/repo-graph.md"

    def _instr_user(self, repo):
        return _home() / ".codeium/windsurf/memories/global_rules.md"

    def entry_permission_fields(self, permissions):
        return {"alwaysAllow": list(TOOL_NAMES)} if permissions else {}


class VSCode(Target):
    id = "vscode"
    label = "VS Code (Copilot)"
    config_key = "servers"  # NOT mcpServers
    entry_type = "stdio"
    detect_bins = ("code",)

    @property
    def detect_paths(self):  # type: ignore[override]
        return (_vscode_user_dir(),)

    def _mcp_project(self, repo):
        return repo / ".vscode/mcp.json"

    def _mcp_user(self, repo):
        return _vscode_user_dir() / "mcp.json"

    def _instr_project(self, repo):
        return repo / ".github/copilot-instructions.md"


class Codex(Target):
    id = "codex"
    label = "Codex CLI"
    detect_bins = ("codex",)

    @property
    def detect_paths(self):  # type: ignore[override]
        return (_home() / ".codex",)

    def _instr_project(self, repo):
        return repo / "AGENTS.md"

    def _instr_user(self, repo):
        return _home() / ".codex/AGENTS.md"

    def _toml_paths(self, repo):
        return repo / ".codex/config.toml", _home() / ".codex/config.toml"

    def write_mcp(self, repo, scope, permissions, dry):
        proj, usr = self._toml_paths(repo)
        path, eff = _pick(scope, proj, usr)
        if not path:
            return []
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        data = load_toml(path)
        table = f"mcp_servers.{SERVER_NAME}"
        entry = {"command": _uvx(eff), "args": [PACKAGE, "--repo", _repo_arg(str(repo), eff)]}
        existing = data.get("mcp_servers", {}).get(SERVER_NAME)
        matches = existing is not None and existing.get("command") == entry["command"] and existing.get("args") == entry["args"]
        action = "unchanged" if matches else ("updated" if existing else "created")
        if not dry and action != "unchanged":
            if existing:
                text, _ = remove_toml_table(text, table)
            block = render_toml_table(table, entry)
            text = (text.rstrip() + "\n\n" if text.strip() else "") + block
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return [Change(self.id, "mcp", str(path), action)]

    def remove_mcp(self, repo, dry):
        changes = []
        table = f"mcp_servers.{SERVER_NAME}"
        for path in self._toml_paths(repo):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            new, removed = remove_toml_table(text, table)
            if removed:
                if not dry:
                    if new.strip():
                        path.write_text(new, encoding="utf-8")
                    else:
                        path.unlink(missing_ok=True)  # we created an otherwise-empty config.toml
                changes.append(Change(self.id, "mcp", str(path), "removed"))
        return changes


class Gemini(Target):
    id = "gemini"
    label = "Gemini CLI"
    detect_bins = ("gemini",)

    @property
    def detect_paths(self):  # type: ignore[override]
        return (_home() / ".gemini",)

    def _mcp_project(self, repo):
        return repo / ".gemini/settings.json"

    def _mcp_user(self, repo):
        return _home() / ".gemini/settings.json"

    def _instr_project(self, repo):
        return repo / "GEMINI.md"

    def _instr_user(self, repo):
        return _home() / ".gemini/GEMINI.md"

    def entry_permission_fields(self, permissions):
        return {"trust": True} if permissions else {}


class Opencode(Target):
    id = "opencode"
    label = "opencode"
    config_key = "mcp"  # NOT mcpServers
    command_array = True  # command is one [exe, *args] array
    detect_bins = ("opencode",)

    @property
    def detect_paths(self):  # type: ignore[override]
        return (_home() / ".config/opencode",)

    def _mcp_project(self, repo):
        return repo / "opencode.json"

    def _mcp_user(self, repo):
        return _home() / ".config/opencode/opencode.json"

    def _instr_project(self, repo):
        return repo / "AGENTS.md"

    def _instr_user(self, repo):
        return _home() / ".config/opencode/AGENTS.md"

    def _perm_glob(self) -> str:
        return f"{SERVER_NAME}*"  # opencode exposes MCP tools as <server>_<tool>

    def write_permissions(self, repo, scope, dry):
        path, _ = _pick(scope, self._mcp_project(repo), self._mcp_user(repo))
        if not path:
            return []
        data = load_json(path)
        perm = data.get("permission")
        glob = self._perm_glob()
        if isinstance(perm, dict) and perm.get(glob) == "allow":
            return [Change(self.id, "permissions", str(path), "unchanged")]
        if not dry:
            if not isinstance(data.get("permission"), dict):
                data["permission"] = {}
            data["permission"][glob] = "allow"
            write_json(path, data)
        return [Change(self.id, "permissions", str(path), "created")]

    def remove_permissions(self, repo, dry):
        changes = []
        glob = self._perm_glob()
        for path in _both(self._mcp_project(repo), self._mcp_user(repo)):
            data = load_json(path)
            perm = data.get("permission")
            if isinstance(perm, dict) and glob in perm:
                if not dry:
                    del perm[glob]
                    if not perm:
                        data.pop("permission", None)
                    _write_or_unlink_json(path, data)
                changes.append(Change(self.id, "permissions", str(path), "removed"))
        return changes


class Kiro(Target):
    id = "kiro"
    label = "Kiro"
    detect_bins = ("kiro",)
    instr_owned = True

    @property
    def detect_paths(self):  # type: ignore[override]
        return (_home() / ".kiro",)

    def _mcp_project(self, repo):
        return repo / ".kiro/settings/mcp.json"

    def _mcp_user(self, repo):
        return _home() / ".kiro/settings/mcp.json"

    def _instr_project(self, repo):
        return repo / ".kiro/steering/repo-graph.md"

    def _instr_user(self, repo):
        return _home() / ".kiro/steering/repo-graph.md"

    def entry_permission_fields(self, permissions):
        return {"autoApprove": ["*"]} if permissions else {}


# ── registry ──────────────────────────────────────────────────────────────────

_TARGETS: list[Target] = [
    ClaudeCode(),
    ClaudeDesktop(),
    Cursor(),
    Windsurf(),
    VSCode(),
    Codex(),
    Gemini(),
    Opencode(),
    Kiro(),
]

REGISTRY: dict[str, Target] = {t.id: t for t in _TARGETS}


def all_targets() -> list[Target]:
    return list(_TARGETS)


def detected_targets() -> list[Target]:
    return [t for t in _TARGETS if t.detect()]
