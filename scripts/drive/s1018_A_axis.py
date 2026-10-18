"""Sweep A (2026-10-18), Step 6: one axis varied -- a project whose path has spaces and a
non-ASCII character (`~/Documents/aw sweepA ü 1018`). One Haiku 4.5 turn under Workspace only:
write a non-ASCII file name, read it back, a refused copy outside, an ordinary pipe; then the
cost row, the outside-write record and the timeline read back.

    py -3.11 scripts/drive/s1018_A_axis.py <project-id>
"""

import json
import os
import pathlib
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
os.environ["AW_P"] = sys.argv[1]
from s1018_A_lib import P, e2e, q, req  # noqa: E402

s, r = req("POST", f"/projects/{P}/runners", {"name": "h45", "cli": "claude", "model": "claude-haiku-4-5-20251001"})
print("runner", s)
print("agent", req("POST", f"/projects/{P}/agents", {"name": "uma", "runner_id": r["id"]}))
rid = e2e.cmd_turn(P, "uma", (
    "Do these in order, one tool call each, and do not retry a refused one: 1. Use the Write tool to "
    "create ünï café.txt containing olá. 2. Run with Bash: cat 'ünï café.txt' | wc -c 3. Run with "
    "Bash: cp 'ünï café.txt' .. 4. Run with Bash: git status --short. Then reply one line per step."),
    perm="workspace", fresh=True)
print("status", e2e.wait_for(rid, 6))
e2e.dump_turn(rid, tools=False)
for row in q("select data from event_logs where project_id=? and event_type='permission_denied' and data like ?", P, f"%{rid}%"):
    print("DENIED:", json.loads(row["data"])["reason"][:300])
ws = pathlib.Path(q("select working_directory from projects where id=?", P)[0]["working_directory"]) / ".agentweave" / "worktrees" / "uma"
print("workspace:", ws, "files:", sorted(p.name for p in ws.iterdir()) if ws.is_dir() else None)
print("copied outside?", (ws.parent / "ünï café.txt").exists())
print("usage:", q("select status, api_equivalent_usd_micros, input_tokens from turn_usage where run_id=?", rid))
print("run:", q("select status, runner_version, harness_mcp_status, outside_workspace_writes from runs where id=?", rid))
s, tl = req("GET", f"/projects/{P}/agents/uma/timeline")
print("timeline:", s, json.dumps(tl, ensure_ascii=False)[:600])
