"""Shared pytest fixtures for 0.3.0 smoke tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def py_smoke_repo(tmp_path: Path) -> Path:
    """Copy tests/fixtures/py_smoke/ to tmp_path so the analyzer sees it
    without the '/tests/' skip rule tripping."""
    src = FIXTURES_DIR / "py_smoke"
    dst = tmp_path / "py_smoke"
    shutil.copytree(src, dst)
    return dst
