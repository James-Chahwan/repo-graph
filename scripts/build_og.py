#!/usr/bin/env python3
"""Render docs/og.png — the 1200x630 social card for repo-graph.com.

Uses the same design language as the site and quokk4.net: the cozy radial wash,
Fraunces for display, Space Grotesk for body, and the periwinkle->peach accent.

Fonts are fetched from google/fonts on first run and cached in /tmp/ogfonts.
    python3 scripts/build_og.py
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "og.png"
FONTS = Path("/tmp/ogfonts")
SRC = {
    "Fraunces.ttf": "https://github.com/google/fonts/raw/main/ofl/fraunces/"
                    "Fraunces%5BSOFT%2CWONK%2Copsz%2Cwght%5D.ttf",
    "SpaceGrotesk.ttf": "https://github.com/google/fonts/raw/main/ofl/spacegrotesk/"
                        "SpaceGrotesk%5Bwght%5D.ttf",
}

W, H = 1200, 630
BG = (243, 241, 242)
HEAD = (26, 34, 51)
SUB = (75, 87, 112)
DIM = (94, 104, 124)
LINE = (203, 208, 219)
CARD = (247, 246, 252)
G0, G1 = (155, 143, 242), (242, 163, 127)   # accent gradient stops


def font(name: str, size: int, wght: float) -> ImageFont.FreeTypeFont:
    FONTS.mkdir(exist_ok=True)
    path = FONTS / name
    if not path.exists():
        subprocess.run(["curl", "-sL", SRC[name], "-o", str(path)], check=True, timeout=120)
    f = ImageFont.truetype(str(path), size)
    try:
        axes = [a["name"].decode() if isinstance(a["name"], bytes) else str(a["name"])
                for a in f.get_variation_axes()]
        vals = []
        for ax in axes:
            low = ax.lower()
            if "weight" in low or low == "wght":
                vals.append(wght)
            elif "optical" in low or low == "opsz":
                vals.append(min(144, max(9, size)))
            elif "soft" in low:
                vals.append(0)
            elif "wonk" in low:
                vals.append(0)
            else:
                vals.append(0)
        f.set_variation_by_axes(vals)
    except Exception:
        pass
    return f


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

# cozy radial wash: bright near the top-centre, settling into the warm grey
cx, cy, maxr = W * 0.5, H * 0.14, (W ** 2 + H ** 2) ** 0.5 * 0.72
for y in range(H):
    # row-wise approximation is enough for a soft, vertical-dominant wash
    dy = (y - cy) / maxr
    t = min(1.0, abs(dy) * 1.55)
    d.line([(0, y), (W, y)], fill=lerp((251, 248, 255), (236, 237, 241), t))

# accent bar
for x in range(W):
    d.line([(x, 0), (x, 7)], fill=lerp(G0, G1, x / W))

pad = 84
f_title = font("Fraunces.ttf", 104, 700)
f_tag = font("SpaceGrotesk.ttf", 34, 500)
f_sub = font("SpaceGrotesk.ttf", 25, 400)
f_mono = font("SpaceGrotesk.ttf", 27, 500)

y = 118
d.text((pad, y), "repo-graph", font=f_title, fill=HEAD)

# gradient underline under the wordmark
tw = d.textlength("repo-graph", font=f_title)
uy = y + 140   # below the descenders of 'p' and 'g'
for x in range(int(tw)):
    d.line([(pad + x, uy), (pad + x, uy + 7)], fill=lerp(G0, G1, x / max(tw, 1)))

y = uy + 44
d.text((pad, y), "A structural map of your codebase, for AI coding assistants.",
       font=f_tag, fill=SUB)
y += 52
d.text((pad, y), "The model navigates to the right files instead of reading everything.",
       font=f_sub, fill=DIM)

# install command card
cy0 = H - 168
cw = W - pad * 2
d.rounded_rectangle([pad, cy0, pad + cw, cy0 + 78], radius=22, fill=CARD, outline=LINE, width=1)
d.text((pad + 28, cy0 + 24), "pip install mcp-repo-graph", font=f_mono, fill=HEAD)

foot = "repo-graph.com   ·   6 MCP tools   ·   20+ languages   ·   frontend to backend"
d.text((pad, H - 62), foot, font=font("SpaceGrotesk.ttf", 22, 400), fill=DIM)

OUT.parent.mkdir(parents=True, exist_ok=True)
img.save(OUT, optimize=True)
print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB, {W}x{H})")
