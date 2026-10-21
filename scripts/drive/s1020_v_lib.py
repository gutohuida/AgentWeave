"""Helpers for the 2026-10-20 sweep: Requirements, evidence & coverage x Drift (s1020_v_*.py).

The drive keeps what one phase hands the next in a JSON file beside the e2e state, since every
phase is a fresh process.
"""

import json
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude/skills/e2e-loop"))
import e2e  # noqa: E402
from e2e import request  # noqa: E402,F401

MEMO = e2e.STATE.with_name(e2e.STATE.stem + "-memo.json")
RESULTS = []


def memo(**kw):
    data = json.loads(MEMO.read_text()) if MEMO.exists() else {}
    data.update(kw)
    MEMO.write_text(json.dumps(data, indent=2))
    return data


def say(label, ok, detail=""):
    RESULTS.append((label, ok))
    print(("HELD " if ok else "ODD  ") + label + (f"\n     {detail}" if detail else ""))


def show(label, st, out):
    print(f"  {label}: {st} {json.dumps(out, ensure_ascii=False)[:600]}")


def summary():
    print("\nSUMMARY", sum(ok for _, ok in RESULTS), "held /", len(RESULTS))
    for label, ok in RESULTS:
        if not ok:
            print("  ODD:", label)


def git(directory, *args):
    return subprocess.run(["git", "-C", str(directory), *args], capture_output=True, text=True,
                          encoding="utf-8").stdout.strip()


def commit_file(directory, rel, text, msg):
    p = pathlib.Path(directory) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    git(directory, "add", rel)
    git(directory, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", msg)
    return git(directory, "rev-parse", "HEAD")


def coverage(project, doc):
    st, out = request("GET", f"/projects/{project}/project/spec/coverage?document={doc}")
    return {e["identifier"]: e for e in out.get("requirements", [])} if st == 200 else {"_err": (st, out)}


def evidence(project, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    st, out = request("GET", f"/projects/{project}/project/spec/evidence" + (f"?{q}" if q else ""))
    return out.get("evidence", []) if st == 200 else []


def wait_run(run_id, minutes=10):
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        st, out = request("GET", f"/runs/{run_id}")
        if st == 200 and out.get("status") not in ("running", "queued", "pending", "starting"):
            return out
        time.sleep(5)
    return {"status": "timeout"}
