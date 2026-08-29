"""Does an assignee nobody can be wedge the review gate?

`PATCH /tasks/{id}` accepts `assignee` without checking the roster, so a task can be assigned to a
name that is on no roster. `review_dispatch_refusal` reads `task.assignee` to refuse a second
reviewer — so if the holder is a ghost, the refusal names an agent that cannot finish, and its
stated remedy ("let the review in flight finish") can never occur.

This asks whether that is reachable, or whether something upstream catches it first.

Run: AW_PROJECT=<proj> AW_KEY=<key> py -3.11 scripts/drive/t_ghost_assignee.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api, show  # noqa: E402

code, task = api("POST", f"/projects/{P}/tasks", {"title": "Ghost-held review subject"})
tid = task["id"]
print(f"task {tid}")

for status in ("in_progress", "completed"):
    code, out = api("PATCH", f"/projects/{P}/tasks/{tid}", {"status": status})
    print(f"  -> {status}: {code}")

code, out = api("PATCH", f"/projects/{P}/tasks/{tid}", {"assignee": "ghost-reviewer"})
print(f"assign to a name on no roster: {code}")

code, out = api("PATCH", f"/projects/{P}/tasks/{tid}", {"status": "under_review"})
print(f"-> under_review: {code}")

code, out = api("GET", f"/projects/{P}/tasks/{tid}")
print(f"task now: status={out.get('status')!r} assignee={out.get('assignee')!r}")

print()
print("Now dispatch a real reviewer at it — the same call an operator makes from the board.")
code, out = api(
    "POST",
    f"/projects/{P}/agent/trigger",
    {"agent": "driver", "review_task_id": tid, "message": "please review"},
)
show("POST /agent/trigger (review dispatch)", code, out)

print()
print("And can the ghost be cleared, so the operator has a way out?")
code, out = api("PATCH", f"/projects/{P}/tasks/{tid}", {"assignee": None})
print(f"PATCH assignee=null: {code}")
code, out = api("GET", f"/projects/{P}/tasks/{tid}")
print(f"assignee after clearing: {out.get('assignee')!r}")
code, out = api("PATCH", f"/projects/{P}/tasks/{tid}", {"assignee": "driver"})
print(f"PATCH assignee=driver: {code}")
code, out = api("GET", f"/projects/{P}/tasks/{tid}")
print(f"assignee after reassigning: {out.get('assignee')!r}")
