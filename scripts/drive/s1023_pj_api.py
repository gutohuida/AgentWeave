"""Projects sweep 2026-10-23 -- API probes (scratch Hub :8116, profile pj1023).

    fs        -- GET /fs/roots, /fs/list: missing, file, space + non-ASCII, drive root, bare drive,
                 UNC, `..`, relative, `~`, a junction
    open      -- POST /projects/open: typed paths (missing, file, bare drive, drive root holding
                 projects, space + non-ASCII, trailing separator, the same folder twice)
    relocate  -- POST /projects/{A}/relocate onto B's folder, a missing one, a file, its own
    settings  -- PUT one field per group, read it back; refusals; a deleted project's settings
    instr     -- project instructions: put, read, {}, "", over the limit, deleted project
    branch    -- main-branch suggestion on a repo, a non-repo, a repo with no commits

    py -3.11 scripts/drive/s1023_pj_api.py fs
"""

import json
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from s1023_pj_lib import PA, PB, req, show  # noqa: E402

DOCS = pathlib.Path("C:/Users/huida/Documents")
ODD = DOCS / "aw-pj1023 sp ção"


def fs():
    show("GET", "/fs/roots")
    for p in [
        "C:/nope/xyz",
        str(DOCS / "aw-pj1023-a" / "README.md"),
        str(ODD),
        "C:",
        "C:\\",
        "\\\\localhost\\c$\\Users\\huida\\Documents\\aw-pj1023-a",
        str(DOCS / "aw-pj1023-a" / ".." / ".." / ".."),
        "relative/x",
        "~",
        "Z:\\",
        "C:/Users/Default User",
        "C:/Users/huida/Documents/aw-pj1023-a/\x00x",
    ]:
        status, body = req("GET", "/fs/list?path=" + _q(p))
        ents = body.get("entries") if isinstance(body, dict) else None
        print(f"list {p!r} -> {status} path={body.get('path') if isinstance(body, dict) else ''} "
              f"n={len(ents) if ents is not None else '-'} reason={body.get('reason') if isinstance(body, dict) else body}")


def _q(p):
    import urllib.parse

    return urllib.parse.quote(p, safe="")


def open_():
    targets = [
        str(DOCS / "aw-pj1023-missing"),
        str(DOCS / "aw-pj1023-a" / "README.md"),
        "C:",
        "C:\\",
        str(DOCS),
        str(DOCS / "aw-pj1023-a") + "\\",
        str(DOCS / "aw-pj1023-a").upper(),
    ]
    for t in targets:
        show("POST", "/projects/open", {"path": t}, limit=900)


def open_odd():
    status, body = show("POST", "/projects/open", {"path": str(ODD)}, limit=1500)
    print("marker:", (ODD / ".agentweave" / "project.json").read_text(encoding="utf-8") if (ODD / ".agentweave" / "project.json").exists() else "<none>")


def relocate():
    b_dir = req("GET", f"/projects/{PB}")[1]["working_directory"]
    show("POST", f"/projects/{PA}/relocate", {"path": b_dir}, limit=1500)
    show("POST", f"/projects/{PA}/relocate", {"path": str(DOCS / "aw-pj1023-gone")}, limit=1500)
    show("POST", f"/projects/{PA}/relocate", {"path": str(DOCS / "aw-pj1023-a" / "README.md")}, limit=1500)
    show("POST", f"/projects/{PA}/relocate", {"path": str(ODD)}, limit=1500)
    a_dir = req("GET", f"/projects/{PA}")[1]["working_directory"]
    show("POST", f"/projects/{PA}/relocate", {"path": a_dir}, limit=600)
    show("POST", "/projects/proj-doesnotexist/relocate", {"path": a_dir}, limit=600)


def settings():
    base = req("GET", f"/projects/{PA}/settings")[1]
    print("before:", json.dumps(base))
    for patch in [
        {"hop_budget": 3},
        {"main_branch": "nope-branch"},
        {"main_branch": ""},
        {"hop_budget": 0},
        {"hop_budget": -1},
        {"turn_delivery_cap": 0},
        {"agent_budget": 0},
        {"name": ""},
        {"name": "x" * 300},
        {"checkpoint_mode": "bogus"},
        {"checkpoint_threshold_mode": "percent", "checkpoint_threshold_value": 150},
        {"checks": [{"name": "t", "command": ""}]},
        {"default_permission_mode": "nope"},
    ]:
        status, body = req("PUT", f"/projects/{PA}/settings", patch)
        print(f"PUT {json.dumps(patch)[:80]} -> {status} {json.dumps(body, ensure_ascii=False)[:500]}")
    after = req("GET", f"/projects/{PA}/settings")[1]
    print("diff:", {k: (base.get(k), after.get(k)) for k in after if base.get(k) != after.get(k)})
    summ = req("GET", f"/projects/{PA}")[1]
    print("summary hop_budget:", summ.get("hop_budget"), "name:", summ.get("name"))
    show("GET", "/projects/proj-deadbeef0000/settings", limit=400)
    show("PUT", "/projects/proj-deadbeef0000/settings", {"hop_budget": 2}, limit=400)


def instr():
    show("GET", f"/projects/{PA}/project/instructions", limit=600)
    show("PUT", f"/projects/{PA}/project/instructions", {"content": "Use tabs. Ção ünïcode."}, limit=600)
    show("GET", f"/projects/{PA}/project/instructions", limit=600)
    show("PUT", f"/projects/{PA}/project/instructions", {}, limit=600)
    show("PUT", f"/projects/{PA}/project/instructions", {"content": "y" * 40001}, limit=600)
    show("PUT", f"/projects/{PA}/project/instructions", {"content": None}, limit=600)
    show("GET", "/projects/proj-deadbeef0000/project/instructions", limit=600)
    a_dir = pathlib.Path(req("GET", f"/projects/{PA}")[1]["working_directory"])
    for p in (a_dir / "AGENTS.md", a_dir / ".agentweave" / "instructions.md", a_dir / "CLAUDE.md"):
        print(p, "exists" if p.exists() else "absent")


def branch():
    show("GET", f"/projects/{PA}/main-branch-suggestion", limit=400)
    status, body = req("GET", "/projects")
    for proj in body:
        if proj["name"].startswith("aw-pj1023 sp"):
            show("GET", f"/projects/{proj['id']}/main-branch-suggestion", limit=400)
            show("PUT", f"/projects/{proj['id']}/settings", {"main_branch": "main"}, limit=600)


def reopen():
    """B was deleted (private entries removed) with its folder left as it was: open it again."""
    b_dir = DOCS / "aw-pj1023-b"
    status, body = show("POST", "/projects/open", {"path": str(b_dir)}, limit=600)
    pid = body.get("id")
    print("marker now:", (b_dir / ".agentweave" / "project.json").read_text(encoding="utf-8").strip())
    show("GET", f"/projects/{pid}/vault/map", limit=2500)
    status, srcs = req("GET", f"/projects/{pid}/vault/entries/src-452608a41563")
    print("private stub entry ->", status, json.dumps(srcs, ensure_ascii=False)[:600])
    show("GET", f"/projects/{pid}/worktrees", limit=1200)
    print("git worktrees:", git(b_dir, "worktree", "list"))


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True).stdout.strip()


if __name__ == "__main__":
    {"fs": fs, "open": open_, "open-odd": open_odd, "relocate": relocate, "settings": settings,
     "instr": instr, "branch": branch, "reopen": reopen}[sys.argv[1]]()
