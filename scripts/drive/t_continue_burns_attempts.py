"""Does the Continue button destroy the input it offers to start?

F114 showed that each `POST /agent/trigger` counts a delivery attempt against the queue head, so
three messages consume the three attempts. The conversation view also offers a button for exactly
this situation — *"<agent> has work waiting — start it without sending a message"* — and it calls
`POST /conversations/{id}/continue`.

If that path counts attempts the same way, an operator doing precisely what the UI suggests, to the
message they are worried about, is what destroys it. Three clicks.

Nothing here spawns: the agent is bound to no runner.

Run: AW_PROJECT=<proj> AW_KEY=<key> py -3.11 scripts/drive/t_continue_burns_attempts.py
"""

import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api  # noqa: E402

DB = os.environ.get("AW_DB", r"C:/Users/huida/.agentweave/hub/profiles/beta/agentweave.db")
# A fresh agent per run — see `t_queue_attrition.py` for why reusing a name mixes an earlier
# run's rows into this one's reading.
AGENT = f"continue-{int(time.time()) % 100000}"

api("POST", f"/projects/{P}/agents/register", {"name": AGENT, "contact_mode": "poll"})
code, out = api("POST", f"/projects/{P}/agent/trigger",
                {"agent": AGENT, "message": "the one message", "session_mode": "new"})
conv, entry = out.get("conversation_id"), out.get("queue_entry_id")
print(f"one message queued: entry={entry} conversation={conv}")


def read():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    row = conn.execute(
        "SELECT state, delivery_attempts, abandoned_reason FROM inbound_queue_entries WHERE id = ?",
        (entry,),
    ).fetchone()
    conn.close()
    return row


print(f"  after queueing:      state={read()[0]!r} attempts={read()[1]}")

for click in range(1, 4):
    code, body = api("POST", f"/projects/{P}/conversations/{conv}/continue")
    time.sleep(0.4)
    state, attempts, reason = read()
    # F131 (fixed 2026-08-30): `started` answers "did the conversation you named start". This
    # agent cannot launch at all, so no turn begins for anybody and the value is False either
    # way -- printed, never asserted on, and unaffected by the change.
    started = body.get("started") if isinstance(body, dict) else None
    print(f"  Continue click {click}: HTTP {code} started={started!r} "
          f"-> state={state!r} attempts={attempts}")
    if reason:
        print(f"      abandoned_reason: {reason[:110]}")

state, attempts, reason = read()
print()
if state == "withdrawn":
    print("THREE CLICKS OF 'CONTINUE' DESTROYED THE MESSAGE THE BUTTON OFFERED TO START.")
    print(f"recorded reason: {reason}")
else:
    print(f"the entry survived three clicks: state={state!r} attempts={attempts}")
