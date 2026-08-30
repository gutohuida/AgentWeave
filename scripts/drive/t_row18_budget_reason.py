"""Row 18 x row 6 -- the queue's stated reason for a wait, when the budget is what stops it.

The project token budget pauses *autonomous* turns only; an operator's own message is meant to get
through. Two places decide whether a queued turn counts as autonomous, and they do not decide it
the same way:

  turn_scheduler.schedule_agent  -- builds the turn from the OLDEST eligible entry, restricts it to
                                    that entry's conversation, and calls the turn autonomous when
                                    no entry IN THAT TURN is operator-origin
                                    (`turn_scheduler.py:133-138`).
  GET /queue/{agent}/status      -- looks at EVERY queued entry for the agent, across every
                                    conversation, and names the budget only when they are ALL
                                    non-operator (`inbound_queue.py:145-149`).

So an operator message queued beside a blocked autonomous one satisfies the scheduler's predicate
and not the endpoint's. This drives that: the same stalled state, read twice, before and after the
operator adds their own input.

Real surface only. No row inserts. Haiku turns. Run:

  AW_HUB=http://127.0.0.1:8011 AW_KEY=... AW_PROJECT=proj-... \
      PYTHONIOENCODING=utf-8 py -3.11 scripts/drive/t_row18_budget_reason.py
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api, show  # noqa: E402

P = os.environ.get("AW_PROJECT", "")
FORBIDDEN = {"proj-5e960453", "proj-18e5d4e0"}
HAIKU = "claude-haiku-4-5-20251001"
DRIVER = "driver"
PEER = "peer"

VERDICTS = []
STARTED = time.time()


def check(label, ok, detail=""):
    VERDICTS.append((label, bool(ok), detail))
    print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
    return bool(ok)


def step(label):
    print("\n" + "=" * 74)
    print(f"{label}   (+{int(time.time() - STARTED)}s)")
    print("=" * 74)


def agent_status(name):
    _, body = api("GET", f"/projects/{P}/agents")
    for a in body if isinstance(body, list) else body.get("agents") or []:
        if a.get("name") == name:
            return a.get("status")
    return "?"


def wait_idle(name, limit=420):
    deadline = time.time() + limit
    while time.time() < deadline:
        if agent_status(name) != "running":
            time.sleep(2)
            if agent_status(name) != "running":
                return True
        time.sleep(3)
    return False


def status(name):
    code, body = api("GET", f"/projects/{P}/queue/{name}/status")
    return code, body


def queued(name):
    _, body = api("GET", f"/projects/{P}/queue/{name}?state=queued")
    return body if isinstance(body, list) else []


def ensure_runner():
    _, body = api("GET", f"/projects/{P}/runners")
    for r in body if isinstance(body, list) else []:
        if r.get("model") == HAIKU:
            return r["id"]
    code, body = api("POST", f"/projects/{P}/runners", {"name": "haiku", "cli": "claude",
                                                        "model": HAIKU})
    if code >= 300:
        show("POST /runners", code, body)
        sys.exit("no runner")
    return body["id"]


def ensure_agent(name, runner):
    code, _ = api("POST", f"/projects/{P}/agents", {"name": name, "runner_id": runner})
    if code >= 300:
        api("PATCH", f"/projects/{P}/agents/{name}", {"runner_id": runner})


def main():
    if not P or P in FORBIDDEN:
        sys.exit(f"REFUSING: AW_PROJECT={P!r}")

    step("0. two Haiku agents, and a clean queue")
    runner = ensure_runner()
    ensure_agent(DRIVER, runner)
    ensure_agent(PEER, runner)
    for name in (DRIVER, PEER):
        for e in queued(name):
            api("DELETE", f"/projects/{P}/queue/entries/{e['id']}")
    check("driver queue empty", not queued(DRIVER))

    step("1. record some usage, then set a budget of 1 token so it is exhausted")
    api("PATCH", f"/projects/{P}/accounting/budget", {"token_budget": None})
    code, body = api("POST", f"/projects/{P}/agent/trigger",
                     {"agent": DRIVER, "message": "Reply with the single word: ready."},
                     timeout=120)
    check("warm-up turn accepted", code == 200, f"{code}")
    wait_idle(DRIVER)
    code, budget = api("PATCH", f"/projects/{P}/accounting/budget", {"token_budget": 1})
    show("PATCH budget=1", code, budget, 400)
    check("budget reports exhausted", isinstance(budget, dict) and budget.get("exhausted") is True,
          json.dumps(budget, default=str)[:160])

    step("2. a peer messages driver -- an autonomous entry the budget must hold back")
    code, body = api("POST", f"/projects/{P}/agent/trigger",
                     {"agent": PEER,
                      "message": ("Call send_message(to_agent='driver', subject='budget probe', "
                                  "content='please acknowledge') exactly once, then stop. "
                                  "Do not do anything else.")},
                     timeout=120)
    check("peer turn accepted", code == 200, f"{code}")
    wait_idle(PEER)
    time.sleep(4)
    entries = queued(DRIVER)
    check("driver holds a queued autonomous entry", len(entries) >= 1,
          json.dumps([(e.get("origin_type"), e.get("conversation_id")) for e in entries])[:220])
    check("driver is not running", agent_status(DRIVER) != "running", agent_status(DRIVER))

    step("3. THE CONTROL -- read the reason with only the autonomous entry queued")
    code, before = status(DRIVER)
    show("GET /queue/driver/status", code, before, 400)
    check("reason names the budget", isinstance(before, dict)
          and before.get("waiting_reason") == "token budget exhausted",
          repr(before.get("waiting_reason") if isinstance(before, dict) else before))

    step("4. the operator now sends their own message to the same agent")
    code, trig = api("POST", f"/projects/{P}/agent/trigger",
                     {"agent": DRIVER, "message": "Operator here -- what is blocking you?",
                      "session_mode": "new"},
                     timeout=120)
    show("POST /agent/trigger (operator)", code, trig, 500)
    time.sleep(3)
    check("nothing started", agent_status(DRIVER) != "running", agent_status(DRIVER))
    entries = queued(DRIVER)
    check("two entries now queued", len(entries) >= 2,
          json.dumps([e.get("origin_type") for e in entries]))

    step("5. THE DEFECT -- read the reason again, same stall, operator input added")
    code, after = status(DRIVER)
    show("GET /queue/driver/status", code, after, 400)
    reason = after.get("waiting_reason") if isinstance(after, dict) else None
    check("reason STILL names the budget", reason == "token budget exhausted", repr(reason))

    step("6. clean up -- clear the budget and drain the queue")
    api("PATCH", f"/projects/{P}/accounting/budget", {"token_budget": None})
    for e in queued(DRIVER):
        api("DELETE", f"/projects/{P}/queue/entries/{e['id']}")
    check("queue drained", not queued(DRIVER))

    print("\n" + "=" * 74)
    bad = [v for v in VERDICTS if not v[1]]
    print(f"{len(VERDICTS) - len(bad)}/{len(VERDICTS)} assertions passed")
    for label, _, detail in bad:
        print(f"  FAILED: {label} -- {detail}")
    print("=" * 74)
    return 0 if not bad else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        api("PATCH", f"/projects/{P}/accounting/budget", {"token_budget": None})
