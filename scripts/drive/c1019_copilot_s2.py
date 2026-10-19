"""Scenario 2 (2026-10-19 Copilot stall drive): a task turn whose work needs a file outside the
workspace, so the Workspace judge refuses it, and (after the Hub's one continuation) likely again.
What does the operator see; is the run `completed` with no reply; is the task left in_progress?

    py -3.11 scripts/drive/c1019_copilot_s2.py
"""

import pathlib
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from c1019_copilot_lib import P, e2e, poll, q, report, req  # noqa: E402

out = pathlib.Path.home() / "Documents" / "aw-c1019-outside"
out.mkdir(exist_ok=True)
(out / "notes.txt").write_text("Requirement: mul(a, b) must also accept a third optional "
                               "argument c (default 1) and return a * b * c.\n", encoding="utf-8")
s, t = req("POST", f"/projects/{P}/tasks", {
    "title": "Apply the mul() requirement", "assignee": "cop",
    "description": f"The requirement is in {out / 'notes.txt'}. Apply it to src/calc.py."})
print("task:", s, t.get("id"))
rid = e2e.cmd_turn(
    P, "cop",
    f"Work on your task: read the requirement in {out / 'notes.txt'} and apply it to "
    "src/calc.py, then run `py -3.11 -m pytest -q tests` and report in one line. Do not ask me "
    "anything.",
    task=t["id"], fresh=True)
print(poll(rid, 700))
report(rid)
print("task now:", req("GET", f"/projects/{P}/tasks/{t['id']}")[1].get("status"))
for r in q("select id, code, severity, summary from run_diagnostics where run_id=?", rid) if q(
        "select 1 from sqlite_master where name='run_diagnostics'") else []:
    print("DIAG", r)
