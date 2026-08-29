"""Row 11 LOOPS, second half -- a loop that fires, claims, works, STALLS, drains and stops,
and what the operator can still do to it afterwards.

The first half (a loop firing at all) was driven in earlier sweeps. What had never been driven
is the ending: the difference between a queue that is *stalled* and one that is *drained*, the
four facts `loop_ending.end_loop` promises, and the three ways an operator might try to restart
a loop that has ended.

Run:  AW_HUB=... AW_KEY=... AW_PROJECT=... py -3.11 -u t_row11_loop.py
Never pipe this through `head`: SIGPIPE would kill it before the finally that archives the loop.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

P = os.environ.get("AW_PROJECT") or "proj-dc4d43543bea"
AGENT = os.environ.get("AW_AGENT") or "alpha"
DEADLINE = time.time() + 20 * 60

VERDICTS = []


def verdict(label, ok, detail=""):
    VERDICTS.append((label, ok, detail))
    print("  [%s] %s%s" % ("OK " if ok else "BAD", label, ("  -- " + detail) if detail else ""))


def head(t):
    print()
    print("=" * 78)
    print(t)
    print("=" * 78)


def step(label, method, path, body=None, expect=None, show=False, limit=900):
    code, out = api(method, path, body)
    ok = expect is None or code in (expect if isinstance(expect, tuple) else (expect,))
    print("  %s: %s%s" % (label, code, "" if ok else "   <-- UNEXPECTED"))
    detail = out.get("detail") if isinstance(out, dict) else None
    if isinstance(detail, dict):
        detail = json.dumps(detail, default=str)
    if isinstance(detail, str):
        print("      refusal: " + detail[:400])
    elif show or not ok:
        print("      " + json.dumps(out, default=str, indent=1)[:limit].replace("\n", "\n      "))
    return code, out


def tasks_of(loop_id):
    c, t = api("GET", "/projects/%s/tasks" % P)
    rows = t if isinstance(t, list) else t.get("tasks", [])
    return [x for x in rows if x.get("loop_id") == loop_id]


def loop_row(loop_id):
    c, lp = api("GET", "/projects/%s/loops/%s" % (P, loop_id))
    return lp if isinstance(lp, dict) else {}


def job_row(job_id):
    c, j = api("GET", "/projects/%s/jobs/%s" % (P, job_id))
    return j if isinstance(j, dict) else {}


def history(job_id):
    c, h = api("GET", "/projects/%s/jobs/%s/history" % (P, job_id))
    return h if isinstance(h, list) else []


def snap(job_id, loop_id, t):
    j, lp = job_row(job_id), loop_row(loop_id)
    rows = tasks_of(loop_id)
    c, ag = api("GET", "/projects/%s/agents" % P)
    st = {a["name"]: a.get("status") for a in ag}.get(AGENT, "?")
    print(
        "    t+%4ds %s=%-9s enabled=%-5s runs=%-3s ending=%-9s stop=%-28s tasks=%s"
        % (
            t,
            AGENT,
            st,
            j.get("enabled"),
            j.get("run_count"),
            lp.get("ending_state"),
            (lp.get("stop_reason") or "-")[:28],
            [x["status"] for x in rows],
        )
    )
    sys.stdout.flush()
    return j, lp, rows


def wait_for(job_id, loop_id, pred, why, gap=8, cap=300):
    t0 = time.time()
    while time.time() - t0 < cap and time.time() < DEADLINE:
        j, lp, rows = snap(job_id, loop_id, int(time.time() - t0))
        if pred(j, lp, rows):
            return True, j, lp, rows
        time.sleep(gap)
    j, lp, rows = snap(job_id, loop_id, int(time.time() - t0))
    print("      (gave up waiting for: %s)" % why)
    return False, j, lp, rows


TASKS = [
    {
        "title": "Write loop_r11_a.txt",
        "description": (
            "Create a file named loop_r11_a.txt in your working directory containing exactly "
            "the word ALPHAONE and nothing else. Then mark this task completed. Do nothing else."
        ),
    },
    {
        "title": "Write loop_r11_b.txt",
        "description": (
            "Create a file named loop_r11_b.txt in your working directory containing exactly "
            "the word ALPHATWO and nothing else. Then mark this task completed. Do nothing else."
        ),
    },
]


def main():
    job_id = loop_id = None
    try:
        head("A. Create the loop with a queue of two")
        code, job = step(
            "POST /jobs",
            "POST",
            "/projects/%s/jobs" % P,
            {
                "name": "row11-drain",
                "agent": AGENT,
                "message": "Work the task you have been given, then stop.",
                "cron": "*/1 * * * *",
                "purpose": "Drive a loop to its own ending so the four ending facts can be read.",
                "stop_when_queue_empties": True,
                "enabled": True,
                "initial_tasks": TASKS,
            },
            expect=(200, 201),
        )
        job_id = job.get("id") or job.get("job_id")
        loop = job.get("loop") or {}
        loop_id = loop.get("id")
        if not loop_id:
            c, loops = api("GET", "/projects/%s/loops" % P)
            for lp in loops if isinstance(loops, list) else []:
                if lp.get("job_id") == job_id:
                    loop_id = lp.get("id")
        print("  job=%s loop=%s" % (job_id, loop_id))
        verdict("a loop row was created alongside the job", bool(loop_id))
        seeded = tasks_of(loop_id)
        verdict(
            "the creating call seeded its own queue",
            len(seeded) == 2,
            "%d task(s) carry loop_id" % len(seeded),
        )
        verdict(
            "the create response reports the queue it just seeded, not an empty one",
            bool(loop.get("queue")),
            json.dumps(loop.get("queue"), default=str),
        )

        head("B. Fire it by hand: one task claimed, one turn, one at a time")
        step("POST /jobs/{id}/run", "POST", "/projects/%s/jobs/%s/run" % (P, job_id),
             expect=(200, 201))
        ok, j, lp, rows = wait_for(
            job_id,
            loop_id,
            lambda j, lp, rows: sum(1 for r in rows if r["status"] == "completed") >= 1,
            "the first task to reach completed",
            cap=420,
        )
        verdict("the first firing carried a task to completed", ok,
                str([r["status"] for r in rows]))
        verdict(
            "one task at a time: only one was ever out at once",
            sum(1 for r in rows if r["status"] in ("assigned", "in_progress")) <= 1,
            str([(r["title"][:18], r["status"]) for r in rows]),
        )

        head("C. Let the cron take the second one")
        ok, j, lp, rows = wait_for(
            job_id,
            loop_id,
            lambda j, lp, rows: sum(1 for r in rows if r["status"] == "completed") == 2,
            "both tasks completed",
            cap=480,
        )
        verdict("the loop worked its whole queue unattended", ok,
                str([r["status"] for r in rows]))

        head("D. STALLED is not FINISHED -- both completed, nothing approved")
        print("  waiting ~95s so at least one cron tick lands on a fully-completed queue")
        t0 = time.time()
        while time.time() - t0 < 95 and time.time() < DEADLINE:
            snap(job_id, loop_id, int(time.time() - t0))
            time.sleep(10)
        j, lp, rows = snap(job_id, loop_id, int(time.time() - t0))
        verdict(
            "a queue of completed-but-unapproved work does NOT stop the loop",
            j.get("enabled") is True and lp.get("ending_state") is None,
            "enabled=%s ending_state=%s" % (j.get("enabled"), lp.get("ending_state")),
        )
        hist = history(job_id)
        skipped = [h for h in hist if h.get("status") == "skipped"]
        verdict(
            "the skipped firing says WHY it claimed nothing",
            bool(skipped) and bool(skipped[0].get("error_summary")),
            (skipped[0].get("error_summary") if skipped else "no skipped row at all")[:220],
        )
        print("  --- job history (newest first)")
        for h in hist[:10]:
            print(
                "      %s  %-10s %-8s %s"
                % (
                    h.get("fired_at"),
                    h.get("status"),
                    h.get("trigger"),
                    (h.get("error_summary") or "")[:70],
                )
            )
        verdict(
            "run_count matches the number of history rows (F121's lens, on a loop)",
            j.get("run_count") == len(hist),
            "run_count=%s history_rows=%s" % (j.get("run_count"), len(hist)),
        )

        head("E. The operator approves both, and the queue drains")
        for r in rows:
            step("clear assignee %s" % r["id"][:16], "PATCH",
                 "/projects/%s/tasks/%s" % (P, r["id"]), {"assignee": None}, expect=200)
            step("-> under_review %s" % r["id"][:16], "PATCH",
                 "/projects/%s/tasks/%s" % (P, r["id"]), {"status": "under_review"}, expect=200)
            step("-> approved %s" % r["id"][:16], "PATCH",
                 "/projects/%s/tasks/%s" % (P, r["id"]), {"status": "approved"}, expect=200)
        ok, j, lp, rows = wait_for(
            job_id,
            loop_id,
            lambda j, lp, rows: lp.get("ending_state") is not None,
            "the loop to notice its queue is drained",
            cap=220,
        )
        verdict("the drained queue ended the loop", ok, str(lp.get("stop_reason")))
        verdict(
            "ending_state is `completed`, not `stopped` -- it finished, it was not killed",
            lp.get("ending_state") == "completed",
            str(lp.get("ending_state")),
        )
        verdict(
            "stop_reason is the queue-drained constant",
            lp.get("stop_reason") == "loop queue is empty",
            str(lp.get("stop_reason")),
        )
        verdict("stopped_at is recorded (not the `an unknown time` fallback)",
                bool(lp.get("stopped_at")), str(lp.get("stopped_at")))
        verdict("job.enabled is false -- reported AND true", j.get("enabled") is False,
                "enabled=%s" % j.get("enabled"))

        head("F. Three ways to restart an ended loop, and what each says")
        c1, o1 = step("PATCH enabled=true", "PATCH", "/projects/%s/jobs/%s" % (P, job_id),
                      {"enabled": True}, expect=409)
        d1 = o1.get("detail") if isinstance(o1, dict) else {}
        verdict("re-enabling an ended loop is refused with 409", c1 == 409, str(c1))
        verdict(
            "...and the refusal is machine-readable (`loop_ended`) and names the remedy",
            isinstance(d1, dict)
            and d1.get("code") == "loop_ended"
            and "new loop" in (d1.get("message") or ""),
            json.dumps(d1, default=str)[:220],
        )
        verdict("...and it did not half-apply: the job is still disabled",
                job_row(job_id).get("enabled") is False)

        c2, o2 = step("POST /run on the ended loop", "POST",
                      "/projects/%s/jobs/%s/run" % (P, job_id), expect=400)
        verdict("firing an ended loop by hand is refused with 400", c2 == 400, str(c2))

        c3, o3 = step("POST a task into the closed queue", "POST", "/projects/%s/tasks" % P,
                      {"title": "one more thing", "loop_id": loop_id}, expect=(403, 409, 422))
        verdict("the ended loop's queue is closed to the operator too",
                c3 in (403, 409, 422), str(c3))
        d3 = o3.get("detail") if isinstance(o3, dict) else None
        d3s = d3 if isinstance(d3, str) else json.dumps(d3, default=str)
        verdict("...and that refusal quotes a real time, not `an unknown time`",
                "an unknown time" not in (d3s or ""), (d3s or "")[:220])

        head("G. What the loop leaves behind")
        lp = loop_row(loop_id)
        print("  " + json.dumps(lp, default=str, indent=1)[:1400].replace("\n", "\n  "))
        hist = history(job_id)
        print("  --- final job history")
        for h in hist[:12]:
            print(
                "      %s  %-10s %-8s %s"
                % (
                    h.get("fired_at"),
                    h.get("status"),
                    h.get("trigger"),
                    (h.get("error_summary") or "")[:70],
                )
            )
        j = job_row(job_id)
        verdict(
            "run_count still matches the history rows after the ending",
            j.get("run_count") == len(hist),
            "run_count=%s history_rows=%s" % (j.get("run_count"), len(hist)),
        )

    finally:
        head("Z. Teardown -- leave nothing enabled")
        if loop_id:
            step("archive loop", "POST", "/projects/%s/loops/%s/archive" % (P, loop_id))
        if job_id:
            step("disable job", "PATCH", "/projects/%s/jobs/%s" % (P, job_id), {"enabled": False})
        c, jobs = api("GET", "/projects/%s/jobs" % P)
        live = [x.get("id") for x in (jobs if isinstance(jobs, list) else []) if x.get("enabled")]
        print("  enabled jobs remaining: %s" % live)
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
