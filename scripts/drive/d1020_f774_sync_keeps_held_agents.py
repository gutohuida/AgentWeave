"""F774 drive: POST /session/sync must not delete an agent that holds a task and a live run, and a
payload with no `agents` key must not empty the roster.

Real Haiku turn: `builder` holds an in_progress task and is mid-way through a 90 s sleep.

  py -3.11 scripts/drive/d1020_f774_sync_keeps_held_agents.py <project-id>

(after `e2e.py hub-up <profile> <port>` and `e2e.py setup <name>`, on a port that is not 8000/8010)
"""

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402

P = sys.argv[1]
B = f"/projects/{P}"
failures = []


def say(label, obj=""):
    print(f"--- {label}: {json.dumps(obj, default=str)[:1500]}", flush=True)


def check(label, ok):
    print(("PASS " if ok else "FAIL ") + label, flush=True)
    if not ok:
        failures.append(label)


def roster():
    st, agents = e2e.request("GET", f"{B}/agents")
    return {a["name"]: a for a in agents}


e2e.cmd_agent(P, "builder", "-", "claude", "claude-haiku-4-5-20251001")
e2e.cmd_agent(P, "rev", "-", "claude", "claude-haiku-4-5-20251001")
before = roster()
bound = before["builder"].get("runner_id")
say("roster before", {n: a.get("runner_id") for n, a in before.items()})
check("builder is bound to a runner", bool(bound))

st, task = e2e.request(
    "POST", f"{B}/tasks", {"title": "Hold work", "assignee": "builder", "description": "Wait."}
)
say("task", (st, task.get("id"), task.get("status")))
st, _ = e2e.request("PATCH", f"{B}/tasks/{task['id']}", {"status": "in_progress"})
say("task in_progress", st)

run = e2e.cmd_turn(
    P,
    "builder",
    "Run this exact command and wait for it to finish, then reply 'done': "
    "py -3.11 -c \"import time\nfor i in range(90): time.sleep(1)\"",
    task=task["id"],
    fresh=True,
    perm="workspace",
)
deadline = time.time() + 120
while time.time() < deadline:
    rows = e2e.ro().execute("select status from runs where id=?", (run,)).fetchall()
    if rows and rows[0]["status"] == "running":
        break
    time.sleep(2)
time.sleep(8)
say("run", [dict(r) for r in e2e.ro().execute("select id, status from runs where id=?", (run,))])

# 1. the roster replace omitting the busy agent is refused and names its work
st, res = e2e.request("POST", f"{B}/session/sync", {"data": {"agents": {"rev": {}}}})
say("sync omitting builder", (st, res))
detail = res.get("detail") if isinstance(res, dict) else None
check("omitting a busy agent answers 409", st == 409)
check("the refusal names the task", isinstance(detail, dict) and task["id"] in detail.get("held", {}).get("tasks", []))
check("the refusal names the run", isinstance(detail, dict) and run in detail.get("held", {}).get("runs", []))
check("builder is still on the roster", "builder" in roster())

# 2. a payload with no agents key leaves everything, bindings included
st, res = e2e.request("POST", f"{B}/session/sync", {"data": {"mode": "peer"}})
say("sync mode=peer", (st, res))
after = roster()
check("a payload without agents answers 200", st == 200)
check("every agent is still there", set(after) == set(before))
check("builder keeps its runner", after["builder"].get("runner_id") == bound)

# 3. once the run has ended and the task is decided, the same omission removes it
print("waiting for the run to end...", flush=True)
print("final:", e2e.wait_for(run, 8), flush=True)
e2e.request("PATCH", f"{B}/tasks/{task['id']}", {"status": "completed"})
st, tk = e2e.request("GET", f"{B}/tasks/{task['id']}")
say("task now", tk.get("status"))
if tk.get("status") == "completed":
    # completed is not terminal (it waits for review), so the omission must still be refused
    st, res = e2e.request("POST", f"{B}/session/sync", {"data": {"agents": {"rev": {}}}})
    say("sync omitting builder, task completed", (st, res))
    check("a task awaiting review still holds its agent", st == 409)

print("\nFAILED: " + ", ".join(failures) if failures else "\nALL PASS")
sys.exit(1 if failures else 0)
