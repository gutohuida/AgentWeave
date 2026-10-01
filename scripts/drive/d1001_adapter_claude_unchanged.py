"""Drive `each-runner-cli-is-one-adapter` tasks 5.2/5.3: a Claude run is unchanged by the adapter.

Usage: AW_HUB=http://127.0.0.1:8010 AW_KEY=... AW_DB=<trial db> \
       py -3.11 scripts/drive/d1001_adapter_claude_unchanged.py <project-id> <step>

<step> is one of:
  default   5.2: a Haiku agent at the default posture sends a message and writes a file.
  askme     5.3a: the same agent at "Ask me" asks to write; this script allows the card.
  cli       5.3b: the same agent with `hub_client: "cli"`; records the notice and posture.

Each step prints the run's `run_started` payload, `mcp_adapter_online_at`, the agents list's
posture fields, the run's tool events and `outside_workspace_writes`. Real turns bind Haiku.
"""

import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, "scripts/drive")
sys.stdout.reconfigure(encoding="utf-8")
from aw import api  # noqa: E402

PID, STEP = sys.argv[1], sys.argv[2]
A = "/projects/%s" % PID
DB = "file:" + os.environ["AW_DB"].replace("\\", "/") + "?mode=ro"
NAME = "adapterdrive"
HAIKU = "claude-haiku-4-5-20251001"


def q(sql, *args):
    con = sqlite3.connect(DB, uri=True)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def ensure_agent():
    _, runners = api("GET", A + "/runners")
    runner = next(
        (r for r in runners if r.get("cli") == "claude" and r.get("model") == HAIKU and not r.get("flags")),
        None,
    )
    if runner is None:
        _, runner = api("POST", A + "/runners", {"name": "haiku (adapter drive)", "cli": "claude", "model": HAIKU})
    c, body = api("POST", A + "/agents", {"name": NAME, "runner_id": runner["id"]})
    print("agent", c, "exists" if c == 409 else str(body)[:120])


def agents_row():
    _, body = api("GET", A + "/agents")
    rows = body if isinstance(body, list) else body.get("agents", [])
    row = next(r for r in rows if r.get("name") == NAME)
    return {k: row.get(k) for k in ("runner", "display_model", "permission_mode_at_rest", "permission_mode_built_in", "default_permission_mode")}


def roster_sync(hub_client):
    """`/session/sync` replaces both the stored session data and the roster: any `Agent` row whose
    name is missing from `data.agents` is deleted. So the payload is the stored data as it is, every
    agent row named, and only this agent's entry changed. `GET /agents` is not the roster (it
    omits archived agents, which the sync would still delete), so both are read from the database."""
    (stored,) = q("select data from project_sessions where project_id=?", PID)[0]
    data = json.loads(stored) if isinstance(stored, str) else dict(stored or {})
    agents = dict(data.get("agents") or {})
    names = [r[0] for r in q("select name from agents where project_id=?", PID)]
    for name in names:
        agents.setdefault(name, {})
    agents[NAME] = {**agents.get(NAME, {}), "hub_client": hub_client}
    data["agents"] = agents
    c, resp = api("POST", A + "/session/sync", {"data": data})
    after = [r[0] for r in q("select name from agents where project_id=?", PID)]
    print("session/sync", c, "roster", len(names), "->", len(after), str(resp)[:200] if c >= 300 else "")
    assert c < 300, resp
    assert sorted(after) == sorted(names), "roster changed"
    (stored_after,) = q("select data from project_sessions where project_id=?", PID)[0]
    print("stored session agents:", json.loads(stored_after)["agents"])


def trigger(message):
    before = {r[0] for r in q("select id from runs where project_id=? and agent=?", PID, NAME)}
    c, body = api("POST", A + "/agent/trigger", {"agent": NAME, "message": message}, timeout=90)
    print("trigger", c, str(body)[:200])
    t0 = time.time()
    run_id = None
    while time.time() - t0 < 300:
        time.sleep(3)
        new = [r for r in q("select id, status from runs where project_id=? and agent=?", PID, NAME) if r[0] not in before]
        if new:
            run_id = new[0][0]
        if STEP == "askme" and run_id:
            allow_cards()
        if new and new[0][1] not in ("running", "starting", "queued", "pending"):
            break
    print("run", run_id, q("select status from runs where id=?", run_id), "%.0fs" % (time.time() - t0))
    return run_id


_allowed = set()


def allow_cards():
    _, cards = api("GET", A + "/permission-requests")
    for card in cards if isinstance(cards, list) else []:
        if card.get("agent") == NAME and card.get("status") == "pending" and card["id"] not in _allowed:
            print("ASK-ME CARD", json.dumps({k: card.get(k) for k in ("tool_name", "status", "workspace_verdict", "tool_input")}, ensure_ascii=False)[:400])
            c, _ = api("POST", A + "/permission-requests/%s/decide" % card["id"], {"allow": True})
            print("allowed", c)
            _allowed.add(card["id"])


def report(run_id):
    for (data,) in q("select data from event_logs where event_type='run_started' and data like ?", "%" + run_id + "%"):
        print("run_started:", data)
    cols = [r[1] for r in q("pragma table_info(runs)")]
    want = [c for c in ("mcp_adapter_online_at", "outside_workspace_writes", "workspace_dir", "exit_code") if c in cols]
    row = q("select %s from runs where id=?" % ", ".join(want), run_id)[0]
    for k, v in zip(want, row):
        print("run.%s:" % k, v)
    print("agents list:", agents_row())
    for kind, content, payload in q("select kind, content, payload from agent_outputs where run_id=? order by sequence, timestamp", run_id):
        if kind in ("tool_use", "tool_result", "tool", "permission", "notice") or (payload and "tool" in str(payload)[:200]):
            print("timeline[%s]:" % kind, str(content)[:240].replace("\n", " "))
    first = q("select content from agent_outputs where run_id=? order by sequence, timestamp limit 3", run_id)
    for (content,) in first:
        print("head:", str(content)[:300].replace("\n", " "))


ensure_agent()
if STEP == "default":
    api("PATCH", A + "/agents/" + NAME, {"default_permission_mode": None})
    print("agents list before:", agents_row())
    run = trigger(
        "Do exactly two things, then stop. 1) Use the AgentWeave send_message tool to send the "
        "message 'adapter drive ok' to the agent named user. 2) Create a file named "
        "adapter-drive.txt in your current working directory containing the single line 'ok'. "
        "Do not do anything else."
    )
elif STEP == "askme":
    print("posture", api("PATCH", A + "/agents/" + NAME, {"default_permission_mode": "manual"})[0])
    print("agents list before:", agents_row())
    run = trigger(
        "Create a file named adapter-askme.txt in your current working directory containing the "
        "single line 'ok'. Do nothing else."
    )
elif STEP == "cli":
    api("PATCH", A + "/agents/" + NAME, {"default_permission_mode": None})
    roster_sync("cli")
    print("agents list before:", agents_row())
    run = trigger("Reply with the single word ok. Do not use any tool.")
else:
    raise SystemExit("unknown step " + STEP)
report(run)
