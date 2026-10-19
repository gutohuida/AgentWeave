"""Scenario 7b (2026-10-19 Copilot stall drive): press Stop while a Copilot run waits on an
unanswered permission card (Ask me). How long until the run is stopped, and what happens to the
card?

    py -3.11 scripts/drive/c1019_copilot_s7b.py
"""

import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from c1019_copilot_lib import P, e2e, poll, q, report, req  # noqa: E402

rid = e2e.cmd_turn(
    P, "cop", "Run `git status --short` in the shell and tell me in one line what it shows. "
    "Do not ask me anything.", perm="manual", fresh=True)
t0 = time.time()
while time.time() - t0 < 90 and not q("select 1 from permission_requests where run_id=?", rid):
    time.sleep(1)
print(f"card after {time.time()-t0:.0f}s:", q("select id, status from permission_requests where run_id=?", rid))
time.sleep(5)
t1 = time.time()
print("stop ->", req("POST", f"/projects/{P}/agent/cop/stop"))
print(poll(rid, 180, every=1))
print(f"stopped {time.time()-t1:.1f}s after Stop")
print("cards:", q("select id, status, decided_by, decided_at, dismissed from permission_requests "
                  "where run_id=?", rid))
print("open cards route:", req("GET", f"/projects/{P}/permission-requests?status=pending"))
report(rid)
