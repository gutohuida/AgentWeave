"""Drive F622 (decision D7): a hand-made task with no requirements lands its work on approval.

Before: such a task was approved and Landed, and integration skipped it -- "no accepted evidence
names a commit, so there is nothing to merge" -- with nothing anyone could record to change it.
After: the approved review is the gate, and the task's own branch tip merges into main.

  py -3.11 scripts/drive/d1015_f622_land_without_requirements.py <project-id> [agent]

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


def main(project, agent="alpha"):
    directory = pathlib.Path(
        e2e.ro().execute("select working_directory from projects where id=?", (project,)).fetchone()[0]
    )
    settings = e2e.call("GET", f"/projects/{project}/settings")
    settings["main_branch"] = "master"
    e2e.call("PUT", f"/projects/{project}/settings", settings)
    task_id = e2e.call(
        "POST", f"/projects/{project}/tasks", {"title": "Add GREETING.txt", "assignee": agent}
    )["id"]
    run_id = e2e.cmd_turn(
        project, agent,
        "Create a file GREETING.txt in your workspace containing the word hello, then reply DONE.",
        task=task_id, fresh=True,
    )
    check("the task's turn started", run_id is not None)
    if run_id is None:
        return
    e2e.wait_for(run_id, 5)
    for status in ("completed", "under_review", "approved"):
        code, body = e2e.request("PATCH", f"/projects/{project}/tasks/{task_id}", {"status": status})
        if code != 200:
            check(f"move to {status}", False, f"{code} {str(body)[:200]}")
            return
    rows = e2e.call("GET", f"/projects/{project}/tasks/{task_id}/integrations")["integrations"]
    outcomes = [(r.get("outcome"), r.get("reason")) for r in rows]
    check("integration merged the task's work", any(o == "merged" for o, _ in outcomes), str(outcomes))
    shown = subprocess.run(["git", "-C", str(directory), "show", "master:GREETING.txt"],
                           capture_output=True, text=True)
    check("main holds the task's file", shown.returncode == 0 and "hello" in shown.stdout,
          (shown.stdout or shown.stderr).strip()[:120])


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception as exc:  # a broken drive is a failure, never a pass
        failures.append(f"drive raised {exc!r}")
        raise
    finally:
        print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
