"""Dependencies sweep 2026-10-23, part 2: a hand-authored A -> B -> C and every refusal around it.

Operator routes only (POST /tasks with depends_on, POST/DELETE /tasks/{id}/dependencies, PATCH).
Usage: s1023_dp_chain.py <other-project-id>
"""

import sys

from s1023_dp_common import BASE, sc, show

OTHER = sys.argv[1]


def mk(title, **extra):
    code, t = sc.api("POST", f"{BASE}/tasks", {"title": title, **extra})
    show(f"create {title!r} {extra}", code, t if code >= 300 else {"id": t.get("id"),
         "status": t.get("status"), "prerequisites": t.get("prerequisites")}, 700)
    return t.get("id") if isinstance(t, dict) else None


def dep(task, on):
    code, r = sc.api("POST", f"{BASE}/tasks/{task}/dependencies", {"depends_on": on})
    show(f"POST {task}/dependencies {on}", code, r, 600)


def patch(task, body):
    code, r = sc.api("PATCH", f"{BASE}/tasks/{task}", body)
    out = r if code >= 300 else {"status": r.get("status"), "assignee": r.get("assignee")}
    show(f"PATCH {task} {body}", code, out, 900)


a = mk("A: write notes.txt")
b = mk("B: extend notes.txt", depends_on=[a])
c = mk("C: final notes", depends_on=[b])

# Refusals at creation
_, other = sc.api("POST", f"/projects/{OTHER}/tasks", {"title": "foreign task"})
foreign = other["id"]
print("foreign task in", OTHER, foreign)
mk("X: unknown prereq", depends_on=["task-nope00000000"])
mk("X: cross-project prereq", depends_on=[foreign])
mk("X: self prereq", id="task-selfdep00001", depends_on=["task-selfdep00001"])
mk("X: born in_progress with unmet prereq", depends_on=[c], status="in_progress")
mk("X: born approved with unmet prereq", depends_on=[c], status="approved")

# Refusals on the dependencies route
dep(a, a)
dep(a, c)  # cycle
dep(c, b)  # duplicate
dep(a, foreign)
dep(foreign, a)
dep(a, "task-nope00000000")
code, r = sc.api("DELETE", f"{BASE}/tasks/{a}/dependencies/{c}")
show("DELETE a/dependencies/c (no such edge)", code, r)

# Start B while A is unapproved
patch(b, {"status": "assigned", "assignee": "beta"})
patch(b, {"status": "in_progress"})
code, r = sc.api("GET", f"{BASE}/tasks/{b}")
print("B dependency_state:", r.get("dependency_state"), "prereqs:", r.get("prerequisites"))
print("IDS", a, b, c, foreign)
