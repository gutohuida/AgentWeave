"""Row 12 FLOWS -- a flow on an approved document: parallel firing, and a reviewer
resolved for finished work.

Never reached by any previous sweep. Drives the real surface: document -> approve ->
flow -> manual firing -> real Haiku turns -> review dispatch.

Run:  AW_HUB=... AW_KEY=... AW_PROJECT=... py -3.11 -u t_row12_flows.py
"""

import json
import os
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

P = os.environ.get("AW_PROJECT") or "proj-dc4d43543bea"
# The flow's agent was hard-wired to one night's fixture, so this file could only ever run there.
AGENT = os.environ.get("AW_AGENT") or "alpha"
RUNNER = os.environ.get("AW_RUNNER") or ""
# A fixed document title and a fixed target filename contaminate this file's own next run: the
# second run's tasks are already done before they are dispatched, and "the work landed" passes
# without any work happening. Unique per run.
RUN = os.environ.get("AW_RUN") or time.strftime("%H%M%S")
TARGET = f"calc_{RUN}.py"
BASE = f"/projects/{P}/project"


VERDICTS = []


def check(label, ok, detail=""):
    """Recorded, not just printed. This file used to end with prose an operator had to read; a
    verdict list is what makes a re-drive after a fix answerable in one line."""
    VERDICTS.append((label, bool(ok), detail))
    print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
    return bool(ok)


def step(label, method, path, body=None, expect=None, show=False, limit=900):
    code, out = api(method, path, body)
    ok = expect is None or code in (expect if isinstance(expect, tuple) else (expect,))
    print(f"  {label}: {code}{'' if ok else '   <-- UNEXPECTED'}")
    detail = out.get("detail") if isinstance(out, dict) else None
    if isinstance(detail, dict):
        detail = detail.get("message")
    if isinstance(detail, str):
        print(f"      refusal: {detail[:300]}")
    elif show or not ok:
        blob = json.dumps(out, default=str, indent=1)[:limit]
        print("      " + blob.replace(chr(10), chr(10) + "      "))
    return code, out


def head(t):
    print()
    print("=" * 78)
    print(t)
    print("=" * 78)


PAYLOAD = {
    "schema_version": 1,
    "kind": "change-spec",
    "title": f"{TARGET} grows a power and a modulo",
    "summary": "Two independent additions to the calculator, so a flow has something to run "
    "in parallel and something to review afterwards.",
    "problem": f"{TARGET} does not exist yet and the project has no exponent or remainder.",
    "scope": {"in_scope": [TARGET], "non_goals": ["tests", "packaging"]},
    "requirements": [
        {
            "key": "power",
            "statement": f"{TARGET} SHALL offer a power(a, b) returning a raised to b.",
            "modal": "SHALL",
            "rationale": "The calculator is missing exponentiation.",
        },
        {
            "key": "modulo",
            "statement": f"{TARGET} SHALL offer a modulo(a, b) returning the remainder of a / b.",
            "modal": "SHALL",
            "rationale": "The calculator is missing remainder.",
        },
    ],
    "acceptance_criteria": [
        {
            "key": "power-works",
            "requirement": "power",
            "given": f"{TARGET} after the change",
            "when": "power(2, 3) is called",
            "then": "it returns 8",
        },
        {
            "key": "modulo-works",
            "requirement": "modulo",
            "given": f"{TARGET} after the change",
            "when": "modulo(7, 3) is called",
            "then": "it returns 1",
        },
    ],
    "tasks": [
        {
            "key": "add-power",
            "title": f"Add power(a, b) to {TARGET}",
            "description": f"Append a function power(a, b) returning a ** b to {TARGET} in your "
            "working directory, creating the file if it does not exist. Change nothing else. "
            "Do not run git.",
            "requirements": ["power"],
        },
        {
            "key": "add-modulo",
            "title": f"Add modulo(a, b) to {TARGET}",
            "description": f"Append a function modulo(a, b) returning a % b to {TARGET} in your "
            "working directory, creating the file if it does not exist. Change nothing else. "
            "Do not run git.",
            "requirements": ["modulo"],
        },
    ],
    "design": "Two one-line functions, independent of each other.",
    "lifecycle": "One-off change.",
}


def board():
    c, t = api("GET", f"/projects/{P}/tasks")
    return t if isinstance(t, list) else t.get("tasks", [])


def agents():
    c, a = api("GET", f"/projects/{P}/agents")
    return {x["name"]: x["status"] for x in a}


def show_board(label):
    print(f"  --- board ({label})")
    for t in board():
        print(
            f"      {t['id']}  {t['title'][:44]:<44} {t['status']:<14} "
            f"assignee={t.get('assignee')}"
        )
    print(f"      agents: {agents()}")


def settle(rounds=30, gap=6):
    for i in range(rounds):
        time.sleep(gap)
        st = agents()
        rows = board()
        busy = [n for n, s in st.items() if s not in ("idle", "offline", "error")]
        print(
            f"      t+{(i + 1) * gap:>3}s busy={busy} "
            f"statuses={[(t['status'], t.get('assignee')) for t in rows]}"
        )
        if i >= 2 and not busy:
            return
    print("      (did not settle)")


def worktree_file(agent, filename):
    c, b = api("GET", f"/projects/{P}/worktrees/{agent}")
    if c != 200 or not isinstance(b, dict) or not b.get("working_dir"):
        return None
    path = os.path.join(b["working_dir"], filename)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def task_checkout_file(task_id, filename):
    """A task-bound run's working directory is the task's own checkout, not the agent worktree."""
    c, rows = api("GET", "/projects")
    row = next((x for x in (rows or []) if x.get("id") == P), None) if isinstance(rows, list) else None
    root = (row or {}).get("working_directory")
    if not root:
        return None
    path = os.path.join(root, ".agentweave", "tasks", task_id, filename)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def preflight():
    """Assert what this file describes. Reporting on some other situation is the F137 defect."""
    head("PRE. Preconditions")
    c, rows = api("GET", f"/projects/{P}/agents")
    if c != 200:
        sys.exit(f"cannot list agents on {P}: {c}")
    row = next((a for a in rows if a["name"] == AGENT), None)
    if row is None:
        sys.exit(f"agent {AGENT!r} does not exist on {P} -- set AW_AGENT")
    if row.get("archived"):
        sys.exit(f"agent {AGENT!r} is archived")
    if not row.get("runner_id"):
        sys.exit(f"agent {AGENT!r} has no runner; a flow cannot dispatch to it")
    if RUNNER and row.get("runner_id") != RUNNER:
        sys.exit(f"agent {AGENT!r} is on {row.get('runner_id')!r}, not AW_RUNNER={RUNNER!r}")
    busy = [a["name"] for a in rows if a.get("status") not in ("idle", "offline", "error")]
    if busy:
        sys.exit(f"agents busy before the run: {busy} -- settle() could never distinguish them")
    # Section E needs somewhere for finished work to go that is NOT its author.
    others = [
        a["name"]
        for a in rows
        if a["name"] != AGENT and not a.get("archived") and a.get("runner_id")
    ]
    if not others:
        sys.exit("no second bound agent exists; section E's non-author reviewer cannot resolve")
    c, jobs = api("GET", f"/projects/{P}/jobs")
    live = [j for j in (jobs if isinstance(jobs, list) else []) if j.get("enabled")]
    if live:
        sys.exit(f"jobs already enabled on this project: {[j.get('id') for j in live]}")
    if worktree_file(AGENT, TARGET) is not None:
        sys.exit(f"{TARGET} already exists in {AGENT}'s worktree -- pick a different AW_RUN")
    print(f"  [OK ] {AGENT} bound and idle, reviewers available {others}, no job enabled, "
          f"run tag {RUN}")


def main():
    preflight()
    head("A. An approved document with two independent tasks")
    c, doc = step(
        "create document", "POST", f"{BASE}/documents",
        {"title": PAYLOAD["title"]}, expect=(200, 201),
    )
    path = doc["path"]
    doc_id = doc.get("id")
    q = urllib.parse.quote(path, safe="")
    print(f"      path={path}  id={doc_id}")

    step("write content", "PUT", f"{BASE}/documents/{q}/content",
         {"document": PAYLOAD}, expect=(200, 201))
    step("close exploration", "POST", f"{BASE}/documents/close-exploration?path={q}",
         {"reason": "row 12"}, expect=(200, 201))
    step("propose", "POST", f"{BASE}/documents/propose?path={q}",
         {"reason": "row 12"}, expect=(200, 201))

    head("B. Create the flow BEFORE approval, so materialised tasks land in its queue")
    c, job = step(
        "create flow", "POST", f"/projects/{P}/jobs",
        {
            "name": f"row12-flow-{RUN}",
            "agent": AGENT,
            "message": "Work the task you have been given. Keep the edit minimal.",
            "cron": "0 4 * * *",
            "purpose": "Decompose the calc.py change document and get its two tasks done.",
            "spec_document_id": doc_id,
            "stop_when_queue_empties": True,
            "enabled": True,
        },
        expect=(200, 201), show=True, limit=1600,
    )
    if c >= 300:
        return
    job_id = job["id"]
    # `/loops/{id}` is keyed by the LOOP's own id, not the job's -- reading it with `job_id`
    # answers 404 "Loop not found", which reads as "this job has no loop" for a job whose create
    # response carries one. Guessing a shape instead of reading it is this drive's recurring
    # harness defect; the id is right here in the response.
    loop_id = (job.get("loop") or {}).get("id")
    print(f"      JOB={job_id}  LOOP={loop_id}")
    if not loop_id:
        sys.exit("the job was created without a loop -- the flow legs below have no subject")

    try:
        head("C. Approve the document -- do the tasks materialise into the flow's queue?")
        step("approve", "POST", f"{BASE}/documents/phase?path={q}&to=approved",
             {"reason": "row 12"}, expect=(200, 201))
        time.sleep(2)
        show_board("after approval")
        step("loop detail", "GET", f"/projects/{P}/loops/{loop_id}", expect=200,
             show=True, limit=2500)

        head("D. Fire the flow by hand -- does it start BOTH tasks in parallel?")
        step("run job", "POST", f"/projects/{P}/jobs/{job_id}/run", {},
             expect=(200, 201), show=True)
        settle()
        show_board("after firing 1")
        step("job history", "GET", f"/projects/{P}/jobs/{job_id}/history", expect=200,
             show=True, limit=2500)

        head("E. Fire again -- finished work should be offered to a NON-author reviewer")
        step("run job", "POST", f"/projects/{P}/jobs/{job_id}/run", {},
             expect=(200, 201), show=True)
        settle()
        show_board("after firing 2")
        step("job history", "GET", f"/projects/{P}/jobs/{job_id}/history", expect=200,
             show=True, limit=3000)
        step("loop detail", "GET", f"/projects/{P}/loops/{loop_id}", expect=200,
             show=True, limit=3000)
        head("F. F140: did the tasks actually MOVE, or was firing 2 a re-run of firing 1?")
        # The whole point of `a-flow-briefing-names-its-contract`. Before it, both tasks sat in
        # `in_progress` after firing 1, firing 2 re-claimed and re-briefed the same two agents for
        # finished work, and the board after firing 2 was byte-identical to the board after firing
        # 1. Nothing in the transcript distinguished that from progress -- which is why the pass
        # condition is a status, not a reading.
        #
        # `completed` is the minimum. A task that went further (`under_review`, `approved`) has
        # moved through it, so the check is "left the active band", not "is exactly completed".
        MOVED = {"completed", "under_review", "approved", "revision_needed", "rejected"}
        rows = [t for t in board() if TARGET in t["title"]]
        stuck = [t["id"] for t in rows if t["status"] not in MOVED]
        print(f"      statuses: {[(t['id'], t['status']) for t in rows]}")
        if not check(
            "F140: every task the flow worked has left the active band",
            bool(rows) and not stuck,
            f"still active: {stuck}" if stuck else f"{len(rows)} moved",
        ):
            print("      ^ this is F140 reproducing: the agent was never told what finishing is,")
            print("        so the next firing will claim these same tasks again, forever.")

        head("G. Did the work actually land?")
        # A run bound to a task works in that task's OWN checkout, not the agent's worktree --
        # `.agentweave/tasks/<task id>/`. Looking only in the worktree reported "NO worktree" for
        # work that was sitting on disk, correct and committed, two directories away.
        landed = []
        for t in board():
            if TARGET not in t["title"]:
                continue
            got = task_checkout_file(t["id"], TARGET)
            where = "task checkout" if got is not None else None
            if got is None:
                got = worktree_file(t.get("assignee") or "", TARGET)
                where = "agent worktree" if got is not None else None
            if got is None:
                print(f"      {t['id']} ({t['title'][:40]}): {TARGET} NOWHERE")
                continue
            landed.append(f"{t['id']}:{where}")
            print(f"      {t['id']} ({t['title'][:40]}): {TARGET} in the {where}, "
                  f"{len(got)} chars")
            print("      " + got[:300].replace(chr(10), chr(10) + "      "))
        print(f"      landed: {landed or 'NOWHERE'}")
    finally:
        head("Z. LEAVE NO JOB ENABLED")
        step("disable", "PATCH", f"/projects/{P}/jobs/{job_id}", {"enabled": False})
        step("archive", "POST", f"/projects/{P}/jobs/{job_id}/archive", {})
        step("jobs now", "GET", f"/projects/{P}/jobs", expect=200, show=True, limit=1500)
        head("VERDICTS")
        bad = [v for v in VERDICTS if not v[1]]
        for label, ok, detail in VERDICTS:
            print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
        print(f"\n  {len(VERDICTS) - len(bad)}/{len(VERDICTS)} held")


if __name__ == "__main__":
    main()
