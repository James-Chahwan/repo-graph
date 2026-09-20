"""End-to-end MCP protocol tests.

Spawns the `repo-graph` server as a subprocess, connects via stdio, and
exercises each tool over the actual MCP wire protocol — JSON-RPC, content
blocks, the whole thing. Asserts the response shapes an MCP client (Claude
Code, Cursor, etc.) would actually see.

These differ from `test_mcp_tools.py` (which calls the @mcp.tool functions
directly) by going through:
  - server startup (`repo-graph --repo ...`)
  - stdio transport
  - JSON-RPC framing
  - FastMCP request routing
  - content-block serialization

If a tool's docstring, schema, or return type ever breaks the MCP contract,
these tests catch it before users do.

Marked `e2e` — opt out with `-m "not e2e"` if you don't want subprocess spin-up
in the default loop.
"""

from __future__ import annotations

import shutil
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


pytestmark = pytest.mark.e2e


FIXTURES_DIR = Path(__file__).parent / "fixtures"

EXPECTED_TOOLS = {"orient", "find", "impact", "trace", "read", "refresh"}


@pytest.fixture(scope="module")
def target_repo(tmp_path_factory):
    """Module-scoped fixture: one repo for all e2e tests so we pay server
    startup once."""
    src = FIXTURES_DIR / "http_stack_smoke"
    dst = tmp_path_factory.mktemp("e2e") / "target"
    shutil.copytree(src, dst)
    return dst


def _console_script() -> str:
    """The `repo-graph` console script belonging to the interpreter running the
    tests.

    Plain `"repo-graph"` resolves through PATH, which can be some other
    environment's install — the suite then silently tests a binary that isn't the
    code under test. Prefer the script next to `sys.executable`, and fall back to
    PATH only when there isn't one (an unusual install layout)."""
    candidate = Path(sys.executable).parent / "repo-graph"
    return str(candidate) if candidate.exists() else "repo-graph"


@asynccontextmanager
async def _connect(target_repo: Path):
    """Spawn `repo-graph --repo <target>` and yield an initialized session."""
    params = StdioServerParameters(
        command=_console_script(),
        args=["--repo", str(target_repo)],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


# ── Protocol layer ──────────────────────────────────────────────────────────


async def test_initialize_and_list_tools(target_repo):
    """Server handshakes and advertises exactly the 6 tools with schemas."""
    async with _connect(target_repo) as session:
        result = await session.list_tools()

        names = {t.name for t in result.tools}
        assert names == EXPECTED_TOOLS, (
            f"tool surface mismatch over MCP: "
            f"missing={EXPECTED_TOOLS - names}, extra={names - EXPECTED_TOOLS}"
        )

        # Every tool must have a description (FastMCP pulls from docstring)
        # and a JSON-schema for inputs
        for tool in result.tools:
            assert tool.description, f"tool {tool.name!r} missing description"
            assert tool.input_schema, f"tool {tool.name!r} missing input schema"
            assert tool.input_schema.get("type") == "object"


# ── Content-shape contract ──────────────────────────────────────────────────


def _text(result) -> str:
    """Pull the concatenated text out of a CallToolResult."""
    assert not result.is_error, f"tool returned error: {result}"
    parts = []
    for block in result.content:
        # MCP content blocks are tagged unions; text blocks have .text
        if hasattr(block, "text"):
            parts.append(block.text)
    return "\n".join(parts)


async def test_orient_over_wire(target_repo):
    async with _connect(target_repo) as session:
        body = _text(await session.call_tool("orient", {}))
        assert "repo-graph" in body
        assert "Engine:" in body
        assert "Node kinds:" in body


async def test_orient_full_map_over_wire(target_repo):
    async with _connect(target_repo) as session:
        body = _text(await session.call_tool("orient", {"full": True}))
        assert body, "orient full map returned empty"
        assert len(body) > 50


async def test_find_known_over_wire(target_repo):
    async with _connect(target_repo) as session:
        result = await session.call_tool("find", {"query": "User"})
        body = _text(result)
        # Either matches or politely says no matches — both are valid wire-shape
        assert "matching" in body or "No nodes matched" in body


async def test_find_unknown_over_wire(target_repo):
    async with _connect(target_repo) as session:
        result = await session.call_tool("find", {"query": "zzz_no_such_thing_xxx"})
        body = _text(result)
        # glia 0.5.0: an empty answer is the engine's `absence` envelope (LD.8a),
        # carrying the reason and its FACT/HEURISTIC tier.
        assert "No answer" in body and "no_match" in body


async def test_find_expand_over_wire(target_repo):
    async with _connect(target_repo) as session:
        find_body = _text(await session.call_tool("find", {"query": "User"}))
        if "No nodes matched" in find_body:
            pytest.skip("fixture had no symbol matching 'User'")
        result = await session.call_tool("find", {"query": "User", "expand": True, "top_k": 5})
        body = _text(result)
        assert "expanded" in body or "relevant" in body or "No nodes matched" in body


async def test_impact_unknown_over_wire(target_repo):
    async with _connect(target_repo) as session:
        result = await session.call_tool("impact", {"nodes": "xxx_unknown_xxx"})
        body = _text(result)
        assert "No answer" in body and "unknown_symbol" in body


async def test_trace_feature_unknown_over_wire(target_repo):
    async with _connect(target_repo) as session:
        result = await session.call_tool("trace", {"from_node": "definitely_not_a_real_feature"})
        body = _text(result)
        assert "No answer" in body or "Trace:" in body or "Flow:" in body


async def test_trace_path_unknown_over_wire(target_repo):
    async with _connect(target_repo) as session:
        result = await session.call_tool(
            "trace", {"from_node": "xxx_bogus", "to_node": "yyy_bogus"}
        )
        body = _text(result)
        assert "Node not found" in body


async def test_refresh_over_wire(target_repo):
    async with _connect(target_repo) as session:
        result = await session.call_tool("refresh", {})
        body = _text(result)
        assert body.startswith("Rebuilt")


# ── Cross-call invariants ───────────────────────────────────────────────────


async def test_orient_and_refresh_agree_on_engine_version(target_repo):
    """Both surfaces must report the same engine version — drift here would
    mean orient renders a stale cached value somewhere."""
    async with _connect(target_repo) as session:
        orient_body = _text(await session.call_tool("orient", {}))
        import re
        m = re.search(r"glia-py (\S+)", orient_body)
        assert m, f"orient did not advertise an engine version: {orient_body[:200]}"
        version = m.group(1)
        refresh_body = _text(await session.call_tool("refresh", {}))
        assert version in refresh_body, (
            f"version drift across tools: orient says {version!r}, "
            f"refresh says: {refresh_body[-200:]}"
        )


async def test_all_tools_callable_no_errors(target_repo):
    """Smoke loop: every tool can be invoked over the wire with sensible args
    and returns isError=False. Catches schema validation or routing breakage."""
    async with _connect(target_repo) as session:
        # Warm the graph
        await session.call_tool("orient", {})

        # Per-tool minimal args. trace/impact need a real node; we pass a
        # clearly-unknown one — they should return "Node not found"/"No nodes
        # found" as DATA, not a protocol error.
        invocations = [
            ("orient", {}),
            ("orient", {"full": True}),
            ("find", {"query": "x"}),
            ("find", {"query": "x", "expand": True}),
            ("impact", {"nodes": "x"}),
            ("trace", {"from_node": "x"}),
            ("trace", {"from_node": "x", "to_node": "y"}),
            ("read", {"node": "x"}),
            ("refresh", {}),
        ]

        for name, args in invocations:
            result = await session.call_tool(name, args)
            assert not result.is_error, f"{name}({args}) returned is_error=True: {result}"
            # Every tool must return at least one content block
            assert result.content, f"{name}({args}) returned no content"
