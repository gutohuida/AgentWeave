"""Runners & models phase 3: a real Haiku turn through the alias-bound runner, a model change mid-run,
and the per-run door with an alias (two short turns, both Haiku).

    py -3.11 scripts/drive/s1023_rm_turn.py
"""

import json
import pathlib
import time

from s1023_rm_lib import B, PA, e2e, q, req, show

C = json.loads((pathlib.Path(__file__).resolve().parents[2] / "testbed/rm1023/created.json").read_text())
CH = C["claude-haiku-alias"]
MSG = "Reply with exactly the single word OK and nothing else. Do not call any tool."

s, t1 = show("turn1", "POST", f"{B()}/agent/trigger", {"agent": "a-run", "message": MSG})
run1 = t1.get("run_id")
conv = t1.get("conversation_id")
for _ in range(20):
    st = q("select status,pid from runs where id=?", run1)
    if st and st[0]["status"] == "running" and st[0]["pid"]:
        break
    time.sleep(0.5)
print("  run1 state before mid-run patch", q("select status,pid from runs where id=?", run1))
show("patch-model-midrun", "PATCH", f"{B()}/runners/{CH}", {"model": "claude-haiku-4-5-20251001"})
print("  run1 ended:", e2e.wait_for(run1, 5))
print("  run1 row", q("select status,error,exit_code,harness_mcp_status from runs where id=?", run1))
print("  turn_usage run1", q("select runner,model,status,input_tokens,output_tokens,api_equivalent_usd_micros from turn_usage where run_id=?", run1))
print("  conversation", q("select id,runtime_overrides from conversations where id=?", conv))
print("  run1 cmd log", q("select event_type,data from event_logs where project_id=? and data like ? order by id desc limit 3", PA, f"%{run1}%"))
show("runner-after", "GET", f"{B()}/runners/{CH}")

# Put the runner back on the alias and run the per-run door with an alias override.
show("patch-model-back", "PATCH", f"{B()}/runners/{CH}", {"model": "haiku"})
s, t2 = show("turn2-override-alias", "POST", f"{B()}/agent/trigger",
             {"agent": "a-run", "message": MSG, "conversation_id": conv, "overrides": {"model": "haiku"}})
run2 = t2.get("run_id")
print("  run2 ended:", e2e.wait_for(run2, 5) if run2 else None)
print("  turn_usage run2", q("select runner,model,status,input_tokens,output_tokens,api_equivalent_usd_micros from turn_usage where run_id=?", run2))
print("  conversation after", q("select id,runtime_overrides from conversations where id=?", conv))
s, chat = req("GET", f"{B()}/agent/a-run/chat/{conv}")
print("  chat keys", list(chat.keys()) if isinstance(chat, dict) else type(chat))
print(json.dumps(chat, ensure_ascii=False)[:2500])
json.dump({"run1": run1, "run2": run2, "conv": conv},
          open(pathlib.Path(__file__).resolve().parents[2] / "testbed/rm1023/turns.json", "w"))
