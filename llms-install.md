# Installing repo-graph (for AI install agents)

This guide is written for an AI agent (e.g. Cline) setting up the `repo-graph` MCP
server. repo-graph gives you a structural map of the user's codebase so you navigate
to the right files instead of reading everything first.

## Prerequisites

- **`uv` / `uvx`** must be available. Check with `uvx --version`. If missing, install it:
  - macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - Windows (PowerShell): `irm https://astral.sh/uv/install.ps1 | iex`
- **No API key, account, or login is required.** repo-graph runs fully locally.

## Install

If you have terminal access, the fastest path is one command that configures every
agent on the machine (writes MCP config + a usage block per agent):

```bash
uvx mcp-repo-graph install
```

Otherwise, add the server to the MCP configuration directly. The command **is** the
package. `uvx` fetches and runs it on first use; there is nothing to `pip install`
first.

```json
{
  "mcpServers": {
    "repo-graph": {
      "command": "uvx",
      "args": ["mcp-repo-graph", "--repo", "."]
    }
  }
}
```

- `--repo .` maps the current workspace. To map a different project, replace `.` with
  an absolute path. A public git URL also works (it is cloned on demand), e.g.
  `"--repo", "https://github.com/org/repo"`.
- If your client launches the server from a GUI where `uvx` may not be on `PATH`, use
  the absolute path to `uvx` (find it with `which uvx` / `where uvx`).

## Verify

After the server is connected, call the `status` tool. A successful install returns a
repo overview (node/edge counts, detected languages, entry points). The server exposes
**13 tools** across four tiers — generation (`generate`), navigation (`status`, `flow`,
`trace`, `impact`, `neighbours`, `read`), activation & context (`activate`, `find`,
`locate`, `dense_text`), and health/admin (`graph_view`, `reload`).

## Usage tip

Before grepping or reading files, call `status` to orient, then `dense_text` for full
context or `activate`/`find`/`locate` to scope down. For a bug, paste the stacktrace or
failing test into `locate`, then `read` the top result's source.
