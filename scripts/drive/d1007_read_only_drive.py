"""Drive `a-read-only-agent-holds-no-task-work` (F425) on the trial Hub `:8010`.

A real Haiku turn. `reader` is declared read_only (agent PATCH, before it holds anything) and
`writer` is a writing agent. The operator triggers `reader` on an unassigned task, telling it to
create NOTES.md. On the pre-fix Hub the turn starts, binds the task, and runs in the project
directory, so NOTES.md appears in the operator's checkout. After the fix the trigger is refused
409 with the remedy, no run exists, and the project's git status is unchanged. Creating a task
assigned to `reader` is refused 422; one assigned to `writer` is created.

Usage: py -3.11 scripts/drive/d1007_read_only_drive.py
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


def git_status(root):
    return subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout


def main():
    root = REPO / "testbed/drive1007-readonly" / time.strftime("proj-%H%M%S")
    root.mkdir(parents=True)
    (root / "README.md").write_text("read-only drive\n", encoding="utf-8")
    for cmd in (["git", "init", "-q", "-b", "main"], ["git", "add", "README.md"],
                ["git", "-c", "user.email=d@x.invalid", "-c", "user.name=d", "commit", "-q", "-m", "x"]):
        subprocess.run(cmd, cwd=root, check=True, capture_output=True)
    _, project = api("POST", "/projects/open", {"path": str(root), "name": root.name})
    pid = project["id"]
    P = f"/projects/{pid}"
    api("PATCH", P, {"main_branch": "main"})
    _, runner = api("POST", f"{P}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    for name in ("reader", "writer"):
        api("POST", f"{P}/agents", {"name": name, "runner_id": runner["id"]})
    code, patched = api("PATCH", f"{P}/agents/reader", {"config": {"read_only": True}})
    print("reader read_only", code, str(patched)[:200])

    _, open_task = api("POST", f"{P}/tasks", {"title": "write the notes"})
    task_id = open_task["id"]
    before = git_status(root)

    code, res = api("POST", f"{P}/agent/trigger", {
        "agent": "reader", "task_id": task_id, "session_mode": "new",
        "message": "Create a file named NOTES.md in your current working directory containing the "
                   "single line 'reader was here'. Do nothing else.",
    })
    print("trigger reader on the task", code, str(res)[:300])
    if code == 200 and isinstance(res, dict) and res.get("run_id"):
        for _ in range(72):
            time.sleep(5)
            (status,) = ro("select status from runs where id=?", (res["run_id"],))[0]
            if status not in ("running", "queued", "starting"):
                print("  run", res["run_id"], status)
                break
    check("the read-only agent's work turn is refused", code == 409 and "read-only" in str(res), f"{code}")
    check("the refusal names the remedy", "writing agent" in str(res) and "read_only" in str(res))
    runs = ro("select id from runs where project_id=? and agent='reader'", (pid,))
    check("no run of reader exists", not runs, str(runs))
    after = git_status(root)
    check("the operator's checkout is unchanged", after == before and not (root / "NOTES.md").exists(),
          repr(after))

    code, res = api("POST", f"{P}/tasks", {"title": "for reader", "assignee": "reader"})
    check("a task cannot be created for the read-only agent", code == 422, f"{code} {str(res)[:160]}")
    code, res = api("POST", f"{P}/tasks", {"title": "for writer", "assignee": "writer"})
    check("a task for the writing agent is created", code == 201, f"{code}")

    failed = [n for n, ok in results if not ok]
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    print("project", pid)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
