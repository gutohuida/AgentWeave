"""Runners & models phase 5: a conversation's per-run model ("haiku", set on a Claude runner) after its agent
is rebound to a Copilot runner. Overrides are "trusted rather than re-validated per turn"
(agent_trigger.py:1189-1192), so does the next turn hand Copilot `--model haiku`?

    py -3.11 scripts/drive/s1023_rm_rebind.py
At most one Copilot turn (expected to fail at model selection) on a-run.
"""

import json
import pathlib

from s1023_rm_lib import B, PA, e2e, q, req, show

ROOT = pathlib.Path(__file__).resolve().parents[2]
T = json.loads((ROOT / "testbed/rm1023/turns.json").read_text())
C = json.loads((ROOT / "testbed/rm1023/created.json").read_text())
conv = T["conv"]
cop = [r for r in q("select id,model from runners where project_id=? and cli='copilot' and model='auto'", PA)][0]["id"]
print("copilot runner", cop, "| conversation overrides", q("select runtime_overrides from conversations where id=?", conv))

show("rebind-a-run-to-copilot", "PATCH", f"{B()}/agents/a-run", {"runner_id": cop})
# The composer re-sends what it shows; the stored model is exempt from the catalog check.
s, t = show("trigger-same-conv", "POST", f"{B()}/agent/trigger",
            {"agent": "a-run", "message": "Reply with exactly the single word OK.", "conversation_id": conv})
run = t.get("run_id") if isinstance(t, dict) else None
if run:
    print("  ended:", e2e.wait_for(run, 4))
    print("  run", q("select status,error,exit_code from runs where id=?", run))
    print("  started event", q("select data from event_logs where project_id=? and event_type='run_started' and data like ?", PA, f"%{run}%"))
    print("  usage", q("select runner,model,status,premium_requests,api_equivalent_usd_micros from turn_usage where run_id=?", run))
    s, chat = req("GET", f"{B()}/agent/a-run/chat/{conv}")
    for e in chat.get("entries", []):
        if e.get("run_id") == run:
            print("   ", e["kind"], (e.get("content") or "")[:600])
show("rebind-a-run-back", "PATCH", f"{B()}/agents/a-run", {"runner_id": C["claude-haiku-alias"]})
