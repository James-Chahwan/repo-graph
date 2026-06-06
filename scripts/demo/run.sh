#!/usr/bin/env bash
# One-command side-by-side repo-graph demo for recording.
#   scripts/demo/run.sh <1-5>     one demo
#   scripts/demo/run.sh all       all five, with a cut-point pause between each
#   DEMO_REPO=/path DEMO_SPEED=1.3 scripts/demo/run.sh 3
#
# tmux split: LEFT "✗ without repo-graph" (real grep/cat) · RIGHT "✓ with repo-graph"
# (real flow/trace/impact/dense_text). Top bar shows the demo title; pane borders
# label each side. Counters are grounded in real bytes read.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
N="${1:-1}"
DEMO_REPO="${DEMO_REPO:-/home/ivy/Code/quokka-stack}"
DEMO_SPEED="${DEMO_SPEED:-1.0}"
S="rgdemo"
declare -A TITLE=([1]="TOKEN RACE" [2]="FILES OPENED" [3]="CROSS-STACK TRACE" [4]="CONTEXT WINDOW" [5]="BLAST RADIUS")

[ -d "$DEMO_REPO" ] || { echo "DEMO_REPO not found: $DEMO_REPO" >&2; exit 1; }

# ── batch mode ────────────────────────────────────────────────────────────────
if [ "$N" = "all" ]; then
  for n in 1 2 3 4 5; do
    DEMO_REPO="$DEMO_REPO" DEMO_SPEED="$DEMO_SPEED" "$0" "$n"
    [ "$n" = "5" ] && break
    printf "\n\033[1;35m▶ Demo %s done — stop/cut your recording, then press ENTER for the next.\033[0m " "$n"; read -r _
  done
  echo "All 5 done."; exit 0
fi

echo "Pre-warming graph cache for $DEMO_REPO…"
DEMO_REPO="$DEMO_REPO" python3 "$HERE/rg.py" status >/dev/null 2>&1 || \
  DEMO_REPO="$DEMO_REPO" python3 "$HERE/rg.py" generate >/dev/null 2>&1 || true

tmux kill-session -t "$S" 2>/dev/null || true
tmux new-session -d -s "$S" -x 232 -y 54

# top title bar (vaporwave magenta on black, centered demo title)
tmux set -t "$S" status on
tmux set -t "$S" status-style "bg=colour233,fg=colour213,bold"
tmux set -t "$S" status-left ""; tmux set -t "$S" status-right ""
tmux set -t "$S" status-justify centre
tmux rename-window -t "$S" "◆  repo-graph  ·  DEMO ${N} — ${TITLE[$N]}  ◆"
tmux set -t "$S" window-status-format "#W"; tmux set -t "$S" window-status-current-format "#W"
# labeled pane borders
tmux set -t "$S" pane-border-status top
tmux set -t "$S" pane-border-format " #{pane_title} "
tmux set -t "$S" pane-border-style "fg=colour237"
tmux set -t "$S" pane-active-border-style "fg=colour237"

L="DEMO_REPO='$DEMO_REPO' DEMO_SPEED='$DEMO_SPEED' bash '$HERE/pane.sh'"
tmux send-keys -t "$S" "clear; $L left $N" C-m
tmux split-window -h -t "$S"
tmux send-keys -t "$S" "clear; $L right $N" C-m
tmux select-pane -t "$S".0 -T "✗  WITHOUT repo-graph"
tmux select-pane -t "$S".1 -T "✓  WITH repo-graph"
tmux select-pane -t "$S".0

echo "▶ DEMO $N — ${TITLE[$N]}. 3-second countdown in each pane — start recording now."
echo "  Detach: Ctrl-b d   ·   Kill: tmux kill-session -t $S"
sleep 0.3
exec tmux attach -t "$S"
