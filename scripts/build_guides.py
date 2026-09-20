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
  /* Design language shared with quokk4.net (quokka-stack quokka_web/src/styles.css). */
  :root{--bg:#f3f1f2;
        --card:linear-gradient(158deg,rgba(251,250,255,.88),rgba(246,248,252,.7));
        --card-strong:rgba(247,246,252,.94);
        --line:rgba(129,140,167,.28);--line-strong:rgba(119,130,157,.4);
        --fg:#1f2532;--head:#1a2233;--sub:#4b5770;--dim:#5e687c;
        --accent:#6254c8;--accent-warm:#c2703f;
        --grad:linear-gradient(138deg,#9b8ff2 0%,#f2a37f 100%);
        --radius:20px;--shadow-card:0 8px 20px rgba(127,136,162,.1);
        --display:"Fraunces","Iowan Old Style","Palatino Linotype",serif;
        --body:"Space Grotesk","Avenir Next","Segoe UI",sans-serif;
        --mono:"SFMono-Regular",ui-monospace,"JetBrains Mono","Source Code Pro",Menlo,Consolas,monospace;}
  *{box-sizing:border-box} html{scroll-behavior:smooth}
  body{margin:0;min-height:100vh;background:var(--bg);color:var(--fg);font-family:var(--body);
       line-height:1.7;-webkit-font-smoothing:antialiased;font-size:16px}
  body::before{content:"";position:fixed;inset:0;z-index:0;pointer-events:none;
    background:radial-gradient(circle at 50% 14%,rgba(251,248,255,.92),rgba(246,244,245,.88) 48%,rgba(237,238,241,.9) 100%)}
  body>*{position:relative;z-index:1}
  a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
  .wrap{width:min(760px,calc(100% - 3rem));margin:0 auto}
  .top{border-bottom:1px solid var(--line)}
  .top .wrap{display:flex;align-items:center;justify-content:space-between;height:60px}
  .brand{font-weight:700;color:var(--head);font-family:var(--display)}
  .brand b{background:var(--grad);-webkit-background-clip:text;background-clip:text;
           -webkit-text-fill-color:transparent}
  .top nav a{color:var(--dim);margin-left:18px;font-size:.88rem}
  .top nav a:hover{color:var(--fg)}
  article{padding:52px 0 24px}
  .eyebrow{color:var(--dim);font-size:.72rem;letter-spacing:.16em;text-transform:uppercase;margin:0 0 12px}
  h1{font-family:var(--display);font-size:clamp(2rem,4.8vw,3rem);line-height:1.05;margin:0 0 16px;
     letter-spacing:-.025em;color:var(--head);font-weight:700}
  .lede{color:var(--sub);font-size:1.08rem;margin:0 0 30px}
  h2{font-family:var(--display);font-size:1.45rem;margin:38px 0 10px;color:#253248;
     font-weight:600;letter-spacing:-.02em;line-height:1.2}
  h3{font-family:var(--display);font-size:1.08rem;margin:26px 0 8px;color:#253248;font-weight:600}
  p{margin:0 0 15px} ul,ol{margin:0 0 15px;padding-left:22px} li{margin:5px 0}
  strong{color:var(--head);font-weight:700}
  code{background:var(--card-strong);border:1px solid var(--line);border-radius:6px;
       padding:1px 6px;font-family:var(--mono);font-size:.84rem}
  pre{background:var(--card-strong);border:1px solid var(--line);border-radius:14px;
      padding:16px 18px;overflow:auto;margin:16px 0;box-shadow:var(--shadow-card)}
  pre code{background:none;border:0;padding:0;font-size:.8rem;color:var(--fg);line-height:1.55}
  table{border-collapse:collapse;width:100%;margin:16px 0;font-size:.9rem}
  th,td{border:1px solid var(--line);padding:9px 13px;text-align:left}
  th{color:#253248;font-weight:600;background:var(--card-strong)}
  blockquote{border-left:3px solid;border-image:var(--grad) 1;margin:16px 0;padding:2px 18px;color:var(--sub)}
  hr{border:0;border-top:1px solid var(--line);margin:30px 0}
  footer{border-top:1px solid var(--line);padding:30px 0 64px;color:var(--dim);font-size:.85rem}
  footer .cmd{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
              padding:12px 16px;margin:0 0 14px;color:var(--fg);font-family:var(--mono);
              box-shadow:var(--shadow-card)}
  footer .cmd b{color:var(--accent)}
  .cards{display:grid;gap:14px;margin:18px 0}
  .card{display:block;background:var(--card);border:1px solid var(--line);
        border-radius:var(--radius);padding:18px 20px;color:var(--fg);box-shadow:var(--shadow-card)}
  .card:hover{border-color:var(--line-strong);text-decoration:none}
  .card h3{margin:0 0 4px;color:#253248} .card p{margin:0;color:var(--sub);font-size:.9rem}
  .sec{color:var(--accent-warm);font-size:.72rem;letter-spacing:.16em;text-transform:uppercase;margin:30px 0 4px}
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
<meta name="theme-color" content="#f3f1f2">
<meta property="og:type" content="article">
<meta property="og:site_name" content="repo-graph">
<meta property="og:title" content="__TITLE__">
<meta property="og:description" content="__DESC__">
<meta property="og:url" content="__CANON__">
<meta property="og:image" content="https://repo-graph.com/og.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&family=Space+Grotesk:wght@400;500;700&display=swap">
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
<meta name="theme-color" content="#f3f1f2">
<meta property="og:type" content="website">
<meta property="og:title" content="repo-graph guides">
<meta property="og:description" content="Practical how-to guides and workflows for repo-graph.">
<meta property="og:url" content="https://repo-graph.com/guides/">
<meta property="og:image" content="https://repo-graph.com/og.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&family=Space+Grotesk:wght@400;500;700&display=swap">
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
