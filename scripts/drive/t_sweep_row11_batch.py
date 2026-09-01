"""SWEEP ROW 11, second half — a BATCH of questions, and whether the answers arrive together.

The operator plane is driven in `t_sweep_row11_questions.py`. This file drives the half that
cannot be reached from it: `POST /agent-actions/questions/batch` is agent-authenticated, and
`POST /projects/{id}/questions` leaves `batch_id` NULL, so **the only way to make a batch is a
real agent turn calling `ask_user` with more than one question.**

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... AW_PROJECT=proj-... py -3.11 t_sweep_row11_batch.py

What is under test is the design `2026-08-13-answers-arrive-together` (D1/D2) and
`2026-08-11-declining-a-question` (D2), neither of which any existing harness touches:

* a batch shares one `batch_id`, is ordered by `batch_index`, and every row reports `batch_size`;
* answering **part** of a batch delivers nothing — waking the agent on the first answer while the
  operator is still deciding the rest is the interruption batching exists to prevent;
* a **decline can complete a batch**, and then the answers already given are delivered;
* the delivered text names the declined one rather than omitting it, because "the operator passed"
  and "this was never asked" call for opposite behaviour (D4).

`blocking=False` deliberately. A blocking batch is held open by `ask_user`'s own poll loop and the
answers come back as the tool's result, so the queue delivery path — the one this file is about —
is skipped by design (`asker_still_waiting`). Asking non-blocking lets the run end, which is
exactly the state in which delivery is the only way the answers can reach anyone.

One real agent turn on `claude-haiku-4-5` per run, per the standing cheap-runner directive. No job
is created, so there is nothing to leave enabled.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

P = os.environ.get("AW_PROJECT", "")
if P in ("proj-5e960453", "proj-18e5d4e0") or not P:
    print("REFUSING TO RUN: set AW_PROJECT to a drive project.")
    sys.exit(1)
AGENT = os.environ.get("AGENT_A", "asker")
A = f"/projects/{P}"
TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")

PASS, FAIL = [], []


def ok(label, cond, detail=""):
    (PASS if cond else FAIL).append(label)
    print(
        ("  ok   " if cond else "  FAIL ")
        + label
        + (f"  -- {detail}" if detail and not cond else "")
    )


def note(label, value):
    print(f"  ..   {label}: {value}")


def leg(n, title):
    print(f"\n=== LEG {n}: {title}")


def open_batches():
    """Every question in this project that belongs to a batch, grouped by batch id."""
    code, rows = api("GET", f"{A}/questions?limit=1000")
    if not isinstance(rows, list):
        return {}
    groups = {}
    for row in rows:
        if row.get("batch_id"):
            groups.setdefault(row["batch_id"], []).append(row)
    return groups


def queue_for_agent():
    code, entries = api("GET", f"{A}/queue/{AGENT}")
    return entries if isinstance(entries, list) else []


def deliveries():
    """Queue entries that are a batch DELIVERY, not this harness's own trigger message.

    The marker is in the trigger text as well — it has to be, since the prompt is what tells the
    agent to use it — so matching the marker alone counts our own input as a delivery and turns
    leg 3 green-into-red on our own doing. Row 10 nearly manufactured a finding the same way. A
    delivery is identified by what only `_batch_delivery_text` writes.
    """
    out = []
    for e in queue_for_agent():
        content = e.get("content") or ""
        if MARK not in content or content == MESSAGE:
            continue
        if "Answer:" in content or "Declined" in content or "You asked" in content:
            out.append(e)
    return out


MARK = f"r11b-{TAG}"

# =============================================================================================
leg(1, "A real turn asks three questions in one `ask_user` call")

before = set(open_batches())
qbefore = len(queue_for_agent())
note("batches already in this project", len(before))
note("queue entries already waiting for the agent", qbefore)

# Written to make the *shape* of the call unambiguous while leaving the content trivial: this
# harness asserts that a batch of three exists and how it is delivered, never that the questions
# are good ones. The mark is what scopes every later assertion to this run.
MESSAGE = (
    f"Call the ask_user tool exactly once, with blocking set to false and with THREE questions "
    f"in the questions list. Give each one a header, multi_select false, and two options. "
    f"Start every question's text with the marker {MARK}- followed by first, second or third, "
    f"like '{MARK}-first: ...'. Ask about the colour of a button, the name of a file, and the "
    f"order of two menu items — the content does not matter. After the tool returns, reply with "
    f"the single word: asked. Do not do anything else and do not wait for answers."
)
t0 = time.time()
code, run = api(
    "POST",
    f"{A}/agent/trigger",
    {"agent": AGENT, "message": MESSAGE, "overrides": {"permission_mode": "workspace"}},
    timeout=60,
)
ok("the turn started", code == 200, f"{code} {str(run)[:300]}")
RUN_ID = run.get("run_id") or run.get("id") if isinstance(run, dict) else None
note("run id", RUN_ID)

batch_id, rows = None, []
while time.time() - t0 < 240:
    groups = open_batches()
    fresh = {k: v for k, v in groups.items() if k not in before}
    for k, v in fresh.items():
        if any(MARK in r.get("question", "") for r in v):
            batch_id, rows = k, sorted(v, key=lambda r: r.get("batch_index", 0))
            break
    if batch_id:
        break
    time.sleep(3)

ok(
    "a batch appeared, so the agent really did ask several questions at once",
    batch_id is not None,
    f"none after {int(time.time() - t0)}s — the model may not have called ask_user; "
    f"nothing below can be read if this is red",
)
if not batch_id:
    print(f"\n=== ROW 11 (batch): {len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAIL  {f}")
    sys.exit(0)

note("batch id", batch_id)
note("questions in it", [r["id"] for r in rows])
note("seconds to first question", int(time.time() - t0))

# =============================================================================================
leg(2, "What one batch looks like on the wire")

ok("it holds three questions", len(rows) == 3, str(len(rows)))
ok(
    "they share one batch id",
    len({r.get("batch_id") for r in rows}) == 1,
    str({r.get("batch_id") for r in rows}),
)
ok(
    "batch_index is 0,1,2 — the order the agent asked in",
    [r.get("batch_index") for r in rows] == list(range(len(rows))),
    str([r.get("batch_index") for r in rows]),
)
ok(
    "every row reports the size of the batch it belongs to",
    all(r.get("batch_size") == len(rows) for r in rows),
    str([r.get("batch_size") for r in rows]),
)
ok(
    "all three are attributed to the asking agent",
    all(r.get("from_agent") == AGENT for r in rows),
    str({r.get("from_agent") for r in rows}),
)
ok(
    "asked non-blocking, none of them is blocking",
    all(r.get("blocking") is False for r in rows),
    str([r.get("blocking") for r in rows]),
)
ok(
    "each carries the options the schema forces",
    all(len(r.get("options") or []) >= 2 for r in rows),
    str([len(r.get("options") or []) for r in rows]),
)

# The run has to be over before delivery is even possible; `asker_still_waiting` is what the
# delivery path checks. Stated rather than assumed.
#
# Read off the agent roster, not off a run: MEASURED against this Hub's own `/openapi.json`, there
# is no operator route that lists or fetches a run by id, so the roster's `status` is the only
# operator-visible fact about whether a turn is still going.
deadline = time.time() + 180
agent_status = None
while time.time() < deadline:
    code, roster = api("GET", f"{A}/agents")
    hit = [a for a in roster if a.get("name") == AGENT] if isinstance(roster, list) else []
    if hit:
        agent_status = hit[0].get("status")
        if agent_status != "running":
            break
    time.sleep(3)
note("the asking agent's status", agent_status)
ok(
    "precondition: the asking turn has ended, so nobody is holding the tool call open",
    agent_status not in (None, "running"),
    repr(agent_status),
)

# =============================================================================================
leg(3, "Answering PART of a batch must deliver nothing")

q1, q2, q3 = rows[0]["id"], rows[1]["id"], rows[2]["id"]

code, a1 = api("PATCH", f"{A}/questions/{q1}", {"answer": "the first one", "labels": []})
ok("the first question is answered", code == 200, f"{code} {str(a1)[:200]}")
time.sleep(2)
delivered = deliveries()
note("queue entries mentioning this batch after 1 of 3", len(delivered))
ok(
    "answering 1 of 3 queues nothing — the operator is still deciding (D1)",
    not delivered,
    f"{len(delivered)} entry(ies): {json.dumps(delivered)[:300]}",
)

code, a2 = api("PATCH", f"{A}/questions/{q2}", {"answer": "the second one", "labels": []})
ok("the second question is answered", code == 200, f"{code} {str(a2)[:200]}")
time.sleep(2)
delivered = deliveries()
note("queue entries mentioning this batch after 2 of 3", len(delivered))
ok(
    "answering 2 of 3 still queues nothing",
    not delivered,
    f"{len(delivered)} entry(ies): {json.dumps(delivered)[:300]}",
)

# =============================================================================================
leg(4, "A DECLINE completes the batch, and the answers already given are released")

code, d3 = api("POST", f"{A}/questions/{q3}/decline", None)
ok("the third question is declined", code == 200, f"{code} {str(d3)[:200]}")
ok("...and it is recorded as declined, not answered", d3.get("declined") is True and d3.get("answered") is False, str(d3)[:200])

entry = None
deadline = time.time() + 60
while time.time() < deadline:
    hits = deliveries()
    if hits:
        entry = hits[0]
        break
    time.sleep(2)

ok(
    "the decline released the two answers the operator HAD given (D2)",
    entry is not None,
    "nothing was queued — a part-answered batch closed by a decline stranded real answers",
)
if entry is None:
    print(f"\n=== ROW 11 (batch): {len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAIL  {f}")
    sys.exit(0)

text = entry.get("content") or ""
print("\n--- what the agent is told:\n" + text[:1200] + "\n---")
ok("exactly one entry, not one per answer", len(deliveries()) == 1, str(len(deliveries())))
ok("it says how many were asked", "3 questions" in text, text[:200])
ok("it carries the first answer", "the first one" in text, text[:300])
ok("it carries the second answer", "the second one" in text, text[:300])
ok(
    "the declined one is NAMED rather than omitted (D4)",
    "Declined" in text,
    "an agent cannot tell 'the operator passed' from 'this was never asked', and those call for "
    "opposite behaviour",
)
ok(
    "the questions are restated in the order they were asked",
    text.find(rows[0]["question"][:40]) < text.find(rows[1]["question"][:40]) < text.find(rows[2]["question"][:40]),
    f"{text.find(rows[0]['question'][:40])}, {text.find(rows[1]['question'][:40])}, "
    f"{text.find(rows[2]['question'][:40])}",
)
ok("it reaches the agent as operator input at depth zero", entry.get("hop_depth") == 0, repr(entry.get("hop_depth")))
ok("...attributed to the operator, not to another agent", entry.get("origin_type") == "operator", repr(entry.get("origin_type")))
ok("...and addressed to the agent that asked", entry.get("agent") == AGENT, repr(entry.get("agent")))

# Which thread the answers land in. `_deliver_batch_if_complete` reuses the agent's latest open
# conversation and only opens a new one when there is none — and `name_conversation` is a
# documented no-op on a thread that already has a title. So the "named from the first question"
# rule can only be READ on a thread the answer path itself created, which is not this one: this
# run's turn opened the thread and titled it from the trigger message. Recorded as a measurement
# rather than asserted, because asserting it here would be asserting against the harness's own
# setup. The route is `/agent/{agent}/conversations`, MEASURED off `/openapi.json` — there is no
# project-level `/conversations/{id}`.
conv = entry.get("conversation_id")
note("conversation the answers landed in", conv)
code, threads = api("GET", f"{A}/agent/{AGENT}/conversations")
listed = threads if isinstance(threads, list) else (threads or {}).get("conversations") or []
hit = [c for c in listed if c.get("id") == conv]
note("its title", repr(hit[0].get("title")) if hit else "not listed")
ok(
    "the answers land in an existing open thread rather than opening a second one",
    bool(hit),
    f"{conv} is not among the agent's {len(listed)} conversations",
)
ok(
    "...and that thread already carries a title, so the operator can find it",
    bool(hit) and bool(hit[0].get("title")),
    f"title={hit[0].get('title')!r}" if hit else "-",
)

# =============================================================================================
leg(5, "After delivery: what the two operator-facing lists say about a resolved batch")

code, unanswered = api("GET", f"{A}/questions?answered=false&limit=1000")
still_open = [r["id"] for r in unanswered if r.get("batch_id") == batch_id] if isinstance(unanswered, list) else []
note("rows of this batch still in the 'Unanswered' list", still_open)
ok(
    "a fully resolved batch has left the Unanswered list",
    not still_open,
    f"{still_open} — the declined row is resolved and delivered, and is still returned by "
    f"?answered=false, which is what QuestionsPanel renders as Unanswered",
)

print(f"\n=== ROW 11 (batch): {len(PASS)} passed, {len(FAIL)} failed")
for f in FAIL:
    print(f"  FAIL  {f}")
