# repo-graph side-by-side demos

One command per demo → a tmux split you screen-record once, then cut per demo.

- **LEFT** pane = *without repo-graph* — real `grep`/`cat` on the target repo.
- **RIGHT** pane = *with repo-graph* — real tool output (`orient`/`find`/`impact`/`trace`/`read`).
- Counters are **grounded in real bytes** (file size ÷ 4 ≈ tokens) — nothing invented.
- Each demo = a **cited** dev-with-LLM pain point (Sonar/Uvik/Cerbos 2026).

## Run

```bash
scripts/demo/run.sh 1     # 1 Ground the Edit      — "almost right" (66%)  → find + read
scripts/demo/run.sh 2     # 2 Debug a Stack Trace   — slow debugging (45%)  → find kind=stacktrace
scripts/demo/run.sh 3     # 3 Context Rot           — quality decays         → orient seed=
scripts/demo/run.sh 4     # 4 Blast Radius          — off-target changes     → multi-seed impact
scripts/demo/run.sh 5     # 5 Cross-Stack Trace     — FE↔BE disconnect       → trace
scripts/demo/run.sh 6     # 6 Find the Feature      — context retrieval (38%)→ find expand=true
scripts/demo/run.sh 7     # 7 Empty ≠ Safe          — the silent miss        → impact, absence
scripts/demo/run.sh 8     # 8 Safe to Delete?       — grep undercounts       → impact backward
scripts/demo/run.sh all   # all eight, lockstep, + summary/outro end-cards
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
- Traversal is deterministic since glia 0.5.0, so `rg()` no longer retries a
  call until it returns something — the engine bug that needed that is fixed.
