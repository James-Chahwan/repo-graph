#!/usr/bin/env bash
# Open a clean 1920x1080 recording window and play the demo(s). FULLY REVERSIBLE:
# a separate kitty window using recording.kitty.conf + a bare zsh — your real
# kitty/zsh configs are never touched. Close the window when done.
#
#   scripts/demo/record.sh            # all 5, side-by-side (16:9)
#   scripts/demo/record.sh 1          # one demo, side-by-side
#   scripts/demo/record.sh shorts     # all 5, stacked 9:16 for Shorts/Reels (WITH on top)
#   scripts/demo/record.sh shorts 3   # one demo, stacked
#   DEMO_SPEED=1.4 scripts/demo/record.sh all
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
N="${1:-all}"
LAYOUT="${DEMO_LAYOUT:-side}"
if [ "${1:-}" = "shorts" ] || [ "${1:-}" = "stack" ]; then LAYOUT="stack"; N="${2:-all}"; fi
command -v kitty >/dev/null || { echo "kitty not found — open any terminal and run: DEMO_LAYOUT=$LAYOUT $HERE/run.sh $N" >&2; exit 1; }

if [ "$LAYOUT" = "stack" ]; then CONF="$HERE/recording-shorts.kitty.conf"; DIM="1080×1920 portrait · Shorts/Reels (WITH on top)"
else                            CONF="$HERE/recording.kitty.conf";        DIM="1920×1080 landscape · side-by-side"; fi

kitty --config "$CONF" --title "repo-graph demo · recording ($LAYOUT)" \
  zsh -d -f -c "clear; DEMO_LAYOUT=$LAYOUT '$HERE/run.sh' $N; print -P '\n%F{120}✓ done — close this window%f'; exec zsh -d -f" &
disown || true
echo "▶ Opened a $DIM recording window (calm black + pastel-green). Demo: $N"
echo "  A fixed-size terminal you can record or overlay as a background video."
echo "  Reversible — close the window when done; nothing permanent changed."
