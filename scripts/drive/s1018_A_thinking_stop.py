"""Sweep A (2026-10-18): F578 thinking on Haiku 5.5, then Stop mid-turn and read what the crash
path records for cost (F678 says those rows are not differenced).

    py -3.11 scripts/drive/s1018_A_thinking_stop.py <agent>
"""

import json
import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1018_A_lib import P, e2e, q, req  # noqa: E402

agent = sys.argv[1]
r1 = e2e.cmd_turn(P, agent, "Think step by step: is 391 prime? Answer yes or no with the factor.",
                  fresh=True, perm="workspace")
print("r1", e2e.wait_for(r1, 6))
e2e.dump_turn(r1)
r2 = e2e.cmd_turn(P, agent, "Run exactly this with the Bash tool and wait for it: "
                  "py -3.11 -c \"import time; time.sleep(120)\" ; then reply DONE.", perm="workspace")
deadline = time.time() + 120
while time.time() < deadline:
    rows = q("select kind, content from agent_outputs where run_id=? and kind='tool_use'", r2)
    if rows:
        break
    time.sleep(3)
print("tool calls before stop:", rows)
time.sleep(5)
print("stop:", req("POST", f"/projects/{P}/agent/{agent}/stop", {}))
print("r2", e2e.wait_for(r2, 3))
e2e.dump_turn(r2)
r3 = e2e.cmd_turn(P, agent, "Reply with the word AFTER.", perm="workspace")
print("r3", e2e.wait_for(r3, 5))
for rid in (r1, r2, r3):
    print(json.dumps(q(
        "select r.id, r.status, r.error, r.session_id, u.status ustatus, u.api_equivalent_usd_micros cost, "
        "u.input_tokens, u.output_tokens, u.session_totals from runs r left join turn_usage u "
        "on u.run_id=r.id where r.id=?", rid), default=str))
