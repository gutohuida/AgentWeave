# Design — Conversations continue

## Context

Peer delivery is resolved by `peer_bound_conversation` (`hub/hub/conversations.py:172`) on a single
condition: an open conversation owned by the recipient whose `bound_sender_conversation_id` equals
the sender's conversation. The binding is written once, when `hub/hub/api/v1/messages.py:196` mints
the recipient's thread, and it is only ever read in that one direction.

The row therefore records "B's thread `convB1` belongs to A's line of work `convA1`". When B replies
from `convB1`, the code asks "which conversation owned by A is bound to `convB1`?" — a question the
data cannot answer, because the link runs the other way. So it mints. Every reply does this, which
is why three messages produced three conversations.

Two constraints shape the fix.

**There is no predecessor→successor column on `Conversation`.** The columns are `sequence`, `id`,
`project_id`, `agent`, `provider_session_id`, `lifecycle`, `title`, `title_set_by_operator`,
`origin`, `runtime_overrides`, `bound_sender_conversation_id`, `bound_sender_agent`, `task_id`,
`checkpoint_warning`, and timestamps. A checkpoint cutover
(`hub/hub/checkpoint_cutover.py:91-110`) opens a successor and archives the predecessor, but the
only durable trace of the pairing is in `checkpoints` (`previous_checkpoint_id`, `lineage_id`) and
in a derived title prefix. Nothing on the conversation says what it continues.

**A cutover already breaks delivery in the forward direction, today.** The cutover copies
`bound_sender_conversation_id` to the successor, which keeps *inbound* traffic reaching the
recipient's current thread. It does nothing for the sender side: once A's own `convA1` is cut over
to `convA2`, A sends from a new id, no thread is bound to it, and A's next message to B mints a new
thread. This is a pre-existing defect of the same shape, and any reverse rule that ignores it would
be correct on paper and broken the first time a long exchange checkpoints.

## Goals / Non-Goals

**Goals:**

- A reply reaches the conversation it is replying to, in the ordinary case where two agents are
  corresponding.
- Continuity survives a checkpoint cutover on either side of the exchange.
- An agent can open a fresh thread on purpose, and only on purpose.
- Existing bound delivery is bit-for-bit unchanged where it already works.

**Non-Goals:**

- Repairing conversations already scattered by this defect.
- Group threads or multi-owner conversations. A conversation stays owned by one agent.
- Any heuristic that opens a thread on its own — no topic detection, no idle timeout, no length
  trigger.
- Changing the senderless binding (`bound_sender_agent`), which is a separate and correct contract.

## Decisions

### D1 — Resolve forward first, then reverse, then mint

Delivery for a message that names no recipient conversation resolves in this order:

1. **`start_new_thread` is true** → mint immediately, skipping both lookups.
2. **Forward** — an open conversation owned by the recipient, bound to the sender's line of work.
   This is today's rule, widened by D3.
3. **Reverse** — the conversation the sender's own thread is bound to, when that conversation is
   owned by the recipient. This is the new rule.
4. **Mint** — as today, binding the new thread to the sender's conversation.

Forward is tried first specifically so that **every case that resolves today resolves identically**.
The reverse lookup can only fire where the current code would have minted, which is exactly the
defect. That ordering is what makes this change safe to ship without a data migration.

*Alternative considered: reverse first.* Rejected — it changes established deliveries. Where both
could match, the forward binding is the thread the recipient is actively using for this line of
work, and preferring it preserves the "separate lines of work reach separate threads" guarantee
that the existing requirement is built on.

### D2 — The reverse rule, stated exactly

Let `src` be the sender's conversation. The reverse lookup succeeds when:

- `src.bound_sender_conversation_id` is set; **and**
- the conversation it names is owned by the recipient; **and**
- an open conversation exists in that conversation's lineage (D3).

Delivery goes to the newest open conversation in that lineage. It fails — and falls through to mint
— in every other case, including when the named conversation is owned by a third agent.

That third-agent condition is what makes the rule compose beyond two participants. Traced:

| Step | Forward | Reverse | Result |
|---|---|---|---|
| A(`convA1`) → B | miss | — | mint `convB1` bound `convA1` |
| B(`convB1`) → A | miss | `convB1`→`convA1`, owned by A ✓ | **`convA1`** |
| A(`convA1`) → B | hit `convB1` | — | `convB1` |
| B(`convB1`) → C | miss | `convB1`→`convA1`, owned by A ✗ | mint `convC1` bound `convB1` |
| C(`convC1`) → A | miss | `convC1`→`convB1`, owned by B ✗ | mint `convA2` bound `convC1` |
| A(`convA2`) → C | miss | `convA2`→`convC1`, owned by C ✓ | **`convC1`** |

A and C had no prior thread, so opening one is right; once they have one, both directions hold it.
The A↔B pair settles into a stable two-thread ping-pong, which is what "keep talking in the same
conversation" means when each participant owns their own side.

### D3 — A `lineage_id` column, not a predecessor walk

Both the forward and reverse rules need "the line of work", not "the conversation id", because a
cutover replaces the id. Add one column:

```
Conversation.lineage_id : str, indexed
```

Set to the conversation's own id at creation. A cutover successor inherits its predecessor's value.
Then:

- **Forward** matches `bound_sender_conversation_id IN (ids of conversations sharing src.lineage_id)`
  rather than `== src.id`. This fixes the pre-existing sender-side cutover break described in
  Context.
- **Reverse** resolves the named conversation's `lineage_id`, then takes the newest open
  conversation with that lineage owned by the recipient. No recursive walk, no successor pointer.

*Alternative considered: a `continues_conversation_id` predecessor pointer.* Rejected — it requires
a recursive walk on every delivery, and the walk is unbounded in a long-lived project. `lineage_id`
answers the same question with one indexed equality, and the codebase already uses exactly this
pattern on `checkpoints.lineage_id`.

*Alternative considered: derive lineage from `checkpoints` at query time.* Rejected — it makes a
routing decision depend on a join into checkpoint history, and a conversation with pruned
checkpoints would silently lose its lineage.

**Backfill:** existing rows get `lineage_id = id`. Past cutover chains are therefore not
reconstructed, which is consistent with the proposal's non-goal of repairing history. Deriving them
from `checkpoints` is possible and deliberately not done; a wrong guess would re-route live threads.

### D4 — `start_new_thread` is an explicit boolean on `send_message`

Default `False`. True mints a fresh recipient thread bound to the sender's conversation, which then
wins subsequent forward lookups because the newest binding is selected. No schema change is needed
for branching itself — the existing "newest bound thread" ordering already does the right thing.

*Alternative considered: a sentinel value on `conversation_id`.* Rejected — `conversation_id` names
a real conversation the sender chose, and overloading it with a magic string reads badly in the tool
schema, which is the agent's only documentation.

The flag is refused in combination with an explicit `conversation_id`: naming a thread and asking
for a new one are contradictory, and silently preferring one would hide a caller's mistake.

### D5 — A reply continues into an operator-origin thread

The reverse rule tests ownership and lifecycle, not `origin`. A delegation begun in an operator's
conversation returns to it, so one line of work stays in one place. The visible consequence is that
an operator's thread shows an inbound entry authored by an agent the operator never addressed.

**The correspondent is already visible in that thread, and attribution already works.** Checked
rather than assumed:

- `_message_to_timeline` (`hub/hub/api/v1/agent_chat.py:203-206`) already puts the delegating
  agent's *outbound* message into the operator's timeline as an `outbound_peer` entry. The third
  agent's name is therefore present today; this change adds the other half of an exchange whose
  first half is already on screen.
- `_queue_entry_to_timeline` (`agent_chat.py:171-180`) classifies any non-operator, non-job origin
  as `inbound_peer` and carries `participant = origin_agent`.
- `participantLabel` (`hub/ui/src/components/agents/AgentTimeline.tsx:738-745`) labels
  `operator_input` as "You", right-aligned, and `inbound_peer` with the sending agent's name,
  left-aligned; line 849 colours it by that agent's own colour.

So a continued reply cannot be mistaken for something the operator wrote, and needs no new
rendering. What remains is a judgement no test makes: whether a two-party thread that now carries a
*complete* third-party exchange still reads as the operator's conversation rather than as a log.

*Alternative considered: continue only into `origin: peer` threads.* Rejected by the operator — it
splits a single line of work across two conversations, which is the problem being fixed.

### D6 — `send_message`'s description is corrected in the same change

`hub/hub/mcp_server.py:191-194` tells agents that omitting `conversation_id` means "use their most
recent one". Recency delivery was removed when the binding contract shipped. Leaving a stale
description next to a new parameter would teach the wrong model of a surface this change is
specifically about. `mcp_server.py` may import only stdlib + fastmcp, and the flag is passed
straight through to the Hub, so nothing new is imported.

### D7 — The cutover fix stays in this change

The forward-direction cutover break is a **separate, pre-existing defect**. It predates the reply
defect, has nothing to do with replies, and the operator has never reported hitting it. Folding it
in roughly doubles the work and is what forces `lineage_id`, migration `0085`, and phases 1 and 2 of
seven. It was raised explicitly as a scope question and the operator chose to keep it.

The reason it belongs here: **both defects have one root cause.** Delivery is keyed on a conversation
identifier, and a conversation identifier is not stable across the thing the product does to long
conversations. The reply defect is that reading the key backwards is not implemented; the cutover
defect is that the key itself expires. Fixing only the first leaves the second at the same seam, and
the reverse rule would work right up until someone accepts a checkpoint mid-exchange — which is
precisely when a long exchange most needs it.

*Alternative considered: ship the reverse lookup and `start_new_thread` alone*, roughly 60 lines and
no schema change, and treat lineage as a follow-up. Rejected by the operator. Worth recording what
it would have cost rather than what it would have saved: the reverse rule would have shipped with a
known dead corner, and the scenario "Continuation survives the replying side's cutover" would have
had to be written as a non-goal instead of a requirement. A spec that carves out the case its own
mechanism cannot reach is harder to finish later than one that never claimed it.

Checkpointing is `offered` by default (`hub/hub/db/models.py:142`), not automatic, so the corner
needs an operator to accept a prompt. That is why it was a real question rather than an obvious one.

## Risks / Trade-offs

- **A reply lands somewhere the sender did not expect.** → The reverse rule only fires where a new
  thread would otherwise have been minted, so nothing moves from one existing thread to another.
  The worst case is a message in the thread it was replying to, which is the intent.

- **An operator's conversation gains traffic they did not send** (D5). → Accepted deliberately,
  and smaller than it first appears: the delegating agent's outbound message is already rendered in
  that thread, and inbound peer entries are already labelled and coloured by their sending agent
  (see D5). No rendering work is implied. The open part is legibility at length, not attribution.

- **`lineage_id` is wrong for pre-existing cutover chains**, since backfill sets it to `id`. → Those
  threads behave exactly as they do today: no better, no worse. No delivery that currently works
  starts failing, because the forward lookup on a self-lineage is equivalent to the current
  equality test.

- **Two agents ping-ponging in one thread pair could loop.** → Already bounded by the project's
  `hop_budget`, which this change does not touch. Continuity does not add a path that budget did
  not already govern.

- **The reverse lookup adds a row fetch per peer send.** → One indexed primary-key load of the
  sender's conversation, on a path that already writes a message, an entry and a queue row. Not
  measurable against that.

- **A long exchange now shares one context.** Continuing rather than branching means a thread grows
  where it used to reset. → This is the point, and checkpointing is the existing answer to a thread
  that grows too large. Worth watching, not worth pre-empting.

## Migration Plan

1. Add `Conversation.lineage_id` in `hub/hub/db/models.py`.
2. New migration in `hub/hub/migrations/versions/`, guarded for a missing table as `0033`/`0034`
   do, since an upgrade from an early revision reaches it with only that revision's tables.
   Backfill `lineage_id = id`, then index it.
3. Bump the head assertions in `hub/tests/test_migrations.py` **and**
   `hub/tests/test_project_persistence.py`.
4. Set `lineage_id` on conversation creation, and inherit it in `checkpoint_cutover.py`.
5. Widen the forward lookup to the lineage; add the reverse lookup; add `start_new_thread`.

**Rollback:** the migration's downgrade drops the column. The resolution change is additive — with
the column absent the forward lookup degrades to today's equality test — so reverting the code
without reverting the migration is safe in either order.

## Open Questions

1. Scope — whether the cutover fix belonged in this change at all. Answered by the operator: it
   stays. See D7.
2. Answered while writing D5: the entry is already distinguished — left-aligned, named for the
   sending agent, in that agent's colour, against the operator's right-aligned "You". The
   remaining question is one of density rather than attribution: at what length does a thread
   carrying a full third-party exchange stop being readable as the operator's own conversation?
   Task 6.6 is where that gets judged.
3. Answered by sweeping the `new_conversation` call sites. There are eight;
   `checkpoint_cutover.py:91` is the only one that inherits, and there is no second successor path
   — `agent_trigger.py` was checked for one and has none. The other seven each begin a genuinely
   new line of work: the peer mint (`messages.py:196`), an operator trigger
   (`agent_trigger.py:794`, `:806`), a loop firing (`scheduler.py:990`), an answered question
   (`questions.py:109`), reconstructed output (`output_recording.py:62`), and an agent request
   (`agents.py:1403`). `agent_trigger.py:800` already states the governing principle, about
   runtime overrides: *"a conversation the operator starts begins clean — they are looking at the
   composer and can choose."* Lineage follows the same rule.

   The sweep also found that `agents.py:1403` never sets `bound_sender_conversation_id`, which
   would split the requesting agent's first follow-up message into a second thread. It is **not**
   fixed here: that line is unreachable, because `request_agent` always fails earlier with a 400.
   See `openspec/explorations/2026-08-21-request-agent-cannot-succeed.md`.

4. Should `start_new_thread` be surfaced to the operator? **No** — answered while exploring.
   `agent-conversation-workspace` already requires that *"starting a conversation is a navigation
   action with a dedicated surface"* (spec.md:881), with the agent preselected, retargetable, and
   nothing persisted until the first message is sent. That is this capability, as a control the
   operator already has. An agent has no navigation surface at all, so the flag is its equivalent
   rather than a second way to do the same thing. Whether the operator should be able to force an
   *agent's* delegation into a new thread is a different question, and the answer is probably no:
   the agent knows whether it is starting a new line of work and the operator is not in that loop.
