#!/usr/bin/env bash
# Open a clean, recording-ready kitty window and play the demo(s). FULLY REVERSIBLE:
# it spawns a separate kitty window using recording.kitty.conf + a bare zsh — your
# real kitty/zsh configs are never touched. Just close the window when done.
#
#   scripts/demo/record.sh            # all 5, lockstep
#   scripts/demo/record.sh 1          # one demo
#   DEMO_SPEED=1.4 scripts/demo/record.sh all
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
N="${1:-all}"
command -v kitty >/dev/null || { echo "kitty not found — open any terminal and run: $HERE/run.sh $N" >&2; exit 1; }

kitty --config "$HERE/recording.kitty.conf" --title "repo-graph demo · recording" \
  zsh -d -f -c "clear; '$HERE/run.sh' $N; print -P '\n%F{82}✓ done — start a fresh recording window per take, or close this one%f'; exec zsh -d -f" &
disown || true
echo "▶ Opened a recording window (kitty + recording.kitty.conf, bare zsh). Demo: $N"
echo "  Reversible — close that window when done; nothing permanent changed."
