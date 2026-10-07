"""Drive `a-decided-task-withdraws-its-waiting-reviews` (F440) on the trial Hub `:8010`.

Acceptance criterion `drive`: a review requested by hand for a reviewer mid-turn (a real Haiku turn
running `python slow_step.py`, which sleeps 60 s) is queued; the operator lands the task before that
turn ends. The entry reads `withdrawn` with the verdict, and after the reviewer's turn ends no review
of the task is delivered and no refusal is recorded. Before the fix the entry stays `queued`, and
the run-end re-drain delivers it into a refusal ("not a status a review starts from").

Usage: py -3.11 scripts/drive/d1007_verdict_withdraws_review.py
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


def git(root, *args):
    out = subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
                         cwd=root, capture_output=True, text=True)
    assert out.returncode == 0, (args, out.stderr)
    return out.stdout.strip()


def wait(predicate, seconds, step=3):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return False


def main():
    root = REPO / "testbed/drive1007-verdict" / time.strftime("proj-%H%M%S")
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "slow_step.py").write_text("import time\ntime.sleep(60)\nprint('slow step done')\n",
                                       encoding="utf-8")
    git(root, "add", "slow_step.py")
    git(root, "commit", "-q", "-m", "seed")

    _, project = api("POST", "/projects/open", {"path": str(root), "name": root.name})
    pid = project["id"]
    P = f"/projects/{pid}"
    api("PATCH", P, {"main_branch": "main"})
    _, runner = api("POST", f"{P}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    for name in ("builder", "critic"):
        api("POST", f"{P}/agents", {"name": name, "runner_id": runner["id"]})

    # A task with evidence naming a commit: a review request is refused without one.
    _, doc = api("POST", f"{P}/project/documents", {"title": "verdict drive"})
    path = doc["path"]
    payload = {
        "schema_version": 1, "kind": doc["kind"], "title": "verdict drive", "summary": "s",
        "problem": "p", "scope": {"in_scope": ["ledger"], "non_goals": ["n"]},
        "requirements": [{"key": "led", "statement": "The ledger MUST exist.", "modal": "MUST"}],
        "acceptance_criteria": [{"key": "c", "requirement": "led", "given": "g", "when": "w", "then": "t"}],
        "tasks": [{"key": "t", "title": "ledger", "description": "d", "requirements": ["led"]}],
        "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []},
        "lifecycle": "one-off", "open_questions": [], "delivery": {"mode": "none"},
    }
    _, res = api("PUT", f"{P}/project/documents/{path}/content", {"document": payload})
    identifier = res["identifiers"]["led"]
    api("POST", f"{P}/project/documents/close-exploration?path={path}")
    api("POST", f"{P}/project/documents/propose?path={path}")
    _, res = api("POST", f"{P}/project/documents/phase?path={path}&to=approved", {"reason": "drive"})
    task_id = res["tasks_created"][0]
    git(root, "checkout", "-q", "-b", "work")
    (root / "ledger.py").write_text("x = 1\n", encoding="utf-8")
    git(root, "add", "ledger.py")
    git(root, "commit", "-q", "-m", "ledger")
    code, ev = api("POST", f"{P}/project/spec/evidence", {
        "identifier": identifier, "summary": "ledger.py exists", "kind": "test_result",
        "locator": "ledger.py", "task_id": task_id, "document": path,
    })
    print("evidence", code)
    git(root, "checkout", "-q", "main")
    for step in ("in_progress", "completed"):
        code, moved = api("PATCH", f"{P}/tasks/{task_id}", {"status": step})
        assert code == 200, (step, moved)

    code, busy = api("POST", f"{P}/agent/trigger", {
        "agent": "critic", "session_mode": "new",
        "message": "Run the command `python slow_step.py` in your working directory and wait for it "
                   "to finish, then reply with its output. Do nothing else.",
    })
    print("critic busy turn", code, str(busy)[:160])
    running = wait(lambda: ro("select count(*) from runs where project_id=? and agent='critic' "
                              "and status='running'", (pid,))[0][0] > 0, 60)
    check("critic is mid-turn", running)

    code, queued = api("POST", f"{P}/agent/trigger", {
        "agent": "critic", "message": "Review the finished work.", "review_task_id": task_id,
    })
    print("review request", code, str(queued)[:200])
    rows = ro("select id, state from inbound_queue_entries where project_id=? and review_task_id=?",
              (pid, task_id))
    check("the review is queued behind critic's turn", len(rows) == 1 and rows[0][1] == "queued", str(rows))
    if not rows:
        raise SystemExit("no review entry was queued; nothing to drive")
    entry_id = rows[0][0]

    code, landed = api("POST", f"{P}/tasks/{task_id}/land")
    print("land", code, landed if code != 200 else landed["status"])
    state, reason, attempts = ro(
        "select state, abandoned_reason, delivery_attempts from inbound_queue_entries where id=?",
        (entry_id,))[0]
    check("landing withdraws the waiting review", state == "withdrawn", f"{state} {reason!r}")
    check("its reason names the verdict", "approved" in (reason or ""), repr(reason))
    events = [json.loads(d) for (d,) in ro(
        "select data from event_logs where project_id=? and event_type='queue_entry_withdrawn'", (pid,))]
    check("the withdrawal is announced", any(e.get("entry_id") == entry_id and e.get("verdict") == "approved"
                                              for e in events), str(events)[:200])

    ended = wait(lambda: ro("select count(*) from runs where project_id=? and agent='critic' "
                            "and status='running'", (pid,))[0][0] == 0, 240, step=5)
    check("critic's turn ended", ended)
    time.sleep(5)
    state, reason, attempts = ro(
        "select state, abandoned_reason, delivery_attempts from inbound_queue_entries where id=?",
        (entry_id,))[0]
    check("after the turn, no delivery of the review was attempted", not attempts,
          f"attempts={attempts} state={state} reason={reason!r}")
    runs = ro("select count(*) from runs where project_id=? and agent='critic'", (pid,))[0][0]
    check("no review turn started for the decided task", runs == 1, f"critic runs: {runs}")

    for (left,) in ro("select id from inbound_queue_entries where project_id=? and state='queued'", (pid,)):
        print("withdraw leftover", left, api("DELETE", f"{P}/queue/entries/{left}")[0])
    failed = [n for n, ok in results if not ok]
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    print("project", pid)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
