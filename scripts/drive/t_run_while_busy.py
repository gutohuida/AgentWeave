"""F48's defect in the branch F48 did not cover: press Run on a loop whose agent is mid-turn.

Found by accident on 2026-08-29 while setting up `t_row11_stalls.py`, then reproduced deliberately
here.

`_do_fire_job` has TWO branches that decline a firing and **record nothing** -- by design, because
the agent's own running `Run` already carries the fact:

  * `DECISION_IN_FLIGHT` -- every candidate is already being worked. This is the one F48 fixed:
    `run_job` re-derives the decision through `_loop_work_is_all_in_flight` and answers 409 with
    "nothing is wrong".
  * the **busy guard** (`_loop_flow_busy_reason`, scheduler.py:2082) -- the loop's agent is mid-turn
    and nobody else is free. It returns False before a `JobRun` is even constructed.

The second one is invisible to F48's re-derivation, because `_loop_work_is_all_in_flight` asks a
different question: it calls `decide_firing`, which never reaches the busy guard. For a loop with
ordinary claimable work whose agent happens to be busy, the answer is `DECISION_CLAIM`, not
`DECISION_IN_FLIGHT` -- so `run_job` falls into the branch below it and answers
**500 "Failed to fire job"** for a loop in perfect health.

**RUN 2026-08-29 19:13 local: 6 of 11 verdicts held, and the five that did not are THIS FILE'S
PREDICTION being wrong, not the product misbehaving.** The busy guard refuses only when the job's
agent is busy AND `_agents_that_are_free` is empty -- and that list is project-scoped, so a free
sibling agent made the firing proceed. It answered 200 and staffed **alpha**, an agent the job does
not name, on a loop whose `job.agent` is `gamma`. That is finding F128. The 500 this file predicted
IS real and is reproduced deterministically in `t_run_while_busy2.py` (F127), which parks an active
task on every sibling first so the free list is genuinely empty. Both files are kept: this one is
where the substitution was found, and its BAD lines are the record of the wrong prediction.

Run:  AW_HUB=... AW_KEY=... AW_PROJECT=... py -3.11 -u t_run_while_busy.py
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
    if isinstance(detail, dict):
        detail = json.dumps(detail, default=str)
    if isinstance(detail, str):
        print("      detail: " + detail[:300])
    return code, out


def agent_status():
    c, ag = api("GET", "/projects/%s/agents" % P)
    return {a["name"]: a.get("status") for a in (ag if isinstance(ag, list) else [])}.get(AGENT)


def history(job_id):
    c, h = api("GET", "/projects/%s/jobs/%s/history" % (P, job_id))
    return h if isinstance(h, list) else []


def wait_for(pred, limit=180, label=""):
    t0 = time.time()
    while time.time() - t0 < limit:
        if pred():
            return True
        time.sleep(4)
    print("  (timed out waiting for %s after %ds)" % (label, limit))
    return False


def main():
    job_id = loop_id = None
    try:
        head("A. A perfectly ordinary loop with one claimable task")
        code, job = step(
            "POST /jobs",
            "POST",
            "/projects/%s/jobs" % P,
            {
                "name": "busy-run",
                "agent": AGENT,
                "message": "Do the next thing on the queue.",
                "cron": "0 4 * * *",
                "purpose": "Reproduce the 500 an operator gets for pressing Run while busy.",
                "enabled": True,
                "initial_tasks": [
                    {
                        "title": "BUSY write busy_marker.txt",
                        "description": "Create busy_marker.txt containing the word BUSYONE.",
                    }
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
        print("  job=%s loop=%s" % (job_id, loop_id))
        verdict("the loop exists with claimable work waiting", bool(job_id) and bool(loop_id))
        base_hist = history(job_id)
        verdict("nothing in its history yet", base_hist == [], str(len(base_hist)))

        head("B. Put the agent to work on something else entirely")
        code, out = step(
            "POST /agent/trigger (an UNRELATED errand, not the loop's task)",
            "POST",
            "/projects/%s/agent/trigger" % P,
            {
                "agent": AGENT,
                "message": (
                    "Create a file called unrelated_errand.txt containing the word ELSEWHERE, "
                    "then read it back and tell me what it says."
                ),
                "overrides": {"permission_mode": "workspace"},
            },
            expect=(200, 201, 202),
            timeout=30,
        )
        started = wait_for(lambda: agent_status() == "running", 60, "the agent to start")
        verdict("the agent really is mid-turn (status `running`)", started, str(agent_status()))
        if not started:
            raise SystemExit("SETUP ABORT: the agent never started; nothing to reproduce.")

        head("C. Press Run. This is the whole finding.")
        code, out = step("POST /jobs/{id}/run  while the agent is busy", "POST",
                         "/projects/%s/jobs/%s/run" % (P, job_id))
        detail = out.get("detail") if isinstance(out, dict) else None
        verdict(
            "REPRODUCED: pressing Run on a healthy loop whose agent is mid-turn answers 500, not "
            "the 409 'nothing is wrong' F48 introduced for exactly this",
            code == 500,
            str(code),
        )
        verdict(
            "and the message is the bare fallback -- it names no reason at all, because the busy "
            "guard wrote no `error_summary` to read",
            detail == "Failed to fire job",
            repr(detail),
        )
        h = history(job_id)
        verdict(
            "no `JobRun` was recorded for the refusal (the guard's own design), so nothing in the "
            "history explains the 500 either",
            h == base_hist,
            "%d -> %d rows" % (len(base_hist), len(h)),
        )
        c, lp = api("GET", "/projects/%s/loops/%s" % (P, loop_id))
        c, j = api("GET", "/projects/%s/jobs/%s" % (P, job_id))
        verdict(
            "nothing is actually wrong: the loop has not ended and the job is still enabled",
            lp.get("ending_state") is None and j.get("enabled") is True,
            "%s / %s" % (lp.get("ending_state"), j.get("enabled")),
        )
        c, t = api("GET", "/projects/%s/tasks" % P)
        mine = [x for x in (t if isinstance(t, list) else []) if x.get("loop_id") == loop_id]
        verdict(
            "its queued work is untouched and still claimable",
            [x["status"] for x in mine] == ["pending"],
            str([(x["id"], x["status"]) for x in mine]),
        )

        head("D. The same call, once the agent is free")
        done = wait_for(lambda: agent_status() == "idle", 240, "the errand to finish")
        verdict("the unrelated errand ended", done, str(agent_status()))
        code2, out2 = step("POST /jobs/{id}/run  with the agent idle", "POST",
                           "/projects/%s/jobs/%s/run" % (P, job_id))
        verdict(
            "the identical request now succeeds -- the 500 was about WHEN it was pressed, not about "
            "anything being broken",
            code2 == 200,
            "%s %s" % (code2, json.dumps(out2, default=str)[:160]),
        )
        h2 = history(job_id)
        verdict(
            "and this firing DID record a row, unlike the refusal",
            len(h2) == len(base_hist) + 1,
            json.dumps([r.get("status") for r in h2], default=str)[:200],
        )
        wait_for(lambda: agent_status() == "idle", 240, "the loop's own turn to finish")

    finally:
        head("Z. Teardown -- leave nothing enabled")
        if job_id:
            step(
                "stop the loop (PATCH stop_reason -- the operator's own ending path)",
                "PATCH",
                "/projects/%s/jobs/%s" % (P, job_id),
                {"stop_reason": "drive teardown"},
            )
        c, t = api("GET", "/projects/%s/tasks" % P)
        for x in t if isinstance(t, list) else []:
            if x.get("loop_id") == loop_id and x["status"] not in ("approved", "rejected"):
                step("reject leftover %s" % x["id"][:16], "PATCH",
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
