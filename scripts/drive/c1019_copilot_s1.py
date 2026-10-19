"""Scenario 1 (2026-10-19 Copilot stall drive): a plain Copilot turn, then a task turn that edits a
file and runs a quick command. Two prompted Copilot turns (claude-haiku-4.5), default posture.

    py -3.11 scripts/drive/c1019_copilot_s1.py plain|task
"""

import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from c1019_copilot_lib import P, e2e, poll, report, req  # noqa: E402

which = sys.argv[1]
if which == "plain":
    rid = e2e.cmd_turn(P, "cop", "Reply with just the word OK and nothing else.", fresh=True)
    print(poll(rid, 300))
    report(rid)
elif which == "task":
    s, t = req("POST", f"/projects/{P}/tasks", {
        "title": "Fix add()", "assignee": "cop",
        "description": "src/calc.py add() subtracts. Make it add, then run the tests."})
    print("task:", s, t.get("id"), t.get("status"))
    rid = e2e.cmd_turn(
        P, "cop",
        "Work on your task: in src/calc.py make add(a, b) return a + b. Then run "
        "`py -3.11 -m pytest -q tests` once and tell me the result in one line. Do not ask me "
        "anything.",
        task=t["id"], fresh=True)
    print(poll(rid, 600))
    report(rid)
    print("task now:", req("GET", f"/projects/{P}/tasks/{t['id']}")[1].get("status"))
