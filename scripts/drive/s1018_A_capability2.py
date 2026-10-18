"""Sweep A (2026-10-18): the F597 path. With a capability question open, the operator turns
allow_agent_jobs on in settings; the question is answered for them and the agent woken; its retry
must succeed. Archives the job and turns the setting off after.

    py -3.11 scripts/drive/s1018_A_capability2.py <agent>
"""

import json
import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1018_A_lib import P, e2e, q, req  # noqa: E402

agent = sys.argv[1]
openq = q("select id, answered, answer from questions where project_id=? and subject_key like 'capability-refusal%' order by created_at", P)
print("capability questions:", openq)
last = q("select id from runs where project_id=? and agent=? order by started_at desc limit 1", P, agent)[0]["id"]
s, res = req("PUT", f"/projects/{P}/settings", {"allow_agent_jobs": True})
print("PUT", s, res.get("allow_agent_jobs"), res.get("warnings"))
print("after:", q("select id, answered, answer from questions where project_id=? and subject_key like 'capability-refusal%' order by created_at", P))
time.sleep(6)
runs = q("select id, status from runs where project_id=? and agent=? order by started_at desc limit 1", P, agent)
if runs and runs[0]["id"] != last:
    print("woken run", runs[0]["id"], e2e.wait_for(runs[0]["id"], 5))
    e2e.dump_turn(runs[0]["id"])
else:
    print("no run woke")
s, jobs = req("GET", f"/projects/{P}/jobs?include_archived=true")
print("jobs:", json.dumps([{k: j.get(k) for k in ("id", "name", "enabled", "agent", "created_by")} for j in jobs]))
for j in jobs:
    print("archive", j["id"], req("POST", f"/projects/{P}/jobs/{j['id']}/archive")[0])
print("off:", req("PUT", f"/projects/{P}/settings", {"allow_agent_jobs": False})[0])
