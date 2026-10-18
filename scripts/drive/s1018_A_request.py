"""Sweep A (2026-10-18): request_agent from a real agent turn. Over the agent budget first (F648:
does the refusal name remedies?), then with room: an unknown template, a route word, and a good
request (does it copy runner/charter/config but not grants?).

    py -3.11 scripts/drive/s1018_A_request.py <agent>
"""

import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1018_A_lib import P, e2e, q, req  # noqa: E402

agent = sys.argv[1]
base = f"/projects/{P}"
print("open agents:", q("select count(*) n from agents where project_id=? and archived_at is null", P))
print("budget:", req("GET", base + "/settings")[1]["agent_budget"])
req("PATCH", base + "/agents/board", {"can_read_checkpoints": True, "description": "template agent", "config": {"env_vars": {"X_SWEEP": "1"}}})
r1 = e2e.cmd_turn(P, agent, "Call the AgentWeave tool request_agent with name 'helper1', template 'board', "
                  "task 'Reply with the word READY.'. Reply with the tool's answer verbatim.", perm="workspace", fresh=True)
print("r1", e2e.wait_for(r1, 5))
e2e.dump_turn(r1, tools=False)
print("budget -> 20:", req("PUT", base + "/settings", {"agent_budget": 20})[0])
r2 = e2e.cmd_turn(P, agent, "Make three separate calls to the AgentWeave tool request_agent: (1) name 'helper2', "
                  "template 'ghost', task 'x'; (2) name 'settings', template 'board', task 'x'; (3) name "
                  "'helper1', template 'board', task 'Reply with the word READY.'. Reply with each answer "
                  "verbatim, one per line.", perm="workspace")
print("r2", e2e.wait_for(r2, 5))
e2e.dump_turn(r2, tools=False)
print("helper1 row:", q("select name, runner_id, charter_id, config, description, can_read_checkpoints, default_permission_mode from agents where project_id=? and name in ('helper1','board')", P))
hr = q("select id, status from runs where project_id=? and agent='helper1'", P)
print("helper1 runs:", hr)
for r in hr:
    print(r["id"], e2e.wait_for(r["id"], 4))
    e2e.dump_turn(r["id"], tools=False)
print("budget -> 8:", req("PUT", base + "/settings", {"agent_budget": 8}))
