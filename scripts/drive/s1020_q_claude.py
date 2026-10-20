"""Questions sweep, 2026-10-20, on a Claude agent (`asker`, claude-haiku-4-5-20251001).

    answer   -- a task-bound turn asks; the task parks while it waits; the answer releases it
    decline  -- the operator declines; what the agent is told
    timeout  -- wait 30 s; nobody answers; then a late answer while the run still lives
    leave    -- one asked and left unanswered (wait 30 s); the run ends; how the panel reads it

    py -3.11 scripts/drive/s1020_q_claude.py <phase>
"""

import json
import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1020_q_lib import P, e2e, q, req  # noqa: E402

ASK = ("Call the AgentWeave tool ask_user with the question 'Which name should the new helper "
       "have?' and the options 'double' and 'twice'. ")


def snap(rid, label):
    task = q("select t.id, t.status from tasks t join runs r on r.task_id=t.id where r.id=?", rid)
    st, qs = req("GET", f"/projects/{P}/questions?answered=false")
    mine = [{k: x.get(k) for k in ("id", "blocking", "asker_waiting", "declined", "answered",
                                    "wait_expires_at")} for x in qs if x.get("created_by_run_id") == rid
            or x.get("from_agent") == "asker"]
    run = q("select status from runs where id=?", rid)
    print(f"[{label}] run={run} task={task} open_questions={json.dumps(mine)}", flush=True)
    return mine


def wait_question(rid, minutes=4):
    end = time.time() + minutes * 60
    while time.time() < end:
        rows = q("select id, answered, declined from questions where created_by_run_id=? "
                 "order by created_at", rid)
        if rows and not rows[-1]["answered"] and not rows[-1]["declined"]:
            return rows[-1]["id"]
        if q("select status from runs where id=?", rid)[0]["status"] not in (
                "running", "queued", "starting", "pending"):
            return None
        time.sleep(3)
    return None


phase = sys.argv[1]
t0 = time.time()
if phase == "answer":
    task = req("POST", f"/projects/{P}/tasks", {"title": "Add a doubling helper to src/calc.py",
                                                 "description": "Ask the operator for the name.",
                                                 "assignee": "asker"})[1]
    print("task:", task.get("id"), task.get("status"))
    rid = e2e.cmd_turn(P, "asker", ASK + "Wait for the answer, then add that function (returning "
                       "2*x) to src/calc.py, and reply in one line naming the function.",
                       task=task["id"], fresh=True, perm="workspace")
    qid = wait_question(rid)
    print(f"t+{time.time()-t0:.0f}s question {qid}")
    snap(rid, "while waiting")
    time.sleep(8)
    st, res = req("PATCH", f"/projects/{P}/questions/{qid}", {"answer": "twice", "labels": ["twice"]})
    print("answer ->", st, {k: res.get(k) for k in ("answered", "answer", "asker_waiting")}
          if isinstance(res, dict) else res)
    snap(rid, "after answer")
    print("run:", e2e.wait_for(rid, 6))
    snap(rid, "after run")
    e2e.dump_turn(rid)
elif phase == "decline":
    rid = e2e.cmd_turn(P, "asker", ASK + "Wait for the answer. If no answer comes, reply in one "
                       "line quoting exactly what the tool told you.", fresh=True, perm="workspace")
    qid = wait_question(rid)
    print(f"t+{time.time()-t0:.0f}s question {qid}")
    time.sleep(5)
    st, res = req("POST", f"/projects/{P}/questions/{qid}/decline", {"reason": "I'd rather you "
                  "pick; use your judgement."})
    print("decline ->", st, str(res)[:400])
    st, res = req("PATCH", f"/projects/{P}/questions/{qid}", {"answer": "double"})
    print("answer after decline ->", st, str(res)[:300])
    print("run:", e2e.wait_for(rid, 6))
    snap(rid, "after run")
    e2e.dump_turn(rid)
elif phase in ("timeout", "leave"):
    print("wait:", req("PATCH", f"/projects/{P}/agents/asker", {"question_timeout_seconds": 30})[0])
    tail = ("Wait for the answer. If the tool says no answer came in time, run the shell command "
            "`py -3.11 -c \"import time; time.sleep(60)\"`, then call get_answer for that question "
            "and reply in one line with what it returned.") if phase == "timeout" else (
            "Wait for the answer. If none comes, reply in one line saying so.")
    rid = e2e.cmd_turn(P, "asker", ASK + tail, fresh=True, perm="workspace")
    qid = wait_question(rid)
    print(f"t+{time.time()-t0:.0f}s question {qid}")
    snap(rid, "while waiting")
    if phase == "timeout":
        # Past the 30 s wait, while the agent sleeps 60 s: a late answer to a live run.
        while True:
            row = q("select wait_ended_at from questions where id=?", qid)[0]
            if row["wait_ended_at"]:
                break
            time.sleep(3)
        print(f"t+{time.time()-t0:.0f}s wait ended")
        snap(rid, "wait ended")
        time.sleep(10)
        st, res = req("PATCH", f"/projects/{P}/questions/{qid}", {"answer": "double",
                                                                    "labels": ["double"]})
        print(f"t+{time.time()-t0:.0f}s late answer ->", st, str(res)[:400])
    print("run:", e2e.wait_for(rid, 8))
    snap(rid, "after run")
    e2e.dump_turn(rid)
    later = q("select id, status, started_at from runs where agent='asker' and started_at > "
              "(select started_at from runs where id=?) order by started_at", rid)
    print("later runs:", later)
    for r in later:
        e2e.wait_for(r["id"], 4)
        e2e.dump_turn(r["id"])
    print("entries:", q("select id, state, origin_type, delivered_in_run_id, substr(content,1,120) c from inbound_queue_entries "
                        "where agent='asker' order by sequence desc limit 4"))
