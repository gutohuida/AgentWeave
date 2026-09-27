"""b11 drive: F53's three calls plus F157's refusal, on a live Hub. Usage: PID as argv[1]."""

import sys

sys.path.insert(0, "scripts/drive")
sys.stdout.reconfigure(encoding="utf-8")
from aw import api

PID = sys.argv[1]
S = "/projects/%s" % PID
D = S + "/project"
c, doc = api("POST", D + "/documents", {"title": "b11 flow " + sys.argv[2]})
path = doc["path"]
pl = {
    "schema_version": 1, "kind": doc["kind"], "title": "b11 flow " + sys.argv[2], "summary": "One.", "problem": "Drive.",
    "scope": {"in_scope": ["README"], "non_goals": ["Else"]},
    "requirements": [{"key": "r1", "statement": "The README MUST mention item 1.", "modal": "MUST"}],
    "acceptance_criteria": [{"key": "c1", "requirement": "r1", "given": "g", "when": "w", "then": "t"}],
    "tasks": [
        {"key": "t1", "title": "One", "description": "d", "requirements": ["r1"]},
        {"key": "t2", "title": "Two", "description": "d", "requirements": ["r1"]},
    ],
    "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []},
    "lifecycle": "one-off", "open_questions": [],
}
print("write", api("PUT", D + "/documents/%s/content" % path, {"document": pl})[0])
print("close", api("POST", D + "/documents/close-exploration?path=" + path)[0])
c, b = api("POST", D + "/documents/propose?path=" + path)
print("propose", c, b.get("phase"), b.get("blocking"))
c, b = api("POST", D + "/documents/phase?path=%s&to=approved" % path, {"reason": "drive"})
print("approve", c, b.get("phase"))
DOCID = b.get("id")
print("doc id", DOCID)


def flow(name):
    return api(
        "POST", S + "/jobs",
        {"name": name, "agent": "kimi", "message": "Work the queue", "cron": "0 9 * * *",
         "purpose": "Drive b11", "spec_document_id": DOCID or path},
    )


c, j1 = flow("Flow one")
print("flow1", c, str(j1)[:200])
loop1 = (j1.get("loop") or {}).get("id")
c, t = api("GET", S + "/tasks?loop_id=%s" % loop1)
print("loop1 queue", c, [(x["id"], x["status"]) for x in (t if isinstance(t, list) else t.get("tasks", t))])
c, b = api("POST", S + "/jobs/%s/archive" % j1["id"])
print("archive flow1", c)
c, j2 = flow("Flow two")
print("flow2", c, str(j2)[:120])
loop2 = (j2.get("loop") or {}).get("id")
c, t = api("GET", S + "/tasks?loop_id=%s" % loop2)
print("loop2 queue", c, [(x["id"], x["status"], x.get("loop_id")) for x in (t if isinstance(t, list) else t.get("tasks", t))])
c, t = api("GET", S + "/tasks?loop_id=%s" % loop1)
print("loop1 queue after", c, [(x["id"], x["status"]) for x in (t if isinstance(t, list) else t.get("tasks", t))])
c, b = api("GET", S + "/loops/%s" % loop2)
print("loop2 events", [e.get("kind") or e.get("type") for e in (b.get("events") or [])][:10])
c, b = api(
    "POST", S + "/jobs",
    {"name": "Not a loop", "agent": "kimi", "message": "ping", "cron": "0 9 * * *", "spec_document_id": DOCID or path},
)
print("F157 no-purpose create", c, str(b)[:200])
c, b = api("POST", S + "/jobs/%s/archive" % j2["id"])
print("archive flow2", c)
c, b = api("GET", S + "/jobs")
print("jobs left enabled", [(j["name"], j.get("enabled")) for j in (b if isinstance(b, list) else b.get("jobs", []))])
