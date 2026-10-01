"""Drive `a-run-reaches-the-hub-without-mcp` group 9 on a live Hub, one phase per invocation.

    setup  9.1   no model call: a throwaway project, the agents, the launchers, `aw-tool` by hand
    mcp    9.2   Copilot, MCP permitted: "Create an AgentWeave task titled S3-MCP, then stop."
    shim   9.3   Copilot, MCP blocked by `--disable-mcp-server agentweave`: S3-SHIM
    ask    9.4   the same under "Ask me": S3-ASK, and no card should open
    back   9.5/6 flag removed, second turn of 9.3's conversation: S3-BACK (MCP again, resumed)
    f340   9.7   Claude (Haiku) with `deniedMcpServers`: "Reply with the word ok." twice
    f301   9.8   Claude (Haiku) with `hub_client: "cli"`: S3-F301 through `aw-tool`
    spec   9.10  Copilot blocked, a specification document open: "Submit this document unchanged"

A throwaway project under `testbed/scratch/` (never this repository: an agent worktree inside it
loads the operator's own local-scope `agentweave` MCP server, DEAD-ENDS 2026-10-01). Copilot is on
the Free plan, so each prompt is one sentence and only the turns listed run. Needs AW_HUB, AW_KEY
and AW_DB (the Hub's SQLite file, read `mode=ro`). State is kept in
`testbed/scratch/shim-drive/state.json`.
"""

import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from aw import api, show  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
BASE = REPO / "testbed" / "scratch" / "shim-drive"
STATE = BASE / "state.json"
DB = os.environ["AW_DB"]
COP = "cop-s3"
F340 = "cl-f340"
F301 = "cl-f301"
HAIKU = "claude-haiku-4-5-20251001"
DISABLE = ["--disable-mcp-server", "agentweave"]
DENY = ["--settings", json.dumps({"deniedMcpServers": [{"serverName": "agentweave"}]})]


def load():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def save(state):
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def ro(query, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
    try:
        return con.execute(query, args).fetchall()
    finally:
        con.close()


def wait_idle(pid, agent, timeout=600):
    deadline = time.time() + timeout
    time.sleep(2)
    while time.time() < deadline:
        running = ro(
            "select id from runs where project_id=? and agent=? and status='running'", (pid, agent)
        )
        if not running:
            return
        time.sleep(3)
    raise SystemExit(f"{agent} still running after {timeout}s")


def last_run(pid, agent):
    cols = (
        "id",
        "status",
        "conversation_id",
        "harness_mcp_status",
        "plane_surface",
        "mcp_adapter_online_at",
        "started_at",
        "error",
    )
    rows = ro(
        f"select {', '.join(cols)} from runs where project_id=? and agent=? "
        "order by started_at desc limit 1",
        (pid, agent),
    )
    return dict(zip(cols, rows[0]))


def timeline(pid, run_id):
    rows = ro(
        "select kind, content, payload from agent_outputs where project_id=? and run_id=? "
        "order by sequence",
        (pid, run_id),
    )
    for kind, content, payload in rows:
        data = json.loads(payload) if payload else {}
        extra = ""
        if kind in ("tool_use", "tool_result"):
            extra = f" tool={data.get('tool')}"
        if kind in ("diagnostic", "error", "status"):
            extra = f" code={data.get('code') or data.get('phase')}"
        print(f"  [{kind}]{extra} {str(content)[:300]!r}")
    leaked = sum("aw_run_" in f"{c}{p}" for _, c, p in rows)
    print("  stored events holding aw_run_:", leaked)
    return rows


def report(pid, agent, title=None):
    run = last_run(pid, agent)
    print("run:", json.dumps(run, default=str))
    timeline(pid, run["id"])
    cards = ro(
        "select tool_name, status from permission_requests where project_id=? and run_id=?",
        (pid, run["id"]),
    )
    print("permission cards:", cards)
    if title:
        tasks = ro(
            "select id, title, created_by_run_id from tasks where project_id=? and title=?",
            (pid, title),
        )
        print("task:", tasks, "created by this run:", any(t[2] == run["id"] for t in tasks))
    root = pathlib.Path(load()["root"])
    calls = sorted(p.name for p in root.rglob(".agentweave/calls/*.json"))
    print("args files written:", calls)
    return run


def trigger(A, agent, body):
    code, resp = api("POST", f"{A}/agent/trigger", {"agent": agent, **body}, timeout=120)
    show("trigger", code, resp)
    return resp


def sync_hub_client(pid, agent, hub_client):
    """`/session/sync` replaces the roster: this project's every agent, only one entry changed."""
    (stored,) = ro("select data from project_sessions where project_id=?", (pid,)) or [("{}",)]
    data = json.loads(stored) if isinstance(stored, str) else dict(stored or {})
    agents = dict(data.get("agents") or {})
    for (name,) in ro("select name from agents where project_id=?", (pid,)):
        agents.setdefault(name, {})
    agents[agent] = {**agents.get(agent, {}), "hub_client": hub_client}
    data["agents"] = agents
    code, resp = api("POST", f"/projects/{pid}/session/sync", {"data": data})
    show("session/sync", code, resp)


def setup():
    BASE.mkdir(parents=True, exist_ok=True)
    root = BASE / time.strftime("proj-%H%M%S")
    root.mkdir()
    (root / "README.md").write_text("shim drive\n", encoding="utf-8")
    for cmd in (
        ["git", "init", "-b", "main"],
        ["git", "config", "user.email", "d@example.invalid"],
        ["git", "config", "user.name", "d"],
        ["git", "add", "README.md"],
        ["git", "commit", "-m", "x"],
    ):
        subprocess.run(cmd, cwd=root, check=True, capture_output=True)
    code, proj = api("POST", "/projects/open", {"path": str(root), "name": root.name})
    show("project", code, proj)
    pid = proj["id"]
    A = f"/projects/{pid}"
    _, cop_runner = api("POST", f"{A}/runners", {"name": "Copilot shim drive", "cli": "copilot"})
    _, deny_runner = api(
        "POST", f"{A}/runners", {"name": "Haiku denied MCP", "cli": "claude", "model": HAIKU, "flags": DENY}
    )
    _, haiku = api("POST", f"{A}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    for name, runner in ((COP, cop_runner), (F340, deny_runner), (F301, haiku)):
        code, agent = api("POST", f"{A}/agents", {"name": name, "runner_id": runner["id"]})
        show(f"agent {name}", code, agent)
    save({"pid": pid, "root": str(root), "cop_runner": cop_runner["id"]})
    sync_hub_client(pid, F301, "cli")

    from hub import tool_server  # the launchers this checkout's Hub writes

    launchers = tool_server.PIN.launcher_dir()
    print("launcher dir:", launchers, sorted(p.name for p in launchers.iterdir()))
    env = {k: v for k, v in os.environ.items() if not k.startswith("AW_")}
    env["PATH"] = str(launchers) + os.pathsep + env.get("PATH", "")
    for shell in (
        ["powershell", "-NoProfile", "-Command", "aw-tool --list"],
        ["powershell", "-NoProfile", "-Command", "aw-tool list_tasks"],
        ["bash", "-c", "aw-tool --list"],
        ["bash", "-c", "aw-tool list_tasks"],
    ):
        out = subprocess.run(shell, capture_output=True, text=True, env=env, cwd=root, timeout=60)
        last = (out.stdout.strip().splitlines() or [""])[-1]
        print(f"{' '.join(shell[:1] + shell[-1:])}: exit {out.returncode} -> {last[:160]}")


def mcp():
    s = load()
    A = f"/projects/{s['pid']}"
    trigger(A, COP, {"message": "Create an AgentWeave task titled S3-MCP, then stop."})
    wait_idle(s["pid"], COP)
    run = report(s["pid"], COP, "S3-MCP")
    print("announce after start:", run["started_at"], "->", run["mcp_adapter_online_at"])


def shim():
    s = load()
    A = f"/projects/{s['pid']}"
    show("runner flags", *api("PATCH", f"{A}/runners/{s['cop_runner']}", {"flags": DISABLE}))
    resp = trigger(A, COP, {"message": "Create an AgentWeave task titled S3-SHIM, then stop."})
    s["shim_conversation"] = resp.get("conversation_id")
    save(s)
    wait_idle(s["pid"], COP)
    report(s["pid"], COP, "S3-SHIM")


def ask():
    s = load()
    A = f"/projects/{s['pid']}"
    trigger(
        A,
        COP,
        {
            "message": "Create an AgentWeave task titled S3-ASK, then stop.",
            "overrides": {"permission_mode": "manual"},
        },
    )
    wait_idle(s["pid"], COP)
    report(s["pid"], COP, "S3-ASK")


def back():
    s = load()
    A = f"/projects/{s['pid']}"
    show("runner flags", *api("PATCH", f"{A}/runners/{s['cop_runner']}", {"flags": []}))
    trigger(
        A,
        COP,
        {"message": "Create a task titled S3-BACK.", "conversation_id": s["shim_conversation"]},
    )
    wait_idle(s["pid"], COP)
    report(s["pid"], COP, "S3-BACK")


def f340():
    s = load()
    A = f"/projects/{s['pid']}"
    for message in ("Reply with the word ok.", "Reply ok."):
        trigger(A, F340, {"message": message})
        wait_idle(s["pid"], F340)
        run = report(s["pid"], F340)
        context = pathlib.Path(s["root"]).rglob(f".agentweave/context/{F340}.md")
        for path in context:
            text = path.read_text(encoding="utf-8")
            print("context holds the aw-tool section:", "`aw-tool send_message`" in text, path)
        print("told:", run["plane_surface"], "tested:", run["harness_mcp_status"])


def f301():
    """Its own project **outside this repository**: under the repo root, Claude loads the
    operator's local-scope `agentweave` server into a `hub_client: "cli"` run, which would then
    not be tool-less (DEAD-ENDS 2026-10-01), confounding the measurement."""
    import tempfile

    s = load()
    root = pathlib.Path(tempfile.gettempdir()) / "aw-shim-drive" / time.strftime("f301-%H%M%S")
    root.mkdir(parents=True)
    (root / "README.md").write_text("f301 drive\n", encoding="utf-8")
    for cmd in (
        ["git", "init", "-b", "main"],
        ["git", "config", "user.email", "d@example.invalid"],
        ["git", "config", "user.name", "d"],
        ["git", "add", "README.md"],
        ["git", "commit", "-m", "x"],
    ):
        subprocess.run(cmd, cwd=root, check=True, capture_output=True)
    _, proj = api("POST", "/projects/open", {"path": str(root), "name": root.name})
    pid = proj["id"]
    A = f"/projects/{pid}"
    _, haiku = api("POST", f"{A}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    show("agent", *api("POST", f"{A}/agents", {"name": F301, "runner_id": haiku["id"]}))
    sync_hub_client(pid, F301, "cli")
    s["f301_pid"], s["f301_root"] = pid, str(root)
    save(s)
    trigger(A, F301, {"message": "Create an AgentWeave task titled S3-F301, then stop."})
    wait_idle(pid, F301)
    run = last_run(pid, F301)
    print("run:", json.dumps(run, default=str))
    rows = timeline(pid, run["id"])
    for kind, content, payload in rows:
        if kind == "tool_use":
            print("  input:", str(json.loads(payload).get("input"))[:300])
    tasks = ro("select title, created_by_run_id from tasks where project_id=?", (pid,))
    print("tasks:", tasks)


def spec():
    s = load()
    A = f"/projects/{s['pid']}"
    show("runner flags", *api("PATCH", f"{A}/runners/{s['cop_runner']}", {"flags": DISABLE}))
    code, doc = api("POST", f"{A}/project/documents", {"title": "shim drive spec"})
    show("document", code, doc)
    trigger(
        A,
        COP,
        {"message": "Submit this document unchanged, then stop.", "spec_document": doc["path"]},
    )
    wait_idle(s["pid"], COP)
    report(s["pid"], COP)
    events = ro(
        "select event_type from spec_document_events where document_id in "
        "(select id from spec_documents where path=?)",
        (doc["path"],),
    )
    print("document events:", events)


PHASES = {
    "setup": setup,
    "mcp": mcp,
    "shim": shim,
    "ask": ask,
    "back": back,
    "f340": f340,
    "f301": f301,
    "spec": spec,
}

if __name__ == "__main__":
    PHASES[sys.argv[1]]()
