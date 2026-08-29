"""Row 19 x row 8: crash a task-bound run until its input is abandoned.

`reconcile_interrupted_runs` has one branch this repo has never driven:

    if run.task_id and not returned_entry_ids:
        divergences_to_evaluate.append(run.id)

`returned_entry_ids` is empty only when `return_run_entries` gave up on the entry, which happens
at `DELIVERY_ATTEMPT_LIMIT = 3`. So the branch is reachable only by crashing the Hub **three
times** on the same input -- and that is also, precisely, the case the earlier crash drive filed
as "an operator whose Hub crash-loops three times loses the message". This drives both at once.

What it asks:

  crash 1  -> entry returned, attempts 1, run resumes
  crash 2  -> entry returned, attempts 2 -- at RESUME_RETRY_LIMIT the conversation's
              provider_session_id is cleared, so the next delivery is a FRESH session
  crash 3  -> attempts 3: entry `withdrawn`, abandoned_reason set, divergence evaluated

and then the question that matters: with the message gone, **what is the operator shown about a
task that is still `in_progress` and an agent that is now idle?**

Usage:  AW_HUB=... AW_KEY=... AW_PROJECT=... AW_AGENT=beta py -3.11 t_row19_crash_task.py
"""

import os
import subprocess
import sqlite3
import time

from aw import api, show

P = os.environ.get("AW_PROJECT") or "proj-dc4d43543bea"
AGENT = os.environ.get("AW_AGENT") or "beta"
PORT = os.environ.get("AW_PORT") or "8011"
DB = os.environ.get(
    "AW_DB", "sqlite+aiosqlite:///C:/Users/huida/AppData/Local/Temp/aw0829/aw0829.db"
)
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG = os.environ.get("AW_HUBLOG", "C:/Users/huida/AppData/Local/Temp/aw0829/hub_crash.log")


def step(label):
    print("\n" + "=" * 72)
    print(label)
    print("=" * 72)


def ps(script):
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True
    )
    return (r.stdout or "").strip()


def hub_pids():
    raw = ps(
        "Get-CimInstance Win32_Process -Filter \"name='python.exe' or name='py.exe'\" | "
        f"Where-Object {{ $_.CommandLine -like '*uvicorn*--port {PORT}*' }} | "
        "ForEach-Object { $_.ProcessId }"
    )
    return [int(x) for x in raw.split() if x.isdigit()]


def kill_hub():
    pids = hub_pids()
    ps("Stop-Process -Id " + ",".join(str(p) for p in pids) + " -Force")
    time.sleep(3)
    code, _ = api("GET", "/projects", timeout=3)
    print(f"  killed {pids}; GET /projects -> {code}")
    return code == 0


def start_hub():
    subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", PORT, "--host", "127.0.0.1"],
        cwd=os.path.join(REPO, "hub"),
        env={
            **os.environ,
            "DATABASE_URL": DB,
            "AW_BOOTSTRAP_API_KEY": os.environ.get("AW_KEY", ""),
            "AW_TICKET_SECRET": os.environ.get("AW_TICKET_SECRET", "aw0829-ticket-secret"),
        },
        stdout=open(LOG, "ab"),
        stderr=subprocess.STDOUT,
    )
    end = time.time() + 45
    while time.time() < end:
        code, _ = api("GET", "/projects", timeout=3)
        if code == 200:
            return True
        time.sleep(1)
    return False


def sql(query, args=()):
    conn = sqlite3.connect(DB.split("///", 1)[1])
    try:
        cur = conn.execute(query, args)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def entry_row(entry_id):
    rows = sql(
        "SELECT id,state,delivery_attempts,abandoned_reason,conversation_id,delivered_in_run_id,task_id "
        "FROM inbound_queue_entries WHERE id = ?",
        (entry_id,),
    )
    return rows[0] if rows else None


def conv_session(conversation_id):
    rows = sql("SELECT id,provider_session_id FROM conversations WHERE id = ?", (conversation_id,))
    return rows[0] if rows else None


def agent_status():
    _, body = api("GET", f"/projects/{P}/agents")
    rows = body if isinstance(body, list) else body.get("agents", [])
    return next((a["status"] for a in rows if a["name"] == AGENT), None)


def wait_running(timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        if agent_status() == "running":
            return True
        time.sleep(2)
    return False


def main():
    verdicts = []

    step("0. A task for the agent, and a run bound to it")
    code, body = api(
        "POST",
        f"/projects/{P}/tasks",
        {
            "title": "Document calc.py's power function",
            "description": (
                "Append a short docstring to the power() function in calc.py in your working "
                "directory. Change nothing else. Do not run git."
            ),
            "assignee": AGENT,
            "priority": "high",
        },
    )
    show("task", code, body, limit=700)
    if code >= 300:
        return
    task_id = body["id"]

    code, body = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {
            "agent": AGENT,
            "task_id": task_id,
            "message": (
                "Work on your assigned task. Take it one step at a time: first read calc.py, "
                "then think about the wording, then make the edit, then read it back."
            ),
        },
    )
    show("trigger (task-bound)", code, body, limit=700)
    if code >= 300:
        return
    entry_id = body.get("queue_entry_id")
    print("  entry:", entry_row(entry_id))

    for attempt in (1, 2, 3):
        step(f"{attempt}. Crash #{attempt} -- kill the Hub with the task-bound run in flight")
        if not wait_running():
            print("  the agent never went running; nothing to crash on this round")
        time.sleep(6)
        running_runs = sql(
            "SELECT id,status,pid,task_id FROM runs WHERE agent = ? AND status = 'running'", (AGENT,)
        )
        print("  running:", running_runs)
        verdicts.append((f"crash {attempt} landed on a live task-bound run",
                         bool(running_runs) and bool(running_runs[0].get("task_id"))))
        kill_hub()
        print("  restarting...")
        if not start_hub():
            print("  FAIL -- hub did not come back")
            return
        row = entry_row(entry_id)
        print("  entry after restart:", row)
        conv = conv_session(row["conversation_id"]) if row and row.get("conversation_id") else None
        print("  conversation:", conv)
        # RESUME_RETRY_LIMIT = 2: the provider session is dropped so the next delivery starts fresh.
        if attempt == 2:
            verdicts.append(("provider session cleared at the second failure",
                             bool(conv) and conv.get("provider_session_id") is None))
        if attempt == 3:
            verdicts.append(("the entry is withdrawn at the third failure",
                             bool(row) and row.get("state") == "withdrawn"))
            verdicts.append(("and it says why", bool(row and row.get("abandoned_reason"))))
        time.sleep(4)

    step("4. With the message gone -- what is the operator shown?")
    print("  agent:", agent_status())
    show("task", *api("GET", f"/projects/{P}/tasks/{task_id}"), limit=1800)
    print("  runs:", sql("SELECT id,status,task_id,ended_at FROM runs WHERE agent = ? "
                         "ORDER BY started_at DESC LIMIT 5", (AGENT,)))
    show("divergences", *api("GET", f"/projects/{P}/tasks/divergences/recent"), limit=2000)
    code, body = api("GET", f"/projects/{P}/queue/{AGENT}")
    show("inbound queue", code, body, limit=1500)

    step("5. Events, the operator's actual view")
    code, body = api("GET", f"/projects/{P}/events/history?limit=60")
    rows = body.get("events") if isinstance(body, dict) else body
    for e in rows or []:
        if e.get("type") in ("context_warning", "agent_output"):
            continue
        print(f"  {str(e.get('timestamp'))[11:19]} {e.get('type')} {str(e.get('data'))[:170]}")

    step("VERDICTS")
    for label, ok in verdicts:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    print(f"\nTASK={task_id} ENTRY={entry_id}")


if __name__ == "__main__":
    main()
