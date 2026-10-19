"""Ledger sweep, phase 2: a real builder turn (task, message, checkpoint notes), a checkpoint, a cut-over.

py -3.11 scripts/drive/s1019_ledger_p2.py
"""

from s1019_ledger_lib import S, api, ro, save, say, texts, wait_run

P = S["P"]

st, saved = api("PUT", f"/projects/{P}/settings", {"checkpoint_runner_id": S["RUNNER"]})
say("settings checkpoint runner", (st, {k: saved.get(k) for k in ("checkpoint_runner_id",)} if isinstance(saved, dict) else saved))

st, t = api("POST", f"/projects/{P}/tasks", {
    "title": "Fix add()",
    "assignee": "builder",
    "description": "src/calc.py add() subtracts. Make tests/test_calc.py pass.",
})
say("task", (st, {k: t.get(k) for k in ("id", "status", "assignee")} if isinstance(t, dict) else t))
S["T1"] = t["id"]
save()

msg = (
    "Work task " + t["id"] + ": fix add() in src/calc.py so tests/test_calc.py passes "
    "(run `py -3.11 -m pytest -q tests`), commit it, and set the task to completed. Then do exactly two "
    "more things with your AgentWeave tools: (1) send_message to rev, subject 'add fixed', content "
    "'add() fixed in src/calc.py; no reply needed'; (2) submit_checkpoint_notes with intent "
    "'calc add fix done; next is a div() function', suspicions ['mul is untested for negatives'], "
    "warnings ['big.txt is 2 MB, do not read it']. Then stop."
)
st, r = api("POST", f"/projects/{P}/agent/trigger", {
    "agent": "builder", "message": msg, "task_id": t["id"], "overrides": {"permission_mode": "workspace"},
})
say("trigger", (st, r))
run = r["run_id"]
S["R1"] = run
save()
print("final:", wait_run(run, 900))
print(texts(run, 2500))
rows = ro("select id, conversation_id, status, task_id from runs where project_id=? order by started_at", (P,))
say("runs", rows)
S["C1"] = ro("select conversation_id from runs where id=?", (run,))[0]["conversation_id"]
save()

st, notes = api("GET", f"/projects/{P}/conversations/{S['C1']}/checkpoint-notes")
say("notes before checkpoint", (st, notes))
st, task = api("GET", f"/projects/{P}/tasks/{t['id']}")
say("task after", (st, {k: task.get(k) for k in ("status", "assignee")}))
