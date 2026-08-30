"""Row 12, the half F140 blocks: does a flow's REVIEW leg work once a task reaches `completed`?

F140 says a flow re-briefs its agents for finished work forever, because nothing moves the task
out of `in_progress` -- not the briefing, which never names `update_task`, and not the Hub, which
treats an assigned `in_progress` task as one to resume. That finding stops at the symptom. The
question the operator actually has to answer -- which of F140's three repairs is worth building --
depends on what is waiting on the other side of it, and nothing had established that.

So this file steps over F140, and `AW_COMPLETE_BY` decides who steps:

  1. a one-task change-spec document, approved into a flow, with the flow created first so the
     materialised task lands in its queue;
  2. firing 1 -- the flow staffs the task and a real Haiku turn does the work;
  3. `in_progress -> completed`, F140's missing step, made either by the OPERATOR by hand
     (`AW_COMPLETE_BY=operator`, the default -- what F140 leaves them to do) or by the AUTHOR
     AGENT calling `update_task` (`AW_COMPLETE_BY=agent` -- what F140's repair 1 would produce);
  4. any evidence accepted, so the review arm's separate "no commit to review" refusal cannot be
     mistaken for this one;
  5. firing 2 -- is the finished work claimed for review by an agent OTHER than its author, as the
     briefing's own first paragraph promises? Does the task enter `under_review`? Is the reviewer
     told it is reviewing, and given the commit?

The two modes do not give the same answer, and that is the finding. `agent_that_completed` reads
`TaskTransition.actor_agent`, which an operator's transition leaves NULL, and the review arm drops
an unattributable task from the walk with no diagnostic at all.

Real surface only. No row inserts. Haiku turns. LEAVES NO JOB ENABLED.
"""

import json
import os
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

P = os.environ.get("AW_PROJECT") or ""
AGENT = os.environ.get("AW_AGENT") or ""
RUN = os.environ.get("AW_RUN") or time.strftime("%H%M%S")
# WHO makes the missing `-> completed` transition, and it turns out to be the whole question.
#   "operator" -- the operator does it by hand, which is what F140 leaves them to do.
#   "agent"    -- the author agent is told to call `update_task`, which is F140's repair 1.
# `agent_that_completed` reads `TaskTransition.actor_agent` (`task_transition_service.py:123-147`)
# and an operator's transition writes NULL there, so the two are not interchangeable.
COMPLETE_BY = (os.environ.get("AW_COMPLETE_BY") or "operator").lower()
TARGET = f"reviewleg_{RUN}.py"
BASE = f"/projects/{P}/project"

VERDICTS = []


def check(label, ok, detail=""):
    VERDICTS.append((label, bool(ok), detail))
    print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
    return bool(ok)


def head(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def blob(x, limit=1200):
    return json.dumps(x, indent=1, default=str)[:limit]


def agents():
    c, rows = api("GET", f"/projects/{P}/agents")
    return rows if isinstance(rows, list) else []


def statuses():
    return {a["name"]: a["status"] for a in agents()}


def board():
    c, t = api("GET", f"/projects/{P}/tasks")
    return t if isinstance(t, list) else t.get("tasks", [])


def mine():
    return [t for t in board() if TARGET in (t.get("title") or "")]


def settle(rounds=40, gap=6):
    for i in range(rounds):
        time.sleep(gap)
        busy = [n for n, s in statuses().items() if s not in ("idle", "offline", "error")]
        rows = [(t["status"], t.get("assignee")) for t in mine()]
        print(f"      t+{(i + 1) * gap:>3}s busy={busy} mine={rows}")
        if i >= 2 and not busy:
            return
    print("      (did not settle)")


PAYLOAD = {
    "schema_version": 1,
    "kind": "change-spec",
    "title": f"{TARGET} gets a triple()",
    "summary": "One task, so the flow has exactly one thing to finish and then exactly one thing "
    "to offer for review.",
    "problem": f"{TARGET} does not exist.",
    "scope": {"in_scope": [TARGET], "non_goals": ["tests"]},
    "requirements": [
        {
            "key": "triple",
            "statement": f"{TARGET} SHALL offer a triple(a) returning a multiplied by three.",
            "modal": "SHALL",
            "rationale": "The review leg needs a real requirement to be reviewed against.",
        }
    ],
    "acceptance_criteria": [
        {
            "key": "triple-works",
            "requirement": "triple",
            "given": f"{TARGET} after the change",
            "when": "triple(3) is called",
            "then": "it returns 9",
        }
    ],
    "tasks": [
        {
            "key": "add-triple",
            "title": f"Add triple(a) to {TARGET}",
            "description": f"Create {TARGET} in your working directory containing exactly one "
            "function, `triple(a)`, returning a * 3. Change nothing else. Do not run git.",
            "requirements": ["triple"],
        }
    ],
    "design": "One function.",
    "lifecycle": "One-off change.",
}


def preflight():
    head("PRE. Preconditions")
    if not P or not AGENT:
        sys.exit("set AW_PROJECT and AW_AGENT")
    rows = agents()
    if not rows:
        sys.exit(f"cannot read the roster on {P}")
    row = next((a for a in rows if a["name"] == AGENT), None)
    if row is None:
        sys.exit(f"agent {AGENT!r} does not exist on {P}")
    if row.get("archived") or not row.get("runner_id"):
        sys.exit(f"agent {AGENT!r} must be open and bound to a runner")
    busy = [a["name"] for a in rows if a.get("status") not in ("idle", "offline", "error")]
    if busy:
        sys.exit(f"agents busy before the run: {busy}")
    pool = [
        a["name"]
        for a in rows
        if a["name"] != AGENT and not a.get("archived") and a.get("runner_id")
    ]
    if not pool:
        sys.exit("no second bound agent exists, so no non-author reviewer can ever resolve")
    c, jobs = api("GET", f"/projects/{P}/jobs")
    live = [j for j in (jobs if isinstance(jobs, list) else []) if j.get("enabled")]
    if live:
        sys.exit(f"jobs already enabled: {[j.get('id') for j in live]}")
    print(f"  [OK ] author {AGENT}, reviewer pool {pool}, no job enabled, run tag {RUN}")
    return pool


def call(label, method, path, body=None, expect=None, show=False, limit=900):
    code, out = api(method, path, body)
    ok = expect is None or code in (expect if isinstance(expect, tuple) else (expect,))
    print(f"  {label}: {code}{'' if ok else '   <-- UNEXPECTED'}")
    detail = out.get("detail") if isinstance(out, dict) else None
    if isinstance(detail, dict):
        detail = detail.get("message")
    if isinstance(detail, str):
        print(f"      refusal: {detail[:300]}")
    elif show or not ok:
        print("      " + blob(out, limit).replace(chr(10), chr(10) + "      "))
    return code, out


def main():
    pool = preflight()

    head("A. A one-task document, and a flow created before it is approved")
    c, doc = call("create document", "POST", f"{BASE}/documents",
                  {"title": PAYLOAD["title"]}, expect=(200, 201))
    path = doc["path"]
    q = urllib.parse.quote(path, safe="")
    call("write content", "PUT", f"{BASE}/documents/{q}/content",
         {"document": PAYLOAD}, expect=(200, 201))
    call("close exploration", "POST", f"{BASE}/documents/close-exploration?path={q}",
         {"reason": "review leg"}, expect=(200, 201))
    call("propose", "POST", f"{BASE}/documents/propose?path={q}", {"reason": "review leg"},
         expect=(200, 201))

    c, job = call("create flow", "POST", f"/projects/{P}/jobs", {
        "name": f"reviewleg-{RUN}",
        "agent": AGENT,
        "message": "Work the task you have been given. Keep the edit minimal.",
        "cron": "0 4 * * *",
        "purpose": "Get the one task done, then get it reviewed.",
        "spec_document_id": doc.get("id"),
        "stop_when_queue_empties": True,
        "enabled": True,
    }, expect=(200, 201))
    if c >= 300:
        return
    job_id = job["id"]
    loop_id = (job.get("loop") or {}).get("id")
    check("the job opted into a loop", bool(loop_id), str(loop_id))
    if not loop_id:
        return

    try:
        call("approve", "POST", f"{BASE}/documents/phase?path={q}&to=approved",
             {"reason": "review leg"}, expect=(200, 201))
        time.sleep(2)
        rows = mine()
        check("approval materialised exactly one task", len(rows) == 1, str([r["id"] for r in rows]))
        if len(rows) != 1:
            return
        task_id = rows[0]["id"]
        check("...into this loop's queue", rows[0].get("loop_id") == loop_id,
              repr(rows[0].get("loop_id")))

        head("B. Firing 1 -- the flow staffs the task and the work gets done")
        call("run job", "POST", f"/projects/{P}/jobs/{job_id}/run", {}, expect=(200, 201))
        settle()
        t = next((x for x in mine() if x["id"] == task_id), {})
        author = t.get("assignee")
        check("the task was staffed", bool(author), repr(author))
        check("...and is in_progress after the turn, not completed (F140)",
              t.get("status") == "in_progress", repr(t.get("status")))

        head(f"C. F140's missing transition, made by the {COMPLETE_BY.upper()}")
        if COMPLETE_BY == "agent":
            c, b = api("POST", f"/projects/{P}/agent/trigger", {
                "agent": author,
                "task_id": task_id,
                "message": (
                    f"The work on task {task_id} is finished. Do no further editing. "
                    "Do exactly two tool calls and then stop. First, "
                    "mcp__agentweave__record_evidence with identifier='FR-1', "
                    f"task_id='{task_id}', kind='implementation', locator='{TARGET}', and a "
                    "one-sentence summary of what you wrote. Second, "
                    f"mcp__agentweave__update_task with task_id='{task_id}' and "
                    "status='completed'. That is the whole turn."
                ),
                "overrides": {"permission_mode": "workspace"},
            }, timeout=30)
            print(f"  trigger {author}: {c}")
            settle()
            t = next((x for x in mine() if x["id"] == task_id), {})
            check("the AGENT moved its own task to completed",
                  t.get("status") == "completed", repr(t.get("status")))
            if t.get("status") != "completed":
                return
        else:
            c, b = call("in_progress -> completed", "PATCH", f"/projects/{P}/tasks/{task_id}",
                        {"status": "completed"}, expect=200)
            check("the operator can make the transition the agent did not", c == 200, str(c))
            if c != 200:
                return

        head("C2. Accept whatever evidence exists, so the review arm has a commit to hand over")
        # The review arm refuses before resolving a reviewer if no ACCEPTED evidence names a commit
        # (`scheduler.py:1372-1391`). Accepting here isolates the question this file is asking --
        # who completed the task -- from a second, separate reason a review cannot be staffed.
        c, ev = api("GET", f"/projects/{P}/project/spec/evidence")
        rows_ev = [e for e in (ev.get("evidence", []) if isinstance(ev, dict) else [])
                   if e.get("task_id") == task_id]
        for e in rows_ev:
            dc, _ = api("POST", f"/projects/{P}/project/spec/evidence/{e['id']}/decision",
                        {"decision": "accepted", "reason": "review leg"})
            print(f"  accept {e['id']} ({(e.get('footprint') or {}).get('commit_sha')}): {dc}")
        check("the finished work is backed by accepted evidence naming a commit",
              any((e.get("footprint") or {}).get("commit_sha") for e in rows_ev),
              str([(e.get("footprint") or {}).get("commit_sha") for e in rows_ev]))

        head("D. Firing 2 -- is the finished work offered to a NON-author reviewer?")
        before = {t["id"]: t.get("assignee") for t in mine()}
        c, b = call("run job", "POST", f"/projects/{P}/jobs/{job_id}/run", {},
                    expect=(200, 201))
        check(
            "the firing was accepted rather than skipped as a stalled queue",
            c in (200, 201),
            f"{c} {str(b)[:220]}",
        )
        settle()
        t = next((x for x in mine() if x["id"] == task_id), {})
        reviewer = t.get("assignee")
        print(f"      author={author}  reviewer={reviewer}  status={t.get('status')}")
        check("the task left `completed`", t.get("status") != "completed", repr(t.get("status")))
        check("...into a review band, not back into ordinary work",
              t.get("status") in ("under_review", "approved", "revision_needed", "rejected"),
              repr(t.get("status")))
        check("a reviewer was staffed", bool(reviewer), repr(reviewer))
        check("...and it is NOT the author", reviewer != author, f"{author} -> {reviewer}")
        check("...and it is one of the agents that could have taken it",
              reviewer in pool or reviewer == author, f"{reviewer} vs {pool}")
        print(f"      assignee before firing 2: {before}")

        head("E. What was the reviewer actually told?")
        if reviewer and reviewer != author:
            c, q2 = api("GET", f"/projects/{P}/queue/{reviewer}")
            ents = [e for e in (q2 if isinstance(q2, list) else []) if e.get("origin_type") == "job"]
            latest = ents[-1] if ents else None
            content = (latest or {}).get("content", "")
            print("      " + content[:1500].replace(chr(10), chr(10) + "      "))
            check("the reviewer got a briefing at all", bool(content), str(len(content)))
            # These two were written as `"review" in content` and `TARGET in content`, and both
            # passed -- for the wrong reason. "review" matches the flow paragraph's generic
            # sentence about somebody else reviewing, and TARGET matches the implementation task's
            # own title. Neither says anything about THIS turn being a review, which is the claim
            # being tested. Asserted properly below, and it fails: see F143.
            check(
                "F143: the briefing tells the reviewer to BUILD the thing it is meant to check",
                "Finish the task below and stop" in content
                and "Work the task you have been given" in content,
                content[-140:].replace(chr(10), " | "),
            )
            check(
                "the briefing says this turn is a review",
                "this is a review" in content.lower()
                or "you are reviewing" in content.lower(),
                content[:160].replace(chr(10), " | "),
            )
            check(
                "the briefing names the commit under review",
                "commit" in content.lower(),
                content[:160].replace(chr(10), " | "),
            )

        head("F. Where the loop thinks it is")
        call("loop detail", "GET", f"/projects/{P}/loops/{loop_id}", expect=200, show=True,
             limit=2200)
    finally:
        head("Z. LEAVE NO JOB ENABLED")
        call("disable", "PATCH", f"/projects/{P}/jobs/{job_id}", {"enabled": False})
        call("archive", "POST", f"/projects/{P}/jobs/{job_id}/archive", {})
        call("jobs now", "GET", f"/projects/{P}/jobs", expect=200, show=True, limit=400)
        head("VERDICTS")
        bad = [v for v in VERDICTS if not v[1]]
        for label, ok, detail in VERDICTS:
            print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
        print(f"\n  {len(VERDICTS) - len(bad)}/{len(VERDICTS)} held")


if __name__ == "__main__":
    main()
