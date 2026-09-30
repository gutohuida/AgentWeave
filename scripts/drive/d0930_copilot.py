"""Drive `a-copilot-agent-runs-over-acp` group 11 against a live Hub and a real Copilot CLI.

One phase per invocation, so each Free-plan prompt is spent deliberately and read before the next:

    setup   11.1  no model call: a Copilot runner and agent, its home file, launchability
    p1      11.2  prompt 1, Workspace only: write hello.txt, then agentweave-send_message
    p2      11.3  prompt 2, a specification turn (the Hub must run with plan mode switched on)
    p3      11.4  prompt 3, Ask me, same conversation: `echo hi` -> the card is denied
    p4      11.5  prompt 4, stop a running turn; no copilot.exe/powershell.exe child survives

Needs AW_HUB, AW_KEY and AW_DB (the drive profile's SQLite file, read-only here). State between
phases is kept in `testbed/scratch/copilot-drive/state.json`.
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
BASE = REPO / "testbed" / "scratch" / "copilot-drive"
STATE = BASE / "state.json"
DB = os.environ["AW_DB"]
AGENT = "cop-1"


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
    while time.time() < deadline:
        running = ro(
            "select id from runs where project_id=? and agent=? and status='running'", (pid, agent)
        )
        if not running:
            return
        time.sleep(3)
    raise SystemExit(f"{agent} still running after {timeout}s")


def last_run(pid, agent):
    rows = ro(
        "select id, status, session_id, conversation_id, error, exit_code from runs "
        "where project_id=? and agent=? order by started_at desc limit 1",
        (pid, agent),
    )
    return dict(zip(("id", "status", "session_id", "conversation_id", "error", "exit_code"), rows[0]))


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
            extra = f" tool={data.get('tool')} category={data.get('category', '')}"
        if kind in ("diagnostic", "error"):
            extra = f" code={data.get('code')}"
        print(f"  [{kind}]{extra} {str(content)[:220]!r}")
    return rows


def usage(pid, agent):
    rows = ro(
        "select data from event_logs where project_id=? and agent=? and event_type='context_warning' "
        "order by rowid desc limit 1",
        (pid, agent),
    )
    return rows[0][0] if rows else None


def trigger(A, body):
    code, resp = api("POST", f"{A}/agent/trigger", {"agent": AGENT, **body}, timeout=120)
    show("trigger", code, resp)
    return code, resp


def setup():
    BASE.mkdir(parents=True, exist_ok=True)
    root = BASE / time.strftime("proj-%H%M%S")
    root.mkdir()
    (root / "README.md").write_text("copilot drive\n", encoding="utf-8")
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
    code, runners = api("GET", f"{A}/runners")
    print("runner CLIs offered by the seed:", sorted(r["cli"] for r in runners))
    code, runner = api("POST", f"{A}/runners", {"name": "Copilot drive", "cli": "copilot"})
    show("copilot runner", code, runner)
    code, charter = api(
        "POST",
        f"{A}/charters",
        {"name": "Drive builder", "content": "You are cop-1. Keep answers to one line."},
    )
    show("charter", code, charter)
    code, agent = api(
        "POST",
        f"{A}/agents",
        {"name": AGENT, "runner_id": runner["id"], "charter_id": charter["id"]},
    )
    show("agent", code, agent)
    home = pathlib.Path.home() / ".agentweave" / "hub" / "copilot-home" / "projects" / pid / AGENT
    agent_file = home / "agents" / f"{AGENT}.agent.md"
    print("agent file exists:", agent_file.exists())
    if agent_file.exists():
        text = agent_file.read_text(encoding="utf-8")
        print("  holds charter:", "Keep answers to one line." in text)
        print("  holds precedence:", "takes precedence over repository instruction files" in text)
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True
    ).stdout
    print("repository untouched:", status.strip() == "", repr(status))
    code, by_provider = api("GET", f"{A}/runners/launchability-by-provider")
    print("launchability(copilot):", json.dumps(by_provider["providers"]["copilot"]))
    save({"pid": pid, "root": str(root), "home": str(home)})


def p1():
    s = load()
    A = f"/projects/{s['pid']}"
    code, resp = trigger(
        A,
        {
            "message": "Create hello.txt containing hi in your workspace, then send me a one-line "
            "message with agentweave-send_message.",
            "overrides": {"permission_mode": "workspace"},
        },
    )
    s["conversation_id"] = resp.get("conversation_id")
    save(s)
    wait_idle(s["pid"], AGENT)
    run = last_run(s["pid"], AGENT)
    print("run:", run)
    timeline(s["pid"], run["id"])
    print("latest context reading:", usage(s["pid"], AGENT))
    conv = ro(
        "select provider_session_id from conversations where id=?", (s["conversation_id"],)
    )
    print("provider_session_id:", conv)
    msgs = ro(
        "select sender, content from messages where project_id=? order by rowid desc limit 3",
        (s["pid"],),
    )
    print("latest messages:", msgs)


def p2():
    s = load()
    A = f"/projects/{s['pid']}"
    code, doc = api("POST", f"{A}/project/documents", {"title": "copilot drive spec"})
    show("document", code, doc)
    code, resp = trigger(
        A,
        {
            "conversation_id": s["conversation_id"],
            "spec_document": doc["path"],
            "message": "Ask me one question about what this specification should cover.",
        },
    )
    wait_idle(s["pid"], AGENT)
    run = last_run(s["pid"], AGENT)
    print("run:", run)
    timeline(s["pid"], run["id"])
    questions = ro(
        "select status, content from questions where project_id=? order by rowid desc limit 2",
        (s["pid"],),
    )
    print("questions:", questions)


def p3():
    s = load()
    A = f"/projects/{s['pid']}"
    code, resp = trigger(
        A,
        {
            "conversation_id": s["conversation_id"],
            "message": "Run `echo hi` in the shell and tell me what it printed.",
            "overrides": {"permission_mode": "manual"},
        },
    )
    deadline = time.time() + 300
    decided = None
    while time.time() < deadline and decided is None:
        code, pending = api("GET", f"{A}/permission-requests")
        for card in pending if isinstance(pending, list) else []:
            if card.get("status") == "pending" and card.get("agent") == AGENT:
                print("card:", json.dumps(card)[:600])
                code, decided = api(
                    "POST", f"{A}/permission-requests/{card['id']}/decide", {"allow": False}
                )
                show("deny", code, decided)
                break
        if decided is None:
            if not ro(
                "select id from runs where project_id=? and agent=? and status='running'",
                (s["pid"], AGENT),
            ):
                print("the run ended without a card")
                break
            time.sleep(2)
    wait_idle(s["pid"], AGENT)
    run = last_run(s["pid"], AGENT)
    print("run:", run)
    timeline(s["pid"], run["id"])
    print("latest context reading:", usage(s["pid"], AGENT))


def p4():
    s = load()
    A = f"/projects/{s['pid']}"
    code, resp = trigger(
        A,
        {
            "conversation_id": s["conversation_id"],
            "message": "Write a detailed 2000-word essay about the history of version control "
            "systems, then list twenty facts about each one.",
            "overrides": {"permission_mode": "workspace"},
        },
    )
    time.sleep(12)
    code, stopped = api("POST", f"{A}/agent/{AGENT}/stop", {})
    show("stop", code, stopped)
    wait_idle(s["pid"], AGENT, timeout=120)
    run = last_run(s["pid"], AGENT)
    print("run:", run)
    timeline(s["pid"], run["id"])
    time.sleep(3)
    survivors = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*copilot*--acp*' }"
            " | Select-Object ProcessId, CommandLine | Format-List",
        ],
        capture_output=True,
        text=True,
    ).stdout
    print("copilot --acp processes left:", survivors.strip() or "none")


if __name__ == "__main__":
    {"setup": setup, "p1": p1, "p2": p2, "p3": p3, "p4": p4}[sys.argv[1]]()
