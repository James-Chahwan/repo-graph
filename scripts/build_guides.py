#!/usr/bin/env python3
"""Render guides/*.md into styled HTML pages under docs/guides/ for repo-graph.com.

Matches the landing page theme (black + pastel green). Run after editing any
guide:  python3 scripts/build_guides.py
"""
import re
import pathlib
import markdown

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "guides"
OUT = ROOT / "docs" / "guides"
OUT.mkdir(parents=True, exist_ok=True)
SITE = "https://repo-graph.com"

# index order + grouping
START = ["install", "why-repo-graph"]
WORKFLOWS = ["cross-stack-trace", "impact-before-refactor",
             "onboard-new-codebase", "find-the-feature", "daily-driver"]
ORDER = START + WORKFLOWS

CSS = """
  :root{--bg:#0a0a0a;--panel:#101311;--line:#1c241e;--fg:#cfe6d2;--dim:#7e9384;
        --grn:#8effc0;--grn2:#a8ffd0;--red:#e88a8a;
        --mono:"SFMono-Regular",ui-monospace,"JetBrains Mono","Source Code Pro",Menlo,Consolas,monospace;}
  *{box-sizing:border-box} html{scroll-behavior:smooth}
  body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--mono);line-height:1.65;
       -webkit-font-smoothing:antialiased;font-size:15px}
  a{color:var(--grn);text-decoration:none} a:hover{text-decoration:underline}
  .wrap{max-width:760px;margin:0 auto;padding:0 24px}
  .top{border-bottom:1px solid var(--line)}
  .top .wrap{display:flex;align-items:center;justify-content:space-between;height:56px}
  .brand{font-weight:700;color:var(--fg)} .brand b{color:var(--grn)}
  .top nav a{color:var(--dim);margin-left:18px;font-size:14px}
  .top nav a:hover{color:var(--grn)}
  article{padding:48px 0 24px}
  .eyebrow{color:var(--dim);font-size:12px;letter-spacing:.16em;text-transform:uppercase;margin:0 0 12px}
  h1{font-size:clamp(26px,4.5vw,38px);line-height:1.2;margin:0 0 14px;letter-spacing:-.01em}
  .lede{color:var(--dim);font-size:17px;margin:0 0 28px}
  h2{font-size:20px;margin:34px 0 10px;color:var(--grn)}
  h3{font-size:16px;margin:24px 0 8px}
  p{margin:0 0 14px} ul,ol{margin:0 0 14px;padding-left:22px} li{margin:4px 0}
  strong{color:var(--grn2)}
  code{background:#0c0f0d;border:1px solid var(--line);border-radius:5px;padding:1px 6px;font-size:13.5px}
  pre{background:#0c0f0d;border:1px solid var(--line);border-radius:10px;padding:14px 16px;overflow:auto;margin:14px 0}
  pre code{background:none;border:0;padding:0;font-size:13.5px;color:var(--fg)}
  table{border-collapse:collapse;width:100%;margin:14px 0;font-size:14px}
  th,td{border:1px solid var(--line);padding:8px 12px;text-align:left}
  th{color:var(--grn);font-weight:600}
  blockquote{border-left:2px solid var(--line);margin:14px 0;padding:2px 16px;color:var(--dim)}
  hr{border:0;border-top:1px solid var(--line);margin:28px 0}
  footer{border-top:1px solid var(--line);padding:28px 0 64px;color:var(--dim);font-size:13px}
  footer .cmd{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:0 0 14px;color:var(--fg)}
  footer .cmd b{color:var(--grn)}
  .cards{display:grid;gap:14px;margin:18px 0}
  .card{display:block;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px;color:var(--fg)}
  .card:hover{border-color:var(--grn);text-decoration:none}
  .card h3{margin:0 0 4px;color:var(--fg)} .card p{margin:0;color:var(--dim);font-size:14px}
  .sec{color:var(--grn);font-size:12px;letter-spacing:.16em;text-transform:uppercase;margin:28px 0 4px}
"""

TOP = (
    '<div class="top"><div class="wrap">'
    '<a class="brand" href="/"><b>repo</b>-graph</a>'
    '<nav><a href="/guides/">Guides</a><a href="/#install">Install</a>'
    '<a href="https://github.com/James-Chahwan/repo-graph">GitHub</a></nav>'
    '</div></div>'
)

FOOT = (
    '<footer><div class="wrap">'
    '<div class="cmd">$ <b>pip install mcp-repo-graph</b></div>'
    '<a href="/guides/">‹ All guides</a> &nbsp;·&nbsp; '
    '<a href="https://github.com/James-Chahwan/repo-graph">GitHub</a> &nbsp;·&nbsp; '
    'repo-graph.com'
    '</div></footer>'
)

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · repo-graph</title>
<meta name="description" content="__DESC__">
<link rel="canonical" href="__CANON__">
<meta name="theme-color" content="#0a0a0a">
<meta property="og:type" content="article">
<meta property="og:site_name" content="repo-graph">
<meta property="og:title" content="__TITLE__">
<meta property="og:description" content="__DESC__">
<meta property="og:url" content="__CANON__">
<meta property="og:image" content="https://repo-graph.com/og.png">
<meta name="twitter:card" content="summary_large_image">
<style>__CSS__</style>
</head>
<body>
__TOP__
<article><div class="wrap">
<p class="eyebrow">__KIND__</p>
<h1>__TITLE__</h1>
<p class="lede">__DESC__</p>
__BODY__
</div></article>
__FOOT__
</body>
</html>
"""

INDEX = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Guides · repo-graph</title>
<meta name="description" content="How-to guides for repo-graph: install in any AI client, trace cross-stack, impact analysis, onboard a new codebase, and more.">
<link rel="canonical" href="https://repo-graph.com/guides/">
<meta name="theme-color" content="#0a0a0a">
<meta property="og:type" content="website">
<meta property="og:title" content="repo-graph guides">
<meta property="og:description" content="Practical how-to guides and workflows for repo-graph.">
<meta property="og:url" content="https://repo-graph.com/guides/">
<meta property="og:image" content="https://repo-graph.com/og.png">
<style>__CSS__</style>
</head>
<body>
__TOP__
<article><div class="wrap">
<h1>Guides</h1>
<p class="lede">How to install repo-graph and use it in real coding workflows. Short, practical, copy-paste.</p>
__CARDS__
</div></article>
__FOOT__
</body>
</html>
"""

KIND = {
    "why-repo-graph": "Blog post",
    "install": "Setup guide",
}


def parse_front(text):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    fm, body = m.group(1), m.group(2)
    meta = {}
    for line in fm.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if k == "tags":
            v = [t.strip() for t in v.strip("[]").split(",") if t.strip()]
        else:
            v = v.strip().strip('"').strip("'")
        meta[k] = v
    return meta, body


def esc(s):
    return s.replace("&", "&amp;").replace('"', "&quot;")


def build():
    items = []
    for slug in ORDER:
        p = SRC / f"{slug}.md"
        if not p.exists():
            print(f"  skip (missing): {slug}")
            continue
        meta, body = parse_front(p.read_text())
        title = meta.get("title", slug)
        desc = meta.get("description", "")
        body = re.sub(r"^\s*#\s+.*\n", "", body, count=1)  # drop leading H1 (template has the title)
        html_body = markdown.markdown(body, extensions=["fenced_code", "tables", "sane_lists"])
        canon = f"{SITE}/guides/{slug}"
        page = (PAGE
                .replace("__CSS__", CSS).replace("__TOP__", TOP).replace("__FOOT__", FOOT)
                .replace("__KIND__", KIND.get(slug, "How-to guide"))
                .replace("__BODY__", html_body)
                .replace("__TITLE__", esc(title)).replace("__DESC__", esc(desc))
                .replace("__CANON__", canon))
        (OUT / f"{slug}.html").write_text(page)
        items.append((slug, title, desc))
        print(f"  wrote docs/guides/{slug}.html")

    def cards(slugs):
        out = []
        for slug, title, desc in [it for it in items if it[0] in slugs]:
            out.append(f'<a class="card" href="/guides/{slug}"><h3>{esc(title)}</h3><p>{esc(desc)}</p></a>')
        return "\n".join(out)

    cards_html = (
        '<p class="sec">Start here</p><div class="cards">' + cards(START) + "</div>"
        '<p class="sec">Workflows</p><div class="cards">' + cards(WORKFLOWS) + "</div>"
    )
    idx = (INDEX
           .replace("__CSS__", CSS).replace("__TOP__", TOP).replace("__FOOT__", FOOT)
           .replace("__CARDS__", cards_html))
    (OUT / "index.html").write_text(idx)
    print(f"  wrote docs/guides/index.html ({len(items)} guides)")


if __name__ == "__main__":
    build()
