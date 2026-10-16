"""Drive for fix-D13: Start work on a task resumes the agent's conversation for that task.

Before: every Start work opened a new conversation, so a second press re-discovered the repository
in a fresh provider session (wpc-obs-2). After: the second press queues into the first
conversation, and its run resumes the first run's provider session.

  py -3.11 scripts/drive/d1016_d13_start_work_resumes.py <project-name>

Drives the Hub `e2e.py hub-up` started (never :8000 or :8010). Two Haiku turns, each sent exactly
as the UI's Start work sends it (`useStartWorkOnTask`: agent, message, task_id). Exit 1 on any fail.
"""

import importlib.util
import pathlib
import sys

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

HAIKU = "claude-haiku-4-5-20251001"
AGENT = "builder"
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def start_work(project, task_id, title):
    # The UI's own message (`startWorkMessage`), shortened: the route keys on task_id only.
    status, res = e2e.request(
        "POST",
        f"/projects/{project}/agent/trigger",
        {
            "agent": AGENT,
            "message": f"Start work on {task_id}: {title}. Reply with one short sentence; do not "
            "edit any file or run any command.",
            "task_id": task_id,
        },
    )
    if status >= 300:
        raise SystemExit(f"trigger -> {status}: {res}")
    return res


def run_row(run_id):
    return e2e.ro().execute(
        "select conversation_id, session_id, status from runs where id=?", (run_id,)
    ).fetchone()


def latest_run(conversation_id):
    row = e2e.ro().execute(
        "select id from runs where conversation_id=? order by started_at desc limit 1",
        (conversation_id,),
    ).fetchone()
    return row["id"] if row else None


def main(name):
    project = e2e.cmd_setup(name)
    runner = e2e.call(
        "POST", f"/projects/{project}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU}
    )
    status, res = e2e.request(
        "POST", f"/projects/{project}/agents", {"name": AGENT, "runner_id": runner["id"]}
    )
    if status >= 300 and status != 409:
        raise SystemExit(f"agent -> {status}: {res}")
    task = e2e.call(
        "POST", f"/projects/{project}/tasks", {"title": "Say hello", "assignee": AGENT}
    )
    task_id = task["id"]

    first = start_work(project, task_id, "Say hello")
    run1 = first.get("run_id") or latest_run(first["conversation_id"])
    final1 = e2e.wait_for(run1, minutes=4)
    check("the first Start work run completed", final1 == "completed", final1)

    second = start_work(project, task_id, "Say hello")
    check(
        "the second Start work joins the first conversation",
        second["conversation_id"] == first["conversation_id"],
        f"{first['conversation_id']} then {second['conversation_id']}",
    )
    run2 = second.get("run_id") or latest_run(second["conversation_id"])
    final2 = e2e.wait_for(run2, minutes=4)
    check("the second run completed", final2 == "completed", final2)
    row1, row2 = run_row(run1), run_row(run2)
    check(
        "the second run resumed the first provider session",
        bool(row1["session_id"]) and row1["session_id"] == row2["session_id"],
        f"{row1['session_id']} / {row2['session_id']}",
    )
    count = e2e.ro().execute(
        "select count(*) from conversations where agent=? and project_id=?", (AGENT, project)
    ).fetchone()[0]
    check("the agent has one conversation", count == 1, str(count))


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception as exc:  # noqa: BLE001 - a raise is a failure, never ALL PASS
        failures.append(f"raised: {exc!r}")
    print("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)
