"""Sweep D: a Copilot runner on the zero-spend stub provider (port 18034), one turn, then accounting."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from s1018_D_common import mine, save, say, sc  # noqa: E402
m = mine(); b = m["base"]
code, r = sc.api("POST", f"{b}/runners", {"name": "CopilotStub", "cli": "copilot", "model": "claude-haiku-4-5-20251001",
    "provider_config": {"type": "anthropic", "base_url": "http://127.0.0.1:18034", "api_key_var": "MY_F490_KEY"}})
say("runner", (code, r.get("id") if isinstance(r, dict) else r))
code, a = sc.api("POST", f"{b}/agents", {"name": "gamma", "runner_id": r["id"]})
say("agent", (code, str(a)[:200]))
save({"copilot_runner": r["id"]})
code, t = sc.api("POST", f"{b}/agent/trigger", {"agent": "gamma", "message": "Say done.", "overrides": {"permission_mode": "bypassPermissions"}})
say("trigger", (code, t))
rid = t.get("run_id")
sc.poll(lambda: sc.ro("select status from runs where id=?", (rid,))[0][0] not in ("running", "queued", "starting", "pending"), 240, 3)
say("run", sc.ro("select status, exit_code from runs where id=?", (rid,)))
say("outputs", sc.ro("select kind, substr(content,1,200) from agent_outputs where run_id=? order by timestamp", (rid,)))
say("turn_usage", sc.ro("select status, runner, total_tokens, api_equivalent_usd_micros, ai_nano_aiu, premium_requests, session_totals from turn_usage where run_id=?", (rid,)))
d = sc.api("GET", f"{b}/accounting")[1]
say("acct project", d["project"]); say("agents", [(x["agent"], x["measured_turns"], x["unavailable_turns"], x.get("premium_requests"), x.get("ai_nano_aiu")) for x in d["agents"]])
say("preferred", d["preferred_display"])
