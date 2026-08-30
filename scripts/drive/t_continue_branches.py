"""Row 15 CHECKPOINTS -- the `continue` endpoint's REFUSAL and WAITING branches, never driven.

`t_row15_cutover.py` pressed Continue once, on a successor holding a checkpoint entry, and got
`started: true`. Every other branch of `POST /conversations/{id}/continue` was unreached: the route
returns `started = result.waiting_reason is None` (hub/hub/api/v1/checkpoints.py:274), and
`turn_scheduler.schedule_agent` has six distinct waiting reasons.

Two are reachable from the operator surface without inventing state:
  * "queue is empty"          -- press Continue when nothing is queued for the agent;
  * "agent is already running" -- press Continue while that agent is mid-turn.

The third thing driven here is not a branch but a seam. `continue` resolves the conversation only to
404 on it, then calls `schedule_agent(project_id, conversation.agent)` -- which schedules the
AGENT's next queued entry, whatever conversation that belongs to -- and then reports back
`"conversation_id": conversation_id`, the one the operator pressed. Whether those can differ is the
question; this asks the product rather than the code.

That seam was F131, and it was fixed on 2026-08-30. Step 4's assertions have been flipped to the
fixed direction; see the comment there. `started` no longer answers "did a turn begin for this
agent" -- it answers "did the conversation you named start" -- and the answer carries
`started_conversation_id` naming what did run.

Real surface only. No row inserts. Haiku turns. Exact status codes.
"""

import os
import sys
import time

from aw import api, show

P = os.environ.get("AW_PROJECT") or "proj-dc4d43543bea"
AGENT = os.environ.get("AW_AGENT") or "gamma"
HAIKU = os.environ.get("AW_RUNNER") or "runner-8d5eb04a4f25"

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
    c, b = api("GET", f"/projects/{P}/agents")
    if c != 200:
        return "?"
    for a in b:
        if a["name"] == name:
            return a["status"]
    return "?"


def wait_idle(name, limit=300):
    t0 = time.time()
    while time.time() - t0 < limit:
        s = agent_status(name)
        if s in ("idle", "error", "offline"):
            print(f"  settled after {int(time.time() - t0)}s: {name}={s}")
            return s
        time.sleep(4)
    print(f"  TIMEOUT after {limit}s: {name}={agent_status(name)}")
    return None


def conversations(lifecycle="all"):
    c, b = api("GET", f"/projects/{P}/conversations?lifecycle={lifecycle}")
    if c != 200:
        return []
    return b.get("conversations", []) if isinstance(b, dict) else b


def queue():
    c, q = api("GET", f"/projects/{P}/queue/{AGENT}")
    return q if isinstance(q, list) else []


def cont(conv_id, label):
    c, b = api("POST", f"/projects/{P}/conversations/{conv_id}/continue", {}, timeout=60)
    show(label, c, b)
    return c, b


def summarise():
    step("VERDICTS")
    bad = [v for v in VERDICTS if not v[1]]
    for label, ok, detail in VERDICTS:
        print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
    print(f"\n  {len(VERDICTS) - len(bad)}/{len(VERDICTS)} held")


def main():
    step("0. Baseline -- the agent is idle and its queue is empty")
    wait_idle(AGENT)
    q0 = [e for e in queue() if e.get("state") == "queued"]
    check("nothing queued for the agent to start with", not q0, str(q0)[:200])
    convs = [x for x in conversations("all") if x["agent"] == AGENT]
    if not convs:
        sys.exit("no conversation for this agent to press Continue on")
    spare = convs[0]["id"]

    step("1. Continue with an empty queue")
    c, b = cont(spare, "continue (empty queue)")
    check("returns exactly 200, not a refusal status", c == 200, str(c))
    check("it reports the turn did NOT start", b.get("started") is False, str(b.get("started")))
    check(
        "the waiting reason is named, not null",
        b.get("waiting_reason") == "queue is empty",
        repr(b.get("waiting_reason")),
    )
    check(
        "the agent stayed idle -- the press started nothing",
        agent_status(AGENT) == "idle",
        agent_status(AGENT),
    )

    step("2. Continue while that agent is mid-turn")
    before = {x["id"] for x in conversations("all")}
    c, t = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {
            "agent": AGENT,
            "message": "Create a file called CONT_ONE.txt whose entire contents are the single "
            "word CONTONE. Then STOP. Do not create any other file. "
            "End your reply with exactly: NEXT ACTION: create CONT_TWO.txt.",
            "overrides": {"permission_mode": "workspace"},
        },
        timeout=30,
    )
    show("trigger", c, t)
    if c != 200:
        sys.exit(f"trigger refused {c}")
    live = t.get("conversation_id")
    c, b = cont(live, "continue (agent already running)")
    check("returns exactly 200 while busy", c == 200, str(c))
    check("started is False while busy", b.get("started") is False, str(b.get("started")))
    check(
        "the waiting reason names the busy agent's state",
        b.get("waiting_reason") == "agent is already running",
        repr(b.get("waiting_reason")),
    )
    wait_idle(AGENT)

    step("3. Checkpoint the live conversation and cut over -- a queued entry for a NEW conversation")
    c, _ = api("PUT", f"/projects/{P}/settings", {"checkpoint_runner_id": HAIKU})
    check("checkpoint runner set", c == 200, str(c))
    c, cp = api("POST", f"/projects/{P}/conversations/{live}/checkpoint", {}, timeout=420)
    if c != 201:
        show("checkpoint", c, cp)
        check("checkpoint generated (201)", False, str(c))
        summarise()
        return
    check("checkpoint generated (exactly 201)", c == 201)
    c, co = api("POST", f"/projects/{P}/checkpoints/{cp['id']}/cutover", {})
    show("cutover", c, co)
    check("cutover returns exactly 200", c == 200, str(c))
    succ = co.get("successor_conversation_id")
    entry_id = co.get("queue_entry_id")
    queued = [e for e in queue() if e.get("state") == "queued"]
    check(
        "the successor's checkpoint entry is the only thing queued",
        [e.get("id") for e in queued] == [entry_id],
        str([(e.get("id"), e.get("conversation_id")) for e in queued]),
    )

    step("4. THE SEAM -- press Continue on a DIFFERENT conversation, one with nothing queued")
    print(f"  pressing on {spare}, while the queued entry belongs to {succ}")
    c, b = cont(spare, "continue (pressed on the wrong conversation)")
    check("returns exactly 200", c == 200, str(c))
    started = b.get("started")
    check(
        "the response names the conversation the operator PRESSED",
        b.get("conversation_id") == spare,
        repr(b.get("conversation_id")),
    )
    wait_idle(AGENT)
    left = [e for e in queue() if e.get("state") == "queued"]
    print(f"  started={started}  queue left={[e.get('id') for e in left]}")
    # F131, FIXED 2026-08-30 (openspec/changes/continue-starts-what-it-names). These four
    # assertions used to run in the opposite direction -- `started is True` and
    # `waiting_reason is None` -- because F131 wrote them "in the direction the product actually
    # behaves, so the day it is fixed they go red and say why". This is that day; the flip below
    # IS the fix, not a regression in the harness.
    #
    # What still holds unchanged: the OTHER conversation's queued entry is consumed, because the
    # fix deliberately did not change which turn runs. Only the answer changed.
    check(
        "F131: the press still started the OTHER conversation's queued work",
        not left,
        f"left={[e.get('id') for e in left]} pressed={spare} queued_for={succ}",
    )
    check(
        "F131: and it no longer reports success against the conversation that did nothing",
        started is False,
        f"started={started}, reported {b.get('conversation_id')}, ran {succ}",
    )
    check(
        "F131: the answer names the conversation that actually began",
        b.get("started_conversation_id") == succ,
        f"started_conversation_id={b.get('started_conversation_id')!r}, ran {succ}",
    )
    # This is the pressed conversation with NOTHING queued for it -- F131's own reproduction --
    # so "waiting behind other input" would report a queue position that does not exist.
    check(
        "F131: a conversation that queued nothing is not told its input is waiting",
        b.get("waiting_reason") == "this conversation had nothing queued",
        repr(b.get("waiting_reason")),
    )

    summarise()


if __name__ == "__main__":
    try:
        main()
    finally:
        api("PUT", f"/projects/{P}/settings", {"checkpoint_runner_id": None})
        print("\n[teardown] checkpoint_runner_id reset to null")
