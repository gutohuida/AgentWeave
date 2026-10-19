"""Tasks sweep phase 2: a verdict withdraws a review queued behind a busy reviewer; a skipped merge and Retry.

  py -3.11 scripts/drive/s1019_tasks_p2.py
"""
import time

from s1019_tasks import trigger, wait_run
from s1019_tasks_lib import B, S, api, ro, say

t = S["mul"]
code, r = trigger("rev", 'Run exactly this one command and nothing else, then reply "done": '
                  'py -3.11 -c "import time\nfor i in range(90): time.sleep(1)"')
say("long turn", (code, r))
long_run = r["run_id"]
for i in range(30):
    time.sleep(3)
    calls = ro("select count(*) n from agent_outputs where run_id=? and kind='tool_use'", (long_run,))[0]["n"]
    if calls:
        break
say("long run tool calls", calls)
code, r = trigger("rev", "Review the mul() task.", review_task_id=t)
say("review trigger while busy", (code, r))
entry = r.get("queue_entry_id")
st, cur = api("GET", f"{B}/settings")
cur.pop("warnings", None)
cur["main_branch"] = None
say("main_branch -> null", api("PUT", f"{B}/settings", cur)[0])
code, out = api("POST", f"{B}/tasks/{t}/land", {})
say("land (no main branch)", (code, out if code >= 300 else {k: out.get(k) for k in ("status", "assignee")}))
say("entry after verdict", ro("select id, state, review_task_id, abandoned_reason, waiting_reason from inbound_queue_entries where id=?", (entry,)))
say("integrations", ro("select outcome, commit_sha, reason from task_integrations where task_id=?", (t,)))
say("long run ends", wait_run(long_run))
time.sleep(10)
say("rev runs after", ro("select id, status, task_id, started_at from runs where agent='rev' order by started_at desc limit 2"))
say("entry later", ro("select id, state, delivered_in_run_id, abandoned_reason from inbound_queue_entries where id=?", (entry,)))
say("retry while no main", api("POST", f"{B}/tasks/{t}/integrations/retry", {}))
cur["main_branch"] = "master"
say("main_branch -> master", api("PUT", f"{B}/settings", cur)[0])
code, out = api("POST", f"{B}/tasks/{t}/integrations/retry", {})
say("retry", (code, out))
say("retry again", api("POST", f"{B}/tasks/{t}/integrations/retry", {}))
say("retry on unapproved", api("POST", f"{B}/tasks/task-does-not-exist/integrations/retry", {}))
