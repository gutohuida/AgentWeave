"""Does sending more messages destroy the earlier ones?

The queue sweep saw `waiting_count` stop growing while triggers kept succeeding. The suspicion:
`schedule_agent` counts a delivery attempt against **every selected entry** each time it runs, and
it runs on every trigger — so for an agent that cannot launch, three *messages* consume the three
*delivery attempts* the abandonment counter was built for, and the earliest input is dropped
seconds after it was accepted.

Sends five messages to an agent with no runner bound and reads the rows back. Nothing is inferred
from `waiting_count`.

Run: AW_PROJECT=<proj> AW_KEY=<key> py -3.11 scripts/drive/t_queue_attrition.py
"""

import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api  # noqa: E402

DB = os.environ.get(
    "AW_DB", r"C:/Users/huida/.agentweave/hub/profiles/beta/agentweave.db"
)
AGENT = "attrition-probe"

api("POST", f"/projects/{P}/agents/register", {"name": AGENT, "contact_mode": "poll"})
print(f"agent {AGENT} registered with no runner bound")

sent = []
for n in range(1, 6):
    code, out = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {"agent": AGENT, "message": f"message {n}", "session_mode": "new"},
    )
    sent.append((n, code, out.get("queue_entry_id") if isinstance(out, dict) else None))
    print(f"  message {n}: HTTP {code} entry={sent[-1][2]}")
    time.sleep(0.2)

time.sleep(1.0)

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
rows = conn.execute(
    "SELECT id, content, state, delivery_attempts, abandoned_reason "
    "FROM inbound_queue_entries WHERE agent = ? ORDER BY sequence",
    (AGENT,),
).fetchall()

print()
print(f"{'entry':<22} {'content':<12} {'state':<11} {'att':>3}  abandoned_reason")
for eid, content, state, attempts, reason in rows:
    print(f"{eid:<22} {content[:12]:<12} {state:<11} {attempts:>3}  {(reason or '')[:60]}")

queued = [r for r in rows if r[2] == "queued"]
withdrawn = [r for r in rows if r[2] == "withdrawn"]
print()
print(f"sent {len(sent)}, still queued {len(queued)}, withdrawn {len(withdrawn)}")
if withdrawn:
    print()
    print("EVERY withdrawn entry here was dropped without a single run ever being attempted for")
    print("it. Nothing failed to deliver it — the operator simply sent more messages, and each")
    print("trigger re-scheduled the agent and counted an attempt against everything already in")
    print("the queue.")

code, status = api("GET", f"/projects/{P}/queue/{AGENT}/status")
print()
print(f"what the operator is shown: {status}")
