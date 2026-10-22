"""Agents x Charters x Inbound queue sweep 2026-10-22, API phases (scratch Hub :8116, ag1022).

setup   -- alpha (Developer), beta, gamma on the haiku runner
turn    -- gamma one-word turn (leaves a conversation with a provider session)
job     -- a disabled job naming gamma, then a sync that deletes gamma: what becomes of the job
charter -- charter route refusals and read-backs (blank, whitespace, 257 chars, unknown, bound delete)

py -3.11 scripts/drive/s1022_ag_api.py <phase>
"""

import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1022_ag_lib import HAIKU, P, q, req, show  # noqa: E402

B = f"projects/{P}"
LIVE = ("running", "queued", "starting", "pending")


def runner_id():
    return next(r["id"] for r in req("GET", f"{B}/runners")[1] if r.get("model") == HAIKU)


def charter(name):
    return next(c["id"] for c in req("GET", f"{B}/charters")[1] if c["name"] == name)


def wait_run(run_id, limit=180):
    for _ in range(limit // 2):
        row = q("select status from runs where id=?", run_id)
        if row and row[0]["status"] not in LIVE:
            return row[0]["status"]
        time.sleep(2)
    return "timeout"


def setup():
    rid = runner_id()
    show("POST", f"{B}/agents", {"name": "alpha", "runner_id": rid, "charter_id": charter("Developer")}, 400)
    show("POST", f"{B}/agents", {"name": "beta", "runner_id": rid}, 400)
    show("POST", f"{B}/agents", {"name": "gamma", "runner_id": rid}, 400)


def turn():
    status, run = show("POST", f"{B}/agent/trigger", {"agent": "gamma", "message": "Reply with the single word PONG and nothing else."}, 600)
    print("gamma run:", wait_run(run.get("run_id")), run.get("conversation_id"))


def job():
    show("POST", f"{B}/jobs", {"name": "gamma nightly", "agent": "gamma", "message": "Say hi.", "cron": "0 3 * * *", "enabled": False}, 1200)
    status, res = show("POST", f"{B}/session/sync", {"data": {"agents": {"alpha": {}, "beta": {}}}}, 1500)
    print("jobs after:", q("select id, name, agent, enabled, archived_at from jobs where project_id=?", P))
    print("conversations:", q("select id, agent, lifecycle from conversations where project_id=?", P))
    print("agents:", q("select name, runner_id, charter_id from agents where project_id=?", P))


def charter_probes():
    for body in ({"name": "", "content": "x"}, {"name": "   ", "content": "x"}, {"name": "n" * 257, "content": "x"},
                 {"name": "ok"}, {"name": "ok", "content": "x", "extra": 1}):
        show("POST", f"{B}/charters", body, 500)
    show("PATCH", f"{B}/charters/charter-nope", {"content": "x"}, 300)
    show("PATCH", f"{B}/charters/{charter('Developer')}", {"name": "  "}, 500)
    show("DELETE", f"{B}/charters/{charter('Developer')}", None, 500)


def chain():
    show("PUT", f"{B}/settings", {"hop_budget": 1}, 400)
    status, run = show("POST", f"{B}/agent/trigger", {"agent": "alpha", "message": (
        "Send beta one message with your send_message tool: 'Please reply to alpha with the single word PONG, "
        "using send_message.' Then end your turn; do nothing else.")}, 600)
    print("alpha:", wait_run(run.get("run_id")))
    for _ in range(60):
        rows = q("select id, agent, state, hop_depth, waiting_reason, delivered_in_run_id, conversation_id from inbound_queue_entries where project_id=? and agent in ('alpha','beta') order by sequence", P)
        if any(r["agent"] == "alpha" and r["hop_depth"] >= 2 for r in rows) and not q("select id from runs where project_id=? and status in ('running','queued','starting','pending')", P):
            break
        time.sleep(3)
    for r in rows:
        print(r)
    print("messages:", q("select * from messages where project_id=? order by rowid", P))


{"chain": chain, "setup": setup, "turn": turn, "job": job, "charter": charter_probes}[sys.argv[1]]()
