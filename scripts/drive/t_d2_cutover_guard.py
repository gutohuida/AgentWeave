"""D-2: drive the night's F126 cutover guard (3142a91) independently, over real HTTP.

The night wrote the guard, its tests and its own drive. That drive pressed the button three times
in a row from one client and asked what the route returned. This one asks the three questions that
sequence cannot reach:

1. **The remedy the refusal names.** The 409 says "if it was archived by hand, unarchive it
   first". Do exactly that to a conversation whose checkpoint is *spent*, then press again.
2. **Two presses at once.** The finding's own account of how this happens in the wild is "a
   retried request after a network timeout" and "a second browser tab" — concurrent, not
   sequential. The guard reads `predecessor.lifecycle` and writes later in the same coroutine.
3. **A legitimate chain still works.** A guard that refuses too much would break handing a
   successor over in turn, which is the feature.

Setup is `setup_d2_cutover.py`. Nothing here binds a runner or spends a turn.
"""

import json
import os
import sqlite3
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("AW_HUB", "http://127.0.0.1:8011")
os.environ.setdefault("AW_KEY", "aw_live_d2drive0000000000000000000")

from aw import api, show  # noqa: E402

P = "proj-d2drive"
AGENT = "delta"
V = []


def check(label, ok, detail=""):
    V.append((label, bool(ok), detail))
    print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))


def convs():
    c, b = api("GET", f"/projects/{P}/conversations?lifecycle=all")
    if c != 200:
        return []
    return b.get("conversations", []) if isinstance(b, dict) else b


def _db():
    return sqlite3.connect(os.environ["AW_DB"])


def successors_of(lineage_id):
    """The successor rows of one lineage.

    Counted from the row store rather than from `GET /conversations`, which does not carry
    `lineage_id` in its payload -- every press is still real HTTP; only the tally is read here,
    because "two successors of one predecessor" is a statement about rows.
    """
    with _db() as c:
        return [
            {"id": r[0], "title": r[1], "lifecycle": r[2], "lineage_id": r[3]}
            for r in c.execute(
                "SELECT id,title,lifecycle,lineage_id FROM conversations "
                "WHERE origin='handoff' AND lineage_id=?",
                (lineage_id,),
            )
        ]


def checkpoint_entries_for(conversation_ids):
    with _db() as c:
        return [
            {"id": r[0], "conversation_id": r[1]}
            for r in c.execute(
                "SELECT id,conversation_id FROM inbound_queue_entries WHERE origin_type='checkpoint'"
            )
            if r[1] in conversation_ids
        ]


def cutover(ckpt):
    return api("POST", f"/projects/{P}/checkpoints/{ckpt}/cutover", {})


# ---------------------------------------------------------------- probe 1
print("\n=== 1. the refusal names a remedy: unarchive, then press again ===")
CK1 = sys.argv[1]
CONV1 = "conv-d2-unarchive"

c1, b1 = cutover(CK1)
check("first cutover 200", c1 == 200, str(c1))
print(f"  first successor: {b1.get('successor_conversation_id') if isinstance(b1, dict) else b1}")

c2, b2 = cutover(CK1)
detail = b2.get("detail") if isinstance(b2, dict) else str(b2)
check("second cutover 409 (the night's result, reproduced independently)", c2 == 409, str(c2))
check(
    "and the refusal tells the operator to unarchive it first",
    isinstance(detail, str) and "unarchive it first" in detail,
    repr(detail)[:160],
)

cu, bu = api("POST", f"/projects/{P}/agent/{AGENT}/conversations/{CONV1}/unarchive", {})
check("the remedy the refusal names is reachable over HTTP", cu == 200, str(cu))
check(
    "and it reopens the predecessor",
    isinstance(bu, dict) and bu.get("lifecycle") == "open",
    str(isinstance(bu, dict) and bu.get("lifecycle")),
)

c3, b3 = cutover(CK1)
show("cutover after following the refusal's own advice", c3, b3)
second_successor = b3.get("successor_conversation_id") if isinstance(b3, dict) else None
succ1 = successors_of(CONV1)
entries1 = checkpoint_entries_for({s["id"] for s in succ1})
check(
    "THE PROBE: the spent checkpoint is still refused after the remedy",
    c3 == 409,
    f"status {c3}, successor {second_successor}",
)
check(
    "exactly one successor exists for this lineage",
    len(succ1) == 1,
    str([s["id"] for s in succ1]),
)
check(
    "exactly one checkpoint queue entry -- no second billed delivery",
    len(entries1) == 1,
    str([(e["id"], e["conversation_id"]) for e in entries1]),
)
# What the operator actually sees in the navigation tree, over the list route rather than the
# row store, because two rows only matter if two conversations show up.
visible = [c for c in convs() if c.get("origin") == "handoff"
           and c.get("title") == "Continued: Ship the parser"]
check(
    "the operator's conversation list shows one continuation, not two identically titled ones",
    len(visible) == 1,
    str([(c["id"], c["title"], c["lifecycle"]) for c in visible]),
)
if len(succ1) > 1:
    print(f"      titles: {sorted({s['title'] for s in succ1})}")
    print(f"      lineage: {[s['lineage_id'] for s in succ1]}")

# ---------------------------------------------------------------- probe 2
print("\n=== 2. two presses at once on one unspent checkpoint ===")
CK2 = sys.argv[2]
CONV2 = "conv-d2-race"
results = {}


def press(n):
    results[n] = cutover(CK2)


threads = [threading.Thread(target=press, args=(n,)) for n in range(2)]
for t in threads:
    t.start()
for t in threads:
    t.join()

codes = sorted(r[0] for r in results.values())
for n, (code, body) in sorted(results.items()):
    print(f"  press {n}: {code} {json.dumps(body, default=str)[:200]}")
succ2 = successors_of(CONV2)
entries2 = checkpoint_entries_for({s["id"] for s in succ2})
check("one press succeeded", codes.count(200) == 1, str(codes))
check(
    "the other was refused (409), not accepted and not a 500",
    codes.count(409) == 1,
    str(codes),
)
check(
    "THE PROBE: exactly one successor after two simultaneous presses",
    len(succ2) == 1,
    str([s["id"] for s in succ2]),
)
check(
    "and exactly one checkpoint queue entry",
    len(entries2) == 1,
    str([(e["id"], e["conversation_id"]) for e in entries2]),
)
if len(succ2) > 1:
    print(f"      titles: {[s['title'] for s in succ2]}")

# ---------------------------------------------------------------- probe 3
print("\n=== 3. a real chain: hand the successor over in turn ===")
CK3 = sys.argv[3]
CONV3 = "conv-d2-chain"
c4, b4 = cutover(CK3)
check("first hop 200", c4 == 200, str(c4))
hop1 = b4.get("successor_conversation_id") if isinstance(b4, dict) else None

seed = os.popen(
    f'py -3.11 "{os.path.join(os.path.dirname(os.path.abspath(__file__)), "setup_d2_cutover.py")}" '
    f'"{os.environ["AW_DB"]}" ckpt {hop1}'
).read()
print(f"  seeded a checkpoint on the successor: {seed.strip()}")
ck_hop2 = json.loads(seed.strip().splitlines()[-1])["checkpoint"]

c5, b5 = cutover(ck_hop2)
show("second hop", c5, b5)

# Fixture artefact, not a defect: nothing here runs a turn, so the successor's own checkpoint
# entry is still `queued`, and `archivable`'s undelivered-entry refusal fires before the new
# guard is ever reached. Withdrawing the entry stands in for the run that would have consumed
# it, and isolates the guard from a refusal that predates it.
if c5 == 409 and "waiting to be delivered" in str(b5):
    with _db() as c:
        stranded = [
            r[0]
            for r in c.execute(
                "SELECT id FROM inbound_queue_entries WHERE conversation_id=? AND state='queued'",
                (hop1,),
            )
        ]
    for entry_id in stranded:
        rc, _ = api("DELETE", f"/projects/{P}/queue/entries/{entry_id}")
        print(f"  withdrew {entry_id} [{rc}] -- standing in for the run that would consume it")
    c5, b5 = cutover(ck_hop2)
    show("second hop, with nothing left undelivered", c5, b5)

hop2 = b5.get("successor_conversation_id") if isinstance(b5, dict) else None
check("THE PROBE: the guard does not refuse a legitimate second hop", c5 == 200, str(c5))
chain = successors_of(CONV3)
check("the chain is two successors long", len(chain) == 2, str([s["id"] for s in chain]))
titles = {s["id"]: s["title"] for s in chain}
check(
    "and the title did not stack prefixes",
    all("Continued: Continued:" not in (t or "") for t in titles.values()),
    str(titles),
)
check(
    "each hop stayed in the one lineage",
    all(s["lineage_id"] == CONV3 for s in chain),
    str([s.get("lineage_id") for s in chain]),
)
firsts = [s for s in chain if s["id"] == hop1]
check(
    "the first successor is archived by its own cutover",
    bool(firsts) and firsts[0]["lifecycle"] == "archived",
    str(firsts and firsts[0]["lifecycle"]),
)
check(
    "the second hop's successor is the one just minted, still open",
    any(s["id"] == hop2 and s["lifecycle"] == "open" for s in chain),
    str([(s["id"], s["lifecycle"]) for s in chain]),
)

print("\n=== VERDICTS ===")
bad = [v for v in V if not v[1]]
for label, ok, d in V:
    print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {d}" if d else ""))
print(f"\n  {len(V) - len(bad)}/{len(V)} held")
sys.exit(1 if bad else 0)
