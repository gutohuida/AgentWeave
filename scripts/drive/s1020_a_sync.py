"""Agents sweep, 2026-10-20: POST /session/sync after F774, driven by direct API calls (the only
way it is reached). No real agent turns: the agents that would run are given no runner.

    py -3.11 scripts/drive/s1020_a_sync.py setup|probe
"""

import json
import sys

from s1020_a_lib import P, e2e, q, req, show

A = f"/projects/{P}"


def roster():
    return {
        r["name"]: (r["lifecycle"], r["runner_id"], r["charter_id"])
        for r in q(
            "select name, lifecycle, runner_id, charter_id from agents where project_id=?", P
        )
    }


def sync(data, label):
    status, res = req("POST", f"{A}/session/sync", {"data": data})
    print(f"\n## {label}\nPOST /session/sync {json.dumps(data)[:160]} -> {status}")
    print(json.dumps(res, ensure_ascii=False)[:900])
    print("roster now:", roster())
    return status, res


def setup():
    e2e.cmd_agent(P, "alpha", "Developer", "claude", "claude-haiku-4-5-20251001")
    e2e.cmd_agent(P, "beta", "Code Reviewer", "claude", "claude-haiku-4-5-20251001")
    # gamma and delta: runner unbound after creation (Add agent requires one), so an operator
    # message to them is held, never run.
    for name in ("gamma", "delta"):
        e2e.cmd_agent(P, name, "-", "claude", "claude-haiku-4-5-20251001")
        show("PATCH", f"{A}/agents/{name}", {"runner_id": None}, limit=200)
    show(
        "POST", f"{A}/tasks", {"title": "beta holds this", "assignee": "beta", "status": "assigned"}
    )
    show("POST", f"{A}/agent/trigger", {"agent": "delta", "message": "held for delta"})
    show("POST", f"{A}/agent/trigger", {"agent": "gamma", "message": "held for gamma"})
    print(roster())


def probe():
    before = roster()
    print("before:", before)
    sync({}, "no agents key")
    sync({"agents": ["alpha"]}, "agents as a list")
    sync({"agents": "alpha"}, "agents as a string")
    sync({"agents": None}, "agents null")
    names = {n: {} for n in before}
    sync({**{"agents": {**names, "Operator": {}}}}, "a reserved name added")
    sync({"agents": {**names, "settings": {}}}, "a route word added")
    sync({"agents": {**names, "bad name!": {}}}, "an invalid name")
    sync({"agents": {n: {} for n in before if n != "beta"}}, "omit beta (holds a task)")
    # gamma: archive it first (an archived agent with a conversation); delta keeps a held message.
    show("POST", f"{A}/agents/gamma/archive", {})
    print(
        "queue entries:",
        q("select id, agent, state from inbound_queue_entries where project_id=?", P),
    )
    sync({"agents": {"alpha": {}, "beta": {}}}, "omit gamma (archived) and delta (held message)")
    print(
        "queue entries after:",
        q("select id, agent, state from inbound_queue_entries where project_id=?", P),
    )
    print(
        "conversations:", q("select id, agent, lifecycle from conversations where project_id=?", P)
    )
    show("GET", f"{A}/queue/delta")
    show("GET", f"{A}/agents/gamma/chat")
    for c in q("select id from conversations where project_id=? and agent='gamma'", P):
        show("GET", f"{A}/agents/gamma/chat/{c['id']}", limit=800)
        show("POST", f"{A}/agents/gamma/unarchive", {})
    show("GET", f"{A}/session/sync", limit=600)
    print(
        "events:",
        q(
            "select event_type, data from event_logs where project_id=? and event_type in "
            "('session_synced','worktree_released','agent_removed') order by id",
            P,
        ),
    )


if __name__ == "__main__":
    {"setup": setup, "probe": probe}[sys.argv[1]]()
