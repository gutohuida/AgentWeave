"""Row 11 LOOPS -- the OTHER ending, and the thing `loop_ending.py`'s own docstring says went
wrong once: a loop that reads `stopped` and goes on firing anyway.

`t_row11_loop.py` drives the queue-drained ending (`ending_state: "completed"`). This one drives
the stop-time ending (`ending_state: "stopped"`) and then does the only check that distinguishes
"the four facts were written" from "the loop actually stopped": it watches for two and a half
minutes of wall clock -- three cron ticks -- and asserts `run_count` does not move.

Measured on the trial Hub 2026-08-28, before F13: a loop the operator stopped at 23:09 read
`ending_state: "stopped"` from that second onwards and ran twelve more real agent turns.

Run:  AW_HUB=... AW_KEY=... AW_PROJECT=... py -3.11 -u t_row11_loop_quiet.py
Never pipe this through `head`.
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

P = os.environ.get("AW_PROJECT") or "proj-dc4d43543bea"
AGENT = os.environ.get("AW_AGENT") or "alpha"

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
        print("      refusal: " + detail[:400])
    elif not ok:
        print("      " + json.dumps(out, default=str, indent=1)[:700].replace("\n", "\n      "))
    return code, out


def main():
    job_id = loop_id = None
    try:
        head("A. A loop whose stop time has already passed, with real work in its queue")
        past = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        code, job = step(
            "POST /jobs (stop_at two minutes ago)",
            "POST",
            "/projects/%s/jobs" % P,
            {
                "name": "row11-timeup",
                "agent": AGENT,
                "message": "Work the task you have been given, then stop.",
                "cron": "*/1 * * * *",
                "purpose": "Reach the stop-time ending with work still outstanding.",
                "stop_at": past,
                "enabled": True,
                "initial_tasks": [
                    {
                        "title": "Write loop_r11_c.txt",
                        "description": (
                            "Create loop_r11_c.txt containing the word NEVER. "
                            "This task exists so the queue is NOT empty when the loop stops."
                        ),
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
        verdict("a loop with a past stop time is still created (it ends on its first tick, "
                "it is not refused at creation)", bool(job_id) and bool(loop_id))

        head("B. Fire it: the stop condition is checked before any agent is spawned")
        c, before_agents = api("GET", "/projects/%s/agents" % P)
        code, out = step("POST /jobs/{id}/run", "POST",
                         "/projects/%s/jobs/%s/run" % (P, job_id))
        c, lp = api("GET", "/projects/%s/loops/%s" % (P, loop_id))
        c, j = api("GET", "/projects/%s/jobs/%s" % (P, job_id))
        print("  loop: " + json.dumps(
            {k: lp.get(k) for k in ("ending_state", "stop_reason", "stopped_at")},
            default=str))
        verdict("the loop ended on the firing that found its stop time passed",
                lp.get("ending_state") is not None, str(lp.get("ending_state")))
        verdict("ending_state is `stopped`, NOT `completed` -- its queue still holds open work",
                lp.get("ending_state") == "stopped", str(lp.get("ending_state")))
        verdict("stop_reason names the stop TIME, not the queue",
                "stop time" in (lp.get("stop_reason") or ""), str(lp.get("stop_reason")))
        verdict("stopped_at is recorded", bool(lp.get("stopped_at")), str(lp.get("stopped_at")))
        verdict("job.enabled is false", j.get("enabled") is False, str(j.get("enabled")))
        c, t = api("GET", "/projects/%s/tasks" % P)
        rows = [x for x in (t if isinstance(t, list) else []) if x.get("loop_id") == loop_id]
        verdict("no agent was spawned on the queued work: it is still `pending`",
                bool(rows) and all(r["status"] == "pending" for r in rows),
                str([r["status"] for r in rows]))

        head("C. The quiet window -- three cron ticks with nothing to do")
        c, j = api("GET", "/projects/%s/jobs/%s" % (P, job_id))
        base = j.get("run_count")
        c, hist = api("GET", "/projects/%s/jobs/%s/history" % (P, job_id))
        base_hist = len(hist) if isinstance(hist, list) else 0
        print("  baseline: run_count=%s history_rows=%s" % (base, base_hist))
        t0 = time.time()
        while time.time() - t0 < 160:
            time.sleep(20)
            c, j = api("GET", "/projects/%s/jobs/%s" % (P, job_id))
            c, hist = api("GET", "/projects/%s/jobs/%s/history" % (P, job_id))
            c, ag = api("GET", "/projects/%s/agents" % P)
            st = {a["name"]: a.get("status") for a in ag}.get(AGENT)
            print("    t+%3ds run_count=%s history=%s %s=%s"
                  % (int(time.time() - t0), j.get("run_count"),
                     len(hist) if isinstance(hist, list) else "?", AGENT, st))
            sys.stdout.flush()
        verdict(
            "an ended loop fires nothing over three cron ticks -- stopped is TRUE, not merely "
            "reported",
            j.get("run_count") == base
            and (len(hist) if isinstance(hist, list) else -1) == base_hist,
            "run_count %s -> %s, history %s -> %s"
            % (base, j.get("run_count"), base_hist,
               len(hist) if isinstance(hist, list) else "?"),
        )
        c, t = api("GET", "/projects/%s/tasks" % P)
        rows = [x for x in (t if isinstance(t, list) else []) if x.get("loop_id") == loop_id]
        verdict("the outstanding task was never picked up after the ending",
                all(r["status"] == "pending" for r in rows),
                str([r["status"] for r in rows]))

        head("D. What an operator can still do with the abandoned work")
        c3, o3 = step("POST another task into the stopped loop's queue", "POST",
                      "/projects/%s/tasks" % P,
                      {"title": "salvage", "loop_id": loop_id}, expect=(403, 409, 422))
        verdict("a stopped loop's queue is closed too (not only a drained one)",
                c3 in (403, 409, 422), str(c3))
        c1, o1 = step("PATCH enabled=true", "PATCH", "/projects/%s/jobs/%s" % (P, job_id),
                      {"enabled": True}, expect=409)
        d1 = o1.get("detail") if isinstance(o1, dict) else {}
        verdict("restarting a time-stopped loop is refused the same way a drained one is",
                c1 == 409 and isinstance(d1, dict) and d1.get("code") == "loop_ended",
                json.dumps(d1, default=str)[:220])
        if rows:
            r = rows[0]
            c4, o4 = step("the orphaned task is still an ordinary task (rename it)", "PATCH",
                          "/projects/%s/tasks/%s" % (P, r["id"]),
                          {"title": "Write loop_r11_c.txt (orphaned)"}, expect=200)
            verdict("work left behind by a stopped loop is not itself frozen", c4 == 200, str(c4))

    finally:
        head("Z. Teardown -- leave nothing enabled")
        c, t = api("GET", "/projects/%s/tasks" % P)
        for x in t if isinstance(t, list) else []:
            if x.get("loop_id") == loop_id and x["status"] not in ("approved", "rejected"):
                step("reject orphan %s" % x["id"][:16], "PATCH",
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
