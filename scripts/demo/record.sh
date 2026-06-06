#!/usr/bin/env bash
# Open a clean, recording-ready kitty window (fullscreen) and play the demo(s).
# FULLY REVERSIBLE: a separate kitty window using recording.kitty.conf + a bare zsh —
# your real kitty/zsh configs are never touched. Close the window when done.
#
#   scripts/demo/record.sh            # all 5, lockstep
#   scripts/demo/record.sh 1          # one demo
#   DEMO_SPEED=1.4 scripts/demo/record.sh all
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
N="${1:-all}"
command -v kitty >/dev/null || { echo "kitty not found — open any terminal and run: $HERE/run.sh $N" >&2; exit 1; }

SOCK="unix:/tmp/kitty-rgdemo-$$"
kitty --config "$HERE/recording.kitty.conf" --listen-on "$SOCK" --title "repo-graph demo · recording" \
  zsh -d -f -c "clear; '$HERE/run.sh' $N; print -P '\n%F{82}✓ done — close this window%f'; exec zsh -d -f" &
disown || true

# force fullscreen once the window is up (start_as is unreliable on some compositors)
for _ in $(seq 1 25); do
  sleep 0.2
  kitty @ --to "$SOCK" resize-os-window --action toggle-fullscreen >/dev/null 2>&1 && break
done

echo "▶ Opened a fullscreen recording window. Demo: $N"
echo "  Fullscreen didn't take? Click the window and press Ctrl+Shift+F11."
echo "  Reversible — close the window when done; nothing permanent changed."
