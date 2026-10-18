"""Sweep A (2026-10-18): capability plane. allow_agent_jobs off -> an agent's create_job is
refused -> the refusal reaches the operator as a question -> the operator grants it by answering
-> the agent's retry succeeds (a disabled job, F638). Then the job is archived.

    py -3.11 scripts/drive/s1018_A_capability.py <agent>
"""

import json
import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1018_A_lib import P, e2e, q, req  # noqa: E402

agent = sys.argv[1]
print("setting:", req("GET", f"/projects/{P}/settings")[1]["allow_agent_jobs"])
before = {r["id"] for r in q("select id from questions where project_id=?", P)}
msg = ("Call the AgentWeave tool create_job with name 'nightly-sweepA', agent '%s', message "
       "'Reply with the word NIGHT.', cron '0 3 * * *', enabled false. If it is refused, reply with "
       "the refusal text verbatim and stop. If you later get a message saying jobs are allowed, call "
       "create_job again with the same arguments and reply with the job id." % agent)
r1 = e2e.cmd_turn(P, agent, msg, perm="workspace", fresh=True)
print("r1", e2e.wait_for(r1, 5))
e2e.dump_turn(r1)
new_q = [r for r in q("select * from questions where project_id=?", P) if r["id"] not in before]
for r in new_q:
    print("QUESTION:", json.dumps(r, default=str)[:1200])
s, open_rows = req("GET", f"/projects/{P}/questions?answered=false")
mine = [r for r in open_rows if r["id"] in {x["id"] for x in new_q}]
print("open from refusal:", [(r["id"], r["from_agent"], r["question"][:200], [o["label"] for o in r.get("options") or []]) for r in mine])
if mine:
    labels = [o["label"] for o in mine[0].get("options") or []]
    yes = next((lab for lab in labels if lab.lower().startswith(("yes", "allow", "enable", "grant"))), labels[0] if labels else "Yes")
    s, res = req("PATCH", f"/projects/{P}/questions/{mine[0]['id']}", {"answer": yes, "labels": [yes]})
    print("answer:", s, json.dumps(res)[:300])
time.sleep(5)
print("setting after answer:", req("GET", f"/projects/{P}/settings")[1]["allow_agent_jobs"])
runs = q("select id, status from runs where project_id=? and agent=? order by started_at desc limit 2", P, agent)
print("runs:", runs)
if runs and runs[0]["id"] != r1:
    print("r2", e2e.wait_for(runs[0]["id"], 5))
    e2e.dump_turn(runs[0]["id"])
s, jobs = req("GET", f"/projects/{P}/jobs?include_archived=true")
print("jobs:", json.dumps(jobs)[:1500])
for j in jobs if isinstance(jobs, list) else []:
    print("archive", j["id"], req("POST", f"/projects/{P}/jobs/{j['id']}/archive"))
print("turn the setting back off:", req("PUT", f"/projects/{P}/settings", {"allow_agent_jobs": False})[0])
