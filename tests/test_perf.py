"""Performance gates for the engine + Python wrapper.

Opt-in: `pytest -m perf`. Default `pytest` runs skip these so the dev loop
stays fast.

These are regression gates, not microbenchmarks — generous budgets so they
don't flake on shared hardware. Tighten when meaningful.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import repo_graph_py


FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Per-fixture generate budget (seconds). All fixtures are tiny — anything
# over a second on this hardware indicates a real regression.
GENERATE_BUDGET_S = 2.0
DENSE_TEXT_BUDGET_S = 0.5


@pytest.mark.perf
@pytest.mark.parametrize("fixture_name", ["py_smoke", "go_smoke", "ts_smoke", "http_stack_smoke"])
def test_generate_under_budget(fixture_name, tmp_path):
    import shutil

    src = FIXTURES_DIR / fixture_name
    dst = tmp_path / fixture_name
    shutil.copytree(src, dst)

    t0 = time.perf_counter()
    pg = repo_graph_py.generate(str(dst))
    dt = time.perf_counter() - t0

    assert pg.node_count() > 0, f"{fixture_name}: generate produced zero nodes"
    assert dt < GENERATE_BUDGET_S, (
        f"{fixture_name}: generate took {dt:.2f}s "
        f"(budget {GENERATE_BUDGET_S}s, {pg.node_count()} nodes)"
    )


@pytest.mark.perf
def test_dense_text_under_budget(http_stack_graph):
    pg, _ = http_stack_graph

    t0 = time.perf_counter()
    text = pg.dense_text()
    dt = time.perf_counter() - t0

    assert text, "dense_text returned empty"
    assert dt < DENSE_TEXT_BUDGET_S, (
        f"dense_text took {dt:.2f}s (budget {DENSE_TEXT_BUDGET_S}s)"
    )


@pytest.mark.perf
def test_activate_under_budget(http_stack_graph):
    """PPR activation should stay snappy on small fixtures."""
    pg, _ = http_stack_graph

    # Find any real node id to seed from
    nodes = pg.nodes_json()
    import json as _json
    parsed = _json.loads(nodes) if isinstance(nodes, str) else nodes
    if not parsed:
        pytest.skip("fixture has no nodes")
    seed_id = parsed[0]["id"]

    t0 = time.perf_counter()
    scores = pg.activate([seed_id], 20)
    dt = time.perf_counter() - t0

    assert dt < 0.5, f"activate took {dt:.2f}s (budget 0.5s)"
    assert len(scores) > 0
