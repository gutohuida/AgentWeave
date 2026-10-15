"""Drive F613: a Land over a conflicting task says the conflict, not "nothing is wrong yet".

Before: a task whose branch conflicts with main errored every check run ("does not merge cleanly"),
and each Land answered "This task's checks are still running ... Nothing is wrong yet", starting
another run that could only error. After: the conflict is the refusal and no check run starts (a
retry over any other error is said with that error: `test_project_checks_gate.py`).

  py -3.11 scripts/drive/d1015_f613_errored_checks_said.py <project-id> [agent]

One Haiku turn. Exit 1 when any check fails.
"""

import importlib.util
import pathlib
import subprocess
import sys
import time

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


def check_runs(task_id):
    return [
        (row["state"], row["error"])
        for row in e2e.ro().execute(
            "select state, error from task_check_runs where task_id=? order by started_at",
            (task_id,),
        )
    ]


def settle(task_id):
    deadline = time.time() + 120
    while time.time() < deadline:
        runs = check_runs(task_id)
        if runs and runs[-1][0] != "running":
            return runs
        time.sleep(2)
    return check_runs(task_id)


def main(project, agent="alpha"):
    directory = pathlib.Path(
        e2e.ro().execute("select working_directory from projects where id=?", (project,)).fetchone()[0]
    )
    settings = e2e.call("GET", f"/projects/{project}/settings")
    settings["main_branch"] = "master"
    settings["checks"] = [{"name": "git-version", "command": "git --version"}]
    e2e.call("PUT", f"/projects/{project}/settings", settings)
    task_id = e2e.call(
        "POST", f"/projects/{project}/tasks", {"title": "Rewrite NOTE.txt", "assignee": agent}
    )["id"]
    run_id = e2e.cmd_turn(
        project, agent,
        "Create NOTE.txt in your workspace containing exactly the line: from the task. "
        "Commit it with git (message: note), then reply DONE.",
        task=task_id, fresh=True,
    )
    check("the task's turn started", run_id is not None)
    if run_id is None:
        return
    e2e.wait_for(run_id, 5)
    # main gains a different NOTE.txt, so the task's branch no longer merges cleanly.
    (directory / "NOTE.txt").write_text("from main\n", encoding="utf-8")
    git(directory, "add", "NOTE.txt")
    git(directory, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "main note")
    for status in ("completed",):
        code, body = e2e.request("PATCH", f"/projects/{project}/tasks/{task_id}", {"status": status})
        check(f"move to {status}", code == 200, f"{code} {str(body)[:200]}")

    before = settle(task_id)  # completion starts one run (task_transition_service); Land must add none
    answers = []
    for _ in range(3):
        code, body = e2e.request("POST", f"/projects/{project}/tasks/{task_id}/land", {})
        detail = body.get("detail") if isinstance(body, dict) else None
        message = detail.get("message", "") if isinstance(detail, dict) else str(body)
        gate = isinstance(detail, dict) and detail.get("code") == "gate_unsatisfied"
        answers.append((code, message, gate))
        print(f"  land -> {code}: {message[:300]}")
        print(f"  check runs: {settle(task_id)}")
    runs = check_runs(task_id)
    refused = [message for code, message, gate in answers if code == 409 and gate]
    check("every Land was refused by the gate", len(refused) == len(answers), str(answers)[:400])
    check("each refusal names the conflict",
          all("does not merge cleanly" in m for m in refused), str(refused)[:400])
    check("no Land said nothing is wrong",
          all("Nothing is wrong yet" not in m and "still running" not in m for m in refused),
          str(refused)[:400])
    check("no Land started a check run that could only error", len(runs) == len(before), str(runs))


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception as exc:  # a broken drive is a failure, never a pass
        failures.append(f"drive raised {exc!r}")
        raise
    finally:
        print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
