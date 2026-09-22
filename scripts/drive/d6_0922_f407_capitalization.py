"""DRIVE 2026-09-22 (D-6) -- F407: `own_review_remedy`'s under_review sentence now capitalises.

`own_review_remedy` (`hub/hub/scheduler.py`) used to return "decide it yourself: ..." lowercase,
which every real caller places after a full stop (`agent_trigger.py:503,511,521,848`), producing a
sentence fragment like "... finish. decide it yourself: ...". Fixed to "Decide it yourself: ...".
Unit-tested green (`hub/tests/test_a_refusal_names_a_remedy_that_works.py`, mutation-checked by
hand: reverting the one-word fix turns 3 of those 18 tests red), not yet driven against a live Hub.

This reaches the public precheck (`review_dispatch_refusal`, `agent_trigger.py:495-521`, the site
of three of the four callers) through the real HTTP surface: one real Haiku turn completes a task
and records evidence naming a commit (the gate `commit_for_task_review` enforces before this
precheck ever runs), an operator PATCH wedges that task `under_review` under a second agent, and a
third agent is dispatched with `review_task_id` naming it -- the "already under review by X" 409.

Real surface only, REST calls through `aw.api`. One real Haiku turn (the author's), bound to
`claude-haiku-4-5-20251001`. The review-dispatch 409 itself fires before any turn would be
started for the reviewer, so only one turn total runs.

Run (from scripts/drive):
  AW_HUB=http://127.0.0.1:<port> AW_KEY=<key> py -3.11 -u d6_0922_f407_capitalization.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import aw  # noqa: E402
from aw import api, task_rows  # noqa: E402

HAIKU = "claude-haiku-4-5-20251001"
AUTHOR = "f407-author"
REVIEWER_A = "f407-rev-a"
REVIEWER_B = "f407-rev-b"
FORBIDDEN = ("proj-5e960453", "proj-18e5d4e0")
RUN = time.strftime("%H%M%S")
FAR_CRON = "0 4 1 1 *"

ROOT = None
P = ""
JOBS = []
VERDICTS = []


def check(label, ok, detail=""):
    VERDICTS.append((label, bool(ok), detail))
    print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
    return bool(ok)


def git(*args):
    p = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, encoding="utf-8")
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def must(*args):
    code, out, err = git(*args)
    if code != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {err or out}")
    return out


def make_project():
    global ROOT, P
    ROOT = tempfile.mkdtemp(prefix="aw-f407-")
    must("init", "-q")
    must("config", "user.email", "drive@example.com")
    must("config", "user.name", "Drive")
    must("checkout", "-q", "-b", "main")
    with open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8") as handle:
        handle.write("base\n")
    must("add", "README.md")
    must("commit", "-q", "-m", "base")

    code, created = api("POST", "/projects/open", {"path": ROOT, "name": f"f407-drive-{RUN}"})
    if code not in (200, 201):
        raise SystemExit(f"could not open the project: {code} {created}")
    P = created["id"]
    aw.P = P
    if P in FORBIDDEN:
        raise SystemExit(f"REFUSING: the Hub handed back {P}")
    code, saved = api("PUT", f"/projects/{P}/settings", {"main_branch": "main"})
    if code != 200:
        raise SystemExit(f"could not set the main branch: {code} {saved}")
    print(f"  project {P} at {ROOT}")


def ensure_runner():
    code, body = api(
        "POST", f"/projects/{P}/runners", {"name": "haiku", "cli": "claude", "model": HAIKU}
    )
    if code >= 300:
        raise SystemExit(f"no runner: {code} {body}")
    return body["id"]


def ensure_agent(name, runner):
    code, body = api("POST", f"/projects/{P}/agents", {"name": name, "runner_id": runner})
    if code >= 300:
        raise SystemExit(f"no agent {name}: {code} {body}")


def statuses():
    code, body = api("GET", f"/projects/{P}/agents")
    return {a["name"]: a.get("status") for a in (body if isinstance(body, list) else [])}


def board():
    code, body = api("GET", f"/projects/{P}/tasks?limit=500")
    return task_rows(body)


def task(tid):
    return next((t for t in board() if t["id"] == tid), None)


def move(tid, status, assignee=None, expect=200):
    payload = {"status": status}
    if assignee is not None:
        payload["assignee"] = assignee
    code, body = api("PATCH", f"/projects/{P}/tasks/{tid}", payload)
    ok = code == expect
    print(f"  {'    ' if ok else 'BAD '}-> {status}" + (f" ({assignee})" if assignee else "") + f"  [{code}]")
    if not ok:
        print("      " + json.dumps(body, indent=1, default=str)[:700])
        raise SystemExit(f"could not move the task to {status}")
    return body


def wait_for(pred, seconds, what):
    end = time.time() + seconds
    while time.time() < end:
        if pred():
            return True
        time.sleep(1)
    print(f"      timed out waiting for {what}")
    return False


def settle(label, rounds=40, gap=5):
    for i in range(rounds):
        time.sleep(gap)
        busy = {n: s for n, s in statuses().items() if s not in ("idle", "offline", "error", None)}
        print(f"      [{label}] t+{(i + 1) * gap:>3}s busy={busy}")
        if i >= 1 and not busy:
            return True
    print(f"      [{label}] did not settle")
    return False


def one_task_document(target):
    payload = {
        "schema_version": 1,
        "kind": "change-spec",
        "title": f"{target} exists",
        "summary": "One file, so there is exactly one piece of work to complete.",
        "problem": f"{target} does not exist.",
        "scope": {"in_scope": [target], "non_goals": ["anything else"]},
        "requirements": [
            {
                "key": "file",
                "statement": f"The project SHALL contain {target} holding the line ok.",
                "modal": "SHALL",
                "rationale": "A drive needs one completable task.",
            }
        ],
        "acceptance_criteria": [
            {
                "key": "file-exists",
                "requirement": "file",
                "given": "the project after the change",
                "when": f"{target} is read",
                "then": "it holds the single line ok",
            }
        ],
        "tasks": [
            {
                "key": "write-file",
                "title": f"Create {target}",
                "description": f"Create {target} in your working directory containing exactly the "
                f"line `ok`. Change nothing else. Then call update_task to mark this task "
                f"completed.",
                "requirements": ["file"],
            }
        ],
    }
    base = f"/projects/{P}/project"
    code, doc = api("POST", f"{base}/documents", {"title": payload["title"]})
    if code >= 300:
        raise SystemExit(f"create document failed: {code} {doc}")
    q = urllib.parse.quote(doc["path"], safe="")
    api("PUT", f"{base}/documents/{q}/content", {"document": payload})
    api("POST", f"{base}/documents/close-exploration?path={q}", {"reason": "drive f407"})
    api("POST", f"{base}/documents/propose?path={q}", {"reason": "drive"})
    return doc.get("id"), q


def make_flow(doc_id):
    code, job = api(
        "POST",
        f"/projects/{P}/jobs",
        {
            "name": f"f407-self-{RUN}",
            "agent": AUTHOR,
            "message": "Work the task you have been given. Keep the edit minimal.",
            "cron": FAR_CRON,
            "purpose": "Author one file and complete the task, so it carries recorded evidence.",
            "spec_document_id": doc_id,
            "stop_when_queue_empties": True,
            "enabled": True,
        },
    )
    if code != 201:
        raise SystemExit(f"could not create the flow: {code} {job}")
    JOBS.append(job["id"])
    loop_id = (job.get("loop") or {}).get("id")
    if not loop_id:
        raise SystemExit(f"the flow opted into no loop: {json.dumps(job, default=str)[:700]}")
    return job["id"], loop_id


def fire(job_id, label):
    code, body = api("POST", f"/projects/{P}/jobs/{job_id}/run", {})
    detail = body.get("detail") if isinstance(body, dict) else body
    print(f"  fire[{label}] -> {code}")
    print(f"      {json.dumps(detail, default=str)[:700]}")
    return code, detail


def author_completes_with_evidence():
    print("=" * 78)
    print("SETUP -- a real Haiku turn authors one file and completes its own task")
    print("=" * 78)
    target = f"f407_{RUN}.txt"
    doc_id, q = one_task_document(target)
    job_id, loop_id = make_flow(doc_id)
    api(
        "POST",
        f"/projects/{P}/project/documents/phase?path={q}&to=approved",
        {"reason": "drive f407"},
    )
    time.sleep(1)
    mine = [t for t in board() if t.get("loop_id") == loop_id]
    check("the approval put one task on the flow's queue", len(mine) == 1, str(mine)[:200])
    tid = mine[0]["id"]

    code, detail = fire(job_id, "author works")
    check("the author's firing started", code == 200, str(code))
    started = wait_for(lambda: statuses().get(AUTHOR) == "running", 90, f"{AUTHOR} to start")
    check(f"{AUTHOR}'s real Haiku turn started", started, str(statuses()))
    settle("author turn")
    row = task(tid)
    check(
        "the author completed the task, holding it, with recorded evidence",
        row and row["status"] == "completed" and row.get("assignee") == AUTHOR,
        f"{row and row['status']} / {row and row.get('assignee')}",
    )
    api("PATCH", f"/projects/{P}/jobs/{job_id}", {"enabled": False})
    return tid


def main():
    make_project()
    runner = ensure_runner()
    ensure_agent(AUTHOR, runner)
    ensure_agent(REVIEWER_A, runner)
    ensure_agent(REVIEWER_B, runner)

    tid = author_completes_with_evidence()

    print("\n" + "=" * 78)
    print("WEDGE -- operator PATCHes the completed task to under_review, held by rev-a")
    print("=" * 78)
    move(tid, "under_review", REVIEWER_A)
    row = task(tid)
    check(
        "the task is under_review, held by rev-a",
        row and row["status"] == "under_review" and row.get("assignee") == REVIEWER_A,
        f"{row and row['status']} / {row and row.get('assignee')}",
    )

    print("\n" + "=" * 78)
    print("DRIVE -- rev-b dispatched with review_task_id, real HTTP 409")
    print("=" * 78)
    code, body = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {"agent": REVIEWER_B, "message": "review it", "review_task_id": tid, "session_mode": "new"},
    )
    detail = body.get("detail") if isinstance(body, dict) else body
    print(f"  {code} {detail!r}")
    check("the dispatch refuses with 409", code == 409, str(code))
    check(
        "the refusal names the task and the holder",
        tid in str(detail) and REVIEWER_A in str(detail),
        str(detail),
    )
    check(
        "the sentence after the full stop is capitalised: 'Decide it yourself'",
        "Decide it yourself: approve, reject, or send it back with revision_needed." in str(detail),
        str(detail),
    )
    check("the old lowercase fragment is gone", "finish. decide it yourself" not in str(detail), str(detail))
    check("no stray double-remedy duplication", str(detail).count("Decide it yourself") == 1, str(detail))

    print("\n" + "=" * 78)
    print("TEARDOWN -- leave no job enabled (confirmed by a direct query, not assumed)")
    print("=" * 78)
    for jid in set(JOBS):
        c, _ = api("PATCH", f"/projects/{P}/jobs/{jid}", {"enabled": False})
        print(f"  disable {jid} -> {c}")
    code, jobs_now = api("GET", f"/projects/{P}/jobs?include_archived=true")
    left = [j.get("id") for j in (jobs_now if isinstance(jobs_now, list) else []) if j.get("enabled")]
    check("no job left enabled (GET /jobs?include_archived=true)", not left, str(left))

    print("\n" + "=" * 78)
    print("VERDICT")
    print("=" * 78)
    for label, ok, det in VERDICTS:
        print(f"  {'OK ' if ok else 'BAD'}  {label}" + (f"  -- {det}" if det else ""))
    bad = [v for v in VERDICTS if not v[1]]
    print(f"\n  {len(VERDICTS) - len(bad)}/{len(VERDICTS)}   project {P} at {ROOT}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
