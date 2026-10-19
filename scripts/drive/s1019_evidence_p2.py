"""Sweep 2026-10-19, part 2: does an open drift candidate on overturned evidence hide the rejection
from the approval gate? Control: the same walk on a requirement with no drift.

  AW_E2E_STATE=... py -3.11 scripts/drive/s1019_evidence_p2.py <project-id> <project-dir> <doc> <EG2>
"""

import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude/skills/e2e-loop"))
from e2e import request  # noqa: E402

P, DIR, DOC, EG2 = sys.argv[1], pathlib.Path(sys.argv[2]), sys.argv[3], sys.argv[4]
BASE = f"/projects/{P}/project"


def show(label, st, out):
    print(f"{label}: {st} {json.dumps(out)[:600]}")


st, out = request("POST", f"{BASE}/spec/evidence/{EG2}/overturn", {"reason": "x"})
show("overturn an awaiting piece (expect 409 not_decided)", st, out)

# the big commit's diff (named commit, >400 KB patch, non-ASCII path with a space)
big_sha = subprocess.run(["git", "-C", str(DIR), "log", "--format=%H", "-1", "--", "todo/data file ü.txt"],
                         capture_output=True, text=True, encoding="utf-8").stdout.strip()
st, ev = request("POST", f"{BASE}/spec/evidence", {"identifier": "FR-2", "document": DOC, "summary": "data", "commit": big_sha})
show("record with the big commit", st, {k: ev.get(k) for k in ("id", "review_state")})
st, d = request("GET", f"{BASE}/spec/evidence/{ev['id']}/diff")
print("big diff:", st, "truncated=", d.get("truncated"), [(f["path"], f["status"], len(f["patch"])) for f in d.get("files", [])], d.get("reason"))

# approve the document so its tasks exist
for step in ("close-exploration", "propose"):
    st, out = request("POST", f"{BASE}/documents/{step}?path={DOC}")
    print(step, st, json.dumps(out)[:200])
st, out = request("POST", f"{BASE}/documents/phase?path={DOC}&to=approved", {"reason": "drive", "approve_anyway": True})
print("approve", st, json.dumps(out)[:300])
st, tasks = request("GET", f"/projects/{P}/tasks")
mine = {t["title"].split()[1]: t for t in tasks["tasks"] if t["title"].startswith("Build ")}
print("tasks:", {k: (t["id"], t["status"], [x.get("identifier") for x in t.get("requirement_links", [])]) for k, t in mine.items()})
st, cov = request("GET", f"{BASE}/spec/coverage?document={DOC}")
print("coverage:", {e["identifier"]: e["state"] for e in cov["requirements"]})

CTRL = DOC.replace("ev-sweep", "ev-ctrl")
request("POST", f"{BASE}/documents", {"path": CTRL, "title": "Control"})
ctrl = {"schema_version": 1, "kind": "change-spec", "title": "Control",
        "scope": {"in_scope": ["x"], "non_goals": ["y"]},
        "requirements": [{"key": "delta", "statement": "It MUST export CSV.", "modal": "MUST"}],
        "acceptance_criteria": [{"key": "c-d", "requirement": "delta", "given": "g", "when": "w", "then": "t"}],
        "delivery": {"mode": "none"},
        "tasks": [{"key": "t-d", "title": "Build delta ctrl", "description": "Do.", "requirements": ["delta"]}]}
st, out = request("PUT", f"{BASE}/documents/{CTRL}/content", {"document": ctrl})
st, ev = request("POST", f"{BASE}/spec/evidence", {"identifier": "FR-1", "document": CTRL, "summary": "csv out"})
request("POST", f"{BASE}/spec/evidence/{ev['id']}/overturn", {"reason": "it writes TSV"})
for step in ("close-exploration", "propose"):
    request("POST", f"{BASE}/documents/{step}?path={CTRL}")
request("POST", f"{BASE}/documents/phase?path={CTRL}&to=approved", {"reason": "drive", "approve_anyway": True})
st, tasks = request("GET", f"/projects/{P}/tasks")
mine.update({t["title"].split()[1]: t for t in tasks["tasks"] if t["title"] == "Build delta ctrl"})
st, cov = request("GET", f"{BASE}/spec/coverage?document={CTRL}")
print("control coverage:", {e["identifier"]: e["state"] for e in cov["requirements"]})

for key in ("gamma", "delta"):
    t = mine[key]["id"]
    for to in ("assigned", "in_progress", "completed", "under_review"):
        body = {"status": to}
        if to == "assigned":
            body["assignee"] = "builder"
        st, out = request("PATCH", f"/projects/{P}/tasks/{t}", body)
        if st >= 300:
            show(f"  {key} -> {to}", st, out)
    st, out = request("PATCH", f"/projects/{P}/tasks/{t}", {"status": "approved"})
    show(f"{key}: operator approves (FR {'FR-3 drifting, all evidence rejected' if key == 'gamma' else 'control FR-1 rejected, no drift'})", st, out)
