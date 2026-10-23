"""2026-10-23 resilience drive: a pending ask_user question open across a Hub kill + restart.

    py -3.11 scripts/drive/s1023_lc_ask.py hold        # beta asks, waits; prints question + run
    py -3.11 scripts/drive/s1023_lc_ask.py after <run> # after restart: run, question, queue, events
    py -3.11 scripts/drive/s1023_lc_ask.py answer <question-id> <choice>
"""

import json
import sys
import time

from s1023_lc_lib import B, P, q, req, show


def hold(agent="beta"):
    body = {"agent": agent, "overrides": {"permission_mode": "workspace"},
            "message": "Before anything else, use your ask_user tool to ask me one question: "
                       "'Which colour should the banner be?' with the options red and blue. "
                       "Wait for my answer, then reply with just the colour I chose."}
    st, r = show("POST", f"{B}/agent/trigger", body, limit=500)
    run = r.get("run_id")
    for _ in range(50):
        time.sleep(3)
        qs = req("GET", f"{B}/questions")[1]
        items = qs if isinstance(qs, list) else qs.get("questions", [])
        pend = [x for x in items if x.get("status") in ("pending", "open", None) and x.get("agent", agent) == agent]
        if pend:
            print("PENDING QUESTION", json.dumps(pend[-1], ensure_ascii=False)[:800])
            break
    print("RUN", q("select id, status, pid from runs where id=?", run))
    print(json.dumps({"run": run}))


def after(run, agent="beta"):
    print("RUN", q("select id, status, exit_code, substr(error,1,300) e, ended_at from runs where agent=? order by started_at", agent))
    show("GET", f"{B}/questions", limit=2500)
    for e in q("select sequence, state, delivered_in_run_id, delivery_attempts, abandoned_reason, substr(waiting_reason,1,200) w from inbound_queue_entries where project_id=? and agent=? order by sequence", P, agent):
        print("QROW", e)
    for e in q("select event_type, substr(data,1,300) d, timestamp from event_logs where project_id=? and agent=? order by timestamp desc limit 10", P, agent):
        print("EVENT", e)


def answer(qid, choice):
    show("GET", f"{B}/questions/{qid}", limit=1500)
    st, r = show("PATCH", f"{B}/questions/{qid}", {"answer": choice}, limit=1500)


if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])
