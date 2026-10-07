"""Drive `a-flow-stages-its-review-in-the-dispatch` task 2.8 on the trial Hub `:8010`.

The test guide's human-only step 1 (F327's B1 row) through the real app, and the success path the
dispatch now owns:

- A flow whose two tasks the operator completed, each with evidence naming a commit. The first
  task's commit is pruned from the repository (branch deleted, `git gc --prune=now`).
- Press Run: the reviewer's dispatch is refused for the missing commit. The task still reads
  `completed` with no holder and no new transition (was: `under_review`, held by a reviewer that
  never ran); the firing is `failed` with the refusal.
- Press Run again: the first task is surfaced with the refusal (`review_unstaffed`, "withdraw that
  input") and nobody is re-staffed onto it; the second task's review is dispatched to a real Haiku
  turn and the dispatch stages it (`under_review`, held by that reviewer).
- The operator sends a third agent to the first task: not refused as "already under review".

Usage: py -3.11 scripts/drive/d1007_review_staged_drive.py
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
AGENTS = ("alice", "critic", "other")
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


def task_row(task_id):
    status, assignee = ro("select status, assignee from tasks where id=?", (task_id,))[0]
    (count,) = ro("select count(*) from task_transitions where task_id=?", (task_id,))[0]
    return status, assignee, count


def review_entries(task_id):
    return ro(
        "select agent, state, delivery_attempts, waiting_reason from inbound_queue_entries "
        "where review_task_id=? order by sequence", (task_id,))


def main():
    root = REPO / "testbed/drive1007-reviewstaged" / time.strftime("proj-%H%M%S")
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("review staged drive\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")

    _, project = api("POST", "/projects/open", {"path": str(root), "name": root.name})
    pid = project["id"]
    P = f"/projects/{pid}"
    api("PATCH", P, {"main_branch": "main"})
    _, runner = api("POST", f"{P}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    for name in AGENTS:
        api("POST", f"{P}/agents", {"name": name, "runner_id": runner["id"]})

    _, doc = api("POST", f"{P}/project/documents", {"title": "review staged"})
    path = doc["path"]
    payload = {
        "schema_version": 1, "kind": doc["kind"], "title": "review staged", "summary": "s",
        "problem": "p", "scope": {"in_scope": ["ledger"], "non_goals": ["n"]},
        "requirements": [{"key": "led", "statement": "The ledger MUST exist.", "modal": "MUST"}],
        "acceptance_criteria": [{"key": "c", "requirement": "led", "given": "g", "when": "w", "then": "t"}],
        "tasks": [
            {"key": "ta", "title": "ledger a", "description": "d", "requirements": ["led"]},
            {"key": "tb", "title": "ledger b", "description": "d", "requirements": ["led"]},
        ],
        "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []},
        "lifecycle": "one-off", "open_questions": [], "delivery": {"mode": "none"},
    }
    _, res = api("PUT", f"{P}/project/documents/{path}/content", {"document": payload})
    identifier = res["identifiers"]["led"]
    api("POST", f"{P}/project/documents/close-exploration?path={path}")
    api("POST", f"{P}/project/documents/propose?path={path}")
    code, res = api("POST", f"{P}/project/documents/phase?path={path}&to=approved", {"reason": "drive"})
    doc_id = res.get("id") or path
    task_a, task_b = res["tasks_created"][:2]
    print("tasks", task_a, task_b)

    # Each task's work on its own branch, recorded as operator evidence while the root is there.
    for task_id, branch, body in ((task_a, "work-a", "a = 1\n"), (task_b, "work-b", "b = 2\n")):
        git(root, "checkout", "-q", "-b", branch, "main")
        (root / "ledger.py").write_text(body, encoding="utf-8")
        git(root, "add", "ledger.py")
        git(root, "commit", "-q", "-m", f"ledger {branch}")
        code, ev = api("POST", f"{P}/project/spec/evidence", {
            "identifier": identifier, "summary": "ledger.py exists", "kind": "test_result",
            "locator": "ledger.py", "task_id": task_id, "document": path,
        })
        print("evidence", task_id, code, (ev.get("footprint") or {}).get("commit_sha") if code == 201 else ev)
        for step in ("in_progress", "completed"):
            code, moved = api("PATCH", f"{P}/tasks/{task_id}", {"status": step})
            assert code == 200, (step, moved)
    git(root, "checkout", "-q", "main")
    sha_a = git(root, "rev-parse", "work-a")
    git(root, "branch", "-D", "work-a")
    git(root, "reflog", "expire", "--expire=now", "--all")
    git(root, "gc", "-q", "--prune=now")
    check("task A's commit is gone from the repository",
          subprocess.run(["git", "cat-file", "-e", sha_a], cwd=root).returncode != 0, sha_a[:12])

    code, job = api("POST", f"{P}/jobs", {
        "name": "review staged drive", "agent": "alice", "cron": "0 3 1 1 *", "session_mode": "new",
        "message": "Review the task you are given. Keep it short.",
        "purpose": "review staged drive", "spec_document_id": doc_id,
    })
    assert code == 201, (code, job)
    job_id = job["id"]
    try:
        before_a = task_row(task_a)
        print("before", before_a)

        # Press 1. Width is bounded by free agents, so both reviews are staffed in one firing: A's
        # dispatch is refused for the pruned commit, B's starts a real Haiku review turn.
        code, fired = api("POST", f"{P}/jobs/{job_id}/run")
        print("press 1", code, str(fired)[:200])
        time.sleep(3)
        after_a = task_row(task_a)
        check("A still reads completed, holder unchanged (F327)",
              after_a[:2] == ("completed", before_a[1]), str(after_a))
        check("A travelled no transition", after_a[2] == before_a[2], f"{before_a[2]} -> {after_a[2]}")
        entries = review_entries(task_a)
        print("A's review entries", entries)
        refused = [e for e in entries if e[2] and e[3]]
        check("A's review entry is queued with its refusal", len(refused) == 1 and refused[0][1] == "queued",
              str(entries))
        first_reviewer = refused[0][0] if refused else None
        job_runs = ro("select status, error_summary from job_runs where job_id=?", (job_id,))
        check("A's firing row is failed with the refusal",
              any(s == "failed" and e and "not present" in e for s, e in job_runs), str(job_runs)[:300])
        staged_b = ro(
            "select actor_kind, origin, job_id from task_transitions where task_id=? and to_status='under_review'",
            (task_b,))
        check("B's review was staged by its dispatch, as the flow's move",
              len(staged_b) == 1 and staged_b[0][1:] == ("job", job_id), str(staged_b))
        holder_b = task_row(task_b)[1]
        check("B's reviewer is not A's refused one", holder_b in AGENTS and holder_b != first_reviewer,
              f"{holder_b} vs {first_reviewer}")
        runs_b = ro("select id, status from runs where project_id=? and agent=?", (pid, holder_b))
        check("B's reviewer has a real run", bool(runs_b), str(runs_b[:1]))

        # The operator's own remedy: a different reviewer for A.
        third = next(a for a in AGENTS if a not in (first_reviewer, holder_b))
        code, sent = api("POST", f"{P}/agent/trigger",
                         {"agent": third, "message": "review it", "review_task_id": task_a})
        print("operator sends", third, code, str(sent)[:300])
        check("the operator's other reviewer is not refused as already under review",
              "already under review" not in str(sent), str(sent)[:200])
        check("A is still completed after the operator's request", task_row(task_a)[:2] == after_a[:2],
              str(task_row(task_a)))

        for _ in range(60):
            time.sleep(5)
            if all(s != "running" for (s,) in ro("select status from runs where project_id=?", (pid,))):
                break
        print("B after its review", task_row(task_b))

        # Press 2: A is surfaced with its refusal and nobody is re-staffed onto it.
        before_events = ro("select count(*) from event_logs where project_id=?", (pid,))[0][0]
        code, fired = api("POST", f"{P}/jobs/{job_id}/run")
        print("press 2", code, str(fired)[:300])
        time.sleep(3)
        reasons = [str(fired)] + [
            (json.loads(d) or {}).get("reason") or "" for (d,) in ro(
                "select data from event_logs where project_id=? and event_type in "
                "('review_unstaffed', 'job_stalled', 'loop_stalled') order by timestamp", (pid,))
        ]
        named = [r for r in reasons if task_a in r and "withdraw that input" in r]
        check("the flow names A's refusal and says to withdraw it", bool(named),
              " | ".join(r[:160] for r in reasons[-3:]))
        flow_entries = [e for e in review_entries(task_a) if e[0] != third]
        check("A's review is not staffed twice", len(flow_entries) == 1, str(review_entries(task_a)))
        print("events after press 2:", ro("select count(*) from event_logs where project_id=?", (pid,))[0][0] - before_events)
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
