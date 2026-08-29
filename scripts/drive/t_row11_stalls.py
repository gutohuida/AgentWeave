"""Row 11 LOOPS -- the three stall shapes iteration 7 did NOT drive.

`_loop_stall_reason` has four branches. Iteration 7 drove exactly one: the queue whose tasks are
all `completed` and unapproved ("no claimable task among N open"). The other three have never been
driven live:

  1. every claimable candidate refused by `dependency_gate`, prerequisite still workable
     -> "loop queue is stalled: 1 still awaiting a prerequisite's approval"
  2. the same, but the prerequisite is `rejected` and will never clear
     -> "loop queue is stalled: 1 gated on a rejected prerequisite that will not clear on its own"
  3. the generic message with `blocked` in the breakdown -- a task waiting on a PERSON
     -> "loop queue is stalled: no claimable task among 1 open (1 blocked)"

And underneath all three, design D6's coalescing, which no drive has touched at all: a *continuing*
stall must count into the existing `JobRun` (tick_count++, `fired_at` frozen) instead of appending
a row, while a stall that CHANGES SHAPE must get its own row. That is the difference between a
stalled loop the operator can read and twelve identical rows an hour burying the firings that
worked.

Every stall must also leave the loop ALIVE: skipped, not stopped. `job.enabled` stays true,
`ending_state` stays null, no agent is spawned.

Run:  AW_HUB=... AW_KEY=... AW_PROJECT=... py -3.11 -u t_row11_stalls.py
Never pipe this through `head` -- SIGPIPE kills the teardown.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

P = os.environ.get("AW_PROJECT") or "proj-dc4d43543bea"
AGENT = os.environ.get("AW_AGENT") or "beta"

VERDICTS = []


def verdict(label, ok, detail=""):
    VERDICTS.append((label, ok, detail))
    print("  [%s] %s%s" % ("OK " if ok else "BAD", label, ("  -- " + detail) if detail else ""))


def head(t):
    print()
    print("=" * 78)
    print(t)
    print("=" * 78)


def step(label, method, path, body=None, expect=None):
    code, out = api(method, path, body)
    ok = expect is None or code in (expect if isinstance(expect, tuple) else (expect,))
    print("  %s: %s%s" % (label, code, "" if ok else "   <-- UNEXPECTED"))
    detail = out.get("detail") if isinstance(out, dict) else None
    if isinstance(detail, dict):
        detail = json.dumps(detail, default=str)
    if isinstance(detail, str):
        print("      detail: " + detail[:400])
    elif not ok:
        print("      " + json.dumps(out, default=str, indent=1)[:700].replace("\n", "\n      "))
    return code, out


def history(job_id):
    c, h = api("GET", "/projects/%s/jobs/%s/history" % (P, job_id))
    return h if isinstance(h, list) else []


def skipped_events(job_id):
    c, evs = api("GET", "/projects/%s/events/history?limit=500" % P)
    return [
        e
        for e in (evs if isinstance(evs, list) else [])
        if e.get("type") == "job_run_skipped" and (e.get("data") or {}).get("job_id") == job_id
    ]


def fire(job_id, label):
    """Fire the job by hand. A stalled firing answers 409 with the reason as `detail`."""
    code, out = step(label, "POST", "/projects/%s/jobs/%s/run" % (P, job_id))
    detail = out.get("detail") if isinstance(out, dict) else None
    return code, (detail if isinstance(detail, str) else json.dumps(out, default=str))


def statuses(loop_id):
    c, t = api("GET", "/projects/%s/tasks" % P)
    return {
        x["id"]: x["status"]
        for x in (t if isinstance(t, list) else [])
        if x.get("loop_id") == loop_id
    }


def main():
    job_id = loop_id = a_id = b_id = None
    try:
        head("A. A loop with two tasks and an ordering between them")
        # Cron far in the future so nothing ticks underneath the drive; `enabled` must be true
        # because `POST /jobs/{id}/run` refuses a disabled job with 400.
        code, job = step(
            "POST /jobs (two initial tasks, cron 04:00)",
            "POST",
            "/projects/%s/jobs" % P,
            {
                "name": "row11-stalls",
                "agent": AGENT,
                "message": "Do the next thing on the queue.",
                "cron": "0 4 * * *",
                "purpose": "Drive the three stall shapes that have never been driven.",
                "enabled": True,
                "initial_tasks": [
                    {"title": "STALLS prerequisite", "description": "The task B waits on."},
                    {
                        "title": "STALLS dependent",
                        "description": "Cannot start until A is approved.",
                    },
                ],
            },
            expect=(200, 201),
        )
        job_id = job.get("id") or job.get("job_id")
        loop_id = (job.get("loop") or {}).get("id")
        if not loop_id:
            c, loops = api("GET", "/projects/%s/loops" % P)
            for lp in loops if isinstance(loops, list) else []:
                if lp.get("job_id") == job_id:
                    loop_id = lp.get("id")
        c, t = api("GET", "/projects/%s/tasks" % P)
        mine = [x for x in (t if isinstance(t, list) else []) if x.get("loop_id") == loop_id]
        for x in mine:
            if "prerequisite" in x["title"]:
                a_id = x["id"]
            if "dependent" in x["title"]:
                b_id = x["id"]
        print("  job=%s loop=%s A=%s B=%s" % (job_id, loop_id, a_id, b_id))
        verdict("the loop and both queue tasks exist", all([job_id, loop_id, a_id, b_id]))

        c, dep = step(
            "POST /tasks/B/dependencies {depends_on: A}",
            "POST",
            "/projects/%s/tasks/%s/dependencies" % (P, b_id),
            {"depends_on": a_id},
            expect=201,
        )
        verdict(
            "an operator can declare the ordering by hand (F36's route), outcome not `duplicate`",
            c == 201 and isinstance(dep, dict) and dep.get("outcome") != "duplicate",
            json.dumps(dep, default=str)[:160],
        )
        c, t = api("GET", "/projects/%s/tasks" % P)
        brow = [x for x in (t if isinstance(t, list) else []) if x["id"] == b_id][0]
        arow = [x for x in (t if isinstance(t, list) else []) if x["id"] == a_id][0]
        verdict(
            "B's response carries the prerequisite and A's carries the dependent -- the edge is "
            "visible from both ends",
            [p.get("id") for p in (brow.get("prerequisites") or [])] == [a_id]
            and [d.get("id") for d in (arow.get("dependents") or [])] == [b_id],
            "B.prereq=%s A.dependents=%s" % (brow.get("prerequisites"), arow.get("dependents")),
        )

        head("B. Shape 1 -- the prerequisite is BLOCKED, so B is gated but not hopeless")
        step(
            "A -> in_progress",
            "PATCH",
            "/projects/%s/tasks/%s" % (P, a_id),
            {"status": "in_progress"},
            expect=200,
        )
        step(
            "A -> blocked",
            "PATCH",
            "/projects/%s/tasks/%s" % (P, a_id),
            {"status": "blocked", "blocked_reason": "waiting on a person to answer"},
            expect=200,
        )
        print("  statuses: %s" % statuses(loop_id))
        if statuses(loop_id).get(a_id) != "blocked":
            raise SystemExit(
                "SETUP ABORT: A is %r, not `blocked` -- firing now would CLAIM it and spawn a real "
                "turn instead of stalling." % statuses(loop_id).get(a_id)
            )
        before_hist = history(job_id)
        before_evs = skipped_events(job_id)

        code, detail = fire(job_id, "POST /jobs/{id}/run  (shape 1)")
        UNMET = "loop queue is stalled: 1 still awaiting a prerequisite's approval"
        verdict("a gated-queue firing is refused with exactly 409", code == 409, str(code))
        verdict(
            "the reason is the GATE's sentence, naming the remedy (wait/review), not the generic "
            "'no claimable task among N open'",
            detail == UNMET,
            repr(detail),
        )
        c, lp = api("GET", "/projects/%s/loops/%s" % (P, loop_id))
        c, j = api("GET", "/projects/%s/jobs/%s" % (P, job_id))
        verdict(
            "stalled is not stopped: ending_state is still null",
            lp.get("ending_state") is None,
            str(lp.get("ending_state")),
        )
        verdict(
            "stalled is not stopped: the job is still enabled and still scheduled",
            j.get("enabled") is True and bool(j.get("next_run")),
            "enabled=%s next_run=%s" % (j.get("enabled"), j.get("next_run")),
        )
        verdict(
            "no agent was spawned: B is untouched at `pending`",
            statuses(loop_id).get(b_id) == "pending",
            str(statuses(loop_id)),
        )
        h1 = history(job_id)
        new1 = [r for r in h1 if r["id"] not in {x["id"] for x in before_hist}]
        verdict(
            "exactly one new history row, status `skipped`, carrying the reason",
            len(new1) == 1
            and new1[0]["status"] == "skipped"
            and new1[0].get("error_summary") == UNMET,
            json.dumps(
                [
                    {k: r.get(k) for k in ("status", "tick_count", "error_summary")}
                    for r in new1
                ],
                default=str,
            )[:300],
        )
        verdict(
            "its tick_count is 1 -- one refusal so far",
            bool(new1) and new1[0].get("tick_count") == 1,
            str(new1[0].get("tick_count") if new1 else None),
        )
        e1 = skipped_events(job_id)
        verdict(
            "a `job_run_skipped` event was persisted for the operator's activity feed",
            len(e1) == len(before_evs) + 1,
            "%d -> %d" % (len(before_evs), len(e1)),
        )

        head("C. The SAME stall again -- design D6: count in place, do not append")
        row_id, fired_at = new1[0]["id"], new1[0]["fired_at"]
        code2, detail2 = fire(job_id, "POST /jobs/{id}/run  (same shape, second time)")
        verdict(
            "the second refusal answers 409 with the same sentence",
            code2 == 409 and detail2 == UNMET,
            "%s %r" % (code2, detail2),
        )
        h2 = history(job_id)
        verdict(
            "NO second row was appended -- a stalled loop does not bury its own history",
            len(h2) == len(h1),
            "%d -> %d rows" % (len(h1), len(h2)),
        )
        same = [r for r in h2 if r["id"] == row_id]
        verdict(
            "the existing row counted the re-check: tick_count 1 -> 2",
            bool(same) and same[0].get("tick_count") == 2,
            str(same[0].get("tick_count") if same else None),
        )
        verdict(
            "`fired_at` was NOT moved -- the row reads 'this stall began then', so a real firing "
            "still sorts above it",
            bool(same) and same[0]["fired_at"] == fired_at,
            "%s -> %s" % (fired_at, same[0]["fired_at"] if same else None),
        )
        e2 = skipped_events(job_id)
        verdict(
            "a CONTINUING stall emits no second event either (the feed is not spammed)",
            len(e2) == len(e1),
            "%d -> %d" % (len(e1), len(e2)),
        )

        head("D. Shape 2 -- the prerequisite is REJECTED and will never clear")
        step(
            "A -> rejected",
            "PATCH",
            "/projects/%s/tasks/%s" % (P, a_id),
            {"status": "rejected"},
            expect=200,
        )
        print("  statuses: %s" % statuses(loop_id))
        code3, detail3 = fire(job_id, "POST /jobs/{id}/run  (shape 2)")
        REJ = (
            "loop queue is stalled: 1 gated on a rejected prerequisite that will not clear on "
            "its own"
        )
        verdict(
            "a permanently gated queue is still a 409 SKIP, not a stop -- `rejected -> pending` is "
            "operator-only and reversible",
            code3 == 409,
            str(code3),
        )
        verdict(
            "the reason distinguishes 'will never clear' from 'not yet' -- the remedies differ",
            detail3 == REJ,
            repr(detail3),
        )
        c, lp = api("GET", "/projects/%s/loops/%s" % (P, loop_id))
        c, j = api("GET", "/projects/%s/jobs/%s" % (P, job_id))
        verdict(
            "the loop is still alive after a permanent gate (ending_state null, job enabled)",
            lp.get("ending_state") is None and j.get("enabled") is True,
            "%s / %s" % (lp.get("ending_state"), j.get("enabled")),
        )
        h3 = history(job_id)
        new3 = [r for r in h3 if r["id"] not in {x["id"] for x in h2}]
        verdict(
            "a stall that CHANGED SHAPE got its own row instead of hiding inside the count",
            len(new3) == 1 and new3[0].get("error_summary") == REJ,
            json.dumps(
                [{k: r.get(k) for k in ("tick_count", "error_summary")} for r in new3],
                default=str,
            )[:300],
        )
        verdict(
            "the first row's count is frozen where it was -- it is not resurrected",
            [r for r in h3 if r["id"] == row_id][0].get("tick_count") == 2,
            str([r for r in h3 if r["id"] == row_id][0].get("tick_count")),
        )

        head("E. Shape 3 -- no gate at all, one task waiting on a PERSON")
        step(
            "DELETE the dependency",
            "DELETE",
            "/projects/%s/tasks/%s/dependencies/%s" % (P, b_id, a_id),
            expect=204,
        )
        step(
            "B -> in_progress",
            "PATCH",
            "/projects/%s/tasks/%s" % (P, b_id),
            {"status": "in_progress"},
            expect=200,
        )
        step(
            "B -> blocked",
            "PATCH",
            "/projects/%s/tasks/%s" % (P, b_id),
            {"status": "blocked", "blocked_reason": "waiting on a person to answer"},
            expect=200,
        )
        print("  statuses: %s" % statuses(loop_id))
        if statuses(loop_id).get(b_id) != "blocked":
            raise SystemExit("SETUP ABORT: B is %r, not `blocked`." % statuses(loop_id).get(b_id))
        code4, detail4 = fire(job_id, "POST /jobs/{id}/run  (shape 3)")
        BLOCKED = "loop queue is stalled: no claimable task among 1 open (1 blocked)"
        verdict(
            "a queue holding only a blocked task stalls rather than spawning",
            code4 == 409,
            str(code4),
        )
        verdict(
            "the breakdown names the status a person has to clear, and counts the REJECTED "
            "prerequisite as gone (terminal), not as open work",
            detail4 == BLOCKED,
            repr(detail4),
        )
        h4 = history(job_id)
        new4 = [r for r in h4 if r["id"] not in {x["id"] for x in h3}]
        verdict(
            "third shape, third row",
            len(new4) == 1 and new4[0].get("error_summary") == BLOCKED,
            json.dumps([r.get("error_summary") for r in new4], default=str)[:200],
        )

        head("F. Nothing spawned, across all four firings")
        # There is no `/runs` collection route on a project, so the honest record of what each
        # firing did is `JobRun` itself: a firing that spawned carries `in_progress`/`completed`/
        # `failed` and a `session_id`, a firing that stalled carries `skipped` and a reason.
        hist = history(job_id)
        verdict(
            "every JobRun this loop ever wrote is a `skipped` stall -- four firings, zero spawns",
            bool(hist) and all(r["status"] == "skipped" for r in hist),
            json.dumps([(r["status"], r.get("session_id")) for r in hist], default=str)[:300],
        )
        verdict(
            "no firing carries a session_id: nothing was ever handed to a runner",
            all(r.get("session_id") is None for r in hist),
            json.dumps([r.get("session_id") for r in hist], default=str)[:200],
        )
        c, ag = api("GET", "/projects/%s/agents" % P)
        me = {a["name"]: a.get("status") for a in (ag if isinstance(ag, list) else [])}.get(AGENT)
        verdict(
            "the loop's agent never left idle across all four firings",
            me == "idle",
            "%s=%s" % (AGENT, me),
        )
        c, j = api("GET", "/projects/%s/jobs/%s" % (P, job_id))
        print(
            "  job: %s"
            % json.dumps(
                {k: j.get(k) for k in ("enabled", "run_count", "last_run", "next_run")},
                default=str,
            )
        )
        verdict(
            "the loop survived every stall: still enabled, never ended",
            j.get("enabled") is True,
            str(j.get("enabled")),
        )

    finally:
        head("Z. Teardown -- leave nothing enabled")
        c, t = api("GET", "/projects/%s/tasks" % P)
        for x in t if isinstance(t, list) else []:
            if x.get("loop_id") == loop_id and x["status"] not in ("approved", "rejected"):
                step(
                    "reject leftover %s" % x["id"][:16],
                    "PATCH",
                    "/projects/%s/tasks/%s" % (P, x["id"]),
                    {"status": "rejected"},
                )
        if loop_id:
            step("archive loop", "POST", "/projects/%s/loops/%s/archive" % (P, loop_id))
        if job_id:
            step("disable job", "PATCH", "/projects/%s/jobs/%s" % (P, job_id), {"enabled": False})
        c, jobs = api("GET", "/projects/%s/jobs" % P)
        print(
            "  enabled jobs remaining: %s"
            % [x.get("id") for x in (jobs if isinstance(jobs, list) else []) if x.get("enabled")]
        )
        c, loops = api("GET", "/projects/%s/loops" % P)
        print(
            "  loops listed: %s"
            % [x.get("id") for x in (loops if isinstance(loops, list) else [])]
        )

        head("VERDICTS")
        bad = [v for v in VERDICTS if not v[1]]
        for label, ok, detail in VERDICTS:
            print("  [%s] %s" % ("OK " if ok else "BAD", label))
        print("\n  %d/%d held" % (len(VERDICTS) - len(bad), len(VERDICTS)))


if __name__ == "__main__":
    main()
