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

The two modes did not give the same answer, and that was F142. `agent_that_completed` reads
`TaskTransition.actor_agent`, which an operator's transition leaves NULL, and the review arm dropped
an unattributable task from the walk with no diagnostic at all -- so row one reported
*"no claimable task among 1 open (1 completed)"* forever, a fact about the queue standing in for a
fact about one task.

**`a-review-a-flow-cannot-staff-is-named` inverts row one**, and this file's checks now assert the
fixed behaviour: an operator-completed task reaches a staffed review, with the agents that worked it
excluded. Where no eligible reviewer exists, the refusal must name the task and must NOT be the
status histogram.

**`AW_COMPLETE_BY=operator` no longer reaches the arm it was written for.** Measured 2026-09-09:
F140's repair 1 shipped, so `_compose_loop_briefing` now tells the agent *"call
`update_task(..., status="completed")` when the work is done"* -- and it does, on firing 1. The
task is already `completed` when section C runs, the operator's `PATCH {"status": "completed"}` is
answered `200` and writes **no transition row**, and `completion_attribution` therefore reads the
*agent's* completion. That mode now drives the arm at `scheduler.py:1548` (an agent completed it),
which is the one design D6 says is byte-identical to what shipped. It is kept because it is a real
operator gesture with a real answer, but it is **not** F142's world.

`AW_COMPLETE_BY=operator_after_agent` is that world, reconstructed: an agent does the work on a
turn bound to the task -- so `agents_of_runs_bound_to` and `assignee` both name it -- but the
briefing that tells it to move the task is never delivered, so nothing writes an agent-attributed
`-> completed` and the operator makes that transition by hand. `AW_ALLOW_NO_REVIEWER=1` runs the
same fixture with no second bound agent, which is the only way the arm is *provable* from outside:
`excluded_because` reaches the refusal, and `"has worked on this task"` is the operator arm's
sentence while `"is the one that completed this task"` is the agent arm's.

`AW_COMPLETE_BY=untouched` is **row four**, added with that change: the operator completes a task no
agent ever touched, so the exclusion is empty and a review is staffed with nobody excluded -- the arm
with the widest exclusion behaviour, which had no drive coverage at all. The agent works and records
evidence on a turn triggered **without** `task_id`, so no run binds to the task, no transition names
an agent, and `assignee` is never written.

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
#   "operator"  -- the operator does it by hand, which is what F140 leaves them to do.
#   "agent"     -- the author agent is told to call `update_task`, which is F140's repair 1.
#   "operator_after_agent" -- F142's actual world since F140's repair shipped: an agent works the
#                  task on a turn bound to it, is never told to move it, and the operator makes the
#                  `-> completed` transition. `attribution.actor_kind == "operator"`.
#   "untouched" -- row four: the operator walks the task the whole way and no run ever binds to it,
#                  so no record associates any agent with it and the exclusion is empty.
# `agent_that_completed` reads `TaskTransition.actor_agent` and an operator's transition writes NULL
# there, so the first two are not interchangeable; `completion_attribution` is what tells the two
# NULL worlds apart, and "untouched" is the third.
COMPLETE_BY = (os.environ.get("AW_COMPLETE_BY") or "operator").lower()
# The refusal variant. `resolve_reviewer` only puts `excluded_because` into a sentence when nobody
# resolves, and that sentence is the only place outside the database where the two `None`-author
# arms of `decide_firing` are told apart -- so a project with no second bound agent is not a
# degraded case here, it is the measurement.
ALLOW_NO_REVIEWER = os.environ.get("AW_ALLOW_NO_REVIEWER") == "1"
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
    if not pool and not ALLOW_NO_REVIEWER:
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

        if COMPLETE_BY == "untouched":
            # Row four. No firing, so nothing staffs the task and no run ever binds to it. The
            # agent is triggered WITHOUT `task_id`, which is what keeps `run.task_id` NULL and
            # `assignee` unwritten -- the three records the exclusion reads all stay empty.
            head("B. Row four -- an agent does the work on a turn bound to NO task")
            c, b = api("POST", f"/projects/{P}/agent/trigger", {
                "agent": AGENT,
                "message": (
                    f"Create {TARGET} in your working directory containing exactly one function, "
                    "`triple(a)`, returning a * 3. Change nothing else. Then call "
                    "mcp__agentweave__record_evidence with identifier='FR-1', "
                    f"task_id='{task_id}', kind='implementation', locator='{TARGET}', and a "
                    "one-sentence summary. Do not call update_task. That is the whole turn."
                ),
                "overrides": {"permission_mode": "workspace"},
            }, timeout=30)
            print(f"  trigger {AGENT} (unbound): {c}")
            settle()
            t = next((x for x in mine() if x["id"] == task_id), {})
            author = None
            check("no agent holds the task -- `assignee` was never written",
                  not t.get("assignee"), repr(t.get("assignee")))
            check("...and it never left `pending`", t.get("status") == "pending",
                  repr(t.get("status")))
        elif COMPLETE_BY == "operator_after_agent":
            # The flow is never fired, so `_compose_loop_briefing` -- which since F140's repair
            # tells the agent to call `update_task(..., status="completed")` -- is never composed
            # and the agent is never asked to move the task. The turn IS bound to the task, so
            # `agents_of_runs_bound_to` names the agent and the exclusion is non-empty; what is
            # missing is only the agent-attributed `-> completed`, which is exactly F142's world.
            head("B. An agent works the task on a bound turn, and is never told to move it")
            for to in ("assigned", "in_progress"):
                body = {"status": to}
                if to == "assigned":
                    body["assignee"] = AGENT
                c, _ = call(f"-> {to}", "PATCH", f"/projects/{P}/tasks/{task_id}", body,
                            expect=200)
                if c != 200:
                    return
            c, b = api("POST", f"/projects/{P}/agent/trigger", {
                "agent": AGENT,
                "task_id": task_id,
                "message": (
                    f"Create {TARGET} in your working directory containing exactly one function, "
                    "`triple(a)`, returning a * 3. Change nothing else. Then call "
                    "mcp__agentweave__record_evidence with identifier='FR-1', "
                    f"task_id='{task_id}', kind='implementation', locator='{TARGET}', and a "
                    "one-sentence summary. Do NOT call update_task -- leave the task's status "
                    "exactly where it is. That is the whole turn."
                ),
                "overrides": {"permission_mode": "workspace"},
            }, timeout=30)
            print(f"  trigger {AGENT} (bound to the task): {c}")
            settle()
            t = next((x for x in mine() if x["id"] == task_id), {})
            author = t.get("assignee")
            check("an agent is associated with the task", author == AGENT, repr(author))
            check("...and it is still in_progress, so no agent completed it",
                  t.get("status") == "in_progress", repr(t.get("status")))
            if t.get("status") != "in_progress":
                return
        else:
            head("B. Firing 1 -- the flow staffs the task and the work gets done")
            call("run job", "POST", f"/projects/{P}/jobs/{job_id}/run", {}, expect=(200, 201))
            settle()
            t = next((x for x in mine() if x["id"] == task_id), {})
            author = t.get("assignee")
            check("the task was staffed", bool(author), repr(author))
            # **Swapped 2026-09-09.** This asserted `in_progress` -- F140's broken state, kept
            # deliberately "so the day it is fixed the line swaps and says so". That day was
            # `f3a778f`'s neighbourhood: the briefing now names `update_task` and the agent moves
            # its own task. The consequence for THIS file is that `operator` mode's section C is a
            # no-op PATCH on an already-`completed` task, so the arm it drives is the agent one.
            check("F140 fixed: the agent moved its own task to completed, unasked by this file",
                  t.get("status") == "completed", repr(t.get("status")))

        head(f"C. F140's missing transition, made by the {COMPLETE_BY.upper()}")
        if COMPLETE_BY == "untouched":
            for to in ("in_progress", "completed"):
                c, b = call(f"-> {to}", "PATCH", f"/projects/{P}/tasks/{task_id}",
                            {"status": to}, expect=200)
                if c != 200:
                    return
            check("the operator walked it the whole way, and no agent is on the record", True)
        elif COMPLETE_BY == "agent":
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
        elif COMPLETE_BY == "operator_after_agent":
            c, b = call("in_progress -> completed", "PATCH", f"/projects/{P}/tasks/{task_id}",
                        {"status": "completed"}, expect=200)
            if c != 200:
                return
            t = next((x for x in mine() if x["id"] == task_id), {})
            check("the OPERATOR moved a task an agent worked to completed",
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
        # **Row one's expectation inverts here** (F142). Before
        # `a-review-a-flow-cannot-staff-is-named` an operator-completed task was dropped from the
        # walk in silence and this came back `409` with the status histogram. Two outcomes are now
        # acceptable and a third is not: a staffed review, or -- where no eligible reviewer exists
        # -- a refusal that names THE TASK. The histogram is what must never come back, and it is
        # asserted by string because this file's own history is a check passing on content that
        # said the opposite.
        detail = b.get("detail") if isinstance(b, dict) else None
        if isinstance(detail, dict):
            detail = detail.get("message")
        refusal = detail if isinstance(detail, str) else ""
        check(
            "the refusal, if there is one, does NOT fall back to the queue's status histogram",
            "no claimable task among" not in refusal,
            refusal[:220],
        )
        if c not in (200, 201):
            # A disjunction, so the label says so: the rung-3 sentence is about "this task" without
            # carrying its id (the id rides on the loop's `review_unstaffed` event), and a label
            # reading "names this task" was read as "the id is in the sentence" (night 2026-09-12).
            check(
                "...and it is about this task instead (its id, or 'has worked on this task')",
                task_id in refusal or "has worked on this task" in refusal,
                refusal[:220],
            )
        if pool:
            check(
                "the firing was accepted rather than skipped as a stalled queue",
                c in (200, 201),
                f"{c} {str(b)[:220]}",
            )
        else:
            # With nobody eligible the `409` IS the expected answer -- it is the second of the two
            # outcomes F142 names, and asserting acceptance here would fail the run for behaving as
            # the finding requires.
            check(
                "with nobody eligible the firing refuses, and refuses with a reason",
                c == 409 and bool(refusal),
                f"{c} {refusal[:180]}",
            )
        if not pool:
            # No agent can resolve, so `resolve_reviewer` refuses -- and its sentence carries
            # `excluded_because`, which is the ONLY externally readable difference between
            # `decide_firing`'s two `None`-author arms. `scheduler.py:1548` says "is the one that
            # completed this task"; the operator arm at `:1556` says "has worked on this task".
            # The walk records `unstaffed` rather than failing the firing, so the sentence arrives
            # on the loop's `stall_reason` and not in the run's response body (D4, "surface the
            # step, not stop the flow").
            time.sleep(4)
            c2, det = api("GET", f"/projects/{P}/loops/{loop_id}")
            reason = (det or {}).get("stall_reason") or "" if isinstance(det, dict) else ""
            print("      stall_reason: " + reason[:400])
            # NOT `task_id in reason`. `_stall_reason_from_walk` surfaces `unstaffed[0][1]` --
            # the reason alone -- and the rung-3 sentence is about "this task" without naming it.
            # The claim being tested is that the sentence is about the TASK rather than about the
            # queue, and the histogram is the string that proves it is not.
            check("the stall is about this task, not the queue's status histogram",
                  reason and "no claimable task among" not in reason, reason[:220])
            check("...and the exclusion is the OPERATOR arm's, by its own sentence",
                  "has worked on this task" in reason, reason[:220])
            check("...which is not the agent arm's sentence",
                  "is the one that completed this task" not in reason, reason[:220])
            return
        settle()
        t = next((x for x in mine() if x["id"] == task_id), {})
        reviewer = t.get("assignee")
        print(f"      author={author}  reviewer={reviewer}  status={t.get('status')}")
        check("the task left `completed`", t.get("status") != "completed", repr(t.get("status")))
        check("...into a review band, not back into ordinary work",
              t.get("status") in ("under_review", "approved", "revision_needed", "rejected"),
              repr(t.get("status")))
        check("a reviewer was staffed", bool(reviewer), repr(reviewer))
        if COMPLETE_BY == "untouched":
            # Row four's whole point: nothing associates any agent with this task, so the exclusion
            # is empty and even the flow's own default agent is eligible. A refusal here would mean
            # the exclusion is drawing on a record nobody re-derived.
            check("...with NOBODY excluded -- any bound agent may take it",
                  reviewer in pool or reviewer == AGENT, f"{reviewer} vs {pool + [AGENT]}")
        else:
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
            # These were written as `"review" in content` and `TARGET in content`, and both
            # passed -- for the wrong reason. "review" matches the flow paragraph's generic
            # sentence about somebody else reviewing, and TARGET matches the implementation task's
            # own title. Neither said anything about THIS turn being a review, which is the claim
            # being tested. They were then rewritten to assert F143's actual state, deliberately,
            # "so the day it is fixed the lines swap and say so".
            #
            # `a-flow-briefing-names-its-contract` is that day. The three below are the swapped
            # form: the implementation wording must be GONE, the review wording must be PRESENT,
            # and the queue entry the flow composed must not contradict the turn context.
            check(
                "F143 fixed: the reviewer is no longer told to BUILD the thing it checks",
                "Finish the task below and stop" not in content,
                content[:200].replace(chr(10), " | "),
            )
            check(
                "the briefing says this turn is a review",
                "this turn is a review" in content.lower()
                or "you are reviewing" in content.lower()
                or "checking their work" in content.lower(),
                content[:200].replace(chr(10), " | "),
            )
            check(
                "the briefing names both verdicts, with the tool that records them",
                "update_task" in content
                and "approved" in content
                and "revision_needed" in content,
                content[:260].replace(chr(10), " | "),
            )
            # Round 2 of the change (design D9) settled that the briefing must NOT name the
            # commit, and this check was the reason it had to be settled rather than assumed. The
            # briefing is composed at firing time; the commit is resolved one step later, at
            # spawn, by `commit_for_task_review`. Naming it here would be a second copy of a fact
            # that can disagree with the checkout the reviewer is actually standing in -- which is
            # exactly the case `ReviewContext.work_moved` exists to handle, on the channel that
            # resolved it. The commit belongs to the turn CONTEXT, not to this queue entry.
            check(
                "the briefing does NOT name a commit -- that is the context channel's to state",
                "commit" not in content.lower(),
                content[:200].replace(chr(10), " | "),
            )
            # The loop's own message is delivered immediately after the briefing, unchanged, and
            # was authored for the loop's ordinary firings -- in the run that found F143 a reviewer
            # was handed "Work the task you have been given" right here. The briefing says what
            # that text IS. It must not tell the agent to ignore it: a loop's message may itself
            # address a review, and that instruction would be wrong exactly there.
            check(
                "the briefing identifies the loop's standing message without disowning it",
                "standing message" in content.lower()
                and "ignore" not in content.lower()
                and "disregard" not in content.lower(),
                content[-260:].replace(chr(10), " | "),
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
