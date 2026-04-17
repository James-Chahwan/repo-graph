"""Clone repos and run generate() in isolated subprocesses, log JSONL results."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

WORKDIR = Path("/tmp/repo-graph-sweep")
RESULTS = Path(__file__).parent / "results.jsonl"
RUN_ONE = Path(__file__).parent / "run_one.py"

CLONE_TIMEOUT = 180  # 3 min per clone
GEN_TIMEOUT = 300    # 5 min per generate


def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def clone(repo_spec: str, dest: Path) -> tuple[bool, str]:
    """repo_spec is 'owner/name' or 'owner/name@branch'."""
    if "@" in repo_spec:
        slug, branch = repo_spec.split("@", 1)
        extra = ["-b", branch]
    else:
        slug, extra = repo_spec, []
    url = f"https://github.com/{slug}.git"
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", *extra, url, str(dest)],
            timeout=CLONE_TIMEOUT,
            capture_output=True,
            check=True,
        )
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "clone_timeout"
    except subprocess.CalledProcessError as e:
        return False, f"clone_failed: {e.stderr.decode()[-400:]}"


def run_generate(repo: Path) -> dict:
    try:
        proc = subprocess.run(
            [sys.executable, str(RUN_ONE), str(repo)],
            timeout=GEN_TIMEOUT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return {"ok": False, "error": f"exit {proc.returncode}", "stderr": proc.stderr[-2000:]}
        try:
            return json.loads(proc.stdout.strip().splitlines()[-1])
        except Exception as e:
            return {"ok": False, "error": f"bad_output: {e}", "stdout": proc.stdout[-1000:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "generate_timeout"}


def repo_size_mb(path: Path) -> float:
    try:
        out = subprocess.check_output(["du", "-sm", str(path)]).decode().split()[0]
        return float(out)
    except Exception:
        return -1


def sweep(repo_specs: list[str]):
    WORKDIR.mkdir(parents=True, exist_ok=True)
    # Load already-done to allow resume
    done = set()
    if RESULTS.exists():
        for line in RESULTS.read_text().splitlines():
            try:
                rec = json.loads(line)
                done.add(rec["repo_spec"])
            except Exception:
                pass
    log(f"starting sweep: {len(repo_specs)} repos total, {len(done)} already done")

    with RESULTS.open("a") as fh:
        for i, spec in enumerate(repo_specs, 1):
            if spec in done:
                log(f"[{i}/{len(repo_specs)}] skip (already done): {spec}")
                continue
            name = spec.split("@")[0].replace("/", "__")
            dest = WORKDIR / name
            # cleanup stale
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            log(f"[{i}/{len(repo_specs)}] cloning {spec}")
            ok, err = clone(spec, dest)
            rec = {"repo_spec": spec}
            if not ok:
                rec.update({"ok": False, "phase": "clone", "error": err})
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
                log(f"  clone failed: {err[:120]}")
                continue
            size = repo_size_mb(dest)
            rec["size_mb"] = size
            log(f"  generating (size={size}MB)")
            t0 = time.time()
            gen = run_generate(dest)
            rec["total_wall_s"] = round(time.time() - t0, 3)
            rec.update(gen)
            if not rec.get("ok"):
                rec["phase"] = "generate"
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            if rec.get("ok"):
                log(f"  ok nodes={rec.get('node_count')} edges={rec.get('edge_count')} cross={rec.get('cross_edge_count')} t={rec.get('elapsed_s')}s")
            else:
                log(f"  FAIL {rec.get('error', '')[:160]}")
            # free disk: delete clone after measurement
            shutil.rmtree(dest, ignore_errors=True)
    log("sweep complete")


if __name__ == "__main__":
    repo_list_path = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "repos.txt"
    specs = [
        l.strip() for l in Path(repo_list_path).read_text().splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]
    sweep(specs)
