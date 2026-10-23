"""Dependencies sweep 2026-10-23, part 1: the planner's same-file warning through the operator doors.

A document with two tasks sharing lib.py and no depends_on, plus two tasks with no `files`.
Reads what the save, propose and approve answers say, then what the materialised tasks carry.
"""

from s1023_dp_common import BASE, doc_route, make_doc, sc, show

tasks = [
    {"key": "t1", "title": "Add add()", "description": "Add add() to lib.py.",
     "requirements": ["r1"], "files": ["lib.py"]},
    {"key": "t2", "title": "Add sub()", "description": "Add sub() to lib.py.",
     "requirements": ["r2"], "files": ["./lib.py"]},
    {"key": "t3", "title": "Add mul()", "description": "Add mul() somewhere.",
     "requirements": ["r3"]},
    {"key": "t4", "title": "Add div()", "description": "Add div() somewhere.",
     "requirements": ["r4"], "depends_on": ["t3"]},
]
path, code, res, payload = make_doc("Planner warning fixture", tasks)
print("DOC", path)
show("PUT content", code, res, 3000)

code, res = sc.api("POST", doc_route("close-exploration", path))
show("close-exploration", code, res, 800)
code, res = sc.api("POST", doc_route("propose", path))
show("propose", code, res, 3000)
code, res = sc.api("POST", doc_route("phase", path, "&to=approved"), {"reason": "drive"})
show("approve (no anyway)", code, res, 3000)
code, res = sc.api("POST", doc_route("phase", path, "&to=approved"),
                   {"reason": "drive", "approve_anyway": True})
show("approve anyway", code, res, 1500)

code, page = sc.api("GET", f"{BASE}/tasks?limit=500")
rows = page["tasks"] if isinstance(page, dict) else page
for t in rows:
    print(t["id"], t["status"], repr(t["title"]), "depends_on=", t.get("depends_on"),
          "files=", t.get("files"), "spec_task_key=", t.get("spec_task_key"))
