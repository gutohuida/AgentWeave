"""Acceptance drive for F603: work from a turn that claimed its task mid-turn reaches the task.

Before: a mail turn ran in the agent's own worktree, claimed task A partway through and fixed it
there; the task's checkout was later cut fresh from main for the review, so the reviewer saw the
unfixed code and sent it back. After: at the run's end the turn's commits are carried onto the
task's own branch, which is what a review checks out and what Land merges.

  py -3.11 scripts/drive/d1015_f603_mid_turn_claim.py <project-id> [agent]

One Haiku turn. Exit 1 when any check fails.
"""

import importlib.util
import pathlib
import subprocess
import sys

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def git(directory, *args):
    return subprocess.run(["git", "-C", str(directory), *args], capture_output=True, text=True)


def main(project, agent="alpha"):
    directory = pathlib.Path(
        e2e.ro().execute("select working_directory from projects where id=?", (project,)).fetchone()[0]
    )
    task = e2e.call("POST", f"/projects/{project}/tasks", {"title": "Write FIX.txt saying fixed"})
    task_id = task["id"]
    run_id = e2e.cmd_turn(
        project, agent,
        f"There is a task {task_id}. Do these steps in order: 1) move task {task_id} to "
        "in_progress with the Hub's update_task tool; 2) create a file FIX.txt in your workspace "
        f"containing the word fixed; 3) move task {task_id} to completed. Then reply DONE.",
        fresh=True,
    )
    check("the untasked turn started", run_id is not None)
    if run_id is None:
        return
    e2e.wait_for(run_id, 6)
    row = e2e.ro().execute("select task_id, workspace_dir from runs where id=?", (run_id,)).fetchone()
    check("the run claimed the task mid-turn", row["task_id"] == task_id, str(dict(row)))
    check("and ran in the agent's own worktree", "worktrees" in (row["workspace_dir"] or ""),
          row["workspace_dir"] or "")
    status = e2e.ro().execute("select status from tasks where id=?", (task_id,)).fetchone()["status"]
    check("the task was completed", status == "completed", status)
    branch = f"agentweave/task/{task_id}"
    shown = git(directory, "show", f"{branch}:FIX.txt")
    check("the task's own branch carries the turn's work", shown.returncode == 0 and "fixed" in shown.stdout,
          (shown.stdout or shown.stderr).strip()[:160])
    target = e2e.request("GET", f"/projects/{project}/tasks/{task_id}")[1]
    print("task:", {k: target.get(k) for k in ("status", "assignee")} if isinstance(target, dict) else target)


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception as exc:  # a broken drive is a failure, never a pass
        failures.append(f"drive raised {exc!r}")
        raise
    finally:
        print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
