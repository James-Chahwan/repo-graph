# repo-graph side-by-side demos

One command per demo → a tmux split you screen-record once, then cut per demo.

- **LEFT** pane = *without repo-graph* — real `grep`/`cat` on the target repo.
- **RIGHT** pane = *with repo-graph* — real tool output (`find`/`read`/`locate`/`impact`/`trace`/`activate`/`dense_text`/`flow`).
- Counters are **grounded in real bytes** (file size ÷ 4 ≈ tokens) — nothing invented.
- Each demo = a **cited** dev-with-LLM pain point (Sonar/Uvik/Cerbos 2026).

## Run

```bash
scripts/demo/run.sh 1     # 1 Ground the Edit      — "almost right" (66%)  → find + read
scripts/demo/run.sh 2     # 2 Debug a Stack Trace   — slow debugging (45%)  → locate + read
scripts/demo/run.sh 3     # 3 Context Rot           — quality decays         → scoped dense_text
scripts/demo/run.sh 4     # 4 Blast Radius          — off-target changes     → multi-seed impact
scripts/demo/run.sh 5     # 5 Cross-Stack Trace     — FE↔BE disconnect       → trace
scripts/demo/run.sh 6     # 6 Find the Feature      — context retrieval (38%)→ activate
scripts/demo/run.sh 7     # 7 Token Race            — context cost           → flow
scripts/demo/run.sh all   # all seven, lockstep, + summary/outro end-cards
```

Options:

```bash
DEMO_REPO=/path/to/cross-stack/repo   # default: /home/ivy/Code/quokka-stack
DEMO_SPEED=1.4                        # higher = slower typing/pacing
```

## Recording

1. Run `run.sh <n>`. Each pane shows a **3-second countdown** — start your recorder then.
2. Let it play to the freeze card (the stat box is the money-frame).
3. Detach with `Ctrl-b d`, or `tmux kill-session -t rgdemo`.

## Notes

- Requires `tmux`, the editable repo-graph install, and a real cross-stack repo.
- `run.sh` pre-warms the `.gmap` cache so right-pane calls are sub-second.
- `rg()` retries past a transient engine non-determinism where `impact`/`trace`
  occasionally return empty for a node that has results (a `repo-graph-py` bug to
  fix upstream — see the engine repo).
