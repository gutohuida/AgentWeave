"""Full-surface sweep, part 4: conversations, continuation and checkpoints.

Rows 5 and 15 of the coverage matrix, as far as they reach without spawning a provider run. The
probe agent is bound to no runner, so every trigger queues durably and nothing is ever started —
which is enough to exercise conversation lifecycle, lineage, renaming, the continue affordance and
every checkpoint refusal.

Run: AW_PROJECT=<proj> AW_KEY=<key> py -3.11 scripts/drive/t_sweep_conversations.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api  # noqa: E402

AGENT = "conv-probe"
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


api("POST", f"/projects/{P}/agents/register", {"name": AGENT, "contact_mode": "poll"})

print("=" * 78)
print("ROW 5 — conversations: lifecycle, lineage, renaming, continuation")
print("=" * 78)
code, out = probe(5, "start a conversation", "POST", f"/projects/{P}/agent/trigger",
                  {"agent": AGENT, "message": "first message", "session_mode": "new"}, expect=200)
conv = out.get("conversation_id")
entry = out.get("queue_entry_id")
print(f"      conversation={conv}")

probe(5, "list this agent's conversations", "GET", f"/projects/{P}/agent/{AGENT}/conversations",
      expect=200)
probe(5, "read its chat", "GET", f"/projects/{P}/agent/{AGENT}/chat/{conv}", expect=200)
probe(5, "rename it", "PATCH", f"/projects/{P}/agent/{AGENT}/conversations/{conv}",
      {"title": "Renamed by the sweep"}, expect=200)
probe(5, "rename it to an empty title", "PATCH",
      f"/projects/{P}/agent/{AGENT}/conversations/{conv}", {"title": ""})
probe(5, "read a conversation that does not exist", "GET",
      f"/projects/{P}/agent/{AGENT}/chat/conv-nope")
probe(5, "archive it while input is still queued", "POST",
      f"/projects/{P}/agent/{AGENT}/conversations/{conv}/archive")
probe(5, "continue it (nothing can launch)", "POST",
      f"/projects/{P}/conversations/{conv}/continue")
probe(5, "continue a conversation that does not exist", "POST",
      f"/projects/{P}/conversations/conv-nope/continue")

probe(5, "withdraw the entry", "DELETE", f"/projects/{P}/queue/entries/{entry}", expect=200)
probe(5, "archive it now the queue is empty", "POST",
      f"/projects/{P}/agent/{AGENT}/conversations/{conv}/archive", expect=200)
probe(5, "send to the archived conversation", "POST", f"/projects/{P}/agent/trigger",
      {"agent": AGENT, "message": "after archive", "conversation_id": conv})
probe(5, "unarchive it", "POST", f"/projects/{P}/agent/{AGENT}/conversations/{conv}/unarchive",
      expect=200)
probe(5, "archive it twice", "POST", f"/projects/{P}/agent/{AGENT}/conversations/{conv}/archive",
      expect=200)
probe(5, "and again", "POST", f"/projects/{P}/agent/{AGENT}/conversations/{conv}/archive")

print()
print("=" * 78)
print("ROW 15 — checkpoints")
print("=" * 78)
probe(15, "list checkpoints for the conversation", "GET",
      f"/projects/{P}/conversations/{conv}/checkpoints", expect=200)
probe(15, "write a checkpoint for an archived conversation", "POST",
      f"/projects/{P}/conversations/{conv}/checkpoint")
probe(15, "write a checkpoint for a conversation that does not exist", "POST",
      f"/projects/{P}/conversations/conv-nope/checkpoint")
probe(15, "render a checkpoint that does not exist", "GET",
      f"/projects/{P}/checkpoints/ckpt-nope/rendered")
probe(15, "cut over to a checkpoint that does not exist", "POST",
      f"/projects/{P}/checkpoints/ckpt-nope/cutover")
probe(15, "dismiss a warning on a conversation that does not exist", "POST",
      f"/projects/{P}/conversations/conv-nope/dismiss-checkpoint-warning")

print()
print("=" * 78)
print("SUMMARY")
print("=" * 78)
for row, label, code, ok, detail in RESULTS:
    if not ok:
        print(f"  UNEXPECTED [{row}] {label} -> {code}  {(detail or '')[:130]}")

REMEDY = ("try", "use ", "first", "instead", "bind", "create", "reassign", "unarchive", "correct",
          "wait", "set ", "remove", "valid", "must", "should", "run ", "choose", "available",
          "one of", "already", "reopen", "close", "cannot", "stop it")
print()
print("4xx refusals whose message names no remedy:")
for row, label, code, _ok, detail in RESULTS:
    if detail and 400 <= code < 500 and not any(w in detail.lower() for w in REMEDY):
        print(f"  [{row}] {code} {label}: {detail[:170]}")
