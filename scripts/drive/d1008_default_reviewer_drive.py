"""Acceptance drive for `a-document-names-its-default-reviewer` (F508's default half), on `:8010`.

A fresh project with three Haiku agents: `alice` builds, `critic` is the document's default reviewer,
and `aaa-stub` is a free agent that sorts first, which is the one the flow's rung 2 ("any free
agent", roster in name order) picks when nothing names a reviewer. That is F508's leftover stub.

- A flow-delivered document whose `delivery.reviewer` is `critic`, and no task naming a reviewer.
- While it is proposed, its read says who reviews (`delivery_status.reviewer`).
- Approved: the flow is created from the delivery, never firing on its own (yearly cron).
- The one task is completed by hand, with evidence naming a commit on its own branch.
- Press Run: the review goes to `critic` and the task is `under_review` held by `critic`.

Before the change the Hub keeps `delivery.reviewer` (the payload allows extra fields) and ignores it,
so the review goes to `aaa-stub`. Spends one Haiku review turn.

Usage: py -3.11 scripts/drive/d1008_default_reviewer_drive.py
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
AGENTS = ("alice", "critic", "aaa-stub")
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


def main():
    root = REPO / "testbed/drive1008-defaultreviewer" / time.strftime("proj-%H%M%S")
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("default reviewer drive\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")

    _, project = api("POST", "/projects/open", {"path": str(root), "name": root.name})
    pid = project["id"]
    P = f"/projects/{pid}"
    api("PATCH", P, {"main_branch": "main"})
    _, runner = api("POST", f"{P}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    for name in AGENTS:
        code, _ = api("POST", f"{P}/agents", {"name": name, "runner_id": runner["id"]})
        assert code in (200, 201), (name, code)

    _, doc = api("POST", f"{P}/project/documents", {"title": "default reviewer"})
    path = doc["path"]
    payload = {
        "schema_version": 1, "kind": doc["kind"], "title": "default reviewer", "summary": "s",
        "problem": "p", "scope": {"in_scope": ["ledger"], "non_goals": ["n"]},
        "requirements": [{"key": "led", "statement": "The ledger MUST exist.", "modal": "MUST"}],
        "acceptance_criteria": [{"key": "c", "requirement": "led", "given": "g", "when": "w", "then": "t"}],
        "tasks": [{"key": "ta", "title": "ledger", "description": "d", "requirements": ["led"]}],
        "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []},
        "lifecycle": "one-off", "open_questions": [],
        "delivery": {"mode": "flow", "agent": "alice", "reviewer": "critic",
                     "stop_when_queue_empties": True, "cron": "0 3 1 1 *"},
    }
    code, res = api("PUT", f"{P}/project/documents/{path}/content", {"document": payload})
    assert code == 200, (code, res)
    identifier = res["identifiers"]["led"]
    api("POST", f"{P}/project/documents/close-exploration?path={path}")
    code, res = api("POST", f"{P}/project/documents/propose?path={path}")
    assert isinstance(res, dict) and res.get("phase") == "proposed", res

    _, read = api("GET", f"{P}/project/spec?path={path}")
    status = read.get("delivery_status") or {}
    check("the proposed document's read names its reviewer",
          status.get("reviewer") == "critic" and status.get("reviewer_state") == "ok", json.dumps(status))

    code, res = api("POST", f"{P}/project/documents/phase?path={path}&to=approved", {"reason": "drive"})
    assert code == 200, (code, res)
    (task_id,) = res["tasks_created"][:1]
    flow = (res.get("approval_outcome") or {}).get("flow") or {}
    job_id = flow.get("job_id")
    assert job_id, ("no flow was created", flow)
    print("task", task_id, "flow", job_id)

    try:
        git(root, "checkout", "-q", "-b", "work", "main")
        (root / "ledger.py").write_text("ledger = []\n", encoding="utf-8")
        git(root, "add", "ledger.py")
        git(root, "commit", "-q", "-m", "ledger")
        code, ev = api("POST", f"{P}/project/spec/evidence", {
            "identifier": identifier, "summary": "ledger.py exists", "kind": "test_result",
            "locator": "ledger.py", "task_id": task_id, "document": path,
        })
        assert code == 201, (code, ev)
        git(root, "checkout", "-q", "main")
        for step in ("in_progress", "completed"):
            code, moved = api("PATCH", f"{P}/tasks/{task_id}", {"status": step})
            assert code == 200, (step, moved)

        code, fired = api("POST", f"{P}/jobs/{job_id}/run")
        print("run", code, str(fired)[:300])
        time.sleep(3)
        entries = ro("select agent, state from inbound_queue_entries where review_task_id=? order by sequence",
                     (task_id,))
        check("the review is queued to the document's default reviewer",
              [a for a, _ in entries] == ["critic"], str(entries))
        status, assignee = ro("select status, assignee from tasks where id=?", (task_id,))[0]
        check("the task is under review, held by critic",
              (status, assignee) == ("under_review", "critic"), f"{status} / {assignee}")

        for _ in range(60):
            if all(s != "running" for (s,) in ro("select status from runs where project_id=?", (pid,))):
                break
            time.sleep(5)
    finally:
        print("disable", api("PATCH", f"{P}/jobs/{job_id}", {"enabled": False})[0])
        print("archive", api("POST", f"{P}/jobs/{job_id}/archive")[0])
        for (entry_id,) in ro("select id from inbound_queue_entries where project_id=? and state='queued'", (pid,)):
            print("withdraw", entry_id, api("DELETE", f"{P}/queue/entries/{entry_id}")[0])
    failed = [n for n, ok in results if not ok]
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    print("project", pid)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
