"""Leg 6.2 -- an obstructed agent workspace holds the operator's message instead of destroying it.

F188: `POST /agent/trigger` and every `Continue` after it counted a delivery attempt against the
queue head even when the refusal was "I could not prepare *your own* workspace" -- a condition no
number of retries can clear. Three attempts and the operator's message was withdrawn with an
`abandoned_reason` claiming three failed deliveries.

This blocks `.agentweave/worktrees/<agent>` with a plain directory, sends one message, and presses
the conversation's Continue button three times -- four delivery opportunities against a limit of
three. The message must still be queued, at zero attempts, and the queue must tell the operator
what to remove.

    AW_HUB=http://127.0.0.1:8011 AW_PROJECT=... AW_AGENT=... AW_ROOT=... \
        py -3.11 scripts/drive/t_ablocked_p6_held.py
"""

import os
import pathlib
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api, show  # noqa: E402

DB = os.environ["AW_DB"]
AGENT = os.environ["AW_AGENT"]
ROOT = pathlib.Path(os.environ["AW_ROOT"])
BLOCK = ROOT / ".agentweave" / "worktrees" / AGENT

ok = []


def check(label, condition, detail=""):
    ok.append(bool(condition))
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}{('  -- ' + detail) if detail else ''}")


def read(entry_id):
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    row = conn.execute(
        "SELECT state, delivery_attempts, abandoned_reason, waiting_reason "
        "FROM inbound_queue_entries WHERE id = ?",
        (entry_id,),
    ).fetchone()
    conn.close()
    return row


print("=== the obstruction an operator can actually create ===")
BLOCK.mkdir(parents=True, exist_ok=True)
(BLOCK / "notes.txt").write_text("something the operator left here\n", encoding="utf-8")
print(f"  plain directory at {BLOCK} (not a git worktree, not a symlink)")

print()
print("=== the message ===")
code, out = api(
    "POST",
    f"/projects/{P}/agent/trigger",
    {"agent": AGENT, "message": "please summarise calc.py in one sentence", "session_mode": "new"},
)
show("POST /agent/trigger", code, out, limit=900)
conv, entry = out.get("conversation_id"), out.get("queue_entry_id")
check("the request was accepted, not refused", code == 200, f"HTTP {code}")
state, attempts, abandoned, waiting = read(entry)
print(f"  after the trigger: state={state!r} attempts={attempts}")
print(f"  waiting_reason: {waiting}")

print()
print("=== three clicks of Continue ===")
for click in range(1, 4):
    code, body = api("POST", f"/projects/{P}/conversations/{conv}/continue")
    time.sleep(0.6)
    state, attempts, abandoned, waiting = read(entry)
    started = body.get("started") if isinstance(body, dict) else None
    print(f"  click {click}: HTTP {code} started={started!r} -> state={state!r} attempts={attempts}")

print()
print("=== what the operator is left holding ===")
state, attempts, abandoned, waiting = read(entry)
check("the message is STILL QUEUED", state == "queued", f"state={state!r}")
check("no delivery attempt was counted", attempts == 0, f"attempts={attempts}")
check("nothing was abandoned", abandoned is None, f"abandoned_reason={abandoned!r}")

code, status = api("GET", f"/projects/{P}/queue/{AGENT}/status")
show("GET /queue/{agent}/status", code, status, limit=1400)
screen = (status or {}).get("waiting_reason") if isinstance(status, dict) else None
check("the queue screen names the workspace that failed", bool(screen) and "own workspace" in screen)
check("the queue screen names the directory to remove", bool(screen) and str(BLOCK) in screen,
      f"looking for {BLOCK}")
check("the queue screen states the remedy", bool(screen) and "rm -r" in screen)
check("the queue screen promises the prune that follows", bool(screen) and "prune" in (screen or ""))

code, entries = api("GET", f"/projects/{P}/queue/{AGENT}")
if isinstance(entries, list):
    print(f"--- GET /queue/{AGENT}: {len(entries)} entries")
    for e in entries:
        print(f"    {e.get('id')} state={e.get('state')!r} attempts={e.get('delivery_attempts')}")

print()
print(f"6.2: {sum(ok)}/{len(ok)}")
print(f"AW_CONV_A={conv}")
print(f"AW_ENTRY_A={entry}")
