"""Jobs & loops drive 2026-10-23 (scratch Hub :8111, la1023): the agent plane for jobs.

off  -- allow_agent_jobs off: alpha (Haiku) calls run_job / toggle_job; what it reads, the question
on   -- allow_agent_jobs on: alpha calls run_job on the archived agent's plain job and loop, and
        toggle_job on the gone agent's job; compare with the operator's answers
look -- runs, job_runs (requested_by_run_id), questions, events since

py -3.11 scripts/drive/s1023_la_agent.py <phase>
"""

import json
import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1023_la_lib import P, q, req, show  # noqa: E402

B = f"projects/{P}"
LIVE = ("running", "queued", "starting", "pending")


def jid(name):
    return q("select id from ai_jobs where project_id=? and name=?", P, name)[0]["id"]


def wait_run(run_id, limit=300):
    for _ in range(limit // 3):
        row = q("select status from runs where id=?", run_id)
        if row and row[0]["status"] not in LIVE:
            return row[0]["status"]
        time.sleep(3)
    return "timeout"


def turn(msg):
    st, run = show("POST", f"{B}/agent/trigger", {"agent": "alpha", "message": msg}, 600)
    rid = run.get("run_id")
    print("run", rid, wait_run(rid))
    for o in q("select kind as output_type, substr(content,1,1500) c from agent_outputs where run_id=? order by rowid", rid):
        print("  OUT", o["output_type"], o["c"].replace("\n", " ")[:1500])
    return rid


def off():
    show("PUT", f"{B}/settings", {"allow_agent_jobs": False}, 200)
    turn(
        "Use your AgentWeave tools (aw-tool) for exactly these two calls and nothing else, then end your turn: "
        f"1) run_job with job_id {jid('arch1 on')}; 2) toggle_job with job_id {jid('gone1 off')} and enabled true. "
        "Do not retry anything. In your final message quote, word for word, the full response text of each call."
    )


def on():
    show("PUT", f"{B}/settings", {"allow_agent_jobs": True}, 200)
    turn(
        "Use your AgentWeave tools (aw-tool) for exactly these three calls and nothing else, then end your turn: "
        f"1) run_job with job_id {jid('arch1 on')}; 2) run_job with job_id {jid('arch1 loop')}; "
        f"3) toggle_job with job_id {jid('gone1 off')} and enabled true. "
        "Do not retry anything. In your final message quote, word for word, the full response text of each call."
    )
    show("PUT", f"{B}/settings", {"allow_agent_jobs": False}, 200)


def look():
    print("RUNS", q("select id, agent, status from runs where project_id=? order by started_at", P))
    print("JOB_RUNS", q("select j.name, r.status, r.trigger, r.requested_by_run_id, substr(r.error_summary,1,120) e, r.tick_count from job_runs r join ai_jobs j on j.id=r.job_id where j.project_id=? order by r.fired_at", P))
    print("QUESTIONS", [dict(x) for x in q("select * from questions where project_id=? order by rowid", P)][-3:])
    print("EVENTS", [(e["event_type"], e["data"][:200]) for e in q("select event_type, data from event_logs where project_id=? and (event_type like 'job_%' or event_type like '%refus%' or event_type like 'question%') order by timestamp", P)][-12:])


if __name__ == "__main__":
    globals()[sys.argv[1]]()
