"""Jobs & loops drive 2026-10-23 (scratch Hub :8111, la1023): least-driven loop paths.

adopt     -- approved document -> loop A (disabled) -> a second loop refused -> A archived ->
             loop B adopts what A left (one task A rejected stays A's)
settings  -- loop B: definition edits staged (pending_*), a no-stop-condition edit, read back
control   -- Delegate / Take back / an unknown value
stop      -- Stop B with a reason, then Run and re-enable on the ended loop
norunner  -- an agent with no runner: plain job and loop, Run now (want 200 + waiting_reason)

py -3.11 scripts/drive/s1023_la_loops.py <step>
"""

import json
import pathlib
import sys
import urllib.parse

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1023_la_lib import P, q, req, show  # noqa: E402

B = f"projects/{P}"
D = f"{B}/project"
FAR = "0 0 1 1 *"
STATE = pathlib.Path(__file__).resolve().parents[2] / "testbed" / "drive1023la" / "loops_state.json"
S = json.loads(STATE.read_text()) if STATE.exists() else {}
DOC = {
    "schema_version": 1, "kind": "change-spec", "title": "Two marker files",
    "summary": "Write two marker files.", "problem": "Markers are missing.",
    "scope": {"in_scope": ["M1.txt", "M2.txt"], "non_goals": []},
    "requirements": [{"key": "m", "modal": "MUST", "statement": "The repository MUST contain M1.txt and M2.txt, each holding OK.", "rationale": "Markers."}],
    "acceptance_criteria": [{"key": "a-m", "requirement": "m", "given": "the repo", "when": "listed", "then": "both files hold OK", "checked_by": "agent"}],
    "tasks": [
        {"key": "t-m1", "title": "Write M1.txt", "description": "Create M1.txt holding OK and commit it.", "requirements": ["m"]},
        {"key": "t-m2", "title": "Write M2.txt", "description": "Create M2.txt holding OK and commit it.", "requirements": ["m"]},
    ],
    "algorithms": [], "design": "Trivial.", "evidence": {"checked": [], "limits": []},
    "lifecycle": "one-off", "open_questions": [],
}


def save():
    STATE.write_text(json.dumps(S, indent=1))


def qp(p):
    return urllib.parse.quote(p)


def loop_view(lid, tag=""):
    st, lp = req("GET", f"{B}/loops/{lid}")
    keep = ("state", "control", "purpose", "stop_at", "stop_when_queue_empties", "pending_edit", "stop_reason",
            "stopped_at", "ending_state", "stall_reason", "archived_at", "queue", "history")
    print("LOOP", tag, lid, st, json.dumps({k: lp.get(k) for k in keep if k in lp}, ensure_ascii=False)[:2500])
    print("  ROW", q("select purpose, stop_at, stop_when_queue_empties, pending_purpose, pending_stop_at, pending_stop_when_queue_empties, pending_agent, control, ending_state, stop_reason from loops where id=?", lid))
    return lp


def doc_tasks():
    for t in q("select id, title, status, assignee, loop_id from tasks where project_id=? and spec_document_id=?", P, S.get("doc_id")):
        print("  TASK", t)


def mkloop(name, enabled=False):
    body = {"name": name, "agent": "alpha", "cron": FAR, "enabled": enabled,
            "message": "Work the next task on your loop's queue.", "purpose": name,
            "stop_when_queue_empties": True, "spec_document_id": S["doc_id"]}
    st, j = show("POST", f"{B}/jobs", body, limit=700)
    return st, j


def adopt():
    code, doc = req("POST", f"{D}/documents", {"title": DOC["title"], "kind": "change-spec"})
    path = doc["path"]
    S.update(doc=path, doc_id=doc.get("id")); save()
    print("write", req("PUT", f"{D}/documents/{qp(path)}/content", {"document": DOC})[0])
    print("close", req("POST", f"{D}/documents/close-exploration?path={qp(path)}")[0])
    print("propose", req("POST", f"{D}/documents/propose?path={qp(path)}")[0])
    st, res = req("POST", f"{D}/documents/phase?path={qp(path)}&to=approved", {"reason": "adopt drive", "approve_anyway": True})
    print("approve", st, json.dumps(res, ensure_ascii=False)[:300])
    doc_tasks()
    st, a = mkloop("loop A on the document")
    S.update(jobA=a["id"], loopA=a["loop"]["id"]); save()
    doc_tasks()
    first = q("select id from tasks where project_id=? and spec_document_id=? order by title", P, S["doc_id"])
    S["doneA"] = first[0]["id"]; save()
    show("PATCH", f"{B}/tasks/{S['doneA']}", {"status": "rejected"}, limit=300)
    mkloop("loop B while A lives")
    print("ORPHAN JOBS", q("select id, name, enabled, archived_at from ai_jobs where project_id=? and name like 'loop B while%'", P))
    show("POST", f"{B}/jobs/{a['id']}/archive", limit=600)
    loop_view(S["loopA"], "A after archive")
    st, b = mkloop("loop B adopts")
    S.update(jobB=b["id"], loopB=b["loop"]["id"]); save()
    doc_tasks()
    for e in q("select event_type, loop_id, data from event_logs where project_id=? and event_type like 'loop_%' order by timestamp", P):
        print("  EVENT", e["event_type"], e["loop_id"], e["data"][:300])
    loop_view(S["loopB"], "B")


def settings():
    j = S["jobB"]
    show("PATCH", f"{B}/jobs/{j}", {"purpose": "Edited purpose", "stop_at": "2027-06-01T00:00:00Z"}, limit=400)
    loop_view(S["loopB"], "staged")
    # Drop the only stop condition: what does the operator's route say?
    show("PATCH", f"{B}/jobs/{j}", {"stop_when_queue_empties": False}, limit=600)
    loop_view(S["loopB"], "no-stop staged")
    # a stop_at in the past
    show("PATCH", f"{B}/jobs/{j}", {"stop_at": "2020-01-01T00:00:00Z"}, limit=600)
    loop_view(S["loopB"], "past stop_at")
    show("PATCH", f"{B}/jobs/{j}", {"purpose": ""}, limit=600)
    show("PATCH", f"{B}/jobs/{j}", {"stop_at": None, "stop_when_queue_empties": None}, limit=600)
    loop_view(S["loopB"], "after nulls")


def control():
    lid = S["loopB"]
    for c in ("creator", "operator", "banana", "Creator", ""):
        st, r = req("POST", f"{B}/loops/{lid}/control", {"control": c})
        print("control", repr(c), "->", st, (r or {}).get("control") if isinstance(r, dict) else r)
    print("EVENTS", [e["data"] for e in q("select data from event_logs where project_id=? and event_type='loop_control_changed' order by timestamp", P)])
    print("creator:", q("select created_by_run_id from loops where id=?", lid))


def stop():
    j = S["jobB"]
    show("PATCH", f"{B}/jobs/{j}", {"stop_reason": "operator: not needed after all"}, limit=800)
    loop_view(S["loopB"], "stopped")
    show("POST", f"{B}/jobs/{j}/run", limit=600)
    show("PATCH", f"{B}/jobs/{j}", {"enabled": True}, limit=600)
    show("PATCH", f"{B}/jobs/{j}", {"stop_reason": "a second reason"}, limit=600)
    show("PATCH", f"{B}/jobs/{j}", {"purpose": "edit an ended loop"}, limit=600)
    doc_tasks()
    print("EVENTS", [(e["event_type"], e["data"][:200]) for e in q("select event_type, data from event_logs where project_id=? and (event_type like 'loop_%' or event_type like 'job_%') and loop_id=? order by timestamp", P, S["loopB"])])


def norunner():
    rid = q("select id from runners where project_id=? limit 1", P)[0]["id"]
    show("POST", f"{B}/agents", {"name": "norun", "runner_id": rid}, limit=400)
    print("AGENT", q("select name, runner_id, lifecycle from agents where project_id=? and name='norun'", P))
    st, jp = show("POST", f"{B}/jobs", {"name": "norun plain", "agent": "norun", "message": "Say hi.", "cron": FAR, "enabled": True}, limit=300)
    st, jl = show("POST", f"{B}/jobs", {"name": "norun loop", "agent": "norun", "message": "Work the next task.", "cron": FAR, "enabled": True,
                                         "purpose": "norun", "stop_when_queue_empties": True,
                                         "initial_tasks": [{"title": "norun task", "description": "Write N.txt."}]}, limit=300)
    S.update(norun_plain=jp["id"], norun_loop=jl["id"], norun_loop_id=jl["loop"]["id"]); save()
    show("PATCH", f"{B}/agents/norun", {"runner_id": None}, limit=400)
    print("AGENT", q("select name, runner_id, lifecycle from agents where project_id=? and name='norun'", P))
    show("POST", f"{B}/jobs/{jp['id']}/run", limit=800)
    show("POST", f"{B}/jobs/{jl['id']}/run", limit=800)
    show("POST", f"{B}/jobs/{jl['id']}/run", limit=800)
    print("QUEUE", q("select agent, state, waiting_reason, job_id from inbound_queue_entries where project_id=? and agent='norun'", P))
    print("RUNS", q("select r.status, j.name, substr(r.error_summary,1,200) e, r.tick_count from job_runs r join ai_jobs j on j.id=r.job_id where j.agent='norun'"))
    print("TASKS", q("select title, status, assignee from tasks where project_id=? and title='norun task'", P))


def withdraw():
    for e in q("select id from inbound_queue_entries where project_id=? and agent='norun' and state='queued'", P):
        show("DELETE", f"{B}/queue/entries/{e['id']}", limit=300)
    print("QUEUE", q("select agent, state, waiting_reason, job_id from inbound_queue_entries where project_id=? and agent='norun'", P))
    print("RUNS", q("select r.status, j.name, substr(r.error_summary,1,200) e from job_runs r join ai_jobs j on j.id=r.job_id where j.agent='norun'", P))



def flowc():
    """A second approved document and a live (disabled) flow C on it, for the Settings screen."""
    code, doc = req("POST", f"{D}/documents", {"title": "Flow C markers", "kind": "change-spec"})
    path = doc["path"]
    d2 = dict(DOC, title="Flow C markers")
    print("write", req("PUT", f"{D}/documents/{qp(path)}/content", {"document": d2})[0])
    req("POST", f"{D}/documents/close-exploration?path={qp(path)}")
    req("POST", f"{D}/documents/propose?path={qp(path)}")
    print("approve", req("POST", f"{D}/documents/phase?path={qp(path)}&to=approved", {"reason": "flow C", "approve_anyway": True})[0])
    body = {"name": "flow C", "agent": "alpha", "cron": FAR, "enabled": False, "message": "Work the next task.",
            "purpose": "flow C", "stop_when_queue_empties": True, "spec_document_id": doc["id"]}
    st, j = show("POST", f"{B}/jobs", body, limit=200)
    S.update(jobC=j["id"], loopC=j["loop"]["id"]); save()
    print("LOOP C", S["loopC"])


def loopd():
    """A documentless loop for alpha (Haiku) with one task: fire, work, review, drain, stop."""
    body = {"name": "loop D", "agent": "alpha", "cron": FAR, "enabled": True, "message": "Work the next task on your loop's queue.",
            "purpose": "loop D drive", "stop_when_queue_empties": True,
            "initial_tasks": [{"title": "Write D.txt", "description": "Create D.txt containing the single word OK, commit it, then mark this task completed. Do nothing else."}]}
    st, j = show("POST", f"{B}/jobs", body, limit=200)
    S.update(jobD=j["id"], loopD=j["loop"]["id"]); save()
    show("POST", f"{B}/jobs/{j['id']}/run", limit=600)


def loopd_after():
    loop_view(S["loopD"], "D")
    print("TASKS", q("select id, title, status, assignee from tasks where loop_id=?", S["loopD"]))
    print("RUNS", q("select id, status from runs where project_id=? and agent='alpha' order by started_at", P)[-2:])
    print("JOBRUNS", q("select id, status, substr(error_summary,1,150) e from job_runs where job_id=?", S["jobD"]))


if __name__ == "__main__":
    globals()[sys.argv[1]]()
