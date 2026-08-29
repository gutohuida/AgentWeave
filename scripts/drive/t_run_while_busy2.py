"""F48's defect in the sibling branch: press Run when the BUSY GUARD refuses -> 500.

The first attempt (`t_run_while_busy.py`) failed to reproduce and found something else instead: the
busy guard only refuses when the job's agent is busy AND `_agents_that_are_free` is empty, and that
list is PROJECT-scoped, so a free sibling agent made the firing proceed and staff *someone else*.

This one satisfies the real precondition. "Free" is `not running` AND `holding no active task`
(scheduler.py:944), so parking one active task on every other agent empties the free list without
spending a single turn on them. Then the job's own agent is put mid-turn for real, and Run is
pressed.

Expected if the finding is real: the busy guard refuses, records NOTHING (by design), and
`run_job` -- whose F48 re-derivation asks `decide_firing`, which never reaches the busy guard --
falls through to `500 "Failed to fire job"` for a loop in perfect health.

Run:  AW_HUB=... AW_KEY=... AW_PROJECT=... py -3.11 -u t_run_while_busy2.py
Never pipe this through `head` -- SIGPIPE kills the teardown.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

P = os.environ.get("AW_PROJECT") or "proj-dc4d43543bea"
AGENT = os.environ.get("AW_AGENT") or "gamma"
OTHERS = [a for a in (os.environ.get("AW_OTHERS") or "alpha,beta").split(",") if a]

VERDICTS = []


def verdict(label, ok, detail=""):
    VERDICTS.append((label, ok, detail))
    print("  [%s] %s%s" % ("OK " if ok else "BAD", label, ("  -- " + detail) if detail else ""))


def head(t):
    print()
    print("=" * 78)
    print(t)
    print("=" * 78)


def step(label, method, path, body=None, expect=None, timeout=60):
    code, out = api(method, path, body, timeout=timeout)
    ok = expect is None or code in (expect if isinstance(expect, tuple) else (expect,))
    print("  %s: %s%s" % (label, code, "" if ok else "   <-- UNEXPECTED"))
    detail = out.get("detail") if isinstance(out, dict) else None
    if isinstance(detail, str):
        print("      detail: " + detail[:300])
    return code, out


def status_of(name):
    c, ag = api("GET", "/projects/%s/agents" % P)
    return {a["name"]: a.get("status") for a in (ag if isinstance(ag, list) else [])}.get(name)


def wait_for(pred, limit, label):
    t0 = time.time()
    while time.time() - t0 < limit:
        if pred():
            return True
        time.sleep(4)
    print("  (timed out waiting for %s)" % label)
    return False


def main():
    job_id = loop_id = None
    parked = []
    try:
        head("A. Empty the free list: one active task parked on every other agent")
        for other in OTHERS:
            c, t = step(
                "POST /tasks assigned to %s" % other,
                "POST",
                "/projects/%s/tasks" % P,
                {"title": "PARK hold %s busy" % other, "assignee": other, "status": "assigned"},
                expect=(200, 201),
            )
            if isinstance(t, dict) and t.get("id"):
                parked.append(t["id"])
        print("  parked: %s" % parked)
        verdict("every sibling agent now holds an active task", len(parked) == len(OTHERS))

        head("B. An ordinary loop, and its agent put to work elsewhere")
        code, job = step(
            "POST /jobs",
            "POST",
            "/projects/%s/jobs" % P,
            {
                "name": "busy-run-2",
                "agent": AGENT,
                "message": "Do the next thing on the queue.",
                "cron": "0 4 * * *",
                "purpose": "Reproduce the 500 the busy guard hands an operator.",
                "enabled": True,
                "initial_tasks": [{"title": "BUSY2 anything at all"}],
            },
            expect=(200, 201),
        )
        job_id = job.get("id") or job.get("job_id")
        loop_id = (job.get("loop") or {}).get("id")
        c, h = api("GET", "/projects/%s/jobs/%s/history" % (P, job_id))
        base = len(h) if isinstance(h, list) else 0
        print("  job=%s loop=%s history=%d" % (job_id, loop_id, base))

        step(
            "POST /agent/trigger (%s, an unrelated errand)" % AGENT,
            "POST",
            "/projects/%s/agent/trigger" % P,
            {
                "agent": AGENT,
                "message": "Reply with the single word: busy. Do nothing else.",
                "overrides": {"permission_mode": "workspace"},
            },
            expect=(200, 201, 202),
            timeout=30,
        )
        running = wait_for(lambda: status_of(AGENT) == "running", 60, "the agent to start")
        verdict("the loop's own agent is mid-turn", running, str(status_of(AGENT)))
        if not running:
            raise SystemExit("SETUP ABORT: the agent never started.")

        head("C. Press Run")
        code, out = step("POST /jobs/{id}/run", "POST", "/projects/%s/jobs/%s/run" % (P, job_id))
        detail = out.get("detail") if isinstance(out, dict) else None
        verdict(
            "REPRODUCED: a healthy loop, refused by the busy guard, answers 500 -- not the 409 "
            "'nothing is wrong' F48 introduced for the sibling branch",
            code == 500,
            str(code),
        )
        verdict(
            "the message is the bare fallback: the guard recorded no `error_summary` to name",
            detail == "Failed to fire job",
            repr(detail),
        )
        c, h2 = api("GET", "/projects/%s/jobs/%s/history" % (P, job_id))
        verdict(
            "and no `JobRun` was written, so nothing in the loop's history explains the 500",
            (len(h2) if isinstance(h2, list) else -1) == base,
            "%d -> %s" % (base, len(h2) if isinstance(h2, list) else "?"),
        )
        c, lp = api("GET", "/projects/%s/loops/%s" % (P, loop_id))
        c, j = api("GET", "/projects/%s/jobs/%s" % (P, job_id))
        verdict(
            "nothing is wrong: the loop has not ended, the job is still enabled and scheduled",
            lp.get("ending_state") is None and j.get("enabled") is True and bool(j.get("next_run")),
            "%s / %s / %s" % (lp.get("ending_state"), j.get("enabled"), j.get("next_run")),
        )
        c, t = api("GET", "/projects/%s/tasks" % P)
        mine = [x for x in (t if isinstance(t, list) else []) if x.get("loop_id") == loop_id]
        verdict(
            "the queued work is untouched -- the refusal really was a refusal",
            [x["status"] for x in mine] == ["pending"],
            str([(x["id"], x["status"]) for x in mine]),
        )

    finally:
        head("Z. Teardown -- leave nothing enabled")
        if job_id:
            step("stop the loop", "PATCH", "/projects/%s/jobs/%s" % (P, job_id),
                 {"stop_reason": "drive teardown"})
        c, t = api("GET", "/projects/%s/tasks" % P)
        for x in t if isinstance(t, list) else []:
            if (x["id"] in parked or x.get("loop_id") == loop_id) and x["status"] not in (
                "approved",
                "rejected",
            ):
                step("reject %s" % x["id"][:16], "PATCH",
                     "/projects/%s/tasks/%s" % (P, x["id"]), {"status": "rejected"})
        if loop_id:
            step("archive loop", "POST", "/projects/%s/loops/%s/archive" % (P, loop_id))
        if job_id:
            step("disable job", "PATCH", "/projects/%s/jobs/%s" % (P, job_id), {"enabled": False})
        c, jobs = api("GET", "/projects/%s/jobs" % P)
        print("  enabled jobs remaining: %s"
              % [x.get("id") for x in (jobs if isinstance(jobs, list) else []) if x.get("enabled")])
        c, loops = api("GET", "/projects/%s/loops" % P)
        print("  loops listed: %s"
              % [x.get("id") for x in (loops if isinstance(loops, list) else [])])

        head("VERDICTS")
        bad = [v for v in VERDICTS if not v[1]]
        for label, ok, detail in VERDICTS:
            print("  [%s] %s" % ("OK " if ok else "BAD", label))
        print("\n  %d/%d held" % (len(VERDICTS) - len(bad), len(VERDICTS)))


if __name__ == "__main__":
    main()
