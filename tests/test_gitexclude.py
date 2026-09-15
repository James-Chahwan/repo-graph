"""`.ai/repo-graph/` cache is kept out of `git status` via local `info/exclude`."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from repo_graph import gitexclude
from repo_graph.gitexclude import ensure_cache_excluded

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def git(cwd: Path, *args: str) -> str:
    res = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "protocol.file.allow=always",
         "-C", str(cwd), *args],
        capture_output=True, text=True, check=True,
    )
    return res.stdout


def make_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q")
    (path / "main.py").write_text("def main():\n    pass\n")
    git(path, "add", ".")
    git(path, "commit", "-qm", "init")
    return path


def write_cache(root: Path) -> Path:
    cache = root / ".ai" / "repo-graph"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "manifest.json").write_text("{}")
    return cache


def untracked(root: Path) -> str:
    return git(root, "status", "--porcelain", "--untracked-files=all")


@pytest.fixture(autouse=True)
def fresh_memo():
    gitexclude._done.clear()
    yield
    gitexclude._done.clear()


def test_adds_exclude_and_status_clean(tmp_path):
    repo = make_repo(tmp_path / "r")
    cache = write_cache(repo)
    assert ".ai/" in untracked(repo)

    assert ensure_cache_excluded(cache) == "added"
    assert untracked(repo) == ""
    assert "/.ai/repo-graph/" in (repo / ".git/info/exclude").read_text()


def test_idempotent(tmp_path):
    repo = make_repo(tmp_path / "r")
    cache = write_cache(repo)
    ensure_cache_excluded(cache)
    gitexclude._done.clear()  # force a re-read of the file, not the memo
    assert ensure_cache_excluded(cache) == "present"
    assert (repo / ".git/info/exclude").read_text().count("/.ai/repo-graph/") == 1


def test_target_is_subdirectory(tmp_path):
    repo = make_repo(tmp_path / "r")
    cache = write_cache(repo / "services" / "api")
    assert ensure_cache_excluded(cache) == "added"
    assert "/services/api/.ai/repo-graph/" in (repo / ".git/info/exclude").read_text()
    assert untracked(repo) == ""


def test_linked_worktree_uses_common_dir(tmp_path):
    repo = make_repo(tmp_path / "r")
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(wt))
    cache = write_cache(wt)

    assert ensure_cache_excluded(cache) == "added"
    assert untracked(wt) == ""
    assert "/.ai/repo-graph/" in (repo / ".git/info/exclude").read_text()


def test_submodule(tmp_path):
    sub_src = make_repo(tmp_path / "sub_src")
    sup = make_repo(tmp_path / "sup")
    git(sup, "submodule", "add", "-q", str(sub_src), "sub")
    git(sup, "commit", "-qm", "add sub")
    cache = write_cache(sup / "sub")
    assert "sub" in git(sup, "status", "--porcelain")

    assert ensure_cache_excluded(cache) == "added"
    assert untracked(sup / "sub") == ""
    assert git(sup, "status", "--porcelain") == ""


def test_skipped_when_precommit_hook_installed(tmp_path):
    from repo_graph.installer.githook import install_hook
    repo = make_repo(tmp_path / "r")
    install_hook(repo)
    cache = write_cache(repo)

    assert ensure_cache_excluded(cache) == "skipped-hook"
    assert ".ai/" in untracked(repo)


def test_hook_still_stages_cache_after_exclude(tmp_path):
    """Hook installed after the exclude was written: its `git add -f` must win."""
    repo = make_repo(tmp_path / "r")
    cache = write_cache(repo)
    ensure_cache_excluded(cache)
    git(repo, "add", "-f", ".ai/repo-graph")
    assert ".ai/repo-graph/manifest.json" in git(repo, "diff", "--cached", "--name-only")


def test_skipped_when_cache_already_tracked(tmp_path):
    repo = make_repo(tmp_path / "r")
    cache = write_cache(repo)
    git(repo, "add", ".ai")
    git(repo, "commit", "-qm", "commit cache")

    assert ensure_cache_excluded(cache) == "skipped-tracked"
    assert not (repo / ".git/info/exclude").is_file() or \
        "/.ai/repo-graph/" not in (repo / ".git/info/exclude").read_text()


def test_no_git(tmp_path):
    cache = write_cache(tmp_path / "plain")
    assert ensure_cache_excluded(cache) == "no-git"


def test_build_graph_leaves_status_clean(tmp_path, monkeypatch):
    from repo_graph import server
    repo = tmp_path / "target"
    shutil.copytree(FIXTURES_DIR / "http_stack_smoke", repo)
    make_repo(repo)
    monkeypatch.setattr(server, "REPO_PATH", str(repo))
    monkeypatch.setattr(server, "_graph", None)

    server._build_graph(str(repo))

    assert (repo / ".ai" / "repo-graph").is_dir()
    assert untracked(repo) == ""
