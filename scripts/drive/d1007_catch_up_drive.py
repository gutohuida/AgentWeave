"""Drive `a-task-checkout-catches-up-with-its-approved-prerequisites` (F158) on the trial Hub `:8010`.

The test guide's human-only step, through the real trigger and real Haiku turns: task B depends on
task A; B is worked first, so its branch is cut without A's work (shape 1); A is worked and approved;
B's next turn finds A's commit in its checkout, its own work still there.

Usage: py -3.11 scripts/drive/d1007_catch_up_drive.py
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
        HUB + path, data, {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}, method=method
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


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True).stdout.strip()


def turn(A, task_id, message):
    code, run = api("POST", f"{A}/agent/trigger", {"agent": "worker", "message": message, "session_mode": "new", "task_id": task_id})
    print("trigger", task_id, code, run if code != 200 else run.get("run_id"))
    run_id = run["run_id"]
    for _ in range(120):
        time.sleep(5)
        (status,) = ro("select status from runs where id=?", (run_id,))[0]
        if status not in ("running", "queued", "starting"):
            print("  run", run_id, status)
            return status
    return "timeout"


def main():
    root = REPO / "testbed/drive1007-catchup" / time.strftime("proj-%H%M%S")
    root.mkdir(parents=True)
    (root / "README.md").write_text("catch-up drive\n", encoding="utf-8")
    for cmd in (["git", "init", "-b", "main"], ["git", "config", "user.email", "d@example.invalid"],
                ["git", "config", "user.name", "d"], ["git", "add", "."], ["git", "commit", "-m", "x"]):
        subprocess.run(cmd, cwd=root, check=True, capture_output=True)
    _, project = api("POST", "/projects/open", {"path": str(root), "name": root.name})
    pid = project["id"]
    A = f"/projects/{pid}"
    api("PATCH", f"/projects/{pid}", {"main_branch": "main"})
    _, runner = api("POST", f"{A}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    api("POST", f"{A}/agents", {"name": "worker", "runner_id": runner["id"]})
    # On a loop whose work needs no evidence, a task's work is its branch tip (F510's shape), so an
    # approved prerequisite has a commit to bring in. A plain task approved without evidence merges
    # nothing, and so offers nothing to catch up on -- the first run of this drive found exactly that.
    code, job = api("POST", f"{A}/jobs", {
        "name": "catch-up drive", "agent": "worker", "message": "x", "cron": "0 9 1 1 *",
        "purpose": "catch-up drive", "work_needs_evidence": False, "enabled": False,
    })
    loop_id = job["loop"]["id"]
    print("loop", code, loop_id)
    _, task_a = api("POST", f"{A}/tasks", {"title": "Write a.txt", "loop_id": loop_id})
    _, task_b = api("POST", f"{A}/tasks", {"title": "Write b.txt", "loop_id": loop_id})
    a, b = task_a["id"], task_b["id"]
    code, dep = api("POST", f"{A}/tasks/{b}/dependencies", {"depends_on": a})
    print("dependency", code)

    turn(A, b, "Create a file named b.txt containing the single line: b. Do nothing else and do not commit.")
    b_checkout = root / ".agentweave" / "tasks" / b
    check("B's checkout exists", b_checkout.is_dir(), str(b_checkout))

    turn(A, a, "Create a file named a.txt containing the single line: a. Do nothing else and do not commit.")
    code, moved = api("PATCH", f"{A}/tasks/{a}", {"status": "completed"})
    print("A completed", code, moved if code != 200 else moved["status"])
    code, landed = api("POST", f"{A}/tasks/{a}/land")
    print("A landed", code, landed if code != 200 else landed["status"])
    a_tip = git(root, "rev-parse", f"agentweave/task/{a}")
    check("A is approved", ro("select status from tasks where id=?", (a,))[0][0] == "approved")
    check("A's commit is not yet in B's checkout", subprocess.run(
        ["git", "merge-base", "--is-ancestor", a_tip, "HEAD"], cwd=b_checkout).returncode != 0)

    turn(A, b, "List the names of the files in your working directory, and nothing else.")
    check("A's commit is in B's checkout after its next turn", subprocess.run(
        ["git", "merge-base", "--is-ancestor", a_tip, "HEAD"], cwd=b_checkout).returncode == 0, a_tip[:12])
    check("a.txt is present in B's checkout", (b_checkout / "a.txt").exists())
    check("B's own b.txt is still there", (b_checkout / "b.txt").exists())
    print(git(b_checkout, "log", "--oneline", "-6"))
    failed = [n for n, ok in results if not ok]
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
