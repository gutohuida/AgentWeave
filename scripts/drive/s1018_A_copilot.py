"""Sweep A (2026-10-18): a Copilot agent on a provider runner aimed at s1018_A_copilot_stub.py
(no premium requests). Under "Workspace only" the stub asks for: a write of `.mcp.json` (F675),
`Get-Content x | Remove-Item` (F676), an ordinary pipe, and an ordinary write. Checks the refusals
are recorded, legible, and do not end the turn (F660); also F662/F671 catalog/model reporting.

    py -3.11 scripts/drive/s1018_A_copilot.py <stub-port>
"""

import json
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1018_A_lib import P, e2e, q, req  # noqa: E402

port = sys.argv[1]
s, runner = req("PATCH", f"/projects/{P}/runners/runner-8aed42c53632", {
    "model": "claude-haiku-4-5-20251001",
    "provider_config": {"type": "anthropic", "base_url": f"http://127.0.0.1:{port}", "api_key_var": "PROCESSOR_ARCHITECTURE"}})
print("runner:", s, json.dumps(runner)[:400])
s, a = req("POST", f"/projects/{P}/agents", {"name": "cop2", "runner_id": runner["id"]})
print("agent:", s, a)
print("patch env:", req("PATCH", f"/projects/{P}/agents/cop2", {"config": {"env_vars": {"SWEEPA_STUB_KEY": "sk-stub-not-a-real-key-000000000000000"}}})[0])
print("launchability:", req("GET", f"/projects/{P}/agents/launchability")[1]["agents"].get("cop2"))
rid = e2e.cmd_turn(P, "cop2", "Do the scripted steps.", perm="workspace", fresh=True)
if not rid:
    sys.exit(1)
print("status", e2e.wait_for(rid, 6))
e2e.dump_turn(rid)
print("run:", q("select status, error, model, runner_version from runs where id=?", rid) if q("select 1 from pragma_table_info('runs') where name='model'") else q("select status, error, runner_version from runs where id=?", rid))
for r in q("select event_type, data from event_logs where project_id=? and data like ? order by timestamp", P, f"%{rid}%"):
    if r["event_type"] in ("permission_denied", "permission_decided", "copilot.refusal_continued",
                           "copilot.turn_ended_on_refusal", "run_completed", "copilot.model_substituted"):
        print(r["event_type"], r["data"][:500])
print("event types:", sorted({r["event_type"] for r in q("select event_type from event_logs where project_id=? and data like ?", P, f"%{rid}%")}))
