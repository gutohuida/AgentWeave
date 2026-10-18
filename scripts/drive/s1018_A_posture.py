"""Sweep A (2026-10-18): Workspace-only posture on a real Claude turn (Haiku 4.5) -- ordinary
pipes that must run (F676 false positives?), the default refusals, a URL; then "Edit files" with
two writes outside the workspace: the first denied on its card, the second allowed (F614: only the
written one is recorded).

    py -3.11 scripts/drive/s1018_A_posture.py <agent> <project-dir>
"""

import json
import pathlib
import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1018_A_lib import P, e2e, q, req  # noqa: E402

agent, pdir = sys.argv[1], pathlib.Path(sys.argv[2])
ws = pdir / ".agentweave" / "worktrees" / agent
cmds = [
    "git log --oneline | head -3",
    "cat README.md | while read l; do echo \"$l\"; done",
    "git status --short | sed 's/^/  /'",
    "find . -name '*.py' | xargs grep -n def",
    "cp README.md ..",
    "ls ~",
    "curl -s http://127.0.0.1:8031/health",
]
msg = ("This is a test of the Hub's permission checks. Run each of these commands with the Bash "
       "tool, one call per command, exactly as written, in order; do not retry or rewrite a refused "
       "one:\n" + "\n".join(f"{i + 1}. {c}" for i, c in enumerate(cmds)) +
       "\nThen reply with one line per command: allowed or refused, and the refusal reason if any.")
r1 = e2e.cmd_turn(P, agent, msg, perm="workspace", fresh=True)
print("r1", e2e.wait_for(r1, 6))
e2e.dump_turn(r1, tools=False)
for r in q("select data from event_logs where project_id=? and event_type='permission_denied' and data like ?", P, f"%{r1}%"):
    d = json.loads(r["data"])
    print("DENIED:", d.get("agent"), "|", d.get("reason")[:260])
print("README copied outside?", (ws.parent / "README.md").exists())

for f in ("f614-denied.txt", "f614-allowed.txt"):
    if (ws.parent / f).exists():
        (ws.parent / f).unlink()
r2 = e2e.cmd_turn(P, agent, "Use the Write tool to create ../f614-denied.txt containing a, then use the Write "
                  "tool to create ../f614-allowed.txt containing b. Do not retry a refused write. Reply "
                  "with what happened to each.", perm="acceptEdits")
deadline = time.time() + 240
done = set()
while time.time() < deadline:
    if q("select status from runs where id=?", r2)[0]["status"] not in ("running", "queued", "starting", "pending"):
        break
    s, rows = req("GET", f"/projects/{P}/permission-requests")
    for r in rows if isinstance(rows, list) else []:
        if r.get("run_id") == r2 and r["status"] == "pending" and r["id"] not in done:
            target = json.dumps(r.get("tool_input"))
            allow = "f614-allowed" in target
            print("card:", r["tool_name"], target[:140], "verdict:", r.get("workspace_verdict"), "->", "allow" if allow else "deny")
            req("POST", f"/projects/{P}/permission-requests/{r['id']}/decide", {"allow": allow})
            done.add(r["id"])
    time.sleep(2)
print("r2", e2e.wait_for(r2, 3))
e2e.dump_turn(r2, tools=False)
print("files:", {f: (ws.parent / f).exists() for f in ("f614-denied.txt", "f614-allowed.txt")})
print("run outside writes:", q("select outside_workspace_writes from runs where id=?", r2))
print("events:", [r["data"][:300] for r in q("select data from event_logs where project_id=? and event_type='agent_wrote_outside_workspace' and data like ?", P, f"%{r2}%")])
for f in ("f614-denied.txt", "f614-allowed.txt", "README.md"):
    if (ws.parent / f).exists():
        (ws.parent / f).unlink()
