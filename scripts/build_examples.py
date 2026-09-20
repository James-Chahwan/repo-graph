"""Regenerate examples/ as real tool transcripts against the current engine.

Each example is genuine output from the six MCP tools run over a freshly cloned
upstream repo — not hand-written. Run it after an engine release so the published
transcripts match what users actually get:

    python3 scripts/build_examples.py            # clones into /tmp, writes examples/
    python3 scripts/build_examples.py --keep     # reuse existing clones

The engine banner is stamped with this package's version, because a local
pre-release wheel self-reports the previous number until the engine is bumped.
"""
import os, re, sys, time, json, shutil, subprocess, tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "examples"
CLONES = Path("/tmp/exrepos")
KEEP = "--keep" in sys.argv
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
REPOS = [
    ("fastapi", "FastAPI", "Python", "https://github.com/fastapi/fastapi",
     "routes → handlers → data"),
    ("gin", "Gin", "Go", "https://github.com/gin-gonic/gin", "HTTP routing"),
    ("hono", "Hono", "TypeScript", "https://github.com/honojs/hono", "edge routes"),
    ("nestjs", "NestJS", "TypeScript", "https://github.com/nestjs/nest", "modules / DI"),
]
stats = {}


def stamp(text: str) -> str:
    """Pin the engine banner to the release version (a pre-release wheel reports
    the previous number until the engine itself is bumped)."""
    return re.sub(r"glia-py \d+\.\d+\.\d+", f"glia-py {VERSION}", text)


CLONES.mkdir(parents=True, exist_ok=True)
for slug, _t, _l, url, _b in REPOS:
    dest = CLONES / slug
    if dest.is_dir() and KEEP:
        continue
    shutil.rmtree(dest, ignore_errors=True)
    print(f"cloning {url} ...")
    subprocess.run(["git", "clone", "--depth", "1", "-q", url + ".git", str(dest)],
                   check=True, timeout=600)

for slug, title, lang, url, blurb in REPOS:
    repo = str(CLONES / slug)
    if not os.path.isdir(repo):
        print(f"SKIP {slug}"); continue
    os.environ["REPO_GRAPH_REPO"] = repo; os.environ["REPO_GRAPH_WATCH"] = "0"
    for m in [k for k in list(sys.modules) if k.startswith("repo_graph")]:
        del sys.modules[m]
    import repo_graph.server as S
    S.REPO_PATH = repo; S._graph = None
    import glia_py
    shutil.rmtree(glia_py.default_gmap_dir(repo), ignore_errors=True)
    t0 = time.time(); glia_py.generate(repo, incremental=False).save_to_default(repo)
    cold = time.time() - t0
    t1 = time.time(); g = S.get_graph(); warm = time.time() - t1
    pg = g.pygraph

    # a seed worth showing: prefer an entry point with a real flow
    flows = sorted(g.flows.items(), key=lambda kv: -(kv[1].get("reach") or 0))
    seed_flow = flows[0][1] if flows else None
    seed_name = (seed_flow or {}).get("entry", {}).get("name") if seed_flow else None
    if not seed_name:
        seed_name = next(n["name"] for n in g.nodes.values()
                         if n.get("kind") in ("function", "method"))

    # a symbol with a real blast radius
    impact_seed = None
    for n in g.nodes.values():
        if n.get("kind") not in ("function", "method", "class"):
            continue
        try:
            env = pg.blast_radius([n["qname"]], "both", 3, None, False)
        except Exception:
            continue
        if len(env.get("results") or []) >= 5:
            impact_seed = n; break

    stats[slug] = dict(
        nodes=pg.node_count(), edges=pg.edge_count(), cross=pg.cross_edge_count(),
        flows=len(g.flows), cold=cold, warm=warm,
        entry=sum(1 for n in g.nodes.values() if n.get("entry")),
        dead=sum(1 for n in g.nodes.values() if n.get("live") is False),
        roles=sum(1 for n in g.nodes.values() if n.get("roles")),
    )

    blocks = [("orient", "orient()", S.orient(budget=2600))]
    blocks.append((f"find", f'find("{seed_name}")', S.find(seed_name, top_k=6, budget=1400)))
    if impact_seed:
        blocks.append(("impact", f'impact("{impact_seed["name"]}")',
                       S.impact(impact_seed["qname"], depth=3, top_k=8, budget=1600)))
    blocks.append(("trace", f'trace("{seed_name}")', S.trace(seed_name, budget=1600)))

    d = OUT / slug
    for old in d.rglob("*"):
        if old.is_file(): old.unlink()
    for old in sorted(d.rglob("*"), reverse=True):
        if old.is_dir(): old.rmdir()
    d.mkdir(parents=True, exist_ok=True)

    st = stats[slug]
    body = [f"# {title} — what repo-graph sees", "",
            f"[{url}]({url}) · {lang} · {blurb}", "",
            "Real output from the six tools, captured against the current engine. "
            "This is what your assistant gets **before it opens a single file**.", "",
            "| | |", "|---|---|",
            f"| Nodes | {st['nodes']:,} |", f"| Edges | {st['edges']:,} |",
            f"| Cross-stack edges | {st['cross']:,} |",
            f"| Entry points | {st['entry']:,} |",
            f"| Feature flows | {st['flows']:,} |",
            f"| Cold build (full reparse) | {st['cold']:.1f}s |",
            f"| Warm load (cached graph) | {st['warm']:.2f}s |", ""]
    for _tool, call, out in blocks:
        body += [f"## `{call}`", "", "```", stamp(out.rstrip()), "```", ""]
    body += ["---", "",
             "## Reproduce", "", "```bash",
             f"git clone --depth 1 {url}.git /tmp/{slug}",
             f"uvx mcp-repo-graph --repo /tmp/{slug}",
             "```", "",
             "The graph is cached in `/tmp/%s/.glia/graph/` — a sharded binary `.gmap`, "
             "rebuilt automatically when the source changes." % slug, ""]
    (d / "README.md").write_text("\n".join(body))
    print(f"{slug}: {st['nodes']} nodes, {st['edges']} edges, {st['flows']} flows, "
          f"{st['cold']:.1f}s cold / {st['warm']:.2f}s warm -> {d}/README.md")

(CLONES / "stats.json").write_text(json.dumps(stats, indent=2))
print(f"\nwrote {len(stats)} example(s) to {OUT}")
