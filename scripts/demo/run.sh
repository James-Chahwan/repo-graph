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
S="rgdemo"
[ -d "$DEMO_REPO" ] || { echo "DEMO_REPO not found: $DEMO_REPO" >&2; exit 1; }

SYNC="$(mktemp -d "${TMPDIR:-/tmp}/rgdemo.XXXXXX")"   # shared: live stats + lockstep barriers
: > "$SYNC/left.stat"; : > "$SYNC/right.stat"

echo "Pre-warming graph cache for $DEMO_REPO…"
DEMO_REPO="$DEMO_REPO" python3 "$HERE/rg.py" status >/dev/null 2>&1 || \
  DEMO_REPO="$DEMO_REPO" python3 "$HERE/rg.py" generate >/dev/null 2>&1 || true

tmux kill-session -t "$S" 2>/dev/null || true
tmux new-session -d -s "$S" -x 232 -y 54

# ── top comparison bar ────────────────────────────────────────────────────────
tmux set -t "$S" status on
tmux set -t "$S" status-position top
tmux set -t "$S" status-interval 1
tmux set -t "$S" status-style "bg=colour233,fg=colour213,bold"
tmux set -t "$S" status-justify centre
tmux set -t "$S" status-left-length 70
tmux set -t "$S" status-right-length 70
tmux set -t "$S" status-left  "#[fg=colour203,bold] ✗ WITHOUT #[fg=colour252,nobold]#(cat $SYNC/left.stat 2>/dev/null)  "
tmux set -t "$S" status-right "  #[fg=colour252,nobold]#(cat $SYNC/right.stat 2>/dev/null)#[fg=colour120,bold] WITH ✓ "
tmux set -t "$S" window-status-format         "#[fg=colour213,bold]#W"
tmux set -t "$S" window-status-current-format "#[fg=colour213,bold]#W"
tmux rename-window -t "$S" "◆ repo-graph — navigate code by structure (humans + LLMs) ◆"
# labeled pane borders
tmux set -t "$S" pane-border-status top
tmux set -t "$S" pane-border-format " #{pane_title} "
tmux set -t "$S" pane-border-style "fg=colour237"; tmux set -t "$S" pane-active-border-style "fg=colour237"

L="DEMO_REPO='$DEMO_REPO' DEMO_SPEED='$DEMO_SPEED' DEMO_SYNC='$SYNC' bash '$HERE/pane.sh'"
tmux send-keys -t "$S" "clear; $L left $N" C-m
tmux split-window -h -t "$S"
tmux send-keys -t "$S" "clear; $L right $N" C-m
tmux select-pane -t "$S".0 -T "✗  WITHOUT repo-graph"
tmux select-pane -t "$S".1 -T "✓  WITH repo-graph"
tmux select-pane -t "$S".0

echo "▶ Demo $N — 3s countdown in each pane; start recording. (Bar updates live.)"
echo "  Detach: Ctrl-b d   ·   Kill: tmux kill-session -t $S"
sleep 0.3
tmux attach -t "$S"
rm -rf "$SYNC"
