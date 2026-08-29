"""F128, isolated: which agent does a loop actually staff when the one it names is busy?

Iteration 9 found this with a harness that was asserting something else (`t_run_while_busy.py`),
and said so: the measurement was real but nothing about that file was designed to isolate it, and
the substitution was observed exactly once. This harness is written FOR it.

The precondition is the opposite of `t_run_while_busy2.py`'s: the job's own agent is mid-turn and a
sibling is deliberately left FREE, so `_agents_that_are_free(session, project_id)` -- which is
project-scoped -- is non-empty and the busy guard does not refuse.

What is asserted, each against an artefact rather than against a status code alone:
  * pressing Run answers 200 while the named agent is running;
  * the conversation the firing created belongs to a DIFFERENT agent, named;
  * that agent is one of the free siblings, not an arbitrary third thing;
  * the loop's task is assigned to the substitute;
  * the job still presents `agent` as the one it was configured with, which is the whole finding;
  * and a second firing is attempted -- once could be a race. That last one is NOT established
    here: the second press answered 500, which is F127 reproducing in a shape this harness did not
    set up (see FINDINGS.md). The substitution itself is confirmed three times across three runs.

Run:  AW_HUB=... AW_KEY=... AW_PROJECT=... py -3.11 -u t_f128_substitution.py
Never pipe this through `head` -- SIGPIPE kills the teardown.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

P = os.environ.get("AW_PROJECT") or "proj-dc4d43543bea"
AGENT = os.environ.get("AW_AGENT") or "gamma"
FREE = [a for a in (os.environ.get("AW_FREE") or "alpha,beta").split(",") if a]

VERDICTS = []


def verdict(label, ok, detail=""):
    VERDICTS.append((label, bool(ok), detail))
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


def agent_status():
    c, ag = api("GET", "/projects/%s/agents" % P)
    return {a["name"]: a.get("status") for a in (ag if isinstance(ag, list) else [])}


def wait_for(pred, limit, label):
    t0 = time.time()
    while time.time() - t0 < limit:
        if pred():
            return True
        time.sleep(4)
    print("  (timed out waiting for %s)" % label)
    return False


def loop_conversations(loop_id):
    """Every conversation this loop produced, newest last, with the agent that ran it."""
    c, body = api("GET", "/projects/%s/conversations" % P)
    if c != 200:
        return []
    rows = body if isinstance(body, list) else (body or {}).get("conversations") or []

    def loop_of(row):
        loop = row.get("loop")
        if isinstance(loop, dict):
            return loop.get("id")
        return loop or row.get("loop_id")

    return [r for r in rows if loop_of(r) == loop_id]


def main():
    job_id = loop_id = None
    try:
        head("A. Nobody is parked: the siblings stay FREE on purpose")
        before = agent_status()
        print("  statuses: %s" % before)
        verdict(
            "at least one sibling is idle, so the free list is non-empty",
            any(before.get(a) == "idle" for a in FREE),
            str({a: before.get(a) for a in FREE}),
        )

        head("B. A loop that NAMES one agent")
        code, job = step(
            "POST /jobs (agent=%s)" % AGENT,
            "POST",
            "/projects/%s/jobs" % P,
            {
                "name": "f128-who-runs-this",
                "agent": AGENT,
                "message": "Reply with the single word: staffed. Do nothing else.",
                "cron": "0 4 * * *",
                "purpose": "Measure which agent a loop staffs when the one it names is busy.",
                "enabled": True,
                "initial_tasks": [{"title": "F128 first errand"}, {"title": "F128 second errand"}],
            },
            expect=(200, 201),
        )
        job_id = job.get("id") or job.get("job_id")
        loop_id = (job.get("loop") or {}).get("id")
        print("  job=%s loop=%s" % (job_id, loop_id))
        verdict("the job records the agent it was given", job.get("agent") == AGENT, str(job.get("agent")))

        head("C. Put THAT agent mid-turn on an unrelated errand")
        step(
            "POST /agent/trigger (%s)" % AGENT,
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
        running = wait_for(lambda: agent_status().get(AGENT) == "running", 60, "%s to start" % AGENT)
        verdict("the loop's own agent is mid-turn", running, str(agent_status().get(AGENT)))
        if not running:
            raise SystemExit("SETUP ABORT: the named agent never started.")

        head("D. Press Run -- the first firing")
        code, out = step("POST /jobs/{id}/run", "POST", "/projects/%s/jobs/%s/run" % (P, job_id))
        verdict(
            "the firing is ACCEPTED while the named agent is busy (the busy guard does not refuse)",
            code in (200, 201, 202),
            str(code),
        )
        if code not in (200, 201, 202):
            print("  detail: %s" % str(out)[:300])

        got = wait_for(lambda: len(loop_conversations(loop_id)) >= 1, 90, "a conversation to appear")
        convs = loop_conversations(loop_id)
        first = convs[-1] if convs else {}
        who1 = first.get("agent") or first.get("agent_name")
        verdict("the firing created a conversation", got and bool(first), str(first.get("id")))
        verdict(
            "IT RAN ON A DIFFERENT AGENT THAN THE JOB NAMES",
            bool(who1) and who1 != AGENT,
            "job.agent=%s, conversation ran on %s (%s)" % (AGENT, who1, first.get("id")),
        )
        verdict(
            "the substitute is one of the free siblings, not something arbitrary",
            who1 in FREE,
            "%s not in %s" % (who1, FREE),
        )
        verdict("the conversation's origin is the job", first.get("origin") == "job", str(first.get("origin")))

        c, tasks = api("GET", "/projects/%s/tasks" % P)
        mine = [t for t in (tasks if isinstance(tasks, list) else []) if t.get("loop_id") == loop_id]
        claimed = [t for t in mine if t.get("assignee")]
        verdict(
            "the loop's task is assigned to the substitute, not to the agent the job names",
            bool(claimed) and all(t.get("assignee") != AGENT for t in claimed),
            str([(t.get("title"), t.get("assignee"), t.get("status")) for t in mine]),
        )

        c, j = api("GET", "/projects/%s/jobs/%s" % (P, job_id))
        verdict(
            "and the job STILL presents `agent` as the one it was configured with -- nothing "
            "anywhere records that someone else did the work",
            j.get("agent") == AGENT,
            "job.agent=%s while %s ran it" % (j.get("agent"), who1),
        )

        head("E. Once is a race. Fire a SECOND time, with the named agent still busy.")
        def loop_tasks():
            c, rows = api("GET", "/projects/%s/tasks" % P)
            return [t for t in (rows if isinstance(rows, list) else []) if t.get("loop_id") == loop_id]

        # A loop delivers one task at a time: pressing Run again while the first errand is still in
        # flight is refused 409 by F48's re-derivation ("Every task on this loop's queue is already
        # being worked"), which is correct and is NOT a second measurement. Measured on run 1.
        #
        # And waiting for the errand to settle by itself does not work either: a Haiku turn that
        # answers the message does not close the task it was handed, so the row sits `in_progress`
        # indefinitely. Measured on run 2, over four minutes. So the OPERATOR closes it -- which is
        # a real operator action, not a shortcut around one.
        in_flight = [t for t in loop_tasks() if t.get("status") == "in_progress"]
        for t in in_flight:
            step("operator completes %s" % t["id"][:16], "PATCH",
                 "/projects/%s/tasks/%s" % (P, t["id"]), {"status": "completed"})
        queue = loop_tasks()
        ready = any(t.get("status") == "pending" for t in queue) and not any(
            t.get("status") == "in_progress" for t in queue
        )
        verdict(
            "the loop's queue has something pending and nothing in flight, so a second firing is "
            "allowed to start work",
            ready,
            str([(t.get("title"), t.get("status"), t.get("assignee")) for t in queue]),
        )

        if ready:
            if agent_status().get(AGENT) != "running":
                step(
                    "re-trigger %s" % AGENT,
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
                wait_for(lambda: agent_status().get(AGENT) == "running", 60, "%s to restart" % AGENT)
            verdict("the named agent is busy for the second firing too",
                    agent_status().get(AGENT) == "running", str(agent_status().get(AGENT)))

            n_before = len(loop_conversations(loop_id))
            code, out = step("POST /jobs/{id}/run (again)", "POST", "/projects/%s/jobs/%s/run" % (P, job_id))
            print("  second firing: %s" % code)
            wait_for(lambda: len(loop_conversations(loop_id)) > n_before, 120, "a second conversation")
            convs = loop_conversations(loop_id)
            second = convs[-1] if len(convs) > n_before else {}
            who2 = second.get("agent") or second.get("agent_name")
            verdict(
                "the substitution is the RULE, not a one-off: the second firing also ran on "
                "somebody other than the agent the job names",
                bool(who2) and who2 != AGENT,
                "second conversation %s ran on %s" % (second.get("id"), who2),
            )
            print("  conversations on this loop: %s"
                  % [(c.get("id"), c.get("agent") or c.get("agent_name")) for c in convs])

    finally:
        head("Z. Teardown -- leave nothing enabled")
        if job_id:
            step("stop the loop", "PATCH", "/projects/%s/jobs/%s" % (P, job_id),
                 {"stop_reason": "drive teardown"})
        c, tasks = api("GET", "/projects/%s/tasks" % P)
        for t in tasks if isinstance(tasks, list) else []:
            if t.get("loop_id") == loop_id and t.get("status") not in ("approved", "rejected"):
                step("reject %s" % t["id"][:16], "PATCH",
                     "/projects/%s/tasks/%s" % (P, t["id"]), {"status": "rejected"})
        if loop_id:
            step("archive loop", "POST", "/projects/%s/loops/%s/archive" % (P, loop_id))
        if job_id:
            step("disable job", "PATCH", "/projects/%s/jobs/%s" % (P, job_id), {"enabled": False})
        c, jobs = api("GET", "/projects/%s/jobs" % P)
        print("  enabled jobs remaining: %s"
              % [x.get("id") for x in (jobs if isinstance(jobs, list) else []) if x.get("enabled")])
        c, loops = api("GET", "/projects/%s/loops" % P)
        print("  loops listed: %s" % [x.get("id") for x in (loops if isinstance(loops, list) else [])])

        head("VERDICTS")
        bad = [v for v in VERDICTS if not v[1]]
        for label, ok, detail in VERDICTS:
            print("  [%s] %s%s" % ("OK " if ok else "BAD", label, ("  -- " + detail) if detail else ""))
        print("\n  %d/%d held" % (len(VERDICTS) - len(bad), len(VERDICTS)))


if __name__ == "__main__":
    main()
