"""Runners & models phase 6: the job door. A firing opens a new conversation that inherits the agent's
latest per-run model ("haiku") as written; then the job is archived.

    py -3.11 scripts/drive/s1023_rm_jobdoor.py
"""

import json
import pathlib

from s1023_rm_lib import B, PA, e2e, q, show

JOB = json.loads((pathlib.Path(__file__).resolve().parents[2] / "testbed/rm1023/job.json").read_text())["job"]
show("job-before", "GET", f"{B()}/jobs/{JOB}", limit=400)
s, fired = show("job-run", "POST", f"{B()}/jobs/{JOB}/run", {})
runs = q("select id,conversation_id,status from runs where project_id=? and agent='a-run' order by started_at desc limit 1", PA)
print("  newest run", runs)
if runs:
    run = runs[0]["id"]
    print("  ended:", e2e.wait_for(run, 4))
    print("  conversation", q("select id,origin,runtime_overrides from conversations where id=?", runs[0]["conversation_id"]))
    print("  started", q("select data from event_logs where event_type='run_started' and data like ?", f"%{run}%"))
    print("  usage", q("select model,api_equivalent_usd_micros from turn_usage where run_id=?", run))
show("job-archive", "POST", f"{B()}/jobs/{JOB}/archive", {}, limit=300)
