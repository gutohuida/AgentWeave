"""Re-drive of last night's spec fixes F742, F751, F752 on a Hub started with `e2e.py hub-up`.

Real routes. The only database write is the seeded running-run credential the agent routes need
(the pattern of d1012_f546_declared_title.py); everything else is an HTTP call.

  F742  an agent renames a document: the file's payload title follows the row's, and /specs reports
        no intrinsic_metadata_conflict.
  F752  a requirement with accepted evidence at its current wording is proposed with no
        `requirement_without_task`.
  F751  a reviewer's approval leaves an awaiting piece recorded for an earlier wording awaiting.

  py -3.11 scripts/drive/d1019_night_recheck_spec.py <project-id> <project-dir>
"""

import json
import pathlib
import secrets
import sqlite3
import sys
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude/skills/e2e-loop"))
import e2e  # noqa: E402
from e2e import call, request  # noqa: E402

P, DIR = sys.argv[1], pathlib.Path(sys.argv[2])
SFX = __import__("time").strftime("%H%M%S")
BASE = f"/projects/{P}/project"
HUB = e2e.hub() + "/api/v1"


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (f"  {detail}" if detail else ""))
    if not ok:
        raise SystemExit(1)


def seed_run(name, run_id):
    """A running run for `name` and its token, so the agent routes have a credential."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "hub"))
    import os

    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + json.loads(e2e.STATE.read_text())["db"].replace("\\", "/")
    from hub.agent_auth import hash_run_token

    token = "aw_run_" + secrets.token_urlsafe(24)
    db = sqlite3.connect(json.loads(e2e.STATE.read_text())["db"])
    cols = {r[1] for r in db.execute("pragma table_info(runs)")}
    now = "2026-10-19T09:00:00"
    row = {
        "id": run_id, "project_id": P, "agent": name, "status": "running", "turn_depth": 0,
        "capability_token_hash": hash_run_token(token),
    }
    for extra in ("created_at", "started_at", "updated_at"):
        if extra in cols:
            row[extra] = now
    db.execute(
        f"insert into runs ({','.join(row)}) values ({','.join('?' * len(row))})", list(row.values())
    )
    db.commit()
    db.close()
    return token


def agent(token, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        HUB + "/agent-actions" + path, data=data, method=method,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"null")


def doc(title, statement, with_task=False):
    d = {
        "schema_version": 1, "kind": "change-spec", "title": title,
        "scope": {"in_scope": ["x"], "non_goals": ["y"]},
        "requirements": [{"key": "alpha", "statement": statement, "modal": "MUST"}],
        "acceptance_criteria": [
            {"key": "c-alpha", "requirement": "alpha", "given": "g", "when": "w", "then": "t"}
        ],
        "delivery": {"mode": "none"},
    }
    if with_task:
        d["tasks"] = [{"key": "t", "title": "Do it "+SFX, "description": "Do.", "requirements": ["alpha"]}]
    return d


builder = seed_run("builder", "run-rc-b-"+SFX)
reviewer = seed_run("reviewer", "run-rc-r-"+SFX)

# F742 -----------------------------------------------------------------------------------------
OLD = f"spec/changes/rc-old-name-{SFX}/spec.json"
call("POST", f"{BASE}/documents", {"path": OLD, "title": "Old name"})
st, out = agent(builder, "POST", "/spec/documents", {"path": OLD, "document": doc("Old name", "It MUST list today.")})
check("F742 document written by the agent", st == 200, f"{st} {str(out)[:200]}")
call("POST", f"{BASE}/specs/reindex") if False else None
st, out = agent(builder, "POST", "/spec/documents/rename", {"path": OLD, "subject": "Renamed by subject "+SFX})
check("F742 rename answers 200", st == 200, f"{st} {str(out)[:300]}")
new_path = (out or {}).get("path") or ""
on_disk = json.loads((DIR / new_path).read_text(encoding="utf-8")) if new_path else {}
status, specs = request("GET", f"/projects/{P}/project/specs")
check("F742 /specs answers", status == 200, str(status))
conflicts = ["x"] if "intrinsic_metadata_conflict" in json.dumps(specs) else []
check(
    "F742 the file's title follows the row's and /specs reports no metadata conflict",
    on_disk.get("title") == "Renamed by subject "+SFX and not conflicts,
    f"path={new_path} file title={on_disk.get('title')!r} conflicts={len(conflicts)}",
)

# F752 -----------------------------------------------------------------------------------------
REC = f"spec/changes/rc-recorded-{SFX}/spec.json"
call("POST", f"{BASE}/documents", {"path": REC, "title": "Recorded"})
st, out = agent(builder, "POST", "/spec/documents", {"path": REC, "document": doc("Recorded", "It MUST list today.")})
check("F752 document written", st == 200, f"{st} {str(out)[:200]}")
st, ev = request(
    "POST", f"/projects/{P}/project/spec/evidence",
    {"identifier": "FR-1", "document": REC, "kind": "manual_observation", "summary": "built before"},
)
print("   evidence identifier note:", st, str(ev)[:160])
if st >= 400:
    st, req_list = request("GET", f"/projects/{P}/project/spec/requirements")
    print("   requirements:", str(req_list)[:400])
call("POST", f"{BASE}/documents/close-exploration?path={REC}")
proposed = call("POST", f"{BASE}/documents/propose?path={REC}")
codes = {w["code"] for w in proposed.get("warnings", [])}
check(
    "F752 proposed with evidence and no task: no requirement_without_task",
    st < 400 and "requirement_without_task" not in codes,
    f"evidence={st} warnings={sorted(codes)}",
)

# F751 -----------------------------------------------------------------------------------------
T = f"spec/changes/rc-reword-{SFX}/spec.json"
call("POST", f"{BASE}/documents", {"path": T, "title": "Reword"})
st, out = agent(builder, "POST", "/spec/documents", {"path": T, "document": doc("Reword", "It MUST list today.", True)})
check("F751 document written", st == 200, f"{st} {str(out)[:200]}")
call("POST", f"{BASE}/documents/close-exploration?path={T}")
call("POST", f"{BASE}/documents/propose?path={T}")
call("POST", f"{BASE}/documents/phase?path={T}&to=approved", {"reason": "drive", "approve_anyway": True})
status, tasks = request("GET", f"/projects/{P}/tasks")
task = next(t for t in tasks["tasks"] if t["title"] == "Do it "+SFX)["id"]
print("   task", task, [r.get("identifier") for r in task and next(t for t in tasks["tasks"] if t["id"] == task).get("requirement_links", [])])
ident = next(t for t in tasks["tasks"] if t["id"] == task)["requirement_links"]
ident = (ident[0].get("identifier") or ident[0].get("id")) if ident else "FR-1"
for to in ("assigned", "in_progress"):
    call("PATCH", f"/projects/{P}/tasks/{task}", {"status": to, **({"assignee": "builder"} if to == "assigned" else {})})
st, ev = agent(builder, "POST", "/spec/evidence", {"identifier": ident, "summary": "ran it", "task_id": task})
check("F751 the builder's evidence lands awaiting", st == 201 and ev.get("review_state") == "awaiting", f"{st} {str(ev)[:200]}")
for to in ("completed", "under_review"):
    call("PATCH", f"/projects/{P}/tasks/{task}", {"status": to, **({"assignee": "reviewer"} if to == "under_review" else {})})
st, out = request("POST", f"{BASE}/documents/phase?path={T}&to=exploring", {"reason": "reword"})
print("   reopen:", st, str(out)[:200])
st, out = agent(builder, "POST", "/spec/documents", {"path": T, "document": doc("Reword", "It MUST list this week.", True)})
check("F751 requirement reworded", st == 200, f"{st} {str(out)[:200]}")
st, out = agent(reviewer, "PATCH", f"/tasks/{task}", {"status": "approved", "notes": "looks right"})
print("   reviewer approval:", st, str(out)[:200])
status, ev_list = request("GET", f"/projects/{P}/project/spec/evidence")
mine = [e for e in (ev_list if isinstance(ev_list, list) else ev_list.get("evidence", [])) if e["id"] == ev["id"]]
check("F751 the earlier-wording piece is still awaiting after the approval",
      bool(mine) and mine[0]["review_state"] == "awaiting", str(mine)[:240])
print("drive passed")
