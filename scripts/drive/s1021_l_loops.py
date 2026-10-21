"""2026-10-21 loops sweep (scratch Hub :8159): a new loop adopting what an archived loop left (F53),
Stop with a reason and Run on the ended loop (F821), and a loop whose agent cannot start (F819).

    AW_P=proj-... py -3.11 scripts/drive/s1021_l_loops.py <step> [args]
"""

import json
import pathlib
import sys
import time
import urllib.parse

from s1021_l_lib import P, q, req, show

B = f"/projects/{P}"
D = f"{B}/project"
FAR = "0 0 1 1 *"
STATE = pathlib.Path.home() / ".agentweave" / "e2e-l1021-loops.json"
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


def loop_view(lid):
    st, lp = req("GET", f"{B}/loops/{lid}")
    keep = ("state", "queue", "stop_reason", "stopped_at", "ending_state", "stall_reason", "archived_at", "fired_count")
    print("LOOP", lid, st, json.dumps({k: lp.get(k) for k in keep if k in lp}, ensure_ascii=False)[:1500])
    return lp


def doc_tasks():
    for t in req("GET", f"{B}/tasks?limit=50")[1]["tasks"]:
        if t.get("spec_document_id") == S.get("doc_id"):
            print("  TASK", t["id"], t["title"], t["status"], t.get("assignee"), t.get("loop_id"))


def mkloop(name):
    body = {"name": name, "agent": "alpha", "cron": FAR, "enabled": False,
            "message": "Work the next task on your loop's queue.", "purpose": name,
            "stop_when_queue_empties": True, "spec_document_id": S["doc_id"]}
    st, j = show("POST", f"{B}/jobs", body, limit=600)
    return j


def adopt():
    code, doc = req("POST", f"{D}/documents", {"title": DOC["title"], "kind": "change-spec"})
    path = doc["path"]
    S.update(doc=path, doc_id=doc.get("id")); save()
    print("write", req("PUT", f"{D}/documents/{qp(path)}/content", {"document": DOC})[0])
    print("close", req("POST", f"{D}/documents/close-exploration?path={qp(path)}")[0])
    print("propose", req("POST", f"{D}/documents/propose?path={qp(path)}")[0])
    st, res = req("POST", f"{D}/documents/phase?path={qp(path)}&to=approved", {"reason": "adopt drive", "approve_anyway": True})
    print("approve", st, json.dumps((res or {}).get("approval_outcome"), ensure_ascii=False)[:600])
    doc_tasks()
    a = mkloop("loop A on the document")
    S.update(jobA=a["id"], loopA=a["loop"]["id"]); save()
    doc_tasks()
    # One task finished by the operator under loop A: it must stay with A when B adopts.
    first = [t for t in req("GET", f"{B}/tasks?limit=50")[1]["tasks"] if t.get("spec_document_id") == S["doc_id"]]
    done = sorted(first, key=lambda t: t["title"])[0]["id"]
    S["doneA"] = done; save()
    show("PATCH", f"{B}/tasks/{done}", {"status": "rejected"}, limit=300)
    # A second loop on the same document while A is live: refused, legibly?
    mkloop("loop B while A lives")
    show("POST", f"{B}/jobs/{a['id']}/archive", limit=600)
    loop_view(S["loopA"])
    b = mkloop("loop B adopts")
    S.update(jobB=b["id"], loopB=b["loop"]["id"]); save()
    doc_tasks()
    for e in q("select event_type, loop_id, data from event_logs where project_id=? and event_type like 'loop_tasks_%' order by timestamp", P):
        print("  EVENT", e)
    show("GET", f"{B}/jobs/{S['jobA']}/history", limit=1500)
    show("GET", f"{B}/jobs/{S['jobB']}/history", limit=1500)


def stop():
    """Stop loop B with a reason, then press Run on the ended loop (F821)."""
    show("PATCH", f"{B}/jobs/{S['jobB']}", {"stop_reason": "operator: not needed after all"}, limit=800)
    loop_view(S["loopB"])
    show("POST", f"{B}/jobs/{S['jobB']}/run", limit=600)
    show("PATCH", f"{B}/jobs/{S['jobB']}", {"enabled": True}, limit=600)
    show("GET", f"{B}/jobs/{S['jobB']}/history", limit=1500)



def codex():
    """F819 live: a documentless loop whose agent's CLI cannot start (Codex is undrivable here)."""
    st, r = req("POST", f"{B}/runners", {"name": "codex", "cli": "codex"})
    print("codex runner", st, r.get("id") if st < 300 else r)
    show("POST", f"{B}/agents", {"name": "delta", "runner_id": r["id"]}, limit=200)
    body = {"name": "loop E codex", "agent": "delta", "cron": FAR, "enabled": True,
            "message": "Work the next task on your loop's queue.", "purpose": "codex drive",
            "stop_when_queue_empties": True,
            "initial_tasks": [{"title": "Write E.txt", "description": "Create E.txt containing OK, commit it, then complete this task."}]}
    st, j = show("POST", f"{B}/jobs", body, limit=200)
    S.update(jobE=j["id"], loopE=j["loop"]["id"]); save()
    show("POST", f"{B}/jobs/{j['id']}/run", limit=600)


def codex_after():
    loop_view(S["loopE"])
    for t in req("GET", f"{B}/tasks?limit=50")[1]["tasks"]:
        if t.get("loop_id") == S["loopE"]:
            print("  TASK", t["id"], t["title"], t["status"], t.get("assignee"), t.get("blocked_reason"))
    print("RUNS", q("select id, status, substr(error,1,200) e from runs where project_id=? and agent='delta' order by started_at", P))
    for e in req("GET", f"{B}/queue/delta")[1]:
        print("  ENTRY", e["id"], e["state"], e.get("delivery_attempts"), e.get("abandoned_reason") or e.get("waiting_reason"))
    show("GET", f"{B}/jobs/{S['jobE']}/history", limit=1200)


def codex_again():
    before = {r["id"] for r in q("select id from runs where project_id=? and agent='delta'", P)}
    show("POST", f"{B}/jobs/{S['jobE']}/run", limit=800)
    time.sleep(15)
    print("NEW RUNS (want none)", [r for r in q("select id, status from runs where project_id=? and agent='delta'", P) if r["id"] not in before])
    for e in req("GET", f"{B}/queue/delta")[1]:
        print("  ENTRY", e["id"], e["state"], e.get("abandoned_reason") or e.get("waiting_reason"))
    loop_view(S["loopE"])


if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])
