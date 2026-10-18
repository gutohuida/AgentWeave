"""Sweep C: inbound queue & messages — hop-budget chain, operator injection, Withdraw/Continue."""
import json
import sys
import time

from s1018_C_lib import B, P, api, ro, say, texts, trigger, wait_run


def chain():
    say("hop budget 2", api("PUT", f"{B}/settings", {"hop_budget": 2})[0])
    msg = ("Do these two things with AgentWeave tools, then stop. Do not ask me anything.\n"
           "1. Call send_message to the operator (to: \"operator\") saying 'hello operator'. Report the exact answer.\n"
           "2. Call send_message to beta with the text: 'PING 1 from alpha. Reply to alpha with send_message saying PING 2, then stop.' "
           "Report the exact answer of the send verbatim, including any delivery note.")
    c, r = trigger("alpha", msg, fresh=True)
    say("alpha trigger", (c, r.get("run_id")))
    st = wait_run(r["run_id"])
    say("alpha", st)
    for t in texts(r["run_id"]):
        print("TEXT alpha:", t[:900])
    watch(240)


def watch(secs=240):
    end = time.time() + secs
    seen = set()
    while time.time() < end:
        live = ro("select id, agent, status from runs where project_id=? and status in ('running','queued','starting','pending')", (P,))
        for r in ro("select id, agent, status from runs where project_id=? order by started_at desc limit 6", (P,)):
            if r["id"] not in seen and r["status"] not in ("running", "queued", "starting", "pending"):
                seen.add(r["id"])
        if not live:
            time.sleep(8)
            if not ro("select id from runs where project_id=? and status in ('running','queued','starting','pending')", (P,)):
                break
        time.sleep(5)
    report()


def report():
    for r in ro("select id, agent, status, substr(started_at,12,8) t from runs where project_id=? order by started_at desc limit 5", (P,)):
        print("RUN", r)
        for t in texts(r["id"])[-1:]:
            print("   LAST:", t[:600])
    for a in ("alpha", "beta"):
        for e in api("GET", f"{B}/queue/{a}")[1][-3:]:
            print("Q", a, e["id"], e["state"], e["origin_type"], e.get("origin_agent"), e["hop_depth"], e.get("abandoned_reason"), (e.get("content") or "")[:80])
        say(f"status {a}", api("GET", f"{B}/queue/{a}/status")[1])
    say("held events", ro("select event_type, substr(data,1,400) d from event_logs where project_id=? and (event_type like '%hop%' or data like '%held_by_hop%') order by timestamp desc limit 4", (P,)))


if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])
