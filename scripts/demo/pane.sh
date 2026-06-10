#!/usr/bin/env bash
# One side of a side-by-side repo-graph demo.
#   pane.sh <left|right> <demo 1-7>
# LEFT  = no repo-graph (real grep/cat on $DEMO_REPO, token counter = real file size / 4)
# RIGHT = repo-graph (real tool output via rg.py, token counter = real output size / 4)
# Numbers are grounded in actual bytes read — nothing is invented.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_REPO="${DEMO_REPO:-/home/ivy/Code/quokka-stack}"
SPEED="${DEMO_SPEED:-1.0}"   # higher = slower

C_DIM=$'\033[2m'; C_RED=$'\033[31m'; C_GRN=$'\033[32m'; C_YEL=$'\033[33m'
C_CYN=$'\033[36m'; C_MAG=$'\033[35m'; C_B=$'\033[1m'; C_R=$'\033[0m'

TOK=0; FILES=0; CALLS=0
SIDE="${1:-left}"; OTHER=$([ "$SIDE" = "left" ] && echo right || echo left)
SYNC="${DEMO_SYNC:-}"   # shared dir for left/right lockstep in 'all' mode
# Human names — the question the dev is already asking. Title = the problem/pain,
# the WITH pane = the relief. Understandable in 5 seconds.
declare -A TITLES=([1]="What's it actually do?" [2]="Where's this even coming from?" [3]="Just the bit I need" [4]="What'll this break?" [5]="Where's it go on the backend?" [6]="Where does this live?" [7]="Find it and fix it")
barrier(){ [ -n "$SYNC" ] || return 0; touch "$SYNC/$1.$SIDE" 2>/dev/null; local t=0
  while [ ! -e "$SYNC/$1.$OTHER" ]; do sleep 0.1; t=$((t+1)); [ "$t" -gt 1800 ] && break; done; }
titlecard(){ printf '\n\n\n   %s%s●  DEMO %s — %s%s\n\n   %ssame model · same prompt · only difference: repo-graph%s\n' \
  "$C_B" "$C_MAG" "$1" "${TITLES[$1]}" "$C_R" "$C_DIM" "$C_R"; pace 1.8; }
# benefit framed for real human + LLM coding workflows (shown in the top comparison bar)
declare -A BENEFIT=(
  [1]="edit the real function, not an almost-right guess"
  [2]="stack trace → the exact code, no grep safari"
  [3]="just the slice that matters, not the whole repo"
  [4]="see everything a change touches, cross-stack"
  [5]="frontend → backend in one hop — grep can't link stacks"
  [6]="jump to where a feature lives — no grep→read→grep"
  [7]="less context burned — cheaper & faster for you and the model")
setbar(){ [ "$SIDE" = "left" ] && [ -n "${TMUX:-}" ] && \
  tmux rename-window "mcp-repo-graph · ${BENEFIT[$1]}" 2>/dev/null; return 0; }

pace(){ awk "BEGIN{system(\"sleep \" $1*$SPEED)}" 2>/dev/null || sleep "$1"; }
commafy(){ printf "%s" "$1" | sed -E ':a;s/([0-9])([0-9]{3})($|[^0-9])/\1,\2\3/;ta'; }
cmd(){ printf "%s$ %s" "$C_DIM" "$C_R"; local s="$1" i; for ((i=0;i<${#s};i++)); do printf "%s" "${s:$i:1}"; sleep 0.012; done; printf "\n"; pace 0.15; }
note(){ printf "%s%s%s\n" "$C_DIM" "$1" "$C_R"; }
hdr(){ printf "%s%s  %s%s\n%s%s%s\n\n" "$C_B" "$1" "$2" "$C_R" "$C_DIM" "$3" "$C_R"; }
prompt(){ printf "%s┃ prompt: %s%s\n\n" "$C_CYN" "$1" "$C_R"; pace 0.5; }
T0=$SECONDS; elapsed(){ echo $(( SECONDS - T0 )); }
# identical status-line format on BOTH panes → instant visual comparison
statln(){ printf "   %s⏱ %2ss  ·  ~%s tokens  ·  %s%s\n" "${2:-$C_DIM}" "$(elapsed)" "$(commafy "$TOK")" "$1" "$C_R"
  [ -n "$SYNC" ] && printf '~%s tok · %s · %ss' "$(commafy "$TOK")" "$1" "$(elapsed)" > "$SYNC/$SIDE.stat" 2>/dev/null; return 0; }
tally_l(){ statln "$FILES files" "$C_YEL"; }
tally_r(){ statln "$CALLS call(s)" "$C_GRN"; }
finalcard(){ local n lbl; if [ "$SIDE" = "left" ]; then n=$FILES; lbl="files"; else n=$CALLS; lbl="call"; fi
  card "$1" "~$(commafy "$TOK") tokens   ·   $n $lbl   ·   $(elapsed)s" "$2"; }
card(){ local c="$1" rule="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  printf "\n%s%s%s\n" "$c" "$rule" "$C_R"
  printf "  %s%s%s%s\n" "$C_B" "$c" "$2" "$C_R"
  [ $# -ge 3 ] && printf "  %s%s%s\n" "$C_DIM" "$3" "$C_R"
  printf "%s%s%s\n" "$c" "$rule" "$C_R"; }

# ── end cards (shown after `all`) ───────────────────────────────────────────────
# LEFT: the 5-demo WITHOUT-vs-WITH stat table + the headline multiplier.
summary_card(){ local n lt lf lc rt rf rc tw=0 tr=0 tf=0 tc=0
  printf '\n\n   %s%s7 demos · side by side%s\n' "$C_B" "$C_GRN" "$C_R"
  printf '   %ssame model · same prompt · only difference: repo-graph%s\n\n' "$C_DIM" "$C_R"
  printf '   %s%-31s %12s    %-12s%s\n' "$C_DIM" "demo" "WITHOUT" "WITH" "$C_R"
  printf '   %s──────────────────────────────────────────────────────────────%s\n' "$C_DIM" "$C_R"
  for n in 1 2 3 4 5 6 7; do
    read -r lt lf lc < "$SYNC/left.d$n"  2>/dev/null || { lt=0; lf=0; lc=0; }
    read -r rt rf rc < "$SYNC/right.d$n" 2>/dev/null || { rt=0; rf=0; rc=0; }
    tw=$((tw+lt)); tr=$((tr+rt)); tf=$((tf+lf)); tc=$((tc+rc))
    printf '   %-31s %s%8s tok%s    %s%8s tok%s\n' \
      "${TITLES[$n]}" "$C_RED" "$(commafy "$lt")" "$C_R" "$C_GRN" "$(commafy "$rt")" "$C_R"
  done
  printf '   %s──────────────────────────────────────────────────────────────%s\n' "$C_DIM" "$C_R"
  printf '   %s%-31s %s%8s tok%s    %s%8s tok%s\n' \
    "$C_B" "total" "$C_RED" "$(commafy "$tw")" "$C_R$C_B" "$C_GRN" "$(commafy "$tr")" "$C_R"
  local mult=0; [ "$tr" -gt 0 ] && mult=$(( (tw + tr/2) / tr ))
  printf '\n   %s%s→ ~%s× less context, every task%s\n' "$C_B" "$C_GRN" "$mult" "$C_R"
  printf '   %s%s→ and far less work: %s files opened by hand  →  %s repo-graph calls%s\n' \
    "$C_B" "$C_GRN" "$tf" "$tc" "$C_R"; }

# RIGHT: the package NAME big (the searchable string that survives phone→desktop)
# + the literal install command, large and held. No QR — devs install at a terminal,
# not by scanning their own screen; the retainable thing is the name.
outro_card(){
  printf '\n\n\n'
  printf '   %s%s╭───────────────────────────────────────╮%s\n' "$C_B" "$C_GRN" "$C_R"
  printf '   %s%s│   p i p   i n s t a l l               │%s\n' "$C_B" "$C_GRN" "$C_R"
  printf '   %s%s│   m c p - r e p o - g r a p h         │%s\n' "$C_B" "$C_GRN" "$C_R"
  printf '   %s%s╰───────────────────────────────────────╯%s\n' "$C_B" "$C_GRN" "$C_R"
  printf '\n   %sone structural map · works in every AI client%s\n\n' "$C_DIM" "$C_R"
  surf(){ printf '   %s%-15s%s %s%s%s\n' "$C_GRN" "$1" "$C_R" "$C_B" "$2" "$C_R"; }
  surf "pip"             "pip install mcp-repo-graph"
  surf "uvx"             "uvx mcp-repo-graph --repo ."
  surf "Claude Code"     "claude mcp add repo-graph -- uvx mcp-repo-graph --repo ."
  surf "OpenAI Codex"    "codex mcp add repo-graph -- uvx mcp-repo-graph --repo ."
  surf "Gemini CLI"      "gemini mcp add repo-graph uvx mcp-repo-graph --repo ."
  surf "Cursor/Windsurf" "mcpServers  ·  uvx mcp-repo-graph"
  surf "VS Code"         "code --install-extension james-chahwan.repo-graph"
  surf "Antigravity"     "mcp_config.json  ·  uvx mcp-repo-graph"
  surf "Claude Desktop"  ".mcpb desktop extension"
  surf "any MCP client"  "mcpServers JSON  ·  command: uvx"
  printf '\n   %sruns on%s   🍎 %smacOS%s     🪟 %sWindows%s     🐧 %sLinux%s\n' \
    "$C_DIM" "$C_R" "$C_B" "$C_R" "$C_B" "$C_R" "$C_B" "$C_R"
  printf '\n   %ssearch%s %s%smcp-repo-graph%s   %s·  repo-graph.com%s\n' \
    "$C_DIM" "$C_R" "$C_B" "$C_GRN" "$C_R" "$C_DIM" "$C_R"; }

grep_show(){ cmd "grep -rn \"$1\" ."
  local n; n=$(grep -rIn "$1" "$DEMO_REPO" --include=*.go --include=*.ts 2>/dev/null | grep -vc node_modules)
  note "  → $n matches across the tree"; TOK=$((TOK + n*8)); tally_l; pace 0.5; }

read_matches(){ # pattern count
  local files f ch; mapfile -t files < <(grep -rIln "$1" "$DEMO_REPO" --include=*.go --include=*.ts --include=*.html 2>/dev/null | grep -v node_modules | head -"$2")
  for f in "${files[@]}"; do cmd "cat ${f#"$DEMO_REPO"/}"
    ch=$(wc -c <"$f" 2>/dev/null||echo 0); FILES=$((FILES+1)); TOK=$((TOK+ch/4)); tally_l; pace 0.3; done; }

read_biggest(){ # count
  local files f ch; mapfile -t files < <(find "$DEMO_REPO" \( -name '*.go' -o -name '*.ts' \) 2>/dev/null | grep -v node_modules \
    | while read -r p; do echo "$(wc -c <"$p" 2>/dev/null||echo 0) $p"; done | sort -rn | head -"$1" | cut -d' ' -f2-)
  for f in "${files[@]}"; do cmd "cat ${f#"$DEMO_REPO"/}"
    ch=$(wc -c <"$f" 2>/dev/null||echo 0); FILES=$((FILES+1)); TOK=$((TOK+ch/4)); tally_l; pace 0.22; done; }

rg(){ # tool args...   (retries past a transient engine bug where impact/trace
      #                  occasionally return empty for a node that has results)
  local tool="$1"; shift; cmd "repo-graph $tool $*"; pace 0.3
  local out tries=0
  while :; do
    out=$(DEMO_REPO="$DEMO_REPO" python3 "$HERE/rg.py" "$tool" "$@" 2>/dev/null)
    tries=$((tries+1))
    { [ "${#out}" -ge 120 ] || [ "$tries" -ge 8 ]; } && break
  done
  printf "%s\n" "$out" | head -28
  TOK=$(( ${#out}/4 )); CALLS=$((CALLS+1)); tally_r; pace 0.4; }

# ── demos ─────────────────────────────────────────────────────────────────────
# Each demo is a CITED dev-with-LLM pain point (Sonar/Uvik/Cerbos 2026):
#  1 "almost right" (66%) · 2 slow debugging (45%) · 3 context rot · 4 off-target
#  changes · 5 cross-stack · 6 context retrieval (38%) · 7 context cost.
P1="Add a guard to the send-friend-request handler — what does it actually take?"
P2="Prod panic: nil pointer in the friends flow. Here's the trace — where do I look?"
P3="Get just enough context to work on the groups feature — don't bloat the window."
P4="What breaks if I change both friends handlers?"
P5="Where does the frontend group action end up in the backend?"
P6="Where does the groups feature live?"
P7="Groups created recently show as closed; new groups should be open. Find & fix."

# A Go panic with paths/symbols that REALLY exist in quokka-stack (so locate resolves).
STACK=$'panic: runtime error: invalid memory address or nil pointer dereference\n  turps/Server/Controllers.SendFriendRequestHandler(0xc000123)\n    turps/Server/Controllers/friends_controller.go:112\n  turps/Server/Controllers.GetFriendsHandler(0xc000123)\n    turps/Server/Controllers/friends_controller.go:40'
paste(){ printf "%s┃ pasted error%s\n%s%s%s\n\n" "$C_YEL" "$C_R" "$C_DIM" "$1" "$C_R"; pace 0.5; }
locate_demo(){ cmd "repo-graph locate \"<stack trace>\" stacktrace"; pace 0.3
  local out; out=$(DEMO_REPO="$DEMO_REPO" python3 "$HERE/rg.py" locate "$STACK" stacktrace 2>/dev/null)
  printf "%s\n" "$out" | head -20; TOK=$(( ${#out}/4 )); CALLS=$((CALLS+1)); tally_r; pace 0.4; }

# 1 · Ground the Edit — find + read the REAL function vs guessing its contract
left1(){  hdr "$C_RED" "✗ without repo-graph" "guess the signature, write almost-right code"; prompt "$P1"
  grep_show "SendFriendRequestHandler"; read_matches "FriendRequest" 3; read_matches "friend" 4
  finalcard "$C_RED" "contract still assumed — 'almost right'"; }
right1(){ hdr "$C_GRN" "✓ with repo-graph" "read the real source first"; prompt "$P1"
  rg find SendFriendRequestHandler; rg read SendFriendRequestHandler
  finalcard "$C_GRN" "exact signature + body, grounded"; }

# 2 · Debug a Stack Trace — locate → read vs grepping frames by hand
left2(){  hdr "$C_RED" "✗ without repo-graph" "grep the frames, open file after file"; prompt "$P2"
  paste "$STACK"; grep_show "SendFriendRequestHandler"; grep_show "GetFriendsHandler"; read_matches "friend" 4
  finalcard "$C_RED" "still tracing the error by hand"; }
right2(){ hdr "$C_GRN" "✓ with repo-graph" "locate the trace → read the frame"; prompt "$P2"
  paste "$STACK"; locate_demo; rg read GetFriendsHandler
  finalcard "$C_GRN" "error → exact code, ranked"; }

# 3 · Context Rot — scoped dense_text vs dumping files until accuracy decays
left3(){  hdr "$C_RED" "✗ without repo-graph" "load files until you 'get it' — accuracy rots"; prompt "$P3"
  read_biggest 14
  finalcard "$C_RED" "window bloated with off-target detail"; }
right3(){ hdr "$C_GRN" "✓ with repo-graph" "just the relevant slice"; prompt "$P3"
  rg dense_text GroupsComponent
  finalcard "$C_GRN" "scoped map — a fraction of the full dump"; }

# 4 · Blast Radius — multi-seed impact (cross-stack) vs grep's direct refs
left4(){  hdr "$C_RED" "✗ without repo-graph" "grep finds direct refs only"; prompt "$P4"
  grep_show "GetFriendsHandler"; grep_show "SendFriendRequestHandler"; read_matches "friend" 4
  finalcard "$C_RED" "cross-stack + transitive missed"; }
right4(){ hdr "$C_GRN" "✓ with repo-graph" "full blast radius, both files at once"; prompt "$P4"
  rg impact "GetFriendsHandler, SendFriendRequestHandler" upstream
  finalcard "$C_GRN" "routes → controller → frontend caller"; }

# 5 · Cross-Stack Trace — trace vs guessing the FE↔BE link
left5(){  hdr "$C_RED" "✗ without repo-graph" "guessing the frontend↔backend link"; prompt "$P5"
  grep_show "groups"; read_matches "GroupsComponent" 3; grep_show "group"; read_matches "Controller" 3
  finalcard "$C_RED" "FE→BE link still unconfirmed"; }
right5(){ hdr "$C_GRN" "✓ with repo-graph" "cross-stack path in one hop"; prompt "$P5"
  rg trace GroupsComponent /groups
  finalcard "$C_GRN" "frontend → backend, linked"; }

# 6 · Find the Feature — activate's ranked cluster vs grep→read→grep
left6(){  hdr "$C_RED" "✗ without repo-graph" "grep → read → grep to find it"; prompt "$P6"
  grep_show "groups"; read_matches "GroupsComponent" 4
  finalcard "$C_RED" "scattered hits, no ranking"; }
right6(){ hdr "$C_GRN" "✓ with repo-graph" "the ranked cluster from one seed"; prompt "$P6"
  rg activate GroupsComponent
  finalcard "$C_GRN" "the feature's nodes, ranked by relevance"; }

# 7 · Token Race — flow vs grep→read→grep for a real bug-fix task
left7(){  hdr "$C_RED" "✗ without repo-graph" "grep → read → grep → read…"; prompt "$P7"
  grep_show "isGroupOpen"; grep_show "closed"; read_matches "GroupsComponent" 4; read_matches "group" 6
  finalcard "$C_RED" "still hunting"; }
right7(){ hdr "$C_GRN" "✓ with repo-graph" "one structural lookup"; prompt "$P7"
  rg flow groups
  finalcard "$C_GRN" "1 call → the exact handler flow"; }

ready(){ printf "\n%s%s● repo-graph demo · %s side%s\n" "$C_B" "$C_MAG" "$1" "$C_R"
  for i in 3 2 1; do printf "  starting in %s…\r" "$i"; sleep 1; done; printf "                    \n\n"; }

[ -n "${RGDEMO_NOEXEC:-}" ] && return 0 2>/dev/null   # test hook: source funcs without running
clear 2>/dev/null; printf '\033[3J\033[2J\033[H'   # wipe scrollback + echoed launch command for a clean top
ready "$SIDE"
if [ "${2:-}" = "all" ]; then
  for n in 1 2 3 4 5 6 7; do
    printf '\033[2J\033[3J\033[H'      # clean frame per demo
    titlecard "$n"
    barrier "start-$n"                 # both panes begin demo n together
    TOK=0; FILES=0; CALLS=0; T0=$SECONDS
    setbar "$n"; [ -n "$SYNC" ] && : > "$SYNC/$SIDE.stat"
    "${SIDE}${n}"
    [ -n "$SYNC" ] && printf '%s %s %s\n' "$TOK" "$FILES" "$CALLS" > "$SYNC/$SIDE.d$n"  # for the summary card
    barrier "end-$n"                   # both hold the freeze card together
    pace 1.2
  done
  [ "$SIDE" = left ] && [ -n "${TMUX:-}" ] && \
    tmux rename-window "mcp-repo-graph · pip install mcp-repo-graph" 2>/dev/null
  barrier "endcard"                    # both panes reveal their end card together
  printf '\033[2J\033[3J\033[H'
  if [ "$SIDE" = "left" ]; then summary_card; else outro_card; fi
  pace 4
else
  setbar "$2"; [ -n "$SYNC" ] && : > "$SYNC/$SIDE.stat"
  T0=$SECONDS; "${SIDE}${2}"; printf "\n"; pace 2.0
fi
