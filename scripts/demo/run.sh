#!/usr/bin/env bash
# One-command side-by-side repo-graph demo for recording.
#   scripts/demo/run.sh <1-5>      (also: DEMO_REPO=/path DEMO_SPEED=1.3 run.sh 3)
#
# Opens a tmux window split into two panes — LEFT "without repo-graph" (real grep/cat),
# RIGHT "with repo-graph" (real tool output) — runs the chosen demo in both, and attaches
# so you can screen-record the whole thing, then cut per-demo.
#   Demos: 1 Token Race · 2 Files Opened · 3 Cross-Stack Trace · 4 Context Window · 5 Blast Radius
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
N="${1:-1}"
DEMO_REPO="${DEMO_REPO:-/home/ivy/Code/quokka-stack}"
DEMO_SPEED="${DEMO_SPEED:-1.0}"
S="rgdemo"

[ -d "$DEMO_REPO" ] || { echo "DEMO_REPO not found: $DEMO_REPO" >&2; exit 1; }

echo "Pre-warming repo-graph graph cache for $DEMO_REPO (first time ~a few seconds)…"
DEMO_REPO="$DEMO_REPO" python3 "$HERE/rg.py" status >/dev/null 2>&1 || \
  DEMO_REPO="$DEMO_REPO" python3 "$HERE/rg.py" generate >/dev/null 2>&1 || true

tmux kill-session -t "$S" 2>/dev/null || true
tmux new-session -d -s "$S" -x 230 -y 52
tmux set -t "$S" status off
L="DEMO_REPO='$DEMO_REPO' DEMO_SPEED='$DEMO_SPEED' bash '$HERE/pane.sh'"
tmux send-keys -t "$S" "clear; $L left $N" C-m
tmux split-window -h -t "$S"
tmux send-keys -t "$S" "clear; $L right $N" C-m
tmux select-pane -t "$S".0

echo "▶ Demo $N is starting in tmux (3s countdown in each pane — start your recording now)."
echo "  Detach: Ctrl-b then d   ·   Kill: tmux kill-session -t $S"
sleep 0.3
exec tmux attach -t "$S"
