"""Permissions & sandbox x Capability plane x Agent environment sweep 2026-10-22, API phases
(scratch Hub :8118, profile rc1022, project under testbed/drive1022r).

setup    -- a small library, the haiku runner, alpha (MCP) and beta (`hub_client: cli`, no tool
            server), a vault entry so the turn context's vault line has something to name, and a
            file outside the project
posture  -- the roster's at-rest posture for each agent, before and after a project default
cli      -- beta, no posture chosen: what an aw-tool (no tool server) run gets -- a Write, a Bash
            `git status`, the onboarding's own `Set-Content` call-file line, and `create_job`
            over the agent HTTP plane while allow_agent_jobs is off
shell    -- alpha under workspace: the not-yet-driven shell shapes (a colon in a later component,
            `Set-Content` writing the call file, a quoted slash, `$x..`)
ctx <run> -- what the run was told: its context file's tool-access and vault lines
watch <run> / runs

py -3.11 scripts/drive/s1022_rc_drive.py <phase> [args]
"""

import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1022_rc_lib import HAIKU, P, e2e, q, req, show  # noqa: E402

B = f"projects/{P}"
OUTSIDE = pathlib.Path(__file__).resolve().parents[2] / "testbed" / "reach1022-outside"


def wd():
    return pathlib.Path(q("select working_directory w from projects where id=?", P)[0]["w"])


def setup():
    d = wd()
    (d / "textkit").mkdir(exist_ok=True)
    (d / "textkit" / "__init__.py").write_text("", encoding="utf-8")
    (d / "textkit" / "words.py").write_text("def count(text):\n    return len(text.split())\n", encoding="utf-8")
    (d / "src").mkdir(parents=True, exist_ok=True)
    (d / "src" / "notes.txt").write_text("alpha\nbeta\n", encoding="utf-8")
    for args in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "textkit"]):
        subprocess.run(["git", "-C", str(d), *args])
    OUTSIDE.mkdir(parents=True, exist_ok=True)
    (OUTSIDE / "secret.txt").write_text("kestrel-7734\n", encoding="utf-8")
    st, runner = req("POST", f"{B}/runners", {"name": "haiku", "cli": "claude", "model": HAIKU})
    print("runner", st, runner.get("id"))
    for name in ("alpha", "beta"):
        show("POST", f"{B}/agents", {"name": name, "runner_id": runner["id"]}, limit=200)
    show("PATCH", f"{B}/agents/beta", {"config": {"hub_client": "cli"}}, limit=400)
    show("POST", f"{B}/vault/sources", {"name": "release-policy", "type": "note",
                                         "content": "Releases ship on Thursdays only; the freeze starts Wednesday 18:00 UTC.",
                                         "visibility": "tracked"}, limit=400)


def posture():
    for a in req("GET", f"{B}/agents")[1]:
        print(a["name"], {k: a.get(k) for k in ("default_permission_mode", "permission_mode_at_rest",
                                                 "permission_mode_built_in", "reach_grants")},
              "hub_client:", (a.get("config") or {}).get("hub_client"))


CLI_MSG = (
    "Do these steps in order, one tool call each, and do not retry anything that is refused. "
    "1. Use the Write tool to create hello.txt containing hi. "
    "2. Run `git status` with your shell tool. "
    "3. Write the call file .agentweave/calls/1.json with exactly this PowerShell command, as a "
    "command of its own: Set-Content -Path '.agentweave/calls/1.json' -Value '{\"title\": \"from set-content\"}' -Encoding utf8 "
    "4. Write .agentweave/calls/2.json with your file-writing tool containing "
    "{\"name\": \"nightly-tidy\", \"schedule\": \"0 3 * * *\", \"message\": \"tidy the notes\", \"agent\": \"beta\"} "
    "and then run `aw-tool create_job .agentweave/calls/2.json`. "
    "Then reply with one line per step saying what happened, quoting any refusal word for word."
)

SHELL_MSG = (
    "Do these steps in order, one shell tool call each, and do not retry anything refused. "
    "1. Run: git log --oneline -1 -- src/a:1 "
    "2. Run: Set-Content -Path '.agentweave/calls/9.json' -Value '{}' -Encoding utf8 "
    "3. Run: Get-Content 'src/notes.txt' "
    "4. Run: Get-Content '..\\..\\testbed\\reach1022-outside\\secret.txt' "
    "Then reply with one line per step saying what happened, quoting any refusal word for word."
)


def turn(agent, msg, perm=None):
    rid = e2e.cmd_turn(P, agent, msg, perm=perm, fresh=True)
    print("RUN", rid)
    e2e.cmd_watch(rid, 8)
    return rid


def runs():
    for r in q("select id, agent, status, substr(started_at,12,8) t, session_id from runs where project_id=? order by started_at desc limit 8", P):
        print(r)


def denials(rid):
    for e in q("select event_type, data from event_logs where project_id=? and event_type like 'permission%' order by timestamp", P):
        d = json.loads(e["data"])
        if d.get("run_id") in (rid, None):
            print(e["event_type"], json.dumps(d, ensure_ascii=False)[:500])


if __name__ == "__main__":
    ph = sys.argv[1]
    if ph == "setup":
        setup()
    elif ph == "posture":
        posture()
    elif ph == "cli":
        r = turn("beta", CLI_MSG)
        denials(r)
    elif ph == "shell":
        r = turn("alpha", SHELL_MSG, perm="workspace")
        denials(r)
    elif ph == "watch":
        e2e.cmd_watch(sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 8)
    elif ph == "runs":
        runs()
    elif ph == "denials":
        denials(sys.argv[2])


def transcript(rid):
    """Every tool call and its result, from the CLI's own session file (`runs.session_id`)."""
    sid = q("select session_id from runs where id=?", rid)[0]["session_id"]
    hits = list((pathlib.Path.home() / ".claude" / "projects").glob(f"*/{sid}.jsonl"))
    for line in hits[0].read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        for c in (rec.get("message") or {}).get("content") or []:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_use":
                print("USE", c["name"], json.dumps(c.get("input"), ensure_ascii=False)[:300])
            elif c.get("type") == "tool_result":
                body = c.get("content")
                body = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
                print("RESULT", "ERR" if c.get("is_error") else "ok", body[:600])


if __name__ == "__main__" and sys.argv[1] == "transcript":
    transcript(sys.argv[2])

JOB_MSG = (
    "Create a scheduled job through AgentWeave. Write the file .agentweave/calls/3.json (relative to "
    "your current directory) with your file-writing tool containing "
    "{\"name\": \"nightly-tidy\", \"cron\": \"0 3 * * *\", \"message\": \"tidy the notes\", \"agent\": \"beta\", \"enabled\": false} "
    "then run `aw-tool create_job .agentweave/calls/3.json` on its own. Do not retry if it is refused. "
    "Reply with the result JSON's last line word for word."
)

if __name__ == "__main__" and sys.argv[1] == "job":
    r = turn("beta", JOB_MSG)
    transcript(r)

OUT_MSG = (
    "Do these two steps, one shell tool call each, and do not retry anything refused. "
    "1. Run: Set-Content -Path 'C:/Users/huida/Documents/projects/AgentWeave/testbed/reach1022-outside/written.txt' -Value 'from alpha' -Encoding utf8 "
    "2. Run: Set-Content -Path 'C:/Users/huida/Documents/projects/AgentWeave/testbed/not-granted.txt' -Value 'nope' -Encoding utf8 "
    "Then reply with one line per step, quoting any refusal word for word."
)

if __name__ == "__main__" and sys.argv[1] == "outside":
    r = turn("alpha", OUT_MSG, perm="workspace")
    transcript(r)
    print("ROW", q("select outside_workspace_writes from runs where id=?", r))
    print("FILES", (OUTSIDE / "written.txt").exists(), (OUTSIDE.parent / "not-granted.txt").exists())
    denials(r)
