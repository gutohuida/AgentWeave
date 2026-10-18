"""Sweep A (2026-10-18): F678 over three turns of one conversation plus a fresh conversation's
first turn (Haiku 4.5), then the per-project and per-conversation accounting read back.

    py -3.11 scripts/drive/s1018_A_cost.py <agent>
"""

import json
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1018_A_lib import P, e2e, q, req  # noqa: E402

agent = sys.argv[1]
msgs = [
    "List the AgentWeave tools you can call (names only, one line), then say ONE.",
    "Use the Agent tool once (description 'count files') to have a subagent count the .py files "
    "in this workspace with Glob, then reply with the number.",
    "Reply with the word THREE.",
]
runs = []
for i, m in enumerate(msgs):
    rid = e2e.cmd_turn(P, agent, m, fresh=(i == 0), perm="workspace")
    print("status", e2e.wait_for(rid, 6))
    runs.append(rid)
fresh = e2e.cmd_turn(P, agent, "Reply with the word FRESH.", fresh=True, perm="workspace")
print("status", e2e.wait_for(fresh, 6))
rows = []
for rid in runs + [fresh]:
    r = q(
        "select r.id, r.status, r.session_id, r.runner_version, r.conversation_id, "
        "u.api_equivalent_usd_micros cost, u.input_tokens, u.output_tokens, u.cache_read_tokens, "
        "u.cache_write_tokens, u.session_totals from runs r left join turn_usage u on u.run_id=r.id "
        "where r.id=?", rid)
    rows.append(r[0] if r else {"id": rid})
for r in rows:
    print(json.dumps(r, default=str))
conv = rows[0].get("conversation_id")
s, acc = req("GET", f"/projects/{P}/accounting/conversations/{conv}")
print("conversation accounting", s, json.dumps(acc)[:1500])
s, acc = req("GET", f"/projects/{P}/accounting")
print("project accounting", s, json.dumps(acc)[:1500])
for rid in runs[:1]:
    e2e.dump_turn(rid)
e2e.dump_turn(runs[1])
