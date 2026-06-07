#!/usr/bin/env bash
# One-command side-by-side repo-graph demo for recording.
#   scripts/demo/run.sh <1-5>     one demo
#   scripts/demo/run.sh all       all five back-to-back, panes in lockstep
#   DEMO_REPO=/path DEMO_SPEED=1.4 scripts/demo/run.sh all
#
# Top bar is a LIVE comparison: "✗ WITHOUT <stats>  —  benefit  —  <stats> WITH ✓",
# describing the human+LLM workflow win. Panes: LEFT real grep/cat, RIGHT real
# repo-graph (flow/trace/impact/dense_text). Counters grounded in real bytes.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
N="${1:-1}"
DEMO_REPO="${DEMO_REPO:-/home/ivy/Code/quokka-stack}"
DEMO_SPEED="${DEMO_SPEED:-1.0}"
LAYOUT="${DEMO_LAYOUT:-side}"   # side = columns (16:9) · stack = rows (9:16 Shorts/Reels)
S="rgdemo"
[ -d "$DEMO_REPO" ] || { echo "DEMO_REPO not found: $DEMO_REPO" >&2; exit 1; }

SYNC="$(mktemp -d "${TMPDIR:-/tmp}/rgdemo.XXXXXX")"   # shared: live stats + lockstep barriers
: > "$SYNC/left.stat"; : > "$SYNC/right.stat"

echo "Pre-warming graph cache for $DEMO_REPO…"
DEMO_REPO="$DEMO_REPO" python3 "$HERE/rg.py" status >/dev/null 2>&1 || \
  DEMO_REPO="$DEMO_REPO" python3 "$HERE/rg.py" generate >/dev/null 2>&1 || true

tmux kill-session -t "$S" 2>/dev/null || true
# layout: side = horizontal columns (16:9) · stack = vertical rows (9:16 portrait)
if [ "$LAYOUT" = "stack" ]; then NX=160; NY=120; SPLIT=-v; else NX=232; NY=54; SPLIT=-h; fi
tmux new-session -d -s "$S" -x "$NX" -y "$NY"

# ── top comparison bar ────────────────────────────────────────────────────────
tmux set -t "$S" status on
tmux set -t "$S" status-position top
tmux set -t "$S" status 2                  # two rows so nothing truncates
tmux set -t "$S" status-interval 1
tmux set -t "$S" status-style "bg=colour0,fg=colour7,bold"
# row 0: brand + benefit, centred full-width  ·  row 1: WITHOUT (left) ⟷ WITH (right)
tmux set -t "$S" "status-format[0]" "#[align=centre,bg=colour0,fg=colour15,bold] #W "
tmux set -t "$S" "status-format[1]" "#[align=left,bg=colour0,fg=colour1,bold] ✗ WITHOUT #[fg=colour7,nobold]#(cat $SYNC/left.stat 2>/dev/null)#[align=right,fg=colour7,nobold]#(cat $SYNC/right.stat 2>/dev/null)#[fg=colour2,bold] WITH ✓ "
tmux rename-window -t "$S" "mcp-repo-graph · navigate code by structure (humans + LLMs)"
# labeled pane borders
tmux set -t "$S" pane-border-status top
tmux set -t "$S" pane-border-format " #{pane_title} "
tmux set -t "$S" pane-border-style "fg=colour8"; tmux set -t "$S" pane-active-border-style "fg=colour8"

L="DEMO_REPO='$DEMO_REPO' DEMO_SPEED='$DEMO_SPEED' DEMO_SYNC='$SYNC' bash '$HERE/pane.sh'"
# side: WITHOUT left, WITH right · stack (Shorts/Reels): WITH on top, WITHOUT on bottom
if [ "$LAYOUT" = "stack" ]; then P0=right; T0="✓  WITH repo-graph"; P1=left; T1="✗  WITHOUT repo-graph"
else                            P0=left;  T0="✗  WITHOUT repo-graph"; P1=right; T1="✓  WITH repo-graph"; fi
tmux send-keys -t "$S" "clear; $L $P0 $N" C-m
tmux split-window "$SPLIT" -t "$S"
tmux send-keys -t "$S" "clear; $L $P1 $N" C-m
tmux select-pane -t "$S".0 -T "$T0"
tmux select-pane -t "$S".1 -T "$T1"
tmux select-pane -t "$S".0

echo "▶ Demo $N — 3s countdown in each pane; start recording. (Bar updates live.)"
echo "  Detach: Ctrl-b d   ·   Kill: tmux kill-session -t $S"
sleep 0.3
tmux attach -t "$S"
rm -rf "$SYNC"
