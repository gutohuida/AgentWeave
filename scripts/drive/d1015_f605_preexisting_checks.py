"""Acceptance drive for F605: a check that fails on main too is not the task's.

Before: main carried a failing check, every task's check run failed on it, and Land said approving
"would land work that breaks the project" and told the reviewer to send it back; the operator's
only exit was four PATCHes. After: the refusal says the check fails on main too, has no send-back
line and is held for the operator, and Land with an override reason lands the task.

  py -3.11 scripts/drive/d1015_f605_preexisting_checks.py <project-id> [agent]

One Haiku turn. Exit 1 when any check fails.
"""

import importlib.util
import pathlib
import sys
import time

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

failures = []

#: Fails on main and on the task alike: nothing in either tree says it.
CHECK = {"name": "main-defect", "command": "git grep -q DEFECT-FIXED"}
SENDS_BACK = "fixing what the checks found is its author's work"


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def check_runs(task_id):
    return [dict(r) for r in e2e.ro().execute(
        "select state, results from task_check_runs where task_id=? order by started_at", (task_id,))]


def settle(task_id):
    deadline = time.time() + 120
    while time.time() < deadline:
        runs = check_runs(task_id)
        if runs and runs[-1]["state"] != "running":
            return runs
        time.sleep(2)
    return check_runs(task_id)


def land(project, task_id, body=None):
    code, res = e2e.request("POST", f"/projects/{project}/tasks/{task_id}/land", body or {})
    detail = res.get("detail") if isinstance(res, dict) else None
    return code, res, detail if isinstance(detail, dict) else {"message": str(detail or res)}


def main(project, agent="alpha"):
    settings = e2e.call("GET", f"/projects/{project}/settings")
    settings["main_branch"] = "master"
    settings["checks"] = [CHECK]
    e2e.call("PUT", f"/projects/{project}/settings", settings)
    task_id = e2e.call(
        "POST", f"/projects/{project}/tasks", {"title": "Write NOTE.txt", "assignee": agent}
    )["id"]
    run_id = e2e.cmd_turn(
        project, agent,
        "Create NOTE.txt in your workspace containing the line: a note. Commit it with git "
        "(message: note), then reply DONE.",
        task=task_id, fresh=True,
    )
    check("the task's turn started", run_id is not None)
    if run_id is None:
        return
    e2e.wait_for(run_id, 5)
    code, body = e2e.request("PATCH", f"/projects/{project}/tasks/{task_id}", {"status": "completed"})
    check("move to completed", code == 200, f"{code} {str(body)[:200]}")
    print(f"  check runs: {[r['state'] for r in settle(task_id)]}")

    code, _, detail = land(project, task_id)
    message = detail.get("message", "")
    entry = (detail.get("checks") or [{}])[0]
    print(f"  land -> {code}: {message[:400]}")
    check("Land is refused on the checks", code == 409 and bool(detail.get("checks")), str(detail)[:300])
    check("the refusal says the check fails on main too", "on main" in message, message[:300])
    check("the refusal does not tell a reviewer to send it back", SENDS_BACK not in message, message[:300])
    check("the checks entry is pre-existing", entry.get("state") == "preexisting", str(entry)[:200])

    code, res, detail = land(project, task_id, {"override_checks_reason": "main carries the defect"})
    check("Land with an override reason lands it", code == 200, f"{code} {str(res)[:300]}")
    row = e2e.ro().execute(
        "select override_reason from task_transitions where task_id=? and to_status='approved'",
        (task_id,),
    ).fetchone()
    check("the transition records the reason", row is not None and row[0] == "main carries the defect",
          str(dict(row) if row else None))


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception as exc:  # a broken drive is a failure, never a pass
        failures.append(f"drive raised {exc!r}")
        raise
    finally:
        print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
