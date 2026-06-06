#!/usr/bin/env bash
# One-command side-by-side repo-graph demo for recording.
#   scripts/demo/run.sh <1-5>     one demo
#   scripts/demo/run.sh all       all five back-to-back, panes kept in lockstep
#   DEMO_REPO=/path DEMO_SPEED=1.4 scripts/demo/run.sh all
#
# tmux split: LEFT "✗ without repo-graph" (real grep/cat) · RIGHT "✓ with repo-graph"
# (real flow/trace/impact/dense_text). Both panes show the SAME status line
# (⏱ time · ~tokens · files/calls) so the contrast reads at a glance.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
N="${1:-1}"
DEMO_REPO="${DEMO_REPO:-/home/ivy/Code/quokka-stack}"
DEMO_SPEED="${DEMO_SPEED:-1.0}"
S="rgdemo"
declare -A TITLE=([1]="TOKEN RACE" [2]="FILES OPENED" [3]="CROSS-STACK TRACE" [4]="CONTEXT WINDOW" [5]="BLAST RADIUS")
[ -d "$DEMO_REPO" ] || { echo "DEMO_REPO not found: $DEMO_REPO" >&2; exit 1; }

if [ "$N" = "all" ]; then
  BAR="◆  repo-graph  ·  5 demos, side by side  ◆"
  SYNC="$(mktemp -d "${TMPDIR:-/tmp}/rgdemo.XXXXXX")"
else
  BAR="◆  repo-graph  ·  DEMO $N — ${TITLE[$N]:-}  ◆"; SYNC=""
fi

echo "Pre-warming graph cache for $DEMO_REPO…"
DEMO_REPO="$DEMO_REPO" python3 "$HERE/rg.py" status >/dev/null 2>&1 || \
  DEMO_REPO="$DEMO_REPO" python3 "$HERE/rg.py" generate >/dev/null 2>&1 || true

tmux kill-session -t "$S" 2>/dev/null || true
tmux new-session -d -s "$S" -x 232 -y 54
# top title bar (centered, vaporwave magenta)
tmux set -t "$S" status on
tmux set -t "$S" status-style "bg=colour233,fg=colour213,bold"
tmux set -t "$S" status-left ""; tmux set -t "$S" status-right ""
tmux set -t "$S" status-justify centre
tmux rename-window -t "$S" "$BAR"
tmux set -t "$S" window-status-format "#W"; tmux set -t "$S" window-status-current-format "#W"
# labeled pane borders
tmux set -t "$S" pane-border-status top
tmux set -t "$S" pane-border-format " #{pane_title} "
tmux set -t "$S" pane-border-style "fg=colour237"; tmux set -t "$S" pane-active-border-style "fg=colour237"

L="DEMO_REPO='$DEMO_REPO' DEMO_SPEED='$DEMO_SPEED'${SYNC:+ DEMO_SYNC='$SYNC'} bash '$HERE/pane.sh'"
tmux send-keys -t "$S" "clear; $L left $N" C-m
tmux split-window -h -t "$S"
tmux send-keys -t "$S" "clear; $L right $N" C-m
tmux select-pane -t "$S".0 -T "✗  WITHOUT repo-graph"
tmux select-pane -t "$S".1 -T "✓  WITH repo-graph"
tmux select-pane -t "$S".0

echo "▶ $BAR — 3s countdown in each pane; start recording now."
echo "  Detach: Ctrl-b d   ·   Kill: tmux kill-session -t $S"
sleep 0.3
tmux attach -t "$S"
[ -n "$SYNC" ] && rm -rf "$SYNC"
