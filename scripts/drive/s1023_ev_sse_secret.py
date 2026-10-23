"""Secrets redacted in a run's recorded text, one split across two events, file paths left alone.

One Haiku turn writes `aw_live_` and the rest of a fake value in separate replies with a tool call
between them (the per-event pass cannot see the whole value; only the stream join can).

    py -3.11 scripts/drive/s1023_ev_sse_secret.py run|read [run-id]
"""

import json
import sys

from s1023_ev_sse_lib import B, P, q, req, trigger, wait_status

WHAT = sys.argv[1]

MSG = "\n".join([
    "I am checking how the AgentWeave Hub displays a reply that is split by tool calls. Please do these "
    "steps in order; for each 'say' step, reply with exactly the quoted words and nothing else.",
    "1. Say: `Channel prefix aw_live_`",
    "2. Run the shell command: echo one",
    r"3. Say: `Q7xP2mK4R9sT is the channel. Notes are in C:\Users\huida\Documents\aw-ev1023\README.md`",
    "4. Run the shell command: echo two",
    "5. Say: `Second channel aw_live_N4bV6`",
    "6. Run the shell command: echo three",
    "7. Say: `Finished cleanly.`",
])

if WHAT == "run":
    run = trigger("alpha", MSG)
    print("RUN", run, wait_status(run, ("completed", "failed", "stopped"), 300))
else:
    run = sys.argv[2]
    for r in q("select sequence, kind, content from agent_outputs where run_id=? order by sequence", run):
        print(f"{r['sequence']:>4} {r['kind']:<12} {json.dumps(r['content'], ensure_ascii=False)[:260]}")
    st, hist = req("GET", f"{B}/events/history?limit=500")
    blob = json.dumps(hist)
    print("history mentions Q7xP2mK4:", "Q7xP2mK4" in blob, "| N4bV6:", "N4bV6" in blob)
    print("queue entry content:", q("select substr(content,1,400) c from inbound_queue_entries where delivered_in_run_id=?", run))
    print("project:", P)
