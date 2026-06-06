# repo-graph side-by-side demos

One command per demo → a tmux split you screen-record once, then cut per demo.

- **LEFT** pane = *without repo-graph* — real `grep`/`cat` on the target repo.
- **RIGHT** pane = *with repo-graph* — real tool output (`flow`/`trace`/`impact`/`dense_text`).
- Counters are **grounded in real bytes** (file size ÷ 4 ≈ tokens) — nothing invented.

## Run

```bash
scripts/demo/run.sh 1     # 1 Token Race
scripts/demo/run.sh 2     # 2 Files Opened
scripts/demo/run.sh 3     # 3 Cross-Stack Trace
scripts/demo/run.sh 4     # 4 Context Window
scripts/demo/run.sh 5     # 5 Blast Radius
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
