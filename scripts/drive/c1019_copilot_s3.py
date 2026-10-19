"""Scenario 3 (2026-10-19 Copilot stall drive): work that runs past the fixed 600 s turn deadline.
Agent `slow` (own Copilot runner, claude-haiku-4.5) runs a 700 s command. Then watch the requeue:
attempt 2 on the same session, attempt 3 on a fresh one, then withdrawn. Logs every run of the
agent, its queue entry and the events, for up to ~40 minutes.

    py -3.11 scripts/drive/c1019_copilot_s3.py
"""

import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from c1019_copilot_lib import P, e2e, q, report  # noqa: E402

e2e.cmd_agent(P, "slow", "-", "copilot", "claude-haiku-4.5")
t0 = time.time()
rid = e2e.cmd_turn(
    P, "slow",
    "Run this exact command in the shell and wait for it to finish (it takes about 12 minutes, "
    "that is expected): py -3.11 -c \"import time; time.sleep(700); print('slept-done')\" "
    "Then reply with its output. Do not ask me anything.",
    fresh=True)
seen = {}
while time.time() - t0 < 40 * 60:
    runs = q("select id, status, error, started_at, ended_at, session_id from runs where agent='slow' "
             "order by started_at")
    for r in runs:
        key = (r["id"], r["status"])
        if key not in seen:
            seen[key] = time.time() - t0
            print(f"t+{seen[key]:6.0f}s RUN {r}")
    ents = q("select id, state, delivery_attempts, abandoned_reason, delivered_in_run_id, "
             "waiting_reason from inbound_queue_entries where agent='slow'")
    for e in ents:
        key = ("entry",) + tuple(e.values())
        if key not in seen:
            seen[key] = time.time() - t0
            print(f"t+{seen[key]:6.0f}s ENTRY {e}")
    conv = q("select id, provider_session_id from conversations where agent='slow'")
    key = ("conv",) + tuple(tuple(c.values()) for c in conv)
    if key not in seen:
        seen[key] = time.time() - t0
        print(f"t+{seen[key]:6.0f}s CONV {conv}")
    if time.time() - t0 > 90 and ents and all(e["state"] != "queued" for e in ents) and runs and \
            all(r["status"] not in ("running", "queued", "starting") for r in runs):
        break
    sys.stdout.flush()
    time.sleep(10)
for r in q("select id from runs where agent='slow' order by started_at"):
    report(r["id"])
