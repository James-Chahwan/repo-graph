import * as vscode from 'vscode';

/**
 * Registers repo-graph as an MCP server for VS Code's agent mode.
 *
 * Zero-config: it provisions `uvx mcp-repo-graph --repo <workspaceFolder>`, so the
 * user installs the extension and repo-graph maps their open project automatically
 * — no JSON, no path to type. uvx fetches the package + prebuilt Rust engine wheel
 * on first run, so the only requirement is `uv` (https://docs.astral.sh/uv/).
 */
export function activate(context: vscode.ExtensionContext) {
  const didChange = new vscode.EventEmitter<void>();
  // Read the version from package.json rather than a literal — a hardcoded string
  // here silently drifted behind the real release twice (0.4.16, then 0.4.21).
  const version: string = context.extension.packageJSON.version;

  const provider: vscode.McpServerDefinitionProvider = {
    onDidChangeMcpServerDefinitions: didChange.event,
    provideMcpServerDefinitions: async () => {
      const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
      const args = ['mcp-repo-graph'];
      if (folder) {
        args.push('--repo', folder);
      }
      // Positional constructor: (label, command, args, env?, version?)
      return [
        new vscode.McpStdioServerDefinition('repo-graph', 'uvx', args, undefined, version),
      ];
    },
  };

  context.subscriptions.push(
    vscode.lm.registerMcpServerDefinitionProvider('repoGraph', provider),
  );
  // Re-provision when the user opens/switches workspace folders so --repo follows.
  context.subscriptions.push(
    vscode.workspace.onDidChangeWorkspaceFolders(() => didChange.fire()),
  );
  context.subscriptions.push(didChange);
}

export function deactivate() {}
