"""Full-surface sweep, part 3: the inbound queue and the scheduler, without spending a turn.

Rows 6 and part of 19 of the coverage matrix. The trick that makes them free is the agent with no
runner bound: every trigger for it queues durably and nothing ever spawns, so the queue, the
scheduler's attribution, withdrawal, release and concurrent triggers are all reachable without a
single provider token.

That is also the population F108 deliberately does not touch — a refusal about the *environment*
keeps queuing so that performing the repair delivers it (F96) — which makes this file a second,
independent check on that boundary.

Run: AW_PROJECT=<proj> AW_KEY=<key> py -3.11 scripts/drive/t_sweep_queue.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api  # noqa: E402

AGENT = "unbound-driver"
RESULTS = []

# Three preconditions, each of which was silently false on a reused fixture and each of which
# changes what this file measures.
#
# 1. The agent must EXIST. `register` is idempotent, so calling it costs nothing.
# 2. It must be UNARCHIVED. An earlier drive left this name archived, and every trigger below then
#    answered 409 "…is archived" — three UNEXPECTED lines that read as a queue defect and were the
#    harness forgetting its own setup. `register` does not reopen an archived row.
# 3. It must have NO RUNNER. This is the premise the docstring above rests on: "nothing ever
#    spawns, so … not a single provider token". A later drive bound Haiku to this same name, and
#    the file went on claiming to be free while starting real turns — and, worse, silently swapped
#    what it was observing: the waiting_reason it reported was "agent is already running" rather
#    than the never-launchable case it exists to probe. Unbind, and refuse to continue if the
#    unbind did not take, rather than reporting on a situation that is not the one described.
api("POST", f"/projects/{P}/agents/register", {"name": AGENT, "contact_mode": "poll"})
api("POST", f"/projects/{P}/agents/{AGENT}/unarchive")
api("PATCH", f"/projects/{P}/agents/{AGENT}", {"runner_id": None})
_code, _roster = api("GET", f"/projects/{P}/agents")
_row = next(
    (a for a in (_roster if isinstance(_roster, list) else _roster.get("agents", []))
     if a.get("name") == AGENT),
    None,
)
if _row is None or _row.get("runner_id") is not None:
    print(f"REFUSING TO RUN: {AGENT} still has runner_id={_row and _row.get('runner_id')!r}. "
          "Every probe below would spend real provider turns and measure the wrong queue state.")
    sys.exit(1)
print(f"precondition ok: {AGENT} exists, is open, and has no runner bound")


def probe(row, label, method, path, body=None, expect=None):
    code, out = api(method, path, body)
    ok = expect is None or code in (expect if isinstance(expect, tuple) else (expect,))
    detail = out.get("detail") if isinstance(out, dict) else None
    if isinstance(detail, dict):
        detail = detail.get("message")
    RESULTS.append((row, label, code, ok, detail if isinstance(detail, str) else None))
    print(f"[{row}] {label}: {code}{'' if ok else '  <-- UNEXPECTED'}")
    if isinstance(detail, str):
        print(f"      refusal: {detail[:260]}")
    elif not ok:
        print(f"      body: {json.dumps(out, default=str)[:300]}")
    return code, out


def queue_state(label):
    code, out = api("GET", f"/projects/{P}/queue/{AGENT}/status")
    print(f"      {label}: waiting={out.get('waiting_count')} "
          f"attempts={out.get('delivery_attempts')} reason={str(out.get('waiting_reason'))[:70]!r}")
    return out


print("=" * 78)
print("ROW 6 — the inbound queue: durable entries, attribution, withdrawal, release")
print("=" * 78)

code, listing = probe(6, "read the queue", "GET", f"/projects/{P}/queue/{AGENT}", expect=200)
entries = listing if isinstance(listing, list) else listing.get("entries", [])
print(f"      entries already queued: {len(entries)}")

code, first = probe(6, "queue a message", "POST", f"/projects/{P}/agent/trigger",
                    {"agent": AGENT, "message": "first", "session_mode": "new"}, expect=200)
e1 = first.get("queue_entry_id") if isinstance(first, dict) else None
conv1 = first.get("conversation_id") if isinstance(first, dict) else None
print(f"      entry={e1} conversation={conv1}")
print(f"      status said: {str(first.get('status'))!r} / {str(first.get('waiting_reason'))[:80]!r}")
queue_state("after one")

code, second = probe(6, "queue a second, same conversation", "POST",
                     f"/projects/{P}/agent/trigger",
                     {"agent": AGENT, "message": "second", "conversation_id": conv1}, expect=200)
e2 = second.get("queue_entry_id") if isinstance(second, dict) else None
queue_state("after two")

code, third = probe(6, "queue a third in a NEW conversation", "POST",
                    f"/projects/{P}/agent/trigger",
                    {"agent": AGENT, "message": "third", "session_mode": "new"}, expect=200)
e3 = third.get("queue_entry_id") if isinstance(third, dict) else None
conv3 = third.get("conversation_id") if isinstance(third, dict) else None
print(f"      entry={e3} conversation={conv3}")
print("      Does the third request get told about ITS OWN input, or the first conversation's?")
print(f"      waiting_reason: {str(third.get('waiting_reason'))[:140]!r}")
print(f"      conversation_id returned: {conv3!r}  (must be this request's own, not {conv1!r})")

queue_state("after three")

if e2:
    probe(6, "withdraw the second entry", "DELETE", f"/projects/{P}/queue/entries/{e2}",
          expect=200)
    probe(6, "withdraw it again", "DELETE", f"/projects/{P}/queue/entries/{e2}")
    queue_state("after withdrawing one")
probe(6, "withdraw an entry that does not exist", "DELETE",
      f"/projects/{P}/queue/entries/entry-nope")
if e1:
    probe(6, "release the first entry (it is not hop-blocked)", "POST",
          f"/projects/{P}/queue/entries/{e1}/release")
probe(6, "read queue settings", "GET", f"/projects/{P}/queue/settings", expect=200)
probe(6, "queue status for an agent that does not exist", "GET",
      f"/projects/{P}/queue/ghost-agent/status")

print()
print("=" * 78)
print("ROW 19 (part) — two concurrent triggers for one agent")
print("=" * 78)
import concurrent.futures  # noqa: E402


def fire(n):
    return api("POST", f"/projects/{P}/agent/trigger",
               {"agent": AGENT, "message": f"concurrent {n}", "session_mode": "new"})


with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    outcomes = list(pool.map(fire, range(4)))
for i, (code, out) in enumerate(outcomes):
    eid = out.get("queue_entry_id") if isinstance(out, dict) else None
    cid = out.get("conversation_id") if isinstance(out, dict) else None
    print(f"  trigger {i}: {code} entry={eid} conversation={cid}")
# Drop the Nones first. A refused trigger returns no id at all, and counting those as duplicates
# made four identical 409s read as "TWO REQUESTS WERE GIVEN THE SAME QUEUE ENTRY" — an alarm about
# collision raised by an absence of anything to collide.
ids = [o.get("queue_entry_id") for _, o in outcomes if isinstance(o, dict) and o.get("queue_entry_id")]
convs = [o.get("conversation_id") for _, o in outcomes if isinstance(o, dict) and o.get("conversation_id")]
print(f"  distinct entries: {len(set(ids))} of {len(ids)}   "
      f"distinct conversations: {len(set(convs))} of {len(convs)}")
if len(ids) != len(outcomes):
    print(f"  <-- ONLY {len(ids)} OF {len(outcomes)} CONCURRENT TRIGGERS WERE ACCEPTED")
if len(set(ids)) != len(ids):
    print("  <-- TWO REQUESTS WERE GIVEN THE SAME QUEUE ENTRY")
if len(set(convs)) != len(convs):
    print("  <-- TWO 'session_mode: new' REQUESTS SHARED A CONVERSATION")
queue_state("after four concurrent")

# Drain on the way out. Nothing will ever deliver these — the agent has no runner, which is the
# whole premise — so every run used to leave another six behind, and the next run's "entries
# already queued" line grew without anyone deciding it should.
_drained = 0
_, _leftover = api("GET", f"/projects/{P}/queue/{AGENT}")
for _entry in (_leftover if isinstance(_leftover, list) else _leftover.get("entries", [])) or []:
    if _entry.get("state") == "queued":
        api("DELETE", f"/projects/{P}/queue/entries/{_entry['id']}")
        _drained += 1
print(f"
drained {_drained} leftover entr{'y' if _drained == 1 else 'ies'} for {AGENT}")

print()
print("=" * 78)
print("SUMMARY")
print("=" * 78)
for row, label, code, ok, detail in RESULTS:
    if not ok:
        print(f"  UNEXPECTED [{row}] {label} -> {code}  {(detail or '')[:120]}")
print("done")
