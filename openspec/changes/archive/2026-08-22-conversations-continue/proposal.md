# Conversations continue

## Why

A reply between two agents opens a new conversation instead of continuing the one it is replying
to. Measured on the trial Hub, three messages between `speccer` and `builder` produced three
conversations, and a later exchange in the same session produced three more:

```
speccer  conv-527bb75d ──▶ builder  conv-3b97a7d3   (new)
builder  conv-3b97a7d3 ──▶ speccer  conv-e4afb6f5   (new — not conv-527bb75d)
speccer  conv-e4afb6f5 ──▶ builder  conv-ae90c8a5   (new — not conv-3b97a7d3)
```

The cause is that the binding is one-directional. `peer_bound_conversation`
(`hub/hub/conversations.py:172`) resolves delivery on
`Conversation.bound_sender_conversation_id == <the sender's conversation>`. When B replies, B is
writing from its own conversation, whose id is not what A's thread was bound to, so the lookup
misses and `hub/hub/api/v1/messages.py:196` mints another conversation. The link needed to find the
original is already stored on the row; nothing reads it backwards.

This is not a missing feature. `hub/hub/checkpoint_cutover.py` already does the thing that is
*supposed* to open a successor thread — a checkpoint exists, the successor has been given it, and
the predecessor is closed. Peer messaging is opening threads outside the one mechanism meant to
open them, so "when does a new conversation start" is answered in two places that do not know about
each other.

It degrades every multi-agent run today: an exchange that reads as one conversation to a human is
scattered across unrelated threads, and each new thread starts without the history of the exchange
it belongs to.

## What Changes

- **A peer reply continues the conversation it is replying to.** Before minting, delivery resolves
  the binding in reverse: if the sender's own conversation is bound to an open conversation
  belonging to the recipient, the message is delivered there.
- **The reverse resolution survives a checkpoint cutover.** A cutover copies the forward binding to
  the successor (`checkpoint_cutover.py:108-110`) but leaves correspondents' rows pointing at the
  archived predecessor. Conversations gain a `lineage_id`, so delivery matches a *line of work*
  rather than a single conversation id. **This adds a column and a migration.** It also fixes a
  pre-existing break in the forward direction — today an agent sending from a successor opens a new
  thread at the handover, independently of this defect.
- **An agent can branch deliberately.** `send_message` gains `start_new_thread: bool = False`.
  Omitted or false continues; true opens a fresh thread and binds it. This is the "or someone says
  it explicitly" half of the operator's rule, which has no mechanism today.
- **A reply continues into an operator-origin thread.** Delegation started from an operator's
  conversation returns to that conversation rather than opening a peer thread beside it.
- `send_message`'s docstring is corrected: it still tells agents `conversation_id` unset means
  "use their most recent one" (`hub/hub/mcp_server.py:191-194`), which the binding contract
  replaced. It has been describing recency-based delivery since that behaviour was removed.
- **An outbound peer message renders folded, showing its subject.** The same send is already
  announced twice — once as an `agentweave.send_message` tool row, once as a full-content bubble —
  and in a conversation where an agent delegates repeatedly the bubbles crowd out the agent's own
  replies. The fold shows the recipient and the message's `subject`, which `send_message` already
  requires as a short summary line and which `_message_to_timeline`
  (`hub/hub/api/v1/agent_chat.py:203-208`) currently discards. Inbound messages are unchanged.

### Non-Goals

- **Not changing what happens when a sender names `conversation_id` explicitly.** That path already
  addresses a chosen thread and is refused on an archived one; it keeps both behaviours.
- **Not merging existing scattered conversations.** Threads already split by this defect stay
  split. Repair is a corpus-editing problem, not a routing one.
- **Not changing the senderless binding.** Hub- and scheduler-originated traffic keys on sender
  identity and gets one durable thread per source; that is a different contract and it is correct.
- **Not introducing conversation-level participant lists or group threads.** A conversation stays
  owned by exactly one agent; continuity is about which existing thread a message reaches. The
  alternative — one shared room every participant sees, with several agents contributing to a spec
  at once — was raised while specifying this and deliberately deferred; see
  `openspec/explorations/2026-08-21-the-shared-room.md`. Two-thread continuity is a precondition
  for it rather than a detour around it.
- **Not folding inbound peer messages, or turns.** Only the outbound half folds. A turn's folded
  state stays the operator's, per the existing requirement that it is never derived from position.
- **Not auto-branching on any heuristic** — no topic detection, no idle timeout, no length trigger.
  A new thread starts on a cutover or on an explicit request, and on nothing else.

## Capabilities

### New Capabilities

None. This completes an existing contract rather than introducing a new surface.

### Modified Capabilities

- `agent-conversation-workspace`: the queue-routing contract (spec.md:959) currently defines
  delivery in one direction only — "a peer message that names no recipient conversation SHALL be
  delivered to the recipient conversation bound to the sending conversation, creating that binding
  on first use". It gains the reverse rule, the explicit-branch escape, and the cutover case.
- `agent-conversation-handoff`: a cutover must keep correspondents reaching the line of work across
  the handover in *both* directions, not only the forward one it preserves today.
- `agent-tool-surface`: `send_message` gains a parameter, and its description of delivery is
  currently wrong.
- `agent-conversation-workspace` also gains the outbound fold. It sits beside the existing
  requirement that a **turn's** folded state is never derived from position (spec.md:594); a peer
  message is not a turn, and the new requirement says so rather than leaving the two to be read as
  contradictory.

## Impact

**Code**

- `hub/hub/conversations.py` — `peer_bound_conversation` gains reverse resolution.
- `hub/hub/api/v1/messages.py:184-201` — the mint-on-miss branch becomes mint-on-miss-after-reverse,
  and honours `start_new_thread`.
- `hub/hub/db/models.py` — `Conversation` gains `lineage_id`. No lineage column exists today;
  cutover lineage is only recoverable indirectly through `checkpoints.previous_checkpoint_id`.
  design.md D3 explains why a lineage key beats a predecessor pointer.
- `hub/hub/migrations/versions/` — one new migration, guarded for a missing table.
- `hub/hub/checkpoint_cutover.py` — the successor inherits its predecessor's `lineage_id`.
- `hub/hub/mcp_server.py` — the `send_message` parameter and its corrected docstring. This file is
  spawned standalone and may import only stdlib + fastmcp; the parameter is passed through to the
  Hub, so nothing new is imported.
- `hub/hub/schemas/` — the message-create schema carries the new flag.
- `hub/hub/api/v1/agent_chat.py` — `TimelineEntry` carries `subject`; `_message_to_timeline` stops
  discarding it.
- `hub/ui/src/components/agents/AgentTimeline.tsx` — the outbound branch of `MessageEntry` folds.
  `WorkRow` in the same file is the established pattern for a folded row with an inline truncated
  detail and an expand.
- `hub/ui/src/api/agentChat.ts` — the `TimelineEntry` type gains `subject`.

**Tests**

- `hub/tests/test_migrations.py` and `hub/tests/test_project_persistence.py` — head assertions bump.
- The mcp_server/Hub agreement test that asserts the two restatements match.

**Behaviour**

Existing bound threads keep working: the forward lookup is tried first and is unchanged, so a
sender's second message on an established line still lands where it does today. The reverse lookup
only fires where the code currently mints, which is the defect. No data migration is needed for
conversations already scattered — they are simply left alone.
