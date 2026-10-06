"""Acceptance drive for `approval-runs-the-projects-checks` (Tier 2), one phase per invocation.

Drives a Hub started with `e2e.py hub-up` (never :8000/:8010), with real Haiku agents:

    setup     project with a passing pytest test, check `py -3.11 -m pytest -q`, builder + reviewer
    break     the builder breaks the test and completes its task -> a run is recorded `failed`
    review    the reviewer is dispatched; its context names the failure; `approved` is refused with
              the output tail; it sends the task back (`revision_needed`)
    fix       the builder fixes the test and completes -> run `passed`; the reviewer approves; merged
    override  a second task breaks the test; the operator approves with a reason; history shows it
    restart   (run by hand) kill the Hub mid-run, restart it -> the run reads `interrupted`, and
              approval starts a new run
    show      every check run row

Before the build, `setup` fails: the settings route refuses a `checks` field. State lives in
testbed/scratch/checks-drive/state.json. Run from the repo root with `py -3.11`.
"""

import json
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path.home() / ".claude" / "skills" / "e2e-loop"))
sys.stdout.reconfigure(encoding="utf-8")
import e2e  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
STATE = REPO / "testbed" / "scratch" / "checks-drive" / "state.json"
HAIKU = "claude-haiku-4-5-20251001"
CHECK = {"name": "tests", "command": "py -3.11 -m pytest -q", "timeout_seconds": 300}

TEST = '''from calc import add


def test_add():
    assert add(2, 3) == 5
'''
CALC = '''def add(a, b):
    return a + b
'''


def load():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def save(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def must(status, body, what):
    if status >= 300:
        raise SystemExit(f"FAIL {what}: HTTP {status} {json.dumps(body)[:800]}")
    return body


def runs(task_id):
    return [
        dict(r)
        for r in e2e.ro().execute(
            "select state, main_sha, results, started_at from task_check_runs"
            " where task_id=? order by started_at",
            (task_id,),
        )
    ]


def wait_run(task_id, terminal=("passed", "failed", "error"), minutes=10):
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        rows = runs(task_id)
        if rows and rows[-1]["state"] in terminal:
            return rows[-1]
        time.sleep(5)
    raise SystemExit(f"FAIL no terminal check run for {task_id}: {runs(task_id)}")


def turn(project, agent, message, task=None):
    run_id = e2e.cmd_turn(project, agent, message, task=task, fresh=True)
    if not run_id:
        raise SystemExit(f"FAIL turn for {agent}")
    e2e.wait_for(run_id, 15)
    return run_id


def setup():
    project = e2e.cmd_setup("aw-checks-1006")
    root = pathlib.Path.home() / "Documents" / "aw-checks-1006"
    (root / "calc.py").write_text(CALC, encoding="utf-8")
    (root / "test_calc.py").write_text(TEST, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "calc + test"], cwd=root, check=True)
    branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=root, capture_output=True, text=True
    ).stdout.strip()
    settings = must(*e2e.request("GET", f"/projects/{project}/settings"), "read settings")
    settings.update({"main_branch": branch, "checks": [CHECK]})
    saved = must(*e2e.request("PUT", f"/projects/{project}/settings", settings), "save checks")
    assert saved.get("checks") == [CHECK], f"FAIL checks did not round-trip: {saved.get('checks')}"
    e2e.cmd_agent(project, "builder", "-", "claude", HAIKU)
    e2e.cmd_agent(project, "reviewer", "-", "claude", HAIKU)
    save({"project": project, "root": str(root)})
    print("PASS setup: checks saved and read back")


def new_task(project, title, description):
    body = {"title": title, "description": description, "assignee": "builder"}
    return must(*e2e.request("POST", f"/projects/{project}/tasks", body), "create task")["id"]


def break_():
    state = load()
    project = state["project"]
    task = new_task(
        project,
        "Make add subtract",
        "Change calc.add so it returns a - b. Do not edit the tests. Then mark this task completed.",
    )
    turn(project, "builder", f"Do task {task}: change calc.add to return a - b, commit nothing "
         "else, do not touch tests, then set the task to completed with update_task.", task=task)
    row = wait_run(task)
    assert row["state"] == "failed", f"FAIL expected failed, got {row}"
    state["task"] = task
    save(state)
    print("PASS break: run failed ->", json.loads(row["results"])[0].get("exit_code"))


def review():
    state = load()
    project, task = state["project"], state["task"]
    status, res = e2e.request(
        "POST",
        f"/projects/{project}/agent/trigger",
        {"agent": "reviewer", "message": f"Review task {task} and record your verdict.",
         "review_task_id": task, "session_mode": "new"},
    )
    run_id = must(status, res, "dispatch review")["run_id"]
    e2e.wait_for(run_id, 15)
    st = e2e.ro().execute("select status from tasks where id=?", (task,)).fetchone()["status"]
    assert st == "revision_needed", f"FAIL reviewer left the task {st}"
    print("PASS review: sent back")


def fix():
    state = load()
    project, task = state["project"], state["task"]
    turn(project, "builder", f"Task {task} came back: make the tests pass again (calc.add must "
         "return a + b), then set the task to completed.", task=task)
    row = wait_run(task)
    assert row["state"] == "passed", f"FAIL expected passed, got {row}"
    status, res = e2e.request(
        "POST",
        f"/projects/{project}/agent/trigger",
        {"agent": "reviewer", "message": f"Review task {task} again and record your verdict.",
         "review_task_id": task, "session_mode": "new"},
    )
    e2e.wait_for(must(status, res, "dispatch review")["run_id"], 15)
    st = e2e.ro().execute("select status from tasks where id=?", (task,)).fetchone()["status"]
    assert st == "approved", f"FAIL expected approved, got {st}"
    print("PASS fix: passed and approved")


def override():
    state = load()
    project = state["project"]
    task = new_task(project, "Break it again", "Change calc.add to return a * b, then complete.")
    turn(project, "builder", f"Do task {task}: change calc.add to return a * b, then set the "
         "task to completed.", task=task)
    assert wait_run(task)["state"] == "failed"
    for status in ("under_review",):
        must(*e2e.request("PATCH", f"/projects/{project}/tasks/{task}", {"status": status}), status)
    refused = e2e.request("PATCH", f"/projects/{project}/tasks/{task}", {"status": "approved"})
    assert refused[0] == 409, f"FAIL operator approval without a reason was not refused: {refused}"
    body = {"status": "approved", "override_checks_reason": "drive: intentional override"}
    must(*e2e.request("PATCH", f"/projects/{project}/tasks/{task}", body), "override")
    history = json.dumps(e2e.request("GET", f"/projects/{project}/tasks/{task}/history")[1])
    assert "drive: intentional override" in history, "FAIL the reason is not in the history"
    print("PASS override: approved with the reason on record")


def show():
    for row in e2e.ro().execute("select * from task_check_runs order by started_at"):
        print(dict(row))


if __name__ == "__main__":
    {"setup": setup, "break": break_, "review": review, "fix": fix, "override": override,
     "show": show}[sys.argv[1]]()
