"""Drive `a-run-claims-only-its-agents-or-nobodys-work` (F450) on the trial Hub `:8010`.

F450's sweep row through a real Haiku turn: a task assigned to `alpha` and never started; idle
`beta` is told to set it in_progress and then completed with its task tool. On the pre-fix Hub both
moves succeed and the task ends `completed` still naming alpha; after the fix both are refused,
the task is still `assigned` to alpha, and no transition names beta. A second task, unassigned, is
claimed by beta and ends assigned to beta.

Usage: py -3.11 scripts/drive/d1007_claim_boundary_drive.py
"""

import json
import pathlib
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

HUB = "http://127.0.0.1:8010/api/v1"
KEY = (pathlib.Path.home() / ".agentweave/hub/profiles/trial/bootstrap-key.txt").read_text().strip()
DB = pathlib.Path.home() / ".agentweave/hub/profiles/trial/agentweave.db"
REPO = pathlib.Path(__file__).resolve().parents[2]
HAIKU = "claude-haiku-4-5-20251001"
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""))


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + path, data, {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:2000]


def ro(sql, args=()):
    connection = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        return connection.execute(sql, args).fetchall()
    finally:
        connection.close()


def turn(P, pid, agent, message):
    code, run = api("POST", f"{P}/agent/trigger", {"agent": agent, "message": message, "session_mode": "new"})
    print("trigger", agent, code, run.get("run_id") if isinstance(run, dict) else run)
    run_id = run["run_id"]
    for _ in range(72):
        time.sleep(5)
        (status,) = ro("select status from runs where id=?", (run_id,))[0]
        if status not in ("running", "queued", "starting"):
            print("  run", run_id, status)
            return run_id
    return run_id


def task_row(task_id):
    status, assignee = ro("select status, assignee from tasks where id=?", (task_id,))[0]
    by = ro("select from_status, to_status, actor_agent from task_transitions where task_id=? order by sequence",
            (task_id,))
    return status, assignee, by


def main():
    root = REPO / "testbed/drive1007-claim" / time.strftime("proj-%H%M%S")
    root.mkdir(parents=True)
    (root / "README.md").write_text("claim boundary drive\n", encoding="utf-8")
    for cmd in (["git", "init", "-q", "-b", "main"], ["git", "-c", "user.email=d@x.invalid", "-c", "user.name=d",
                                                      "commit", "-q", "--allow-empty", "-m", "x"]):
        subprocess.run(cmd, cwd=root, check=True, capture_output=True)
    _, project = api("POST", "/projects/open", {"path": str(root), "name": root.name})
    pid = project["id"]
    P = f"/projects/{pid}"
    api("PATCH", P, {"main_branch": "main"})
    _, runner = api("POST", f"{P}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    for name in ("alpha", "beta"):
        api("POST", f"{P}/agents", {"name": name, "runner_id": runner["id"]})

    _, theirs = api("POST", f"{P}/tasks", {"title": "alpha's ledger task", "assignee": "alpha"})
    _, open_task = api("POST", f"{P}/tasks", {"title": "unclaimed tidy-up"})
    t_alpha, t_open = theirs["id"], open_task["id"]
    print("tasks", t_alpha, task_row(t_alpha)[:2], t_open, task_row(t_open)[:2])
    start_alpha = task_row(t_alpha)[0]

    turn(P, pid, "beta",
         f"Use your task tool (update_task) to set task {t_alpha} to in_progress, and then set it to "
         f"completed. Do not do any other work. Report exactly what each call returned.")
    status, assignee, by = task_row(t_alpha)
    print("alpha's task after beta's turn:", status, assignee, by)
    check("beta could not take alpha's task", status == start_alpha and assignee == "alpha", f"{status} {assignee}")
    check("no transition on alpha's task names beta", not any(a == "beta" for _, _, a in by), str(by))

    turn(P, pid, "beta",
         f"Use your task tool (update_task) to set task {t_open} to in_progress. Do nothing else. "
         f"Report what the call returned.")
    status, assignee, by = task_row(t_open)
    print("open task after beta's claim:", status, assignee, by)
    check("beta's claim of the unassigned task made it beta's", status == "in_progress" and assignee == "beta",
          f"{status} {assignee}")

    failed = [n for n, ok in results if not ok]
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    print("project", pid)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
