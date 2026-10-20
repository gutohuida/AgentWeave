"""2026-10-20 flows sweep (scratch Hub :8160): a flow on an approved document -- parallel firing,
the reviewer, a verdict withdrawing waiting reviews. Payload reused from s1018_C_flow.py.

    AW_P=proj-... py -3.11 scripts/drive/s1020_l_flow.py <step> [args]
"""

import ast
import json
import pathlib
import sys
import time
import urllib.parse

from s1020_l_lib import P, q, req, show

B = f"/projects/{P}"
D = f"{B}/project"
_src = (pathlib.Path(__file__).parent / "s1018_C_flow.py").read_text(encoding="utf-8")
PAYLOAD = next(ast.literal_eval(n.value) for n in ast.parse(_src).body
               if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "PAYLOAD")
STATE = pathlib.Path.home() / ".agentweave" / "e2e-l1020-flow.json"
S = json.loads(STATE.read_text()) if STATE.exists() else {}


def save():
    STATE.write_text(json.dumps(S, indent=1))


def qp(p):
    return urllib.parse.quote(p)


def status():
    for r in q("select id, agent, status, task_id, substr(started_at,12,8) t from runs where project_id=? order by started_at desc limit 8", P):
        print("  RUN", r)
    for t in req("GET", f"{B}/tasks?limit=50")[1]["tasks"]:
        if t.get("spec_document_id"):
            print("  TASK", t["id"], t["title"][:34], t["status"], t.get("assignee"))
    for a in ("alpha", "beta", "gamma", "rev"):
        qs = [e for e in req("GET", f"{B}/queue/{a}")[1] if e["state"] == "queued"]
        if qs:
            print("  QUEUED", a, [(e["id"], e["origin_type"], e.get("waiting_reason")) for e in qs])
    if S.get("loop"):
        lp = req("GET", f"{B}/loops/{S['loop']}")[1]
        print("  LOOP", json.dumps({k: lp.get(k) for k in ("queue", "stop_reason", "ending_state", "stall_reason", "firing_active")}, ensure_ascii=False)[:900])


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
    st, res = show("POST", f"{B}/jobs/{S['job']}/run", limit=1500)
    time.sleep(6)
    status()


def watch(secs="120"):
    end = time.time() + int(secs)
    while time.time() < end:
        live = q("select count(*) n from runs where project_id=? and status='running'", P)[0]["n"]
        if not live:
            break
        time.sleep(8)
    status()


if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])
