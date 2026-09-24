# Proposal — why queued input waits is told truthfully

**Round 1, 2026-09-24** (bundle B1, spec track S1's queue half). Findings: **F361 (B)** and
**F289 (C)**. Both re-verified by reading on HEAD `404c7d5`. **Nothing here is implemented yet.**

Independent of `a-task-is-attended-only-by-a-turn-that-will-reach-it`: no shared function, no
shared file except that both read `inbound_queue.project_limits`. Either can ship first.

## Why

**F361 — a peer message past the hop budget is suspended, and its sender is told it was sent.**
`create_message_for_actor` queues the entry at `hop_depth = source_run.turn_depth + 1`
(`hub/hub/api/v1/messages.py:77`), emits `queue_chain_suspended` when that exceeds the budget
(`:299-314`), and returns the message as usual (`:319`). The agent route returns it as a plain
`MessageResponse` (`api/v1/agent_actions.py:201-224`; the schema has no delivery field,
`schemas/messages.py:52-65`), and the MCP tool builds its own reply,
`{"success": True, "message_id": …}` (`hub/hub/mcp_server.py:244`). Unchanged since filing
(`git log -S` on that line finds only the file's first commit, `c8cec11`).
On `:8000` 20 of 21 suspended chains sat 2–13 hours; on `LoopEngine_2` the entry that would have
started the next task was one of them, and every sender had been told success.

The operator is not blind: the recipient's timeline derives `hop_budget_exceeded`
(`api/v1/agent_chat.py:218`) and shows *"Autonomous continuation paused … reached the hop budget.
Continue …"* (`hub/ui/src/components/agents/AgentTimeline.tsx:388-399`), and the queue status
derives *"hop budget exhausted"* when every entry is past it (`api/v1/inbound_queue.py:136-137`).
What nobody is told is the **sender** — the one agent that thinks the work moved on.

**F289 — the queue status repeats a remembered refusal as the present reason.** When no live check
answers, `GET /queue/{agent}/status` falls back to the stored `waiting_reason` of the first entry
that has one (`inbound_queue.py:172-178`, the `next(...)` at `:178`); its own comment concedes it is *"a record of the last
attempt, which a repair since then may already have cleared"*. For a D8 checkout refusal
(`agent_trigger.py:990-1001`) the sentence names a holder and a task, so it reads as a live
measurement. Measured at filing: 6m15s of *"d1a090658 is already running a turn on task …"* while
d1a's own status said it ran nothing.

**Changed shape since filing.** F288 (the crash path that left the refusal stranded) was fixed on
2026-09-23: reconciliation now re-drains every agent with queued input. So the measured window is
mostly closed; the route's claim is still unmarked memory, and any refusal whose condition clears
without a re-drain (a transient refusal cleared by the operator; a counted refusal whose cause is
repaired) still reads as present.

## What Changes

- **A held send says so** (design D1). `create_message_for_actor` returns whether the entry it
  queued is past the budget. The send routes' response gains `held_by_hop_budget: Optional[bool]`
  and `delivery_note: Optional[str]`, set only by the two send routes; the MCP `send_message` reply adds both when held. The note names
  the depth and the budget and what would deliver it, and does not suggest a resend.
- **No `waiting_reason` is written onto the held entry** (design D2). ROUNDS.md's sketch said
  "a written `waiting_reason`"; this change writes the reason to the **sender**, and leaves the entry
  derived, because a stored copy outlives a budget the operator raises.
- **The checkout-holder reason is checked now** (design D3). The status route asks
  `tasks_held_by_a_running_turn` for the task the turn would be bound to, whose checkout id comes
  from `takes_own_checkout` on the task row alone, gated by the trigger's own
  `worktrees.takes_task_workspace`, and names the holder only while it holds. It spawns none of the
  gate's raw git calls, and any failure inside the check falls through to the labelled fallback
  (review 2026-09-24, `spec-queue/tracks/reviews/B1-2026-09-24.md` §4).
- **The fallback is labelled as the last attempt's** (design D4): *"the last delivery attempt was
  refused: …"*.

## Capabilities

### New Requirements

- `agent-tool-surface` — *A message the hop budget holds is reported to its sender as not delivered*.
- `agent-conversation-workspace` — *An agent's queue status presents a remembered refusal as a
  record of the last attempt*.

## Impact

- `hub/hub/api/v1/messages.py` (`create_message_for_actor` and `create_message`),
  `hub/hub/api/v1/agent_actions.py` (`send_peer_message`), `hub/hub/schemas/messages.py`
  (`MessageResponse`: two optional fields, default `None`, so a listed message says nothing
  rather than a false `False`).
- `hub/hub/mcp_server.py` (`send_message` reply). **This file is spawned fresh on every agent turn,
  including `:8000`'s** (`.claude/rules/mcp-server.md`), so the reply change reaches the operator's
  live agents on commit. It is additive: `success` and `message_id` are unchanged. The tool reads
  one more JSON field; no import is added.
- `hub/hub/api/v1/inbound_queue.py` (`get_queue_status`).
- No migration, no UI bundle.
- **Neighbour, same file:** bundle B11's `input-the-hub-accepted-is-answered-as-accepted` wraps the
  `schedule_agent` call at the end of `create_message_for_actor` (`messages.py:318`). This change edits
  that function's return value two lines below it. Whichever is built second rebases onto the
  other; neither changes the other's behaviour.
