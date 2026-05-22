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
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


pytestmark = pytest.mark.e2e


FIXTURES_DIR = Path(__file__).parent / "fixtures"

EXPECTED_TOOLS = {
    "generate", "status", "dense_text", "flow", "trace",
    "impact", "neighbours", "activate", "find",
    "graph_view", "reload",
}


@pytest.fixture(scope="module")
def target_repo(tmp_path_factory):
    """Module-scoped fixture: one repo for all e2e tests so we pay server
    startup once."""
    src = FIXTURES_DIR / "http_stack_smoke"
    dst = tmp_path_factory.mktemp("e2e") / "target"
    shutil.copytree(src, dst)
    return dst


@asynccontextmanager
async def _connect(target_repo: Path):
    """Spawn `repo-graph --repo <target>` and yield an initialized session."""
    params = StdioServerParameters(
        command="repo-graph",
        args=["--repo", str(target_repo)],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


# ── Protocol layer ──────────────────────────────────────────────────────────


async def test_initialize_and_list_tools(target_repo):
    """Server handshakes and advertises the expected 11 tools with schemas."""
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
            assert tool.inputSchema, f"tool {tool.name!r} missing input schema"
            assert tool.inputSchema.get("type") == "object"


# ── Content-shape contract ──────────────────────────────────────────────────


def _text(result) -> str:
    """Pull the concatenated text out of a CallToolResult."""
    assert not result.isError, f"tool returned error: {result}"
    parts = []
    for block in result.content:
        # MCP content blocks are tagged unions; text blocks have .text
        if hasattr(block, "text"):
            parts.append(block.text)
    return "\n".join(parts)


async def test_status_over_wire(target_repo):
    async with _connect(target_repo) as session:
        result = await session.call_tool("status", {})
        body = _text(result)
        assert "repo-graph" in body
        assert "Engine:" in body
        assert "Node kinds:" in body


async def test_dense_text_over_wire(target_repo):
    async with _connect(target_repo) as session:
        result = await session.call_tool("dense_text", {})
        body = _text(result)
        assert body, "dense_text returned empty"
        # Sigil notation header from projection-text crate
        assert len(body) > 50


async def test_find_known_over_wire(target_repo):
    async with _connect(target_repo) as session:
        # First, get a real node name via status
        status_body = _text(await session.call_tool("status", {}))
        # Pick a node by querying find with a common partial.
        # http_stack_smoke has a "server" file → likely "main" or "Server" symbols
        result = await session.call_tool("find", {"query": "User"})
        body = _text(result)
        # Either matches or politely says no matches — both are valid wire-shape
        assert "Found" in body or "No nodes found" in body


async def test_find_unknown_over_wire(target_repo):
    async with _connect(target_repo) as session:
        result = await session.call_tool("find", {"query": "zzz_no_such_thing_xxx"})
        body = _text(result)
        assert "No nodes found" in body


async def test_activate_over_wire(target_repo):
    async with _connect(target_repo) as session:
        # Find a real symbol first
        find_body = _text(await session.call_tool("find", {"query": "User"}))
        if "No nodes found" in find_body:
            pytest.skip("fixture had no symbol matching 'User'")

        result = await session.call_tool("activate", {"seeds": "User", "top_k": 5})
        body = _text(result)
        assert "Activation from" in body or "No seed nodes found" in body


async def test_activate_empty_seeds_over_wire(target_repo):
    async with _connect(target_repo) as session:
        result = await session.call_tool("activate", {"seeds": "", "top_k": 5})
        body = _text(result)
        assert "No seed nodes found" in body


async def test_graph_view_overview_over_wire(target_repo):
    async with _connect(target_repo) as session:
        result = await session.call_tool("graph_view", {})
        body = _text(result)
        assert "repo-graph" in body
        assert "Node kinds:" in body


async def test_impact_unknown_over_wire(target_repo):
    async with _connect(target_repo) as session:
        result = await session.call_tool(
            "impact", {"node": "xxx_unknown_xxx"}
        )
        body = _text(result)
        assert "Node not found" in body


async def test_flow_unknown_over_wire(target_repo):
    async with _connect(target_repo) as session:
        result = await session.call_tool("flow", {"feature": "definitely_not_a_real_feature"})
        body = _text(result)
        assert "No flow found" in body


async def test_reload_over_wire(target_repo):
    async with _connect(target_repo) as session:
        result = await session.call_tool("reload", {})
        body = _text(result)
        assert body.startswith("Reloaded:")


async def test_trace_unknown_over_wire(target_repo):
    async with _connect(target_repo) as session:
        result = await session.call_tool(
            "trace", {"from_node": "xxx_bogus", "to_node": "yyy_bogus"}
        )
        body = _text(result)
        assert "Node not found" in body


# ── Cross-call invariants ───────────────────────────────────────────────────


async def test_status_and_dense_text_agree_on_engine_version(target_repo):
    """Both surfaces must report the same engine version — drift here would
    mean status renders a stale cached value somewhere."""
    async with _connect(target_repo) as session:
        status_body = _text(await session.call_tool("status", {}))
        # Engine line in status reads "Engine: repo-graph-py X.Y.Z (Rust + ...)"
        import re
        m = re.search(r"repo-graph-py (\S+)", status_body)
        assert m, f"status did not advertise an engine version: {status_body[:200]}"
        version = m.group(1)
        # The same version string must be in the generate output too
        gen_body = _text(await session.call_tool("generate", {}))
        assert version in gen_body, (
            f"version drift across tools: status says {version!r}, "
            f"generate says: {gen_body[-200:]}"
        )


async def test_all_tools_callable_no_errors(target_repo):
    """Smoke loop: every tool can be invoked over the wire with sensible args
    and returns isError=False. Catches schema validation or routing breakage."""
    async with _connect(target_repo) as session:
        # Warm the graph
        await session.call_tool("status", {})

        # Per-tool minimal args. trace/impact/neighbours/etc need a real node;
        # we pass a clearly-unknown one — they should return "Node not found"
        # as data, NOT as a protocol error.
        invocations = [
            ("generate", {}),
            ("status", {}),
            ("dense_text", {}),
            ("flow", {"feature": "anything"}),
            ("trace", {"from_node": "x", "to_node": "y"}),
            ("impact", {"node": "x"}),
            ("neighbours", {"node": "x"}),
            ("activate", {"seeds": "x"}),
            ("find", {"query": "x"}),
            ("graph_view", {}),
            ("reload", {}),
        ]

        for name, args in invocations:
            result = await session.call_tool(name, args)
            assert not result.isError, f"{name}({args}) returned isError=True: {result}"
            # Every tool must return at least one content block
            assert result.content, f"{name}({args}) returned no content"
