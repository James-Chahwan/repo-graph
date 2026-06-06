#!/usr/bin/env bash
# One side of a side-by-side repo-graph demo.
#   pane.sh <left|right> <demo 1-5>
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

pace(){ awk "BEGIN{system(\"sleep \" $1*$SPEED)}" 2>/dev/null || sleep "$1"; }
commafy(){ printf "%s" "$1" | sed -E ':a;s/([0-9])([0-9]{3})($|[^0-9])/\1,\2\3/;ta'; }
cmd(){ printf "%s$ %s" "$C_DIM" "$C_R"; local s="$1" i; for ((i=0;i<${#s};i++)); do printf "%s" "${s:$i:1}"; sleep 0.012; done; printf "\n"; pace 0.15; }
note(){ printf "%s%s%s\n" "$C_DIM" "$1" "$C_R"; }
hdr(){ printf "%s%s  %s%s\n%s%s%s\n\n" "$C_B" "$1" "$2" "$C_R" "$C_DIM" "$3" "$C_R"; }
prompt(){ printf "%s┃ prompt: %s%s\n\n" "$C_CYN" "$1" "$C_R"; pace 0.5; }
tally_l(){ printf "   %s▸ %s files read · ~%s tokens%s\n" "$C_YEL" "$FILES" "$(commafy "$TOK")" "$C_R"; }
tally_r(){ printf "   %s▸ %s call · ~%s tokens%s\n" "$C_GRN" "$CALLS" "$(commafy "$TOK")" "$C_R"; }
card(){ local c="$1" rule="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  printf "\n%s%s%s\n" "$c" "$rule" "$C_R"
  printf "  %s%s%s%s\n" "$C_B" "$c" "$2" "$C_R"
  [ $# -ge 3 ] && printf "  %s%s%s\n" "$C_DIM" "$3" "$C_R"
  printf "%s%s%s\n" "$c" "$rule" "$C_R"; }

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
P1="Groups created recently show as closed; new groups should be open. Find & fix."
P3="Where does the frontend group action end up in the backend?"
P4="Get enough context to work confidently in this codebase."
P5="What breaks if I change GroupsComponent?"

left1(){  hdr "$C_RED" "✗ without repo-graph" "grep → read → grep → read…"; prompt "$P1"
  grep_show "isGroupOpen"; grep_show "closed"; read_matches "GroupsComponent" 4; read_matches "group" 6
  card "$C_RED" "~$(commafy "$TOK") tokens" "$FILES files read — still hunting"; }
right1(){ hdr "$C_GRN" "✓ with repo-graph" "one structural lookup"; prompt "$P1"
  rg flow groups
  card "$C_GRN" "~$(commafy "$TOK") tokens" "1 call → the exact handler flow"; }

left2(){  left1; }                                  # same scenario, framed on FILES
right2(){ right1; }
left3(){  hdr "$C_RED" "✗ without repo-graph" "guessing the frontend↔backend link"; prompt "$P3"
  grep_show "groups"; read_matches "GroupsComponent" 3; grep_show "group" ; read_matches "Controller" 3
  card "$C_RED" "~$(commafy "$TOK") tokens" "FE→BE link still unconfirmed"; }
right3(){ hdr "$C_GRN" "✓ with repo-graph" "cross-stack path in one hop"; prompt "$P3"
  rg trace GroupsComponent /groups
  card "$C_GRN" "~$(commafy "$TOK") tokens" "frontend → backend, linked"; }

left4(){  hdr "$C_RED" "✗ without repo-graph" "load files until you 'get it'"; prompt "$P4"
  read_biggest 16
  card "$C_RED" "~$(commafy "$TOK") tokens" "$FILES files — context near full"; }
right4(){ hdr "$C_GRN" "✓ with repo-graph" "the whole map, capped"; prompt "$P4"
  rg dense_text
  card "$C_GRN" "~$(commafy "$TOK") tokens" "whole-repo structure, 1 call"; }

left5(){  hdr "$C_RED" "✗ without repo-graph" "grep finds direct refs only"; prompt "$P5"
  grep_show "GroupsComponent"; read_matches "GroupsComponent" 3
  card "$C_RED" "~$(commafy "$TOK") tokens" "direct refs only — transitive missed"; }
right5(){ hdr "$C_GRN" "✓ with repo-graph" "full blast radius by tier"; prompt "$P5"
  rg impact GroupsComponent
  card "$C_GRN" "~$(commafy "$TOK") tokens" "complete downstream graph"; }

ready(){ printf "\n%s%s● repo-graph demo · %s side%s\n" "$C_B" "$C_MAG" "$1" "$C_R"
  for i in 3 2 1; do printf "  starting in %s…\r" "$i"; sleep 1; done; printf "                    \n\n"; }

ready "$1"
"${1}${2}"   # e.g. left1 / right3
printf "\n"; pace 2.0   # hold the freeze card as the final frame
