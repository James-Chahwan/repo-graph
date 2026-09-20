#!/usr/bin/env python3
"""Fresh-machine install matrix for repo-graph.

Simulates a clean machine (isolated HOME, a fresh sample repo) and drives the
install flow end to end: run `repo-graph install --agents all`, assert every
agent's config AND instructions file were written correctly, build the graph on
the sample repo, run a real `orient` query, then `repo-graph uninstall` and assert
it all reversed. Prints a PASS/FAIL line per check and exits non-zero on any
failure, so `docker run` (or CI) gives a single clear signal.

Runs anywhere the package is importable — no Docker required — which is why it's
also the payload of docker/Dockerfile.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import tomllib
from pathlib import Path

RESULTS: list[tuple[bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((ok, name))
    mark = "PASS" if ok else "FAIL"
    line = f"[{mark}] {name}"
    if detail and not ok:
        line += f"  -- {detail}"
    print(line, flush=True)


def _run(args: list[str], env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(args, env=env, capture_output=True, text=True)


def mcp_handshake(cmd: list[str], env: dict, timeout: int = 180) -> tuple[bool, str]:
    """initialize → initialized → tools/list → tools/call orient over stdio.
    True only if the server lists the 6 tools and orient returns an overview."""
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "install-matrix", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "orient", "arguments": {}}},
    ]
    stdin = "".join(json.dumps(m) + "\n" for m in msgs)
    try:
        # Own process group: `uvx` is a launcher, so killing just it leaves the
        # real server as a grandchild holding stdout open and the read below
        # blocks forever (CI hung 6h until GitHub's limit, 2026-09-15).
        p = subprocess.Popen(cmd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, start_new_session=True)
    except OSError as e:
        return False, str(e)
    def kill_tree() -> None:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            p.kill()

    killer = threading.Timer(timeout, kill_tree)  # a hung server can't wedge CI
    killer.start()
    p.stdin.write(stdin)
    p.stdin.flush()
    replies: dict[int, dict] = {}
    try:
        for line in p.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if "id" in msg:
                replies[msg["id"]] = msg
            if 3 in replies:
                break
    finally:
        killer.cancel()
        kill_tree()
        try:
            err = p.stderr.read()[-400:]
        except OSError:
            err = ""
    tools = {t["name"] for t in replies.get(2, {}).get("result", {}).get("tools", [])}
    text = "".join(c.get("text", "") for c in replies.get(3, {}).get("result", {}).get("content", []))
    want = {"orient", "find", "impact", "trace", "read", "refresh"}
    if tools != want:
        return False, f"tools={sorted(tools)} stderr={err}"
    if "nodes" not in text.lower():
        return False, f"orient={text[:200]!r} stderr={err}"
    return True, ""


def _write_sample(repo: Path) -> None:
    (repo / "app").mkdir(parents=True, exist_ok=True)
    (repo / "app" / "main.py").write_text(
        "def handler(req):\n    return db_lookup(req.id)\n\n"
        "def db_lookup(x):\n    return {'id': x}\n"
    )
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "sample"\nversion = "0.0.0"\n'
    )
    (repo / "go.mod").write_text("module sample\n\ngo 1.21\n")
    (repo / "svc.go").write_text(
        "package main\n\nfunc GetUser(id string) string {\n\treturn id\n}\n"
    )


# Per-agent files we expect after `install --agents all` (project scope), and the
# check that the entry/marker actually landed. HOME-scoped ones use $HOME.
def _expected_project(repo: Path) -> list[tuple[str, Path, callable]]:
    def has_mcp(key):
        return lambda p: "repo-graph" in json.loads(p.read_text()).get(key, {})

    def has_marker(p):
        return "repo-graph:start" in p.read_text()

    def toml_has(p):
        return "repo-graph" in tomllib.loads(p.read_text()).get("mcp_servers", {})

    return [
        ("claude-code config", repo / ".mcp.json", has_mcp("mcpServers")),
        ("claude-code CLAUDE.md", repo / "CLAUDE.md", has_marker),
        ("claude-code perms", repo / ".claude/settings.json",
         lambda p: "mcp__repo-graph__*" in json.loads(p.read_text())["permissions"]["allow"]),
        ("cursor config", repo / ".cursor/mcp.json", has_mcp("mcpServers")),
        ("cursor .mdc rule", repo / ".cursor/rules/repo-graph.mdc", has_marker),
        ("vscode config (servers key)", repo / ".vscode/mcp.json", has_mcp("servers")),
        ("vscode instructions", repo / ".github/copilot-instructions.md", has_marker),
        ("codex config (toml)", repo / ".codex/config.toml", toml_has),
        ("codex AGENTS.md", repo / "AGENTS.md", has_marker),
        ("gemini config", repo / ".gemini/settings.json", has_mcp("mcpServers")),
        ("gemini GEMINI.md", repo / "GEMINI.md", has_marker),
        ("opencode config (mcp key)", repo / "opencode.json", has_mcp("mcp")),
        ("kiro config", repo / ".kiro/settings/mcp.json", has_mcp("mcpServers")),
        ("kiro steering", repo / ".kiro/steering/repo-graph.md", has_marker),
    ]


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="rg-matrix-"))
    home = tmp / "home"
    home.mkdir()
    repo = tmp / "sample"
    repo.mkdir()
    _write_sample(repo)

    env = dict(os.environ)
    # Keep user-site importable when running against a local (editable/user) install:
    # user-site is derived from HOME, which we're about to redirect. Pinning
    # PYTHONUSERBASE decouples package discovery from the sandbox HOME. Harmless in
    # a container where the package is installed system-wide.
    real_home = os.environ.get("HOME") or os.path.expanduser("~")
    env.setdefault("PYTHONUSERBASE", str(Path(real_home) / ".local"))
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["REPO_GRAPH_WATCH"] = "0"

    # 1) console script resolves
    which = _run(["repo-graph", "--help"], env)
    check("`repo-graph` console script resolves", which.returncode == 0, which.stderr[:200])

    # 2) install --agents all
    inst = _run(["repo-graph", "install", "--agents", "all", "--repo", str(repo), "--yes"], env)
    check("`repo-graph install --agents all` exits 0", inst.returncode == 0, inst.stderr[:300])

    # 3) every agent's config + instructions written
    for name, path, verify in _expected_project(repo):
        ok = path.is_file()
        if ok:
            try:
                ok = bool(verify(path))
            except Exception as e:  # noqa: BLE001
                ok = False
                check(name, False, f"verify raised: {e}")
                continue
        check(name, ok, f"missing/invalid: {path}")

    # HOME-scoped (user-only) targets
    cd = home / ".config/Claude/claude_desktop_config.json"
    check("claude-desktop config (user, absolute repo)",
          cd.is_file() and json.loads(cd.read_text())["mcpServers"]["repo-graph"]["args"][-1] == str(repo),
          f"missing/invalid: {cd}")
    ws = home / ".codeium/windsurf/mcp_config.json"
    check("windsurf config (user)", ws.is_file() and "repo-graph" in json.loads(ws.read_text())["mcpServers"],
          f"missing/invalid: {ws}")

    # 4) idempotent re-install
    again = _run(["repo-graph", "install", "--agents", "all", "--repo", str(repo), "--yes"], env)
    check("re-install is idempotent (no error)", again.returncode == 0 and "could not be written" not in again.stdout,
          again.stdout[-300:])

    # 5) build the graph + run a real query
    gen = _run(["repo-graph-init", "--repo", str(repo), "--graph-only"], env)
    gmap = repo / ".glia/graph"
    check("graph builds + caches (.glia/graph)", gen.returncode == 0 and gmap.is_dir(), gen.stderr[:300])

    # Real MCP over stdio through the installed console script — what an agent
    # actually launches. Catches import-time breaks (e.g. an incompatible `mcp`
    # SDK) that config-file checks and in-process calls never see.
    ok, detail = mcp_handshake(["repo-graph", "--repo", str(repo)], dict(env, REPO_GRAPH_WATCH="0"))
    check("MCP stdio handshake + `orient` over the installed server", ok, detail)

    # 6) uninstall reverses everything
    un = _run(["repo-graph", "uninstall", "--agents", "all", "--repo", str(repo), "--yes"], env)
    check("`repo-graph uninstall` exits 0", un.returncode == 0, un.stderr[:300])
    check("uninstall removed all agent entries",
          not any(_still_has_repo_graph(p) for _, p, _ in _expected_project(repo)),
          "leftovers: " + ", ".join(str(p) for _, p, _ in _expected_project(repo) if _still_has_repo_graph(p)))

    passed = sum(1 for ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n{'=' * 48}\n{passed}/{total} checks passed\n{'=' * 48}", flush=True)
    return 0 if passed == total else 1


def _safe_read(p: Path) -> str:
    try:
        return p.read_text()
    except OSError:
        return ""


def _still_has_repo_graph(p: Path) -> bool:
    if not p.is_file():
        return False
    txt = _safe_read(p)
    return "repo-graph:start" in txt or '"repo-graph"' in txt or "[mcp_servers.repo-graph]" in txt


def published() -> int:
    """What a new user gets today: `uvx mcp-repo-graph` straight from PyPI, with
    whatever dependency versions resolve right now. Run on a schedule so an
    upstream release that breaks the published package (mcp 2.0, 2026-07-28)
    goes red within a day instead of two months."""
    repo = Path(tempfile.mkdtemp(prefix="rg-published-")) / "sample"
    repo.mkdir()
    _write_sample(repo)
    env = dict(os.environ, REPO_GRAPH_WATCH="0")
    ok, detail = mcp_handshake(["uvx", "--no-cache", "mcp-repo-graph", "--repo", str(repo)], env)
    check("published `uvx mcp-repo-graph`: MCP handshake + `orient`", ok, detail)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(published() if "--published" in sys.argv else main())
