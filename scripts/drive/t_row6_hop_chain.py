"""Row 6 live — an agent-to-agent chain walked into a hop budget, with the operator interrupting.

`t_sweep_queue.py` reaches row 6's mechanics without spending a turn, by triggering an agent that
can never launch. What that cannot produce is a *hop*: hop depth only increments when one agent's
turn sends to another, so the budget — the mechanism that stops two agents talking to each other
forever — has never been driven from the agent side on this fixture.

The chain: the operator triggers `driver` (hop 0). `driver` sends to `peer` (hop 1). `peer` sends
back to `driver` (hop 2). With `hop_budget = 1`, the last one must not be delivered — and the whole
question this file exists to answer is whether the operator can tell that from an agent that simply
went quiet.

Then three interruptions, which is where the seams are: an operator message injected while an entry
sits hop-blocked (operator input is hop 0 and must not be caught by the budget), `release` on the
blocked entry, and a withdrawal.

The project's `hop_budget` is restored to whatever it was on the way out, including on a failure —
leaving a fixture at 1 would quietly break every later drive.

Run: AW_HUB=... AW_KEY=... AW_PROJECT=... [DRIVE_TAG=xyz] py -3.11 scripts/drive/t_row6_hop_chain.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api  # noqa: E402

FORBIDDEN = {"proj-5e960453", "proj-18e5d4e0"}
if P in FORBIDDEN or not P:
    print("REFUSING TO RUN: set AW_PROJECT to a drive project.")
    sys.exit(1)

A = os.environ.get("AGENT_A", "driver")
B = os.environ.get("AGENT_B", "peer")
TAG = os.environ.get("DRIVE_TAG", "r6")
PONG = f"PONG-{TAG.upper()}"

POLL = 4
LIMIT = 40
FAILURES = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAILURES.append((label, str(detail)))
    return ok


def roster():
    _, body = api("GET", f"/projects/{P}/agents")
    return {r["name"]: r for r in (body if isinstance(body, list) else body.get("agents") or [])}


def queue(agent):
    _, body = api("GET", f"/projects/{P}/queue/{agent}")
    rows = body if isinstance(body, list) else body.get("entries", [])
    return rows or []


def queued(agent):
    return [e for e in queue(agent) if e.get("state") == "queued"]


def status(agent):
    _, body = api("GET", f"/projects/{P}/queue/{agent}/status")
    return body if isinstance(body, dict) else {}


def timeline_entry(agent, entry_id):
    """The held-flag lives on the *timeline*, not on the queue listing.

    `hop_budget_exceeded` is a field of `TimelineEntry` (`agent_chat.py:85`, set at
    `agent_chat.py:206-208`), which is what draws the UI's "held / Continue" control
    (`AgentTimeline.tsx:815`). `QueueEntryResponse` — what `GET /queue/{agent}` returns
    (`inbound_queue.py:24-42`) — has no such field, so reading it from there yields `None` for
    every entry, held or not. The first version of this file did exactly that and reported a
    correctly-held entry as one the product had failed to mark.
    """
    _, body = api("GET", f"/projects/{P}/agent/{agent}/chat")
    for e in (body.get("entries") if isinstance(body, dict) else []) or []:
        if e.get("id") == entry_id:
            return e
    return {}


def wait_idle(agents, limit=LIMIT):
    for _ in range(limit):
        rows = roster()
        if all((rows.get(a) or {}).get("status") != "running" for a in agents):
            return True
        time.sleep(POLL)
    return False


def wait_until(label, fn, limit=LIMIT):
    for i in range(limit):
        got = fn()
        if got:
            print(f"  {label} after ~{i * POLL}s")
            return got
        time.sleep(POLL)
    print(f"  TIMEOUT waiting for {label} (~{limit * POLL}s)")
    return None


def show_queues():
    for agent in (A, B):
        rows = queue(agent)
        interesting = [e for e in rows if e.get("state") in ("queued", "delivered")][-4:]
        parts = [f"{(e.get('origin_type') or '?')[:3]}/hop{e.get('hop_depth')}/{e.get('state')}"
                 f"{'/OVER' if e.get('hop_budget_exceeded') else ''}" for e in interesting]
        st = status(agent)
        print(f"    {agent:8s} {' '.join(parts) or '(none)'}"
              f"   waiting={st.get('waiting_count')} reason={str(st.get('waiting_reason'))[:60]!r}")


# --------------------------------------------------------------------------- preconditions
rows = roster()
for name in (A, B):
    row = rows.get(name)
    if row is None:
        print(f"REFUSING TO RUN: agent {name!r} is not on this roster.")
        sys.exit(1)
    if not row.get("runner_id"):
        print(f"REFUSING TO RUN: {name!r} has no runner bound — nothing would ever hop.")
        sys.exit(1)
print(f"precondition ok: {A} and {B} are both bound "
      f"({rows[A].get('display_model')} / {rows[B].get('display_model')})")
if not wait_idle([A, B]):
    print("REFUSING TO RUN: an earlier turn is still running.")
    sys.exit(1)

_, settings = api("GET", f"/projects/{P}/queue/settings")
ORIGINAL = dict(settings) if isinstance(settings, dict) else {}
print(f"  queue settings on entry: {ORIGINAL}")


def restore():
    if ORIGINAL:
        code, _ = api("PATCH", f"/projects/{P}/queue/settings", ORIGINAL)
        print(f"  restored queue settings -> {code}  {ORIGINAL}")


try:
    tightened = {**ORIGINAL, "hop_budget": 1}
    code, _ = api("PATCH", f"/projects/{P}/queue/settings", tightened)
    check("hop budget can be tightened to 1", code == 200, str(code))

    print()
    print("=" * 78)
    print(f"ROW 6 — the chain: operator -> {A} -> {B} -> {A}, under a budget of 1")
    print("=" * 78)

    # Both queues are snapshotted, not just A's. Matching "an entry at hop 1" against B's whole
    # history found the *previous* run's delivered entry in ~0s and reported PASS while this run's
    # agent had not sent anything yet — the fixture is warm and every id in it is a candidate.
    before_a = {e["id"] for e in queue(A)}
    before_b = {e["id"] for e in queue(B)}
    code, out = api("POST", f"/projects/{P}/agent/trigger", {
        "agent": A,
        "session_mode": "new",
        # Both tool names are fully qualified, deliberately. Saying "the send_message tool" in
        # prose makes this a coin flip on a Claude runner — the host ships its own `SendMessage`,
        # the agent picks one, and half the time the chain silently never starts (F139). That is a
        # real product finding and it has its own entry; it is not what THIS file is measuring, and
        # letting it fire here just turns the hop budget into a test of the tool-name lottery.
        "message": (
            f"Call the tool `mcp__agentweave__send_message` (that exact name — do NOT use the "
            f"host's `SendMessage`) exactly once, with to_agent='{B}', subject='ping', and this "
            f"content: \"Call the tool `mcp__agentweave__send_message` (that exact name) exactly "
            f"once, with to_agent='{A}', subject='pong', content='{PONG}'. Then reply with only "
            f"the word DONE.\" After sending, reply with only the word SENT. "
            "Do not read or write any files."
        ),
    })
    print(f"  trigger -> {code} run={out.get('run_id')} conversation={out.get('conversation_id')}")
    check("the chain's first turn started", code == 200 and out.get("status") == "running",
          str(out)[:180])

    hop1 = wait_until(f"{B} has a NEW entry at hop 1",
                      lambda: [e for e in queue(B)
                               if e["id"] not in before_b and e.get("hop_depth") == 1])
    check(f"{A}'s message reached {B}'s queue at hop 1", bool(hop1),
          "" if hop1 else
          f"no new hop-1 entry; {A}'s turn may not have sent one — read its transcript (F139)")
    if hop1:
        e = hop1[-1]
        print(f"    entry {e['id']}  origin={e.get('origin_type')!r} from={e.get('origin_agent')!r} "
              f"state={e.get('state')!r} content={str(e.get('content'))[:60]!r}")
        check(f"it is attributed to {A}, not to the operator",
              e.get("origin_type") == "agent" and e.get("origin_agent") == A,
              f"{e.get('origin_type')}/{e.get('origin_agent')}")

    print("\n  waiting for the chain to come back round...")
    hop2 = wait_until(f"{A} has an entry at hop 2",
                      lambda: [e for e in queue(A)
                               if e["id"] not in before_a and e.get("hop_depth", 0) >= 2])
    show_queues()

    print()
    print("=" * 78)
    print("ROW 6 — what the operator is told when the budget stops a message")
    print("=" * 78)
    if not hop2:
        check("the return message reached the queue at all", False,
              "no hop>=2 entry appeared; the chain did not come back round")
    else:
        e = hop2[-1]
        print(f"    entry {e['id']}  hop={e.get('hop_depth')} state={e.get('state')!r} "
              f"exceeded={e.get('hop_budget_exceeded')!r} attempts={e.get('delivery_attempts')} "
              f"abandoned={e.get('abandoned_reason')!r}")
        check("the over-budget entry is still in the queue rather than discarded",
              e.get("state") in ("queued", "delivered"), repr(e.get("state")))
        tl = timeline_entry(A, e["id"])
        print(f"    timeline: kind={tl.get('kind')!r} hop={tl.get('hop_depth')} "
              f"hop_budget_exceeded={tl.get('hop_budget_exceeded')!r}")
        check("the timeline marks the entry as held by the hop budget",
              tl.get("hop_budget_exceeded") is True, repr(tl.get("hop_budget_exceeded")))
        st = status(A)
        check("the queue status names the hop budget as the reason",
              "hop" in str(st.get("waiting_reason") or "").lower(),
              repr(st.get("waiting_reason")))

        print()
        print("=" * 78)
        print("ROW 6 — the operator interrupts a hop-blocked queue")
        print("=" * 78)
        code, inj = api("POST", f"/projects/{P}/agent/trigger", {
            "agent": A,
            "conversation_id": out.get("conversation_id"),
            "message": "Reply with only the word ACK. Do not read or write any files.",
        })
        entry_id = inj.get("queue_entry_id") if isinstance(inj, dict) else None
        print(f"  operator message -> {code} status={inj.get('status')!r} "
              f"reason={str(inj.get('waiting_reason'))[:70]!r} entry={entry_id}")
        check("an operator message is accepted while the queue is hop-blocked", code == 200,
              str(inj)[:160])
        check("it is not itself blocked by the hop budget",
              inj.get("status") != "queued"
              or "hop" not in str(inj.get("waiting_reason") or "").lower(),
              f"{inj.get('status')} / {inj.get('waiting_reason')}")

        wait_until("the operator's message is delivered",
                   lambda: any(x.get("id") == entry_id and x.get("state") == "delivered"
                               for x in queue(A)) if entry_id else True)
        show_queues()

        blocked = [x for x in queued(A) if x["id"] == e["id"]]
        if blocked:
            code, rel = api("POST", f"/projects/{P}/queue/entries/{e['id']}/release")
            print(f"  release the hop-blocked entry -> {code}  {str(rel)[:200]}")
            check("release accepts an entry the hop budget is actually holding", code == 200,
                  str(rel)[:160])
            wait_until("the released entry is delivered",
                       lambda: any(x.get("id") == e["id"] and x.get("state") == "delivered"
                                   for x in queue(A)))
            after = [x for x in queue(A) if x["id"] == e["id"]]
            check("the released message was then delivered",
                  bool(after) and after[0].get("state") == "delivered",
                  repr(after and after[0].get("state")))
        else:
            print("  (the hop-blocked entry was already consumed; release not exercised)")

    print()
    print("=" * 78)
    print("ROW 6 — withdrawal from a live queue")
    print("=" * 78)
    # Withdrawal is only meaningful against a queue that is actually *holding*. The first version
    # of this file triggered an idle agent and withdrew immediately: the entry was delivered within
    # the same second and the 409 "already delivered/withdrawn" was recorded as a product failure.
    # So occupy the agent first, and withdraw the entry that queues behind the running turn.
    code, busy = api("POST", f"/projects/{P}/agent/trigger", {
        "agent": B, "session_mode": "new",
        "message": "Reply with only the word BUSY. Do not read or write any files.",
    })
    print(f"  occupying {B} -> {code} status={busy.get('status')!r}")
    code, extra = api("POST", f"/projects/{P}/agent/trigger", {
        "agent": B, "session_mode": "new",
        "message": "This message is withdrawn before delivery and must never be seen.",
    })
    wid = extra.get("queue_entry_id") if isinstance(extra, dict) else None
    print(f"  queued behind it: {wid} status={extra.get('status')!r} "
          f"reason={str(extra.get('waiting_reason'))[:50]!r}")
    if not check("the second message queued rather than starting",
                 extra.get("status") == "queued", str(extra.get("status"))):
        wid = None
    if wid:
        code, _ = api("DELETE", f"/projects/{P}/queue/entries/{wid}")
        print(f"  withdraw {wid} -> {code}")
        check("an entry the queue is holding can be withdrawn", code == 200, str(code))
        still = [x for x in queue(B) if x.get("id") == wid]
        check("the withdrawn entry is no longer queued",
              not still or still[0].get("state") != "queued",
              repr(still and still[0].get("state")))
        check("and it was never delivered",
              not still or still[0].get("state") != "delivered",
              repr(still and still[0].get("state")))

finally:
    wait_idle([A, B])
    restore()
    for agent in (A, B):
        for e in queued(agent):
            code, _ = api("DELETE", f"/projects/{P}/queue/entries/{e['id']}")
            print(f"  drained leftover {agent} entry {e['id']} -> {code}")
    print()
    print("=" * 78)
    print(f"SUMMARY — {len(FAILURES)} failure(s)")
    print("=" * 78)
    for label, detail in FAILURES:
        print(f"  FAIL {label}  {detail[:150]}")
