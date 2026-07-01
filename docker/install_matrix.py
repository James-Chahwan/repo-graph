#!/usr/bin/env python3
"""Fresh-machine install matrix for repo-graph.

Simulates a clean machine (isolated HOME, a fresh sample repo) and drives the
install flow end to end: run `repo-graph install --agents all`, assert every
agent's config AND instructions file were written correctly, build the graph on
the sample repo, run a real `status` query, then `repo-graph uninstall` and assert
it all reversed. Prints a PASS/FAIL line per check and exits non-zero on any
failure, so `docker run` (or CI) gives a single clear signal.

Runs anywhere the package is importable — no Docker required — which is why it's
also the payload of docker/Dockerfile.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
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
    gmap = repo / ".ai/repo-graph"
    check("graph builds + caches (.ai/repo-graph)", gen.returncode == 0 and gmap.is_dir(), gen.stderr[:300])

    query_ok = False
    detail = ""
    try:
        env_q = dict(env, REPO_GRAPH_REPO=str(repo))
        code = (
            "import os; os.environ['REPO_GRAPH_WATCH']='0';"
            "import repo_graph.server as s;"
            "out=s.status();"
            "print('NODES_OK' if 'nodes' in out.lower() else 'NO')"
        )
        q = subprocess.run([sys.executable, "-c", code], env=env_q, capture_output=True, text=True)
        query_ok = "NODES_OK" in q.stdout
        detail = (q.stdout + q.stderr)[-300:]
    except Exception as e:  # noqa: BLE001
        detail = str(e)
    check("`status` query returns a repo overview", query_ok, detail)

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


if __name__ == "__main__":
    sys.exit(main())
