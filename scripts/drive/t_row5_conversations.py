"""Row 5 — conversations, driven with two real agent turns.

`t_sweep_conversations.py` covers this row's *API* half against an agent that can never launch:
lifecycle, refusals, archive, rename. What it cannot reach is everything that only exists once a
provider has actually replied — the generated title, the chat transcript, and whether a second
message lands in the *same* conversation the first one built. Those are the three things an operator
means by "conversation", and none of them is observable without spending a turn.

Two Haiku turns, per the standing directive to bind a cheap model for every real drive turn. What
this file asserts is that the thread holds together, not that the agent writes anything good: turn 1
plants a codeword, turn 2 is asked for it back. If turn 2 answers, the provider session carried
across the trigger boundary; if it does not, the two turns were separate conversations wearing one
id.

Preconditions are checked, not assumed — see F137. The agent must exist, be open, and have a runner
bound, which is the *opposite* of `t_sweep_queue.py`'s premise and just as easy to get silently wrong.

Run: AW_HUB=... AW_KEY=... AW_PROJECT=... [AGENT=driver] [DRIVE_TAG=xyz] py -3.11 \
         scripts/drive/t_row5_conversations.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api  # noqa: E402

AGENT = os.environ.get("AGENT", "driver")
TAG = os.environ.get("DRIVE_TAG", "r5")
CODEWORD = f"TANGERINE-{TAG.upper()}"

POLL_SECONDS = 4
WAIT_LIMIT = 45  # ~180s

FAILURES = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAILURES.append((label, detail))
    return ok


def roster_row(name):
    _, body = api("GET", f"/projects/{P}/agents")
    for row in body if isinstance(body, list) else body.get("agents") or []:
        if row.get("name") == name:
            return row
    return None


def wait_idle(limit=WAIT_LIMIT):
    for _ in range(limit):
        row = roster_row(AGENT)
        if row is None or row.get("status") != "running":
            return True
        time.sleep(POLL_SECONDS)
    return False


def conversation(conv_id):
    _, body = api("GET", f"/projects/{P}/agent/{AGENT}/conversations")
    for row in body if isinstance(body, list) else []:
        if row.get("id") == conv_id:
            return row
    return None


def transcript(conv_id):
    """The conversation's timeline.

    The chat route returns `entries`, not `messages`, and each carries a `kind`
    (`operator_input` / `inbound_peer` / `agent_output` / …) rather than a chat `role`
    (`agent_chat.py:177`, `agent_chat.py:637-642`). Guessing the OpenAI-shaped
    `{"messages": [{"role": ...}]}` here read every completed turn as an empty transcript —
    which is what "an agent that never replied" looks like, so the first version of this file
    would have reported a live, correct conversation as broken.
    """
    _, body = api("GET", f"/projects/{P}/agent/{AGENT}/chat/{conv_id}")
    return (body.get("entries") if isinstance(body, dict) else body) or []


def replies(entries):
    """Only what the operator would read as the agent speaking.

    `agent_output` also carries `output_kind: "thinking"` and the run's completion notice; the
    visible answer is the `text` one.
    """
    return [e for e in entries
            if e.get("kind") == "agent_output" and e.get("output_kind") == "text"]


def wait_for_reply(conv_id, min_replies, limit=WAIT_LIMIT):
    for i in range(limit):
        entries = transcript(conv_id)
        if len(replies(entries)) >= min_replies:
            print(f"  reply {min_replies} after ~{i * POLL_SECONDS}s")
            return entries
        time.sleep(POLL_SECONDS)
    print(f"  TIMEOUT waiting for agent reply {min_replies}")
    return transcript(conv_id)


def text_of(entry):
    val = entry.get("content")
    return val if isinstance(val, str) else ""


# --------------------------------------------------------------------------- preconditions
row = roster_row(AGENT)
if row is None:
    print(f"REFUSING TO RUN: agent {AGENT!r} is not on this project's roster.")
    sys.exit(1)
if row.get("lifecycle") == "archived":
    api("POST", f"/projects/{P}/agents/{AGENT}/unarchive")
    row = roster_row(AGENT)
if not row.get("runner_id"):
    print(f"REFUSING TO RUN: agent {AGENT!r} has no runner bound. Every turn below would only "
          "queue, and this file would report a conversation defect for a roster one.")
    sys.exit(1)
print(f"precondition ok: {AGENT} is open and bound to {row['runner_id']} "
      f"({row.get('display_model')})")
if not wait_idle():
    print(f"REFUSING TO RUN: {AGENT} is still running an earlier turn.")
    sys.exit(1)

print()
print("=" * 78)
print("ROW 5 — turn 1: a new conversation, and the title the Hub gives it")
print("=" * 78)

code, out = api("POST", f"/projects/{P}/agent/trigger", {
    "agent": AGENT,
    "session_mode": "new",
    "message": (
        f"Remember this codeword for later in our conversation: {CODEWORD}. "
        "Reply with only the two characters OK. Do not read or write any files, "
        "and do not use any tools."
    ),
})
conv = out.get("conversation_id") if isinstance(out, dict) else None
print(f"  trigger -> {code}  conversation={conv}  status={out.get('status')!r}")
check("trigger accepted and named a conversation", code == 200 and bool(conv), str(out)[:200])
if not conv:
    sys.exit(1)

entries = wait_for_reply(conv, 1)
for m in entries:
    print(f"    [{m.get('kind')}/{m.get('output_kind')}] {text_of(m)[:110]!r}")
check("the operator's own message is in the transcript",
      any(e.get("kind") == "operator_input" and CODEWORD in text_of(e) for e in entries))
check("the agent replied", len(replies(entries)) >= 1,
      f"{len(entries)} entries, {len(replies(entries))} visible replies")

wait_idle()
row1 = conversation(conv)
print(f"  title={row1.get('title')!r}  set_by_operator={row1.get('title_set_by_operator')}  "
      f"origin={row1.get('origin')!r}  psid={str(row1.get('provider_session_id'))[:8]}")
check("the conversation has a title", bool(row1.get("title")))
check("the title is not marked operator-set", row1.get("title_set_by_operator") is False)
check("a provider session was recorded", bool(row1.get("provider_session_id")))
psid1 = row1.get("provider_session_id")

print()
print("=" * 78)
print("ROW 5 — the operator renames it, then speaks again")
print("=" * 78)

NEW_TITLE = f"Operator's own name {TAG}"
code, _ = api("PATCH", f"/projects/{P}/agent/{AGENT}/conversations/{conv}", {"title": NEW_TITLE})
row2 = conversation(conv)
check("rename accepted", code == 200, str(code))
check("the new title is what the operator typed", row2.get("title") == NEW_TITLE,
      repr(row2.get("title")))
check("renaming flips title_set_by_operator", row2.get("title_set_by_operator") is True,
      repr(row2.get("title_set_by_operator")))

code, out2 = api("POST", f"/projects/{P}/agent/trigger", {
    "agent": AGENT,
    "conversation_id": conv,
    "message": ("What was the codeword I gave you earlier? Reply with only the codeword, "
                "nothing else. Do not read or write any files."),
})
conv2 = out2.get("conversation_id") if isinstance(out2, dict) else None
print(f"  trigger -> {code}  conversation={conv2}  status={out2.get('status')!r}")
check("the second message stayed in the same conversation", conv2 == conv,
      f"{conv2} != {conv}")

entries2 = wait_for_reply(conv, 2)
new_entries = entries2[len(entries):]
for m in new_entries:
    print(f"    [{m.get('kind')}/{m.get('output_kind')}] {text_of(m)[:110]!r}")
wait_idle()

tail = " ".join(text_of(m) for m in replies(new_entries))
check("the agent still knows the codeword — the provider session carried across the trigger",
      CODEWORD in tail.upper(), tail[:160])

row3 = conversation(conv)
check("the operator's title survived the next turn", row3.get("title") == NEW_TITLE,
      repr(row3.get("title")))
check("still marked operator-set", row3.get("title_set_by_operator") is True)
print(f"  psid before={str(psid1)[:8]}  after={str(row3.get('provider_session_id'))[:8]}")
check("the conversation kept one provider session",
      row3.get("provider_session_id") == psid1,
      f"{psid1} -> {row3.get('provider_session_id')}")

print()
print("=" * 78)
print("ROW 5 — what the conversation list says about it now")
print("=" * 78)
print(f"  attention={row3.get('attention')!r}  lifecycle={row3.get('lifecycle')!r}  "
      f"updated_at={row3.get('updated_at')}")
usage = row3.get("context_usage") or {}
print(f"  context_usage: status={usage.get('status')!r} percent={usage.get('percent')} "
      f"model={usage.get('model')!r}")
check("the conversation is idle again", row3.get("attention") == "idle",
      repr(row3.get("attention")))
check("context usage was measured for it", usage.get("status") == "measured",
      repr(usage.get("status")))

print()
print("=" * 78)
print(f"SUMMARY — {len(FAILURES)} failure(s)")
print("=" * 78)
for label, detail in FAILURES:
    print(f"  FAIL {label}  {detail[:150]}")
print(f"conversation: {conv}")
