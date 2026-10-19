"""Scenario 4 (2026-10-19 Copilot stall drive): a slow operator.

    card  -- agent `cop` under "Ask me" (manual): a command needs a card; nobody answers it.
    ask   -- agent `asker` (own Copilot runner) with question_timeout_seconds=600 (the allowed
             maximum) calls ask_user; nobody answers. The turn's fixed deadline is also 600 s.
             Watches the runs, the questions and the queue entry across retries, up to ~40 min.

    py -3.11 scripts/drive/c1019_copilot_s4.py card|ask
"""

import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from c1019_copilot_lib import P, e2e, q, report, req  # noqa: E402

mode = sys.argv[1]
if mode == "card":
    t0 = time.time()
    rid = e2e.cmd_turn(
        P, "cop", "Run `git log --oneline -3` in the shell and tell me the newest commit's subject "
        "in one line. Do not ask me anything.", perm="manual", fresh=True)
    while time.time() - t0 < 700:
        st = e2e.ro().execute("select status from runs where id=?", (rid,)).fetchone()["status"]
        cards = q("select id, status, tool_name, created_at, decided_at, decided_by from "
                  "permission_requests where run_id=?", rid)
        print(f"t+{time.time()-t0:5.0f}s run={st} cards={cards}")
        if st not in ("running", "queued", "starting"):
            break
        time.sleep(15)
    report(rid)
elif mode == "ask":
    e2e.cmd_agent(P, "asker", "-", "copilot", "claude-haiku-4.5")
    print("waiting settings:", req("PATCH", f"/projects/{P}/agents/asker",
                                   {"question_timeout_seconds": 600})[0])
    t0 = time.time()
    rid = e2e.cmd_turn(
        P, "asker",
        "Before doing anything else, call the AgentWeave tool ask_user with the question "
        "'Which name should the new helper function have?' and the options 'double' and 'twice'. "
        "Wait for my answer, then add that function (returning 2*x) to src/calc.py and reply in "
        "one line.", fresh=True)
    seen = {}
    while time.time() - t0 < 40 * 60:
        rows = {
            "runs": q("select id, status, error, started_at, ended_at from runs where agent='asker' "
                      "order by started_at"),
            "questions": q("select id, answered, declined, created_at, answered_at, "
                           "wait_expires_at, wait_ended_at, created_by_run_id from questions "
                           "where from_agent='asker'"),
            "entries": q("select id, state, delivery_attempts, abandoned_reason from "
                         "inbound_queue_entries where agent='asker'"),
        }
        for k, v in rows.items():
            for r in v:
                key = (k,) + tuple(str(x) for x in r.values())
                if key not in seen:
                    seen[key] = 1
                    print(f"t+{time.time()-t0:6.0f}s {k} {r}")
        runs = rows["runs"]
        if time.time() - t0 > 90 and runs and all(
                r["status"] not in ("running", "queued", "starting") for r in runs) and all(
                e["state"] != "queued" for e in rows["entries"]):
            break
        sys.stdout.flush()
        time.sleep(10)
    for r in q("select id from runs where agent='asker' order by started_at"):
        report(r["id"])
