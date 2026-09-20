#!/usr/bin/env python3
"""Encode the web-sized clips the site serves, from the master recordings.

Masters live in scripts/demo/shorts/ (gitignored, regenerate with
`node scripts/demo/capture-shorts.cjs`). This writes small h264 + poster pairs
into docs/clips/, which DO ship — that's the `!docs/clips/*.mp4` exception in
.gitignore.

    python3 scripts/build_clips.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "scripts" / "demo" / "shorts"
OUT = ROOT / "docs" / "clips"

#: (source stem, published name, caption, poster timestamp)
#: Portrait 1080x1920 social cuts, re-rendered from docs/wow-*.html so the
#: commands on screen match the shipped tool surface.
SHORTS = [
    # 0.5.0 feature demos first — these are what's new
    ("honest",        "honest",        "An empty answer that explains itself", "00:00:09"),
    ("wholediff",     "wholediff",     "A whole diff in one call",             "00:00:09"),
    ("paths",         "paths",         "Every route the call takes, ranked",   "00:00:09"),
    ("constellation", "constellation", "Your whole codebase, as a graph",      "00:00:07"),
    ("dayone",        "dayone",        "Day one on 80,000 unfamiliar lines",   "00:00:06"),
    ("roulette",      "roulette",      "312 grep hits → 4, ranked",            "00:00:07"),
    ("tectonic",      "tectonic",      "A stacktrace is just coordinates",     "00:00:07"),
    ("typed-blast",   "typed-blast",   "Rename one field — see everything it touches", "00:00:07"),
    ("monorepo",      "monorepo",      "Four apps, and how they actually connect",     "00:00:07"),
    ("polyglot",      "polyglot",      "Eight languages, one graph",                   "00:00:07"),
    ("twomaps",       "twomaps",       "Embeddings drift. Run it twice, get two answers", "00:00:09"),
    ("skyline",       "skyline",       "One feature lights its street",                "00:00:07"),
    ("receipt",       "receipt",       "One line changed. Here is the receipt",        "00:00:08"),
    ("invisible",     "invisible",     "You just ask. It navigates for you",           "00:00:07"),
    ("fresh",         "fresh",         "You changed one line, not the whole repo",     "00:00:07"),
]
# Deliberately NOT shipped: `yours` (demos the config.yaml escape hatch, which the
# 0.5.0 engine no longer reads) and the clip-* terminal cuts (kept for social).

WIDE = ("explainer-wide", "explainer", "00:00:06")


def run(args: list[str]) -> None:
    subprocess.run(args, check=True, capture_output=True)


def encode(src: Path, dest: Path, width: int, crf: int = 31) -> None:
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
         "-vf", f"scale={width}:-2", "-c:v", "libx264", "-crf", str(crf),
         "-preset", "slow", "-profile:v", "high", "-pix_fmt", "yuv420p",
         "-an", "-movflags", "+faststart", str(dest)])


def poster(src: Path, dest: Path, at: str, width: int) -> None:
    run(["ffmpeg", "-y", "-v", "error", "-ss", at, "-i", str(src),
         "-vf", f"scale={width}:-2", "-frames:v", "1", "-q:v", "4", str(dest)])


def kb(p: Path) -> int:
    return p.stat().st_size // 1024


def main() -> int:
    if not SRC.is_dir():
        print(f"no masters at {SRC} — run: node scripts/demo/capture-shorts.cjs", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0

    stem, name, at = WIDE
    src = SRC / f"{stem}.mp4"
    if src.exists():
        encode(src, OUT / f"{name}.mp4", 1280, crf=30)
        poster(src, OUT / f"{name}.jpg", at, 1280)
        total += kb(OUT / f"{name}.mp4")
        print(f"  {name+'.mp4':<22} {kb(OUT / f'{name}.mp4'):>5} KB  (landscape hero)")

    for stem, name, _caption, at in SHORTS:
        src = SRC / f"{stem}.mp4"
        if not src.exists():
            print(f"  ! missing master: {src.name}", file=sys.stderr)
            continue
        encode(src, OUT / f"{name}.mp4", 540)
        poster(src, OUT / f"{name}.jpg", at, 540)
        total += kb(OUT / f"{name}.mp4")
        print(f"  {name+'.mp4':<22} {kb(OUT / f'{name}.mp4'):>5} KB")

    print(f"\n{total} KB of video in docs/clips/ — served by the site")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
