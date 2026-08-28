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
ids = [o.get("queue_entry_id") for _, o in outcomes if isinstance(o, dict)]
convs = [o.get("conversation_id") for _, o in outcomes if isinstance(o, dict)]
print(f"  distinct entries: {len(set(ids))} of {len(ids)}   "
      f"distinct conversations: {len(set(convs))} of {len(convs)}")
if len(set(ids)) != len(ids):
    print("  <-- TWO REQUESTS WERE GIVEN THE SAME QUEUE ENTRY")
if len(set(convs)) != len(convs):
    print("  <-- TWO 'session_mode: new' REQUESTS SHARED A CONVERSATION")
queue_state("after four concurrent")

print()
print("=" * 78)
print("SUMMARY")
print("=" * 78)
for row, label, code, ok, detail in RESULTS:
    if not ok:
        print(f"  UNEXPECTED [{row}] {label} -> {code}  {(detail or '')[:120]}")
print("done")
