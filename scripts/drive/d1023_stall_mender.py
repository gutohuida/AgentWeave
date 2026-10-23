"""Acceptance drive for `a-stalled-project-wakes-a-doctor-that-unblocks-it` (the mender).

Replays the 2026-10-22 night stall on the operator's Hub: approved work whose merge is skipped
because the project's checkout holds someone else's uncommitted tracked change, and then, once
that is cleared, a merge that conflicts because main moved meanwhile.

  py -3.11 scripts/drive/d1023_stall_mender.py <project-id> <agent-with-a-haiku-runner>

On a scratch Hub that `e2e.py hub-up` started, from the checkout under test. The project must
be fresh from `e2e.py setup` (a git repo on `master`). Real Haiku turns: the mender's.

Phases, each a PASS/FAIL line; written first, failing before the build:
  1. the skipped merge records one stall and wakes exactly one mender run;
  2. the mender asks under Needs you and leaves the operator's file untouched;
  3. the same cause again (a retry while still dirty) wakes no second mender;
  4. after the operator commits their file, main moves with a conflicting change and the
     operator answers; the mender resolves the conflict and the work lands, unreviewed;
  5. the stall ends recorded `fixed`;
  6. no mender brief is left queued.
"""

import hashlib
import importlib.util
import pathlib
import sys
import time

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

MODEL = "claude-haiku-4-5-20251001"
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)
    return ok


def git(directory, *args):
    result = e2e.subprocess.run(
        ["git", "-C", str(directory), "-c", "user.name=op", "-c", "user.email=op@example.com", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def api(method, path, body=None):
    status, res = e2e.request(method, path, body)
    return status, res


def mender_runs(project):
    return e2e.ro().execute(
        "select id, status from runs where project_id=? and agent='mender' order by started_at",
        (project,),
    ).fetchall()


def stalls(project):
    status, res = api("GET", f"/projects/{project}/stalls")
    return res.get("stalls", []) if status == 200 and isinstance(res, dict) else None


def mender_questions(project):
    status, res = api("GET", f"/projects/{project}/questions?answered=false")
    if status != 200:
        return []
    return [q for q in res if q.get("from_agent") == "mender" and not q.get("declined")]


def wait(predicate, minutes, label):
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(5)
    print(f"  (gave up waiting for {label} after {minutes} min)")
    return None


def walk_to_approved(project, task_id, agent):
    for status_value in ("assigned", "in_progress", "completed", "under_review", "approved"):
        body = {"status": status_value}
        if status_value == "assigned":
            body["assignee"] = agent
        status, res = api("PATCH", f"/projects/{project}/tasks/{task_id}", body)
        if status >= 300:
            return f"{status_value}: HTTP {status} {res}"
    return None


def latest_integration(project, task_id):
    return e2e.ro().execute(
        "select outcome, reason, actor_kind, actor from task_integrations where task_id=? "
        "order by created_at desc limit 1",
        (task_id,),
    ).fetchone()


def main(project, agent):
    directory = pathlib.Path(
        e2e.ro().execute("select working_directory from projects where id=?", (project,))
        .fetchone()[0]
    )
    runner_id = e2e.ro().execute(
        "select runner_id from agents where project_id=? and name=?", (project, agent)
    ).fetchone()[0]

    # The product, and the operator's own tracked notes.
    (directory / "app.py").write_text("RATE = 1\n\n\ndef total(x):\n    return x * RATE\n")
    (directory / "notes.txt").write_text("operator notes\n")
    git(directory, "add", "app.py", "notes.txt")
    git(directory, "commit", "-q", "-m", "base")

    status, res = api(
        "PATCH",
        f"/projects/{project}/manager/jobs/mender",
        {"enabled": True, "runner_id": runner_id, "model": MODEL},
    )
    check("the mender can be enabled on the Manager page", status == 200, f"HTTP {status} {res}")

    # A documentless loop's task with no requirement link merges its branch tip, as the night's
    # flow tasks merged theirs. Disabled: nothing fires it; it only owns the task.
    status, job = api(
        "POST",
        f"/projects/{project}/jobs",
        {
            "name": "mender drive loop",
            "agent": agent,
            "message": "Work the next task.",
            "cron": "0 0 1 1 *",
            "enabled": False,
            "purpose": "Hold the drive's task",
        },
    )
    if status >= 300:
        raise SystemExit(f"job create failed: HTTP {status} {job}")
    loop_id = e2e.ro().execute("select id from loops where job_id=?", (job["id"],)).fetchone()[0]
    status, task = api(
        "POST",
        f"/projects/{project}/tasks",
        {
            "title": "Raise the rate to 2",
            "description": "RATE = 2 in app.py",
            "assignee": agent,
            "loop_id": loop_id,
        },
    )
    if status >= 300:
        raise SystemExit(f"task create failed: HTTP {status} {task}")
    task_id = task["id"]
    branch = f"agentweave/task/{task_id}"
    git(directory, "checkout", "-q", "-b", branch)
    (directory / "app.py").write_text("RATE = 2\n\n\ndef total(x):\n    return x * RATE\n")
    git(directory, "commit", "-q", "-am", "rate 2")
    git(directory, "checkout", "-q", "master")

    # Someone else's work in progress, in a tracked file of the shared checkout.
    (directory / "notes.txt").write_text("operator notes\nhalf-written thought\n")
    notes_before = sha(directory / "notes.txt")

    refused = walk_to_approved(project, task_id, agent)
    check("the task reaches approved", refused is None, refused or "")
    row = latest_integration(project, task_id)
    check("its merge is skipped on the dirty checkout", bool(row) and row[0] == "skipped", str(tuple(row) if row else row))

    # 1. One stall, one mender.
    found = wait(lambda: stalls(project), 1, "a stall")
    check(
        "1a. the skipped merge is recorded as one stall",
        bool(found) and len(found) == 1,
        str(found if found is not None else "GET /stalls absent"),
    )
    runs = wait(lambda: mender_runs(project), 3, "a mender run")
    check("1b. a mender run starts", bool(runs), str(runs))

    # 2. It asks, and leaves the file alone.
    asked = wait(lambda: mender_questions(project), 10, "the mender's question")
    check("2a. the mender asks under Needs you", bool(asked), str([q.get("question") for q in asked or []]))
    check("2b. the operator's file is untouched", sha(directory / "notes.txt") == notes_before)

    # 3. The same cause again wakes nobody new.
    api("POST", f"/projects/{project}/tasks/{task_id}/integrations/retry")
    time.sleep(20)
    check("3a. still one stall", len(stalls(project) or []) == 1, str(stalls(project)))
    check("3b. still one mender run", len(mender_runs(project)) == 1, str(mender_runs(project)))

    # 4. The operator clears their file; main moves with a conflicting change; they answer.
    git(directory, "commit", "-q", "-am", "operator: notes")
    (directory / "app.py").write_text("RATE = 3\n\n\ndef total(x):\n    return x * RATE\n")
    git(directory, "commit", "-q", "-am", "someone else: rate 3")
    for q in asked or []:
        api(
            "PATCH",
            f"/projects/{project}/questions/{q['id']}",
            {
                "answer": "I committed my notes myself. Land the task now; if it conflicts, "
                "keep the task's RATE = 2.",
                "labels": [],
            },
        )
    landed = wait(
        lambda: (latest_integration(project, task_id) or ("",))[0] == "merged", 15, "the merge"
    )
    row = latest_integration(project, task_id)
    check("4a. the task's work lands on master", bool(landed), str(tuple(row) if row else row))
    check(
        "4b. the landing is the mender's, not a reviewer's",
        bool(row) and row[3] == "mender",
        str(row),
    )
    reviews_after = e2e.ro().execute(
        "select count(*) from task_transitions where task_id=? and to_status='under_review'",
        (task_id,),
    ).fetchone()[0]
    check("4c. no second review was asked for", reviews_after == 1, f"under_review rows: {reviews_after}")
    text = (directory / "app.py").read_text() if git(directory, "rev-parse", "--abbrev-ref", "HEAD") == "master" else ""
    check("4d. master holds the task's RATE = 2", "RATE = 2" in text, text[:40])

    # 5. Outcome.
    ended = wait(
        lambda: [s for s in stalls(project) or [] if s.get("outcome") == "fixed"], 3, "outcome"
    )
    check("5. the stall ends recorded fixed", bool(ended), str(stalls(project)))

    # 6. Nothing left over: a brief queued for a stall that has ended would start a turn about
    # nothing (found by this drive's first passing run).
    leftover = e2e.ro().execute(
        "select id from inbound_queue_entries where project_id=? and agent='mender' "
        "and state='queued'",
        (project,),
    ).fetchall()
    check("6. no mender brief is left queued", not leftover, str([r[0] for r in leftover]))

    print(f"\n{len(failures)} FAIL" if failures else "\nALL PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
