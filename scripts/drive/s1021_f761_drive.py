"""F761 acceptance drive (scratch Hub :8153, profile f761): a piece that names no commit, recorded
with the checkout on master after an unrelated commit, answers no files and a reason from
GET /spec/evidence/{id}/diff; a piece that names a commit on master still shows that commit.

    AW_E2E_STATE=~/.agentweave/e2e-f761.json py -3.11 scripts/drive/s1021_f761_drive.py <project-id> <project-dir>
"""

import os
import pathlib
import subprocess
import sys
import time

os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-f761.json")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402

P, DIR = sys.argv[1], pathlib.Path(sys.argv[2])
BASE = f"/projects/{P}/project"
SFX = time.strftime("%H%M%S")


def git(*args):
    return subprocess.run(["git", "-C", str(DIR), *args], capture_output=True, text=True).stdout.strip()


def commit_file(rel, text, msg):
    (DIR / rel).parent.mkdir(parents=True, exist_ok=True)
    (DIR / rel).write_text(text, encoding="utf-8")
    git("add", rel)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", msg)
    return git("rev-parse", "HEAD")


doc = f"spec/changes/f761-{SFX}/spec.json"
reqs = [{"key": k, "statement": f"It MUST do {k}.", "modal": "MUST"} for k in ("alpha", "beta")]
e2e.request("POST", f"{BASE}/documents", {"path": doc, "title": "F761 " + SFX})
st, out = e2e.request("PUT", f"{BASE}/documents/{doc}/content", {"document": {
    "schema_version": 1, "kind": "change-spec", "title": "F761 " + SFX,
    "scope": {"in_scope": ["list"], "non_goals": ["sync"]}, "requirements": reqs,
    "acceptance_criteria": [{"key": f"c-{q['key']}", "requirement": q["key"], "given": "g", "when": "w",
                             "then": "t"} for q in reqs],
    "delivery": {"mode": "none"}}})
ids = (out or {}).get("identifiers") or {}
A, B = ids.get("alpha", "FR-1"), ids.get("beta", "FR-2")

commit_file("todo/list.py", f"X = {SFX!r}" + chr(10), "made for FR-1")
head = git("rev-parse", "HEAD")
st, nc = e2e.request("POST", f"{BASE}/spec/evidence",
                     {"identifier": B, "document": doc, "summary": "watched it sort", "covers": "partial"})
st2, d = e2e.request("GET", f"{BASE}/spec/evidence/{nc['id']}/diff")
ok1 = st == 201 and st2 == 200 and d["files"] == [] and head[:12] in (d.get("reason") or "")
print(("HELD " if ok1 else "ODD  ") + "no-commit piece: no files and a reason naming the checkout", st, st2, d.get("files"), d.get("reason"))

fix = commit_file("todo/fix.py", f"FIX = {SFX!r}" + chr(10), "the fix")
commit_file("todo/later.py", f"L = {SFX!r}" + chr(10), "later")
st, nm = e2e.request("POST", f"{BASE}/spec/evidence",
                     {"identifier": A, "document": doc, "summary": "fix works", "commit": fix, "locator": "todo/fix.py"})
st2, d = e2e.request("GET", f"{BASE}/spec/evidence/{nm['id']}/diff")
ok2 = st == 201 and st2 == 200 and [f["path"] for f in d["files"]] == ["todo/fix.py"]
print(("HELD " if ok2 else "ODD  ") + "named-commit piece still shows its commit", st, st2, [f["path"] for f in d.get("files", [])], d.get("reason"))
sys.exit(0 if ok1 and ok2 else 1)
