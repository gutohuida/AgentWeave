"""2026-10-23 Permissions & sandbox x Capability plane x Agent environment sweep, API phases
(scratch Hub :8113, profile rc1023, project under testbed/drive1023r).

setup     -- a small library, a file outside the project, the haiku runner, alpha (MCP), beta
             (`hub_client: cli`, no tool server), and copr on a real Copilot runner (claude-haiku-4.5)
f933      -- the roster's at-rest posture for beta and alpha under each project default
judge     -- alpha under Workspace only: `$x..`, a brace pattern, a URL to an ungranted and a
             granted host, a schemeless address
copilot   -- copr under Workspace only with a host grant: granted host allowed, ungranted refused,
             a read root allowed, `..` refused
cfull     -- copr under Full access: an outside write allowed; then a spec turn under Full access
             whose edit must still be refused
jobs      -- alpha (MCP) `create_job` with allow_agent_jobs off -> question -> grant -> retry
transcript <run> / denials <run> / runs / ctx <agent>

    AW_P=proj-... py -3.11 scripts/drive/s1023_rc_drive.py <phase> [args]
"""

import json
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_rc_lib import B, HAIKU, P, e2e, q, req, show  # noqa: E402

OUTSIDE = pathlib.Path(__file__).resolve().parents[2] / "testbed" / "reach1023-outside"


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
    show("PATCH", f"{B}/agents/beta", {"config": {"hub_client": "cli"}}, limit=300)
    st, copr = req("POST", f"{B}/runners", {"name": "copilot-haiku", "cli": "copilot", "model": "claude-haiku-4.5"})
    print("copilot runner", st, copr if st >= 300 else copr.get("id"))
    if st < 300:
        show("POST", f"{B}/agents", {"name": "copr", "runner_id": copr["id"]}, limit=200)
    show("GET", f"{B}/agents/launchability", limit=1500)


def roster():
    for a in req("GET", f"{B}/agents")[1]:
        print(" ", a["name"], {k: a.get(k) for k in ("default_permission_mode", "permission_mode_at_rest",
                                                     "permission_mode_built_in")},
              "hub_client:", (a.get("config") or {}).get("hub_client"))


def f933():
    for mode in (None, "manual", "workspace", "acceptEdits"):
        st, res = req("PUT", f"{B}/settings", {"default_permission_mode": mode})
        print(f"project default {mode!r} -> {st}", "" if st < 300 else res)
        roster()
    req("PUT", f"{B}/settings", {"default_permission_mode": None})


def turn(agent, msg, perm=None, doc=None, minutes=8):
    rid = e2e.cmd_turn(P, agent, msg, perm=perm, fresh=True, doc=doc)
    print("RUN", rid)
    if rid:
        e2e.wait_for(rid, minutes)
        r = q("select status, error from runs where id=?", rid)
        print("STATUS", r[0]["status"] if r else None)
        out = q("select content from agent_outputs where run_id=? and kind='text' order by sequence desc limit 1", rid)
        print("REPLY", (out[0]["content"] if out else "")[:2500])
    return rid


def denials(rid):
    for e in q("select event_type, data from event_logs where project_id=? and (event_type like 'permission%' "
               "or event_type like '%outside%') order by timestamp", P):
        d = json.loads(e["data"])
        if d.get("run_id") in (rid, None):
            print(e["event_type"], json.dumps(d, ensure_ascii=False)[:600])


def transcript(rid):
    """Every tool call and its result, from the Claude CLI's own session file (`runs.session_id`)."""
    sid = q("select session_id from runs where id=?", rid)[0]["session_id"]
    hits = list((pathlib.Path.home() / ".claude" / "projects").glob(f"*/{sid}.jsonl"))
    if not hits:
        print("no Claude session file for", sid)
        return
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
                print("RESULT", "ERR" if c.get("is_error") else "ok", body[:500])


def outputs(rid, limit=60):
    for o in q("select kind, substr(content,1,400) c from agent_outputs where run_id=? order by sequence", rid)[:limit]:
        print(o["kind"], "|", o["c"].replace("\n", " "))


JUDGE_MSG = (
    "Do these steps in order, one shell tool call each, exactly as written, and do not retry anything "
    "refused. 1. Run: $x = 'src'; Get-Content \"$x..\\notes.txt\" "
    "2. Run: Get-ChildItem textkit/{words,__init__}.py "
    "3. Run: curl.exe -s -o NUL -w '%{http_code}' https://example.org/ "
    "4. Run: curl.exe -s -o NUL -w '%{http_code}' https://example.com/ "
    "5. Run: git ls-remote git@example.org:repo.git "
    "Then reply with one line per step saying whether it ran or was refused, quoting any refusal word for word."
)

COP_MSG = (
    "Do these steps in order, one shell command each, exactly as written, and do not retry anything "
    "refused. 1. Run: curl.exe -s -o NUL -w '%{http_code}' https://example.com/ "
    "2. Run: curl.exe -s -o NUL -w '%{http_code}' https://example.org/ "
    "3. Run: Get-Content '" + str(OUTSIDE / "secret.txt").replace("\\", "/") + "' "
    "4. Run: Get-Content '../../src/notes.txt' "
    "Then reply with one line per step saying whether it ran or was refused, quoting any refusal word for word."
)

FULL_MSG = (
    "Do these two steps, one shell command each, exactly as written, and do not retry anything refused. "
    "1. Run: Set-Content -Path '" + str(OUTSIDE / "full.txt").replace("\\", "/") + "' -Value 'from copr' "
    "2. Run: curl.exe -s -o NUL -w '%{http_code}' https://example.org/ "
    "Then reply with one line per step, quoting any refusal word for word."
)

SPEC_MSG = (
    "Before anything else, do exactly this one step and do not retry if refused: create the file "
    "notes/spec-full.txt containing the word draft, using your file-editing tool. Then reply in one "
    "line saying whether the write happened or was refused, quoting any refusal word for word."
)


def grants(hosts=(), roots=()):
    show("PUT", f"{B}/settings", {"reach_grants": {"hosts": list(hosts), "roots": list(roots)}}, limit=400)


if __name__ == "__main__":
    ph = sys.argv[1]
    if ph == "setup":
        setup()
    elif ph == "roster":
        roster()
    elif ph == "f933":
        f933()
    elif ph == "judge":
        grants(hosts=["example.com"])
        r = turn("alpha", JUDGE_MSG, perm="workspace")
        transcript(r)
        denials(r)
    elif ph == "copilot":
        grants(hosts=["example.com"], roots=[{"path": str(OUTSIDE), "access": "read"}])
        r = turn("copr", COP_MSG, perm="workspace")
        outputs(r)
        denials(r)
    elif ph == "cfull":
        grants()
        r = turn("copr", FULL_MSG, perm="bypassPermissions")
        outputs(r)
        print("FILE", (OUTSIDE / "full.txt").exists())
        denials(r)
    elif ph == "cspec":
        st, doc = req("POST", f"{B}/project/documents", {"title": "Notes format"})
        print("doc", st, doc.get("path") if isinstance(doc, dict) else doc)
        r = turn("copr", SPEC_MSG, perm="bypassPermissions", doc=doc["path"])
        outputs(r)
        print("FILE", [str(p) for p in wd().rglob("spec-full.txt")])
        denials(r)
    elif ph == "transcript":
        transcript(sys.argv[2])
    elif ph == "outputs":
        outputs(sys.argv[2], 200)
    elif ph == "denials":
        denials(sys.argv[2])
    elif ph == "runs":
        for r in q("select id, agent, status, substr(started_at,12,8) t, harness_mcp_status, outside_workspace_writes from runs "
                   "where project_id=? order by started_at desc limit 10", P):
            print(r)
    elif ph == "ctx":
        f = wd() / ".agentweave" / "context" / f"{sys.argv[2]}.md"
        print(f.read_text(encoding="utf-8") if f.exists() else f"no {f}")
    elif ph == "sleep":
        time.sleep(float(sys.argv[2]))

JOBS_MSG = (
    "Call the AgentWeave create_job tool exactly once with name 'nightly-tidy', agent 'alpha', "
    "cron '0 3 * * *', message 'tidy the notes', enabled false. Do not retry if it is refused, and "
    "do not call ask_user. Reply with what the tool returned, word for word."
)

if __name__ == "__main__" and sys.argv[1] == "jobs":
    show("PUT", f"{B}/settings", {"allow_agent_jobs": False}, limit=0)
    r = turn("alpha", JOBS_MSG, perm="workspace")
    transcript(r)
    for row in q("select id, answered, substr(question,1,700) qq, options, answer from questions "
                 "where project_id=? order by created_at desc limit 2", P):
        print("QUESTION", json.dumps(row, ensure_ascii=False))
elif __name__ == "__main__" and sys.argv[1] == "grant":
    show("PUT", f"{B}/settings", {"allow_agent_jobs": True}, limit=0)
    time.sleep(2)
    for row in q("select id, answered, answer from questions where project_id=? order by created_at desc limit 1", P):
        print("QUESTION", json.dumps(row, ensure_ascii=False))
    r = turn("alpha", JOBS_MSG, perm="workspace")
    transcript(r)
    st, jobs = req("GET", f"{B}/jobs?include_archived=true")
    for j in jobs:
        print("JOB", j["id"], j["name"], j.get("enabled"), j.get("archived_at"))
        if not j.get("archived_at"):
            req("POST", f"{B}/jobs/{j['id']}/archive")
    show("PUT", f"{B}/settings", {"allow_agent_jobs": False}, limit=0)

ENV_MSG = (
    "Using AgentWeave's tools the way your context file describes, do two things and do not retry "
    "anything refused: 1. read the project's knowledge vault map, and tell me the release day it "
    "states. 2. Send agent alpha the AgentWeave message 'ping from beta, reply not needed'. Reply "
    "with one line per step naming the exact command or tool you used."
)

if __name__ == "__main__" and sys.argv[1] == "env":
    r = turn("beta", ENV_MSG)
    transcript(r)
    f = wd() / ".agentweave" / "context" / "beta.md"
    for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        if "vault" in line.lower() or "send_message" in line or "SendMessage" in line:
            print(f"CTX {i}: {line[:400]}")
