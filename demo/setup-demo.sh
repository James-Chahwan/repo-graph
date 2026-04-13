#!/bin/bash
# Demo setup — isolate quokka-stack for clean before/after recording
# Usage:
#   ./setup-demo.sh before   # Run 1: no repo-graph, no other MCP/plugins
#   ./setup-demo.sh after    # Run 2: only repo-graph MCP, nothing else
#   ./setup-demo.sh restore  # Put everything back

QS="/home/ivy/Code/quokka-stack"
BACKUP_DIR="/tmp/demo-backup"

case "$1" in
  before)
    echo "=== Setting up Run 1: WITHOUT repo-graph ==="

    # Create backup dir
    mkdir -p "$BACKUP_DIR"

    # 1. Back up and remove CLAUDE.md (prevents startup glab/mempalace/workflow reads)
    [ -f "$QS/CLAUDE.md" ] && cp "$QS/CLAUDE.md" "$BACKUP_DIR/CLAUDE.md" && rm "$QS/CLAUDE.md"

    # 2. Back up and remove project MCP config (disables GitLab MCP)
    [ -f "$QS/.claude/mcp.json" ] && cp "$QS/.claude/mcp.json" "$BACKUP_DIR/mcp.json" && rm "$QS/.claude/mcp.json"

    # 3. Back up project settings and replace with clean version (no plugins)
    [ -f "$QS/.claude/settings.json" ] && cp "$QS/.claude/settings.json" "$BACKUP_DIR/settings.json"
    cat > "$QS/.claude/settings.json" << 'EOF'
{
  "permissions": {
    "allow": [
      "Read(**)",
      "Edit(**)",
      "Bash(grep *)",
      "Bash(git *)",
      "Bash(find *)",
      "Bash(ls *)",
      "Bash(go *)"
    ]
  },
  "enabledPlugins": {}
}
EOF

    # 4. Back up global settings and strip plugins
    [ -f "$HOME/.claude/settings.json" ] && cp "$HOME/.claude/settings.json" "$BACKUP_DIR/global-settings.json"
    cat > "$HOME/.claude/settings.json" << 'EOF'
{
  "permissions": {
    "allow": []
  },
  "model": "opus",
  "hooks": {},
  "enabledPlugins": {},
  "effortLevel": "high"
}
EOF

    # 5. Make sure no root .mcp.json exists
    rm -f "$QS/.mcp.json"

    # 6. Make sure the bug is present
    if grep -q 'time.Since(g.CreatedAt) <' "$QS/turps/Server/Controllers/group_controller.go"; then
      echo "WARNING: Bug appears already fixed! Reverting..."
      cd "$QS" && git checkout turps/Server/Controllers/group_controller.go
    fi

    echo ""
    echo "Ready for Run 1 (WITHOUT repo-graph)."
    echo "  cd $QS && claude"
    echo ""
    echo "Paste this prompt:"
    echo '  Groups that were created recently are showing as closed, and old groups show as open. This is backwards — new groups should be open for members to join. Find and fix the bug.'
    echo ""
    echo "When done: type /cost, screenshot, then exit."
    ;;

  after)
    echo "=== Setting up Run 2: WITH repo-graph ==="

    # 1. CLAUDE.md stays removed (same conditions as Run 1)

    # 2. Project MCP stays removed (no GitLab)

    # 3. Project settings stay clean (no plugins)

    # 4. Global settings stay clean (no plugins)

    # 5. Add ONLY repo-graph MCP at the root
    cat > "$QS/.mcp.json" << 'EOF'
{
  "mcpServers": {
    "repo-graph": {
      "command": "repo-graph",
      "args": ["--repo", "/home/ivy/Code/quokka-stack"]
    }
  }
}
EOF

    # 6. Revert the bug fix from Run 1
    cd "$QS" && git checkout turps/Server/Controllers/group_controller.go

    # 7. Make sure graph is fresh
    echo "Regenerating graph..."
    repo-graph-generate --repo "$QS"

    echo ""
    echo "Ready for Run 2 (WITH repo-graph)."
    echo "  cd $QS && claude"
    echo ""
    echo "Paste the same prompt:"
    echo '  Groups that were created recently are showing as closed, and old groups show as open. This is backwards — new groups should be open for members to join. Find and fix the bug.'
    echo ""
    echo "When done: type /cost, screenshot, then exit."
    ;;

  restore)
    echo "=== Restoring original configs ==="

    # Restore everything from backup
    [ -f "$BACKUP_DIR/CLAUDE.md" ] && cp "$BACKUP_DIR/CLAUDE.md" "$QS/CLAUDE.md" && echo "  Restored CLAUDE.md"
    [ -f "$BACKUP_DIR/mcp.json" ] && cp "$BACKUP_DIR/mcp.json" "$QS/.claude/mcp.json" && echo "  Restored .claude/mcp.json"
    [ -f "$BACKUP_DIR/settings.json" ] && cp "$BACKUP_DIR/settings.json" "$QS/.claude/settings.json" && echo "  Restored .claude/settings.json"
    [ -f "$BACKUP_DIR/global-settings.json" ] && cp "$BACKUP_DIR/global-settings.json" "$HOME/.claude/settings.json" && echo "  Restored global settings.json"

    # Remove demo MCP config
    rm -f "$QS/.mcp.json"

    # Revert any code changes
    cd "$QS" && git checkout turps/Server/Controllers/group_controller.go

    echo ""
    echo "Everything restored. Clean up backup:"
    echo "  rm -rf $BACKUP_DIR"
    ;;

  *)
    echo "Usage: $0 {before|after|restore}"
    echo ""
    echo "  before  — Strip all MCP/plugins for Run 1 (without repo-graph)"
    echo "  after   — Add only repo-graph MCP for Run 2, revert bug"
    echo "  restore — Put all original configs back"
    exit 1
    ;;
esac
