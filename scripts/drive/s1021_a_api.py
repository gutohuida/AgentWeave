"""Agents sweep, 2026-10-21: F811 (case twins refused at creation) and F812 (session/sync shape,
`removed`, the agent_removed event, the config lock's sentence), by the operator routes and the
sync route (reached only by direct API calls).

    py -3.11 scripts/drive/s1021_a_api.py setup|f811|f812|history
"""

import json
import sys

from s1021_a_lib import HAIKU, P, e2e, q, req, show

A = f"projects/{P}"


def roster():
    return {
        r["name"]: r["lifecycle"]
        for r in q("select name, lifecycle from agents where project_id=? order by name", P)
    }


def sync(data, label):
    status, res = req("POST", f"{A}/session/sync", {"data": data})
    print(f"\n## {label}\nPOST /session/sync {json.dumps(data)[:160]} -> {status}")
    print(json.dumps(res, ensure_ascii=False)[:900])
    print("roster now:", roster())
    return status, res


def stored():
    status, res = req("GET", f"{A}/session/sync")
    print("GET /session/sync ->", status, json.dumps(res, ensure_ascii=False)[:400])
    return res


def runner_id():
    return next(r["id"] for r in req("GET", f"{A}/runners")[1] if r.get("model") == HAIKU)


def setup():
    e2e.cmd_agent(P, "alpha", "Developer", "claude", HAIKU)
    e2e.cmd_agent(P, "beta", "Code Reviewer", "claude", HAIKU)
    e2e.cmd_agent(P, "eps", "-", "claude", HAIKU)
    print(roster())


def f811():
    rid = runner_id()
    for name in ("EPS", "Alpha", "bEtA"):
        show("POST", f"{A}/agents", {"name": name, "runner_id": rid}, limit=600)
    show("POST", f"{A}/agents/eps/archive", {}, limit=300)
    for name in ("Eps", "eps"):
        show("POST", f"{A}/agents", {"name": name, "runner_id": rid}, limit=600)
    names = {n: {} for n in roster()}
    sync({"agents": {**names, "Beta": {}}}, "sync adds Beta beside beta")
    stored()
    sync({"agents": {**names, "zeta": {}, "ZETA": {}}}, "sync adds zeta and ZETA together")
    stored()
    sync({"agents": {**names, "zeta": {}}}, "sync adds zeta alone")
    show("POST", f"{A}/agents", {"name": "Zeta", "runner_id": rid}, limit=600)
    print(roster())


def f812():
    names = {n: {} for n in roster()}
    for bad, label in ((["alpha"], "list"), ("alpha", "string"), (3, "int"), (True, "bool")):
        sync({"agents": bad}, f"agents as a {label}")
    stored()
    sync({}, "no agents key")
    # a refused payload must not replace the stored row
    sync({"agents": {**names, "bad name!": {}}}, "an invalid name (refused)")
    stored()
    show("PATCH", f"{A}/agents/beta", {"config": {"read_only": True}}, limit=600)
    sync({}, "release with {} (no agents key)")
    stored()
    show("PATCH", f"{A}/agents/beta", {"config": {"read_only": True}}, limit=600)
    show("GET", f"{A}/agents/beta", limit=600)
    show("PATCH", f"{A}/agents/beta", {"config": {"read_only": False}}, limit=300)
    # zeta (added by the sync, no runner, no history) removed by omission
    keep = {n: {} for n in roster() if n != "zeta"}
    sync({"agents": keep}, "omit zeta")
    stored()
    print(
        "events:",
        q(
            "select event_type, severity, agent, data from event_logs where project_id=? and "
            "event_type in ('session_synced','agent_removed','worktree_released') order by id",
            P,
        ),
    )
    show("GET", f"{A}/events/history?limit=5", limit=1500)


def history():
    """gamma with a finished turn and an archived conversation, removed by a sync, then re-created."""
    phase = sys.argv[2]
    if phase == "turn":
        e2e.cmd_agent(P, "gamma", "-", "claude", HAIKU)
        show(
            "POST",
            f"{A}/agent/trigger",
            {"agent": "gamma", "message": "Reply with the single word PONG and nothing else."},
            limit=600,
        )
    elif phase == "remove":
        print(
            "gamma convs:",
            q("select id, lifecycle from conversations where project_id=? and agent='gamma'", P),
        )
        print(
            "gamma runs:",
            q("select id, status from runs where project_id=? and agent='gamma'", P),
        )
        keep = {n: {} for n in roster() if n != "gamma"}
        sync({"agents": keep}, "omit gamma (one finished turn)")
        print(
            "gamma convs after:",
            q("select id, lifecycle from conversations where project_id=? and agent='gamma'", P),
        )
        show("GET", f"{A}/agents/gamma/chat", limit=600)
        show("GET", f"{A}/conversations?agent=gamma", limit=900)
    elif phase == "recreate":
        rid = runner_id()
        show("POST", f"{A}/agents", {"name": "gamma", "runner_id": rid}, limit=600)
        show("GET", f"{A}/agents/gamma/chat", limit=1200)


if __name__ == "__main__":
    {"setup": setup, "f811": f811, "f812": f812, "history": history}[sys.argv[1]]()
