# Privacy Policy

repo-graph runs on your machine and is built to keep your code there.

- **Telemetry / analytics:** None. No tracking, no update checks, no phone-home.
- **Data collection & sharing:** None. Your source code and graph data are never
  sent to repo-graph, its author, or any third party.
- **Local processing & storage:** Scanning and graph-building happen locally; the
  structural graph is cached in your project's `.ai/repo-graph/` directory and
  stays on your device.
- **Network access — only two cases, both user-initiated:**
  1. **Installation.** `uvx` / `pip` downloads the package and its prebuilt engine
     wheel from PyPI — the standard Python install path.
  2. **Git-URL targets.** If you pass a git URL to `--repo`
     (e.g. `--repo https://github.com/org/repo`), repo-graph runs `git clone`
     against the URL **you** specified. It contacts only the remote you chose;
     nothing is sent to repo-graph or its author. Pointing `--repo` at a local
     path (the default) makes zero network calls.
- **Third-party sharing:** None.
- **Data retention:** The local cache persists until you delete it — fully under
  your control.
- **Contact:** https://github.com/James-Chahwan/repo-graph/issues

_Last updated: 2026-06-06._
