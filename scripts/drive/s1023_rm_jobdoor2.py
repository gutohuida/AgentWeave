"""Runners & models phase 6b: an enabled one-shot job (cron once a year) fired by hand, then archived
at once, to read what model its new conversation inherits.

    py -3.11 scripts/drive/s1023_rm_jobdoor2.py
"""

import time

from s1023_rm_lib import B, PA, e2e, q, show

s, job = show("job-create", "POST", f"{B()}/jobs", {"name": "door", "agent": "a-run", "message": "Reply with exactly the single word OK.", "cron": "0 3 1 1 *", "enabled": True}, limit=200)
JOB = job["id"]
try:
    show("job-run", "POST", f"{B()}/jobs/{JOB}/run", {}, limit=600)
finally:
    show("job-disable", "PATCH", f"{B()}/jobs/{JOB}", {"enabled": False}, limit=120)
for _ in range(30):
    runs = q("select r.id,r.conversation_id,c.origin from runs r join conversations c on c.id=r.conversation_id where r.project_id=? and c.origin='job' order by r.started_at desc limit 1", PA)
    if runs:
        break
    time.sleep(1)
print("  job run", runs)
if runs:
    run = runs[0]["id"]
    print("  ended:", e2e.wait_for(run, 4))
    print("  conversation", q("select id,origin,runtime_overrides from conversations where id=?", runs[0]["conversation_id"]))
    print("  started", q("select data from event_logs where event_type='run_started' and data like ?", f"%{run}%"))
    print("  usage", q("select model,api_equivalent_usd_micros from turn_usage where run_id=?", run))
show("job-archive", "POST", f"{B()}/jobs/{JOB}/archive", {}, limit=120)
