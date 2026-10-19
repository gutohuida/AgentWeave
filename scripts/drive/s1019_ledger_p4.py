"""Ledger sweep, phase 4: POST /session/sync omitting builder while builder holds a task and a live run.

py -3.11 scripts/drive/s1019_ledger_p4.py
"""

import time

from s1019_ledger_lib import S, api, git, ro, save, say, texts, wait_run

P = S["P"]

st, t = api("POST", f"/projects/{P}/tasks", {
    "title": "Add div()", "assignee": "builder",
    "description": "Add div(a, b) to src/calc.py raising ZeroDivisionError on b == 0, with a test.",
})
say("task2", (st, {k: t.get(k) for k in ("id", "status", "assignee")}))
S["T2"] = t["id"]
save()

msg = (
    "Work task " + t["id"] + ". FIRST, before anything else, run this exact command and wait for it: "
    "py -3.11 -c \"import time\nfor i in range(100): time.sleep(1)\" . "
    "After it finishes, add div(a, b) to src/calc.py (raise ZeroDivisionError when b == 0), add a test, "
    "run `py -3.11 -m pytest -q tests`, commit, and set the task to completed."
)
st, r = api("POST", f"/projects/{P}/agent/trigger", {
    "agent": "builder", "message": msg, "task_id": t["id"], "overrides": {"permission_mode": "workspace"},
})
say("trigger", (st, {k: r.get(k) for k in ("run_id", "status", "conversation_id")}))
run = r["run_id"]
S["R4"] = run
save()

# wait until the sleep is in flight
deadline = time.time() + 120
while time.time() < deadline:
    out = texts(run, 3000)
    if "sleep" in out or "Called" in out:
        break
    time.sleep(3)
time.sleep(8)
say("run live?", ro("select id, status, task_id, conversation_id from runs where id=?", (run,)))
say("task2 now", ro("select id, status, assignee from tasks where id=?", (t["id"],)))
say("agents before", ro("select name, id, runner_id, archived_at from agents where project_id=?", (P,)))

st, res = api("POST", f"/projects/{P}/session/sync", {"data": {"agents": {"rev": {}}}})
say("SYNC omitting builder", (st, res))
say("agents after", ro("select name, id, runner_id from agents where project_id=?", (P,)))
st, a = api("GET", f"/projects/{P}/agents/builder")
say("GET agents/builder", (st, a))
st, al = api("GET", f"/projects/{P}/agents")
say("GET agents", (st, [x.get("name") for x in al] if isinstance(al, list) else al))
st, tk = api("GET", f"/projects/{P}/tasks/{t['id']}")
say("task2 via API", (st, {k: tk.get(k) for k in ("status", "assignee")} if isinstance(tk, dict) else tk))
say("run still", ro("select id, status from runs where id=?", (run,)))

print("final:", wait_run(run, 900))
print(texts(run, 1500))
say("run after", ro("select id, status, error, snapshot_commit_sha from runs where id=?", (run,)))
say("task2 after", ro("select id, status, assignee from tasks where id=?", (t["id"],)))
say("task1 after", ro("select id, status, assignee from tasks where id=?", (S["T1"],)))
say("conversations", ro("select id, agent, lifecycle from conversations where project_id=? order by sequence", (P,)))
say("events since", ro("select event_type, agent, substr(data,1,300) d from event_logs where project_id=? and "
                       "timestamp > (select started_at from runs where id=?) order by timestamp", (P, run)))
say("divergences", ro("select id, run_id, agent, task_id, outcome from run_divergences where project_id=?", (P,)))
print(git("worktree", "list"))
print(git("branch", "-a"))

# what the operator can do next
st, res = api("POST", f"/projects/{P}/agent/trigger", {"agent": "builder", "message": "status?"})
say("trigger deleted builder", (st, res))
st, res = api("PATCH", f"/projects/{P}/tasks/{t['id']}", {"status": "approved"})
say("approve task2 (operator)", (st, res if not isinstance(res, dict) else {k: res.get(k) for k in ("status", "assignee", "detail")}))
st, res = api("GET", f"/projects/{P}/session/sync")
say("GET session/sync", (st, res))
st, led = api("GET", f"/projects/{P}/ledger")
say("ledger by_agent", (st, led["spend"]["by_agent"] if st == 200 else led))
st, acc = api("GET", f"/projects/{P}/accounting")
say("accounting agents", (st, [(x["agent"], x["total_tokens"]) for x in acc["agents"]] if st == 200 else acc))
