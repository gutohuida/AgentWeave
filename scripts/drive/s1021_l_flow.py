"""2026-10-21 flows sweep (scratch Hub :8159): an idle holder released to a flow, and a review the
flow cannot staff (the named reviewer authored the work) reaching the task story (F768).

    AW_P=proj-... py -3.11 scripts/drive/s1021_l_flow.py <step> [args]
"""

import ast
import copy
import json
import pathlib
import sys
import time
import urllib.parse

from s1021_l_lib import P, q, req, show

B = f"/projects/{P}"
D = f"{B}/project"
_src = (pathlib.Path(__file__).parent / "s1018_C_flow.py").read_text(encoding="utf-8")
PAYLOAD = copy.deepcopy(next(ast.literal_eval(n.value) for n in ast.parse(_src).body
                             if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "PAYLOAD"))
# Two independent tasks only; the named reviewer is a builder, so one review cannot be staffed.
PAYLOAD["requirements"] = PAYLOAD["requirements"][:2]
PAYLOAD["acceptance_criteria"] = PAYLOAD["acceptance_criteria"][:2]
PAYLOAD["tasks"] = PAYLOAD["tasks"][:2]
PAYLOAD["scope"]["in_scope"] = PAYLOAD["scope"]["in_scope"][:3]
PAYLOAD["delivery"]["reviewer"] = "alpha"
STATE = pathlib.Path.home() / ".agentweave" / "e2e-l1021-flow.json"
S = json.loads(STATE.read_text()) if STATE.exists() else {}


def save():
    STATE.write_text(json.dumps(S, indent=1))


def qp(p):
    return urllib.parse.quote(p)


def status():
    for r in q("select id, agent, status, task_id, substr(started_at,12,8) t from runs where project_id=? order by started_at desc limit 8", P):
        print("  RUN", r)
    for t in req("GET", f"{B}/tasks?limit=50")[1]["tasks"]:
        print("  TASK", t["id"], t["title"][:34], t["status"], t.get("assignee"), t.get("loop_id"))
    for a in ("alpha", "beta"):
        qs = [e for e in req("GET", f"{B}/queue/{a}")[1] if e["state"] == "queued"]
        if qs:
            print("  QUEUED", a, [(e["id"], e["origin_type"], e.get("waiting_reason")) for e in qs])
    if S.get("loop"):
        lp = req("GET", f"{B}/loops/{S['loop']}")[1]
        print("  LOOP", json.dumps({k: lp.get(k) for k in ("queue", "stop_reason", "ending_state", "stall_reason", "firing_active")}, ensure_ascii=False)[:1200])
    for e in q("select event_type, substr(timestamp,12,8) t, data from event_logs where project_id=? and event_type in ('review_unstaffed','loop_stalled') order by timestamp", P):
        print("  EVENT", e["event_type"], e["t"], e["data"][:500])


def hold():
    """beta holds an assigned, in-progress operator task that no loop and no queued turn will move."""
    st, t = show("POST", f"{B}/tasks", {"title": "Look into the flaky clock", "description": "Operator's own note; nothing will move it.", "assignee": "beta"}, limit=400)
    S["held"] = t["id"]; save()
    show("PATCH", f"{B}/tasks/{t['id']}", {"status": "in_progress"}, limit=400)
    show("GET", f"{B}/agents", limit=1500)


def start():
    code, doc = req("POST", f"{D}/documents", {"title": PAYLOAD["title"], "kind": "change-spec"})
    path = doc["path"]
    S.update(doc=path, doc_id=doc.get("id")); save()
    print("write", req("PUT", f"{D}/documents/{qp(path)}/content", {"document": PAYLOAD})[0])
    print("close", req("POST", f"{D}/documents/close-exploration?path={qp(path)}")[0])
    st, res = req("POST", f"{D}/documents/propose?path={qp(path)}")
    print("propose", st, (res or {}).get("blocking"))
    st, res = req("POST", f"{D}/documents/phase?path={qp(path)}&to=approved", {"reason": "sweep l flow", "approve_anyway": True})
    print("approve", st, json.dumps((res or {}).get("approval_outcome"), ensure_ascii=False)[:1500])
    time.sleep(4)
    jobs = req("GET", f"{B}/jobs")[1]
    flow = [j for j in jobs if (j.get("loop") or {}).get("spec_document_id") == S["doc_id"]]
    if flow:
        S.update(job=flow[0]["id"], loop=flow[0]["loop"]["id"]); save()
        print("FLOW", flow[0]["id"], flow[0]["loop"]["id"], flow[0]["enabled"], flow[0]["agent"])
    status()


def fire():
    show("POST", f"{B}/jobs/{S['job']}/run", limit=1500)
    time.sleep(6)
    status()


def watch(secs="300"):
    end = time.time() + int(secs)
    while time.time() < end:
        live = q("select count(*) n from runs where project_id=? and status in ('running','starting')", P)[0]["n"]
        if not live:
            break
        time.sleep(8)
    status()


def story(tid):
    st, res = req("GET", f"{B}/tasks/{tid}/story")
    for e in res.get("events", res if isinstance(res, list) else []):
        print("  STORY", json.dumps(e, ensure_ascii=False)[:400])
    if st >= 300:
        print(st, res)


if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])
