"""T-LOOP: watch a real loop claim, work, drain and stop."""

import sys
import time

from aw import api

P = "proj-18e5d4e0"
JOB = "job-f5558cff"


def line(i):
    c, loops = api("GET", f"/projects/{P}/loops")
    lp = loops[0] if isinstance(loops, list) and loops else {}
    c, job = api("GET", f"/projects/{P}/jobs/{JOB}")
    c, ag = api("GET", f"/projects/{P}/agents")
    st = {a["name"]: a.get("status") for a in ag}.get("builder", "?")
    cur = (lp.get("current_task") or {})
    return (
        "%4ds builder=%-8s enabled=%-5s runs=%-3s firing=%-5s ending=%-10s queue=%s current=%s/%s stop=%s"
        % (
            i,
            st,
            job.get("enabled"),
            job.get("run_count"),
            lp.get("firing_active"),
            lp.get("ending_state"),
            lp.get("queue"),
            (cur.get("title") or "-")[:22],
            cur.get("status"),
            (lp.get("stop_reason") or "-")[:40],
        )
    )


if __name__ == "__main__":
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    for i in range(rounds):
        print(line(i * 15))
        sys.stdout.flush()
        time.sleep(15)
    c, hist = api("GET", f"/projects/{P}/jobs/{JOB}/history")
    print("\njob history (newest first):")
    for h in (hist if isinstance(hist, list) else [])[:12]:
        print("  ", h.get("fired_at"), h.get("status"), h.get("trigger"), (h.get("error_summary") or "")[:70])
