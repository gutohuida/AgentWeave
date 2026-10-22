"""2026-10-22 day sweep: Traces x Runs x Logs, events & SSE, scratch Hub (hub-up tr1022 8112).

Gives the Activity digest every kind of turn ending, then F844's busy-elsewhere state.

  turns   P1 alpha: conversation A and B, one finished turn each; P2 beta one turn (F419);
          a task created and moved (task_created / task_updated)
  stop    alpha in A runs a 120 s sleep; Stop through the operator route -> run_stopped
  fail    alpha in A runs a 120 s sleep; its claude process is killed -> run_failed
  ask     alpha in A asks the operator (ask_user, long wait) and is left blocked (for F844's UI)
  state   the project's events, runs and conversations as the routes return them

  py -3.11 scripts/drive/s1022_tr_drive.py <phase>
"""

import json
import os
import pathlib
import subprocess
import sys
import time

os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-tr1022.json")
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STATE_FILE = ROOT / "testbed" / "scratch" / "s1022_tr_state.json"
S = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {"P": "proj-9a2788c8d0d7", "P2": "proj-be3b5882d029"}
LIVE = ("running", "queued", "starting", "pending")
SLEEP = 'Run exactly this shell command and nothing else, then reply DONE: py -3.11 -c "import time\nfor i in range(120): time.sleep(1)"'


def save():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(S, indent=2))


def api(method, path, body=None, project=None):
    if path.startswith("~"):
        path = f"/projects/{project or S['P']}" + path[1:]
    return e2e.request(method, path, body)


def say(label, obj=""):
    text = obj if isinstance(obj, str) else json.dumps(obj, default=str, ensure_ascii=False)
    print(f"--- {label}: {text[:2500]}", flush=True)


def ro(sql, args=()):
    c = e2e.ro()
    try:
        return [dict(r) for r in c.execute(sql, args)]
    finally:
        c.close()


def trigger(agent, message, conversation=None, project=None, perm="workspace"):
    body = {"agent": agent, "message": message, "overrides": {"permission_mode": perm}}
    if conversation:
        body["conversation_id"] = conversation
    st, res = api("POST", "~/agent/trigger", body, project=project)
    say(f"trigger {agent} -> {st}", {k: res.get(k) for k in ("run_id", "status", "conversation_id", "detail")})
    return res.get("run_id")


def wait_run(run_id, secs=600):
    end = time.time() + secs
    while time.time() < end:
        rows = ro("select status from runs where id=?", (run_id,))
        if rows and rows[0]["status"] not in LIVE:
            return rows[0]["status"]
        time.sleep(3)
    return "still-running"


def conv_of(run_id):
    return ro("select conversation_id from runs where id=?", (run_id,))[0]["conversation_id"]


def wait_tool_call(run_id, needle="Called PowerShell", secs=180):
    end = time.time() + secs
    while time.time() < end:
        rows = ro("select count(*) n from agent_outputs where run_id=? and content like ?", (run_id, f"%{needle}%"))
        if rows[0]["n"]:
            return True
        time.sleep(3)
    return False


def phase_turns():
    run = trigger("alpha", "Reply with the single word OK.")
    say("A run", wait_run(run))
    S["A"], S["RUN_OK"] = conv_of(run), run
    run = trigger("alpha", "Reply with the single word BEE.", conversation=None)
    # A trigger without conversation_id continues nothing only if the Hub opens a fresh one: force it.
    if conv_of(run) == S["A"]:
        say("NOTE", "trigger without conversation_id continued A; B is A")
    say("B run", wait_run(run))
    S["B"], S["RUN_B"] = conv_of(run), run
    run = trigger("beta", "Reply with the single word OTHER.", project=S["P2"])
    say("P2 run", wait_run(run))
    S["RUN_P2"] = run
    st, task = api("POST", "~/tasks", {"title": "Digest probe task", "description": "x", "assignee": "alpha"})
    say(f"task create {st}", {k: task.get(k) for k in ("id", "status", "detail")})
    S["TASK"] = task.get("id")
    save()


def phase_stop():
    run = trigger("alpha", SLEEP, conversation=S["A"])
    S["RUN_STOP"] = run
    save()
    say("tool call seen", wait_tool_call(run))
    say("status before stop", ro("select status from runs where id=?", (run,)))
    st, res = api("POST", "~/agent/alpha/stop")
    say(f"stop {st}", res)
    say("final", wait_run(run, 120))


def _claude_children(hub_pid):
    ps = (
        "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine | "
        "ConvertTo-Json -Compress"
    )
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout
    procs = json.loads(out)
    kids = {}
    for p in procs:
        kids.setdefault(p["ParentProcessId"], []).append(p)
    found, stack = [], [hub_pid]
    while stack:
        pid = stack.pop()
        for c in kids.get(pid, []):
            stack.append(c["ProcessId"])
            if (c["Name"] or "").lower().startswith("claude"):
                found.append(c)
    return found


def phase_fail():
    run = trigger("alpha", SLEEP, conversation=S["A"])
    S["RUN_FAIL"] = run
    save()
    say("tool call seen", wait_tool_call(run))
    hub_pid = json.loads(pathlib.Path(os.environ["AW_E2E_STATE"]).read_text())["pid"]
    kids = _claude_children(int(hub_pid))
    say("claude processes under the Hub", [(k["ProcessId"], k["Name"]) for k in kids])
    for k in kids:
        subprocess.run(["taskkill", "/F", "/PID", str(k["ProcessId"])], capture_output=True)
    say("final", wait_run(run, 180))
    say("run row", ro("select status, exit_code, error from runs where id=?", (run,)))


def phase_ask():
    run = trigger(
        "alpha",
        "Call the ask_user tool now to ask me exactly 'Which colour for the border?' with the options red and "
        "blue, waiting up to 600 seconds for the answer. Do nothing else.",
        conversation=S["A"],
    )
    S["RUN_ASK"] = run
    save()
    end = time.time() + 240
    while time.time() < end:
        st, qs = api("GET", "~/questions")
        items = qs if isinstance(qs, list) else qs.get("questions", [])
        live = [q for q in items if not q.get("answered") and q.get("from_agent") == "alpha"]
        if live:
            say("open question", {k: live[0].get(k) for k in ("id", "question", "conversation_id", "asker_waiting")})
            S["Q"] = live[0]["id"]
            save()
            break
        time.sleep(4)
    st, agents = api("GET", "~/agents")
    rows = agents if isinstance(agents, list) else agents.get("agents", [])
    say("alpha roster", [{k: a.get(k) for k in ("name", "status", "running_conversation_id")} for a in rows if a.get("name") == "alpha"])


def phase_state():
    for p in (S["P"], S["P2"]):
        st, ev = e2e.request("GET", f"/projects/{p}/events/history?limit=200")
        items = ev if isinstance(ev, list) else ev.get("events", ev.get("items", []))
        say(f"events {p} ({len(items)})", [(e.get("event_type"), e.get("agent"), (e.get("data") or {}).get("run_id")) for e in items][:80])
    say("runs", ro("select id, agent, status, exit_code, conversation_id from runs order by started_at"))


if __name__ == "__main__":
    {"turns": phase_turns, "stop": phase_stop, "fail": phase_fail, "ask": phase_ask, "state": phase_state}[sys.argv[1]]()
