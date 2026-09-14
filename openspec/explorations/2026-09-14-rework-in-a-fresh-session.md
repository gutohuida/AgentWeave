# Rework in a fresh session

**2026-09-14, day window, I-1 brief 1 of 11.** This is an improvement brief, not a proposal: there
is no change directory and no tasks. Source: `spec-queue/observations/2026-09-14-LoopEngine.md`,
`## Improvements` item 1 and `#### dev` item 1. The figures come from that file, from the `:8000`
database read `mode=ro`, and from the agents' transcripts.

## What we saw

`dev` (Sonnet 5) cost $114.21 over 99 runs. Almost none of that was work the model produced.
- **Cache reads were 316.7 M of its 323.2 M tokens.** Output was 1.7 M.
- **Eight long runs carried 58% of it.** They lasted 13–35 minutes and made 125–294 API calls each.
- **Context grew on every call, with nothing to stop it.** Every fresh session started at 41–45 k
  tokens and the long ones reached 290–547 k. Each call re-read all of it, and no `dev` transcript
  shows a compaction.
- **206.5 M tokens were in sessions spanning more than one run.** `task-d8d4b03d722b` alone took
  86.6 M ($23.80) over seven runs, with its author's session carried through three review rounds to
  428 k.

**How rework reaches the author, measured for this brief.** Across `dev`'s 27 multi-run sessions,
every continuation run that did work (18 of them) was woken by a peer message: 11 from the Architect
(some carrying several entries), 6 from `tester` and 1 from `dev_2`. The other 22 continuations
failed with no delivered entry: they were quota-wall re-spawns (F355).
- A peer message resumes the recipient's conversation (`peer_bound_conversation`, then
  `reply_bound_conversation`: `hub/hub/api/v1/messages.py:222-249`, `hub/hub/conversations.py:200-299`).
- The conversation carries its `provider_session_id`, and a turn resumes whatever is there
  (`hub/hub/api/v1/agent_trigger.py:752-753`).
- So "your evidence was rejected, fix it" lands on the end of the longest session the author has.

**The existing guard could not fire.** The project's checkpoint mode was `offered` at the default
80%-of-window threshold (`hub/hub/checkpoint_policy.py:27-28`). Sonnet 5's window is 1 M tokens
(`model_catalog.py:157-160`), so the offer comes at 800 k. `dev`'s peak was 547 k. The project had
no token budget (`Project.token_budget` is nullable, `db/models.py:82`).

## What would change

An autonomous turn would not resume a conversation that is already expensive to re-read. Past a
size the operator sets, a peer-delivered or rework turn opens a successor conversation, briefed from
the author's checkpoint and the message that woke it, as the automatic cutover already does for
context pressure (`checkpoint_cutover.py:109-144`). The operator's own conversations are untouched.
The threshold means "this is getting costly", not "this is nearly full". The Hub already has a unit
for that, a token count (`THRESHOLD_MODES = ("percent", "tokens")`, `checkpoint_policy.py:21`).

## Why it matters

It helps every operator whose flows run on large-window models: the context never fills, so the
existing guard never trips, and the bill grows faster than the session, because each call re-reads
everything before it. On LoopEngine, a cutover at 150 k would have cut short every session that
reached 290–547 k. How much of the 206.5 M it would have saved is **not measured**: that needs
replaying each session's per-call context against a cutover point. That is cheap to do from
`turn_usage` and should be R1's first step.

## Rough cost — a code-read estimate

- **Files:**
  - `hub/hub/checkpoint_trigger.py` and `checkpoint_cutover.py`, the cutover;
  - `hub/hub/checkpoint_policy.py`, a separate threshold for autonomous turns or a changed default;
  - the delivery path in `hub/hub/turn_scheduler.py` or `agent_trigger.py`, which decides between
    resume and new *before* spawning, where today's trigger reacts to a context reading after one;
  - `hub/hub/checkpoint_handover.py`, which already produces the author's checkpoint when a run
    ends `completed` with notes.
- **Capabilities:** `openspec/specs/conversation-checkpoint` (*"Automatic checkpointing is
  configured as a threshold…"*), `agent-conversation-handoff`, and possibly `usage-accounting`.
- **Migration:** likely one. That is a project and agent column if autonomous turns get their own
  threshold. None if only the default changes.
- **UI:** a setting beside the existing checkpoint threshold, which means a bundle.
- **Not in `mcp_server.py`.**

## Risks and open questions

- **A fresh session loses what the author knew.** The successor is only as good as its checkpoint.
  On LoopEngine the checkpoint machinery was shaky: 7 of 14 probes failed (F360), and
  `submit_checkpoint_notes` failed 23 of 36 calls (F364). Those two should land first, or the
  cheaper rework is also the worse one.
- **Which turns count as autonomous rework** is the operator's call: every peer delivery, only
  `revision_needed` and rejection messages, or any non-operator turn?
- **Percent or tokens by default.** A tokens default would change behaviour for every existing
  project that has `automatic` checkpoints.
- **Unverified:** whether the harness's own auto-compaction, near 95%, ever fires on a 1 M-token
  window before the turn ends. No `dev` transcript shows one.

## The decision, in one line

Approve a spec loop, after F360 and F364 are built, for *an autonomous turn does not resume a
session past a cost threshold*. R1 starts by replaying `dev`'s sessions to measure what it would
have saved.
