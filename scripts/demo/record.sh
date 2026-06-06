#!/usr/bin/env bash
# Open a clean 1920x1080 recording window and play the demo(s). FULLY REVERSIBLE:
# a separate kitty window using recording.kitty.conf + a bare zsh — your real
# kitty/zsh configs are never touched. Close the window when done.
#
#   scripts/demo/record.sh            # all 5, lockstep
#   scripts/demo/record.sh 1          # one demo
#   DEMO_SPEED=1.4 scripts/demo/record.sh all
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
N="${1:-all}"
command -v kitty >/dev/null || { echo "kitty not found — open any terminal and run: $HERE/run.sh $N" >&2; exit 1; }

kitty --config "$HERE/recording.kitty.conf" --title "repo-graph demo · recording" \
  zsh -d -f -c "clear; '$HERE/run.sh' $N; print -P '\n%F{120}✓ done — close this window%f'; exec zsh -d -f" &
disown || true
echo "▶ Opened a 1920×1080 recording window (calm black + pastel-green). Demo: $N"
echo "  A fixed-size terminal you can record or overlay as a background video."
echo "  Reversible — close the window when done; nothing permanent changed."
