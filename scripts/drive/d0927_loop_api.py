"""b10 drive, API half of Human-only 3 and 6 (2026-09-27). AW_HUB, AW_KEY, AW_PROJECT. Never :8000/:8010."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from aw import api, P, require_hub
assert not require_hub().endswith((":8000", ":8010"))
A = "/projects/%s" % P
def mk(name):
    c, j = api("POST", A + "/jobs", {"name": name, "agent": "alpha", "message": "Write hello.txt containing hi, then stop.",
        "cron": "0 0 1 1 *", "purpose": "b10 drive", "enabled": True,
        "initial_tasks": [{"title": "Write hello.txt", "description": "Create hello.txt containing hi."}]})
    assert c in (200, 201), (c, j); return j["id"], j["loop"]["id"]
def lp(l): return api("GET", "%s/loops/%s" % (A, l))[1]
ev = lambda l: [e["event_type"] for e in lp(l)["events"]]

print("== 6: archive a running loop's job")
j, l = mk("b10-D")
c, out = api("POST", "%s/jobs/%s/archive" % (A, j)); print("  archive job:", c, str(out)[:200])
x = lp(l); print("  loop:", x.get("ending_state"), "|", x.get("stop_reason"), "| archived_at", x.get("archived_at")); print("  events:", ev(l))

j, l = mk("b10-E")
c, out = api("POST", "%s/jobs/%s/run" % (A, j)); print("  run:", c, str(out)[:160])
t0 = time.time(); active = False
while time.time() - t0 < 60:
    if lp(l).get("firing_active"): active = True; break
    time.sleep(1)
print("  firing_active seen:", active, "after %.0fs" % (time.time() - t0))
c, out = api("PATCH", "%s/jobs/%s" % (A, j), {"stop_reason": "drive: stop mid-firing"}); print("  stop:", c)
x = lp(l); print("  right after stop: ending", x.get("ending_state"), "firing_active", x.get("firing_active"))
t0 = time.time()
while time.time() - t0 < 240 and lp(l).get("firing_active"): time.sleep(3)
x = lp(l); print("  after settle (%.0fs): ending %s reason %r firing_active %s" % (time.time() - t0, x.get("ending_state"), x.get("stop_reason"), x.get("firing_active")))
c, jb = api("GET", "%s/jobs/%s" % (A, j)); print("  job enabled:", jb.get("enabled"), "run_count", jb.get("run_count"))
c, h = api("GET", "%s/jobs/%s/history" % (A, j)); print("  history rows:", len(h) if isinstance(h, list) else h)
print("  events:", ev(l))
for jid in (j,):
    api("PATCH", "%s/jobs/%s" % (A, jid), {"enabled": False})
