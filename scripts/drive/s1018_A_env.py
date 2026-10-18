"""Sweep A (2026-10-18): Agent environment.

E1 (Workspace only): what the run sees -- CLAUDE_CODE_DISABLE_BACKGROUND_TASKS (F677), the
    operator's skills (F454), the first turn's tool context.
E2: the agent's own env_vars override F677's default; call mode (`hub_client: cli`) with a stale
    `.agentweave/calls/1.json` planted in its workspace first (F663/F664: emptied at turn start?).
E3 ("Edit files", F628): a shell command goes to the operator as a card; the drive allows it.

    py -3.11 scripts/drive/s1018_A_env.py <agent> <project-dir>
"""

import json
import pathlib
import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1018_A_lib import P, e2e, q, req  # noqa: E402

agent, pdir = sys.argv[1], pathlib.Path(sys.argv[2])
r1 = e2e.cmd_turn(P, agent, (
    "Run exactly this with the Bash tool: echo BG=$CLAUDE_CODE_DISABLE_BACKGROUND_TASKS PWD=$PWD . "
    "Then, without calling any tool, answer: (a) list the names of every skill the Skill tool offers "
    "you; (b) do you have AgentWeave tools, and how do you call them (MCP or aw-tool)? "
    "Reply with the echo output and the two answers."), perm="workspace", fresh=True)
print("r1", e2e.wait_for(r1, 5))
e2e.dump_turn(r1)

ws = pdir / ".agentweave" / "worktrees" / agent
calls = ws / ".agentweave" / "calls"
print("workspace exists:", ws.is_dir())
s, res = req("PATCH", f"/projects/{P}/agents/{agent}", {"config": {"hub_client": "cli", "env_vars": {"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "0"}}})
print("patch config:", s, json.dumps(res.get("config") if isinstance(res, dict) else res))
calls.mkdir(parents=True, exist_ok=True)
(calls / "1.json").write_text('{"stale": true}', encoding="utf-8")
print("planted:", sorted(p.name for p in calls.iterdir()))
r2 = e2e.cmd_turn(P, agent, (
    "Run exactly this with the Bash tool: echo BG=$CLAUDE_CODE_DISABLE_BACKGROUND_TASKS . Then "
    "call the AgentWeave tool list_tasks once and reply with the echo output and how many tasks it "
    "returned."), perm="workspace")
time.sleep(4)
print("calls dir right after start:", sorted(p.name for p in calls.iterdir()) if calls.is_dir() else "absent")
print("r2", e2e.wait_for(r2, 5))
e2e.dump_turn(r2)
print("calls dir after:", sorted(p.name for p in calls.iterdir()) if calls.is_dir() else "absent")
print("mcp status:", q("select id, harness_mcp_status from runs where id in (?,?)", r1, r2) if q("select 1 from pragma_table_info('runs') where name='harness_mcp_status'") else "no column")
req("PATCH", f"/projects/{P}/agents/{agent}", {"config": {"hub_client": None, "env_vars": {}}})
print("config now:", q("select config from agents where project_id=? and name=?", P, agent))

r3 = e2e.cmd_turn(P, agent, (
    "Run exactly this with the Bash tool: py -3.11 -c \"print(6*7)\" and reply with its output."),
    perm="acceptEdits", fresh=True)
deadline = time.time() + 180
asked = []
while time.time() < deadline:
    st = q("select status from runs where id=?", r3)[0]["status"]
    if st not in ("running", "queued", "starting", "pending"):
        break
    s, rows = req("GET", f"/projects/{P}/permission-requests")
    for r in rows if isinstance(rows, list) else []:
        if r.get("run_id") == r3 and r["status"] == "pending":
            asked.append((r["tool_name"], r.get("tool_input"), r.get("workspace_verdict")))
            req("POST", f"/projects/{P}/permission-requests/{r['id']}/decide", {"allow": True})
    time.sleep(2)
print("Edit files asked the operator:", asked)
print("r3", e2e.wait_for(r3, 3))
e2e.dump_turn(r3)
print("agents listing pill:", [(a["name"], a.get("permission_mode_at_rest")) for a in req("GET", f"/projects/{P}/agents")[1] if a["name"] == agent])
