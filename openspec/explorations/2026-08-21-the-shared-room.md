# Exploration — The shared room: one conversation, many agents (2026-08-21)

**Status:** PINNED. Not scheduled, deliberately. Raised while specifying
`conversations-continue`; the operator chose the two-thread model for now and asked to keep this.

## Where it came from

Specifying "a reply should continue the conversation" forced a question that had never been asked
out loud: when two agents talk, is that **one** conversation or **two**?

`conversations-continue` answers *two* — each agent owns its own thread, and the two are stably
bound so an exchange stops scattering. That is a routing fix on the model AgentWeave already has.

The operator's reaction named the other model, and it is not a smaller idea:

> "The would be more like multiplayer programing where every message hits every agent and everyone
> communicates as 1. That is a cool concept. Maybe we could implement something like this. Then when
> doing specs or programing you can have multiple agents pitching in. But that is a way harder model
> to manage."

## The two models

```
TWO THREADS (shipping)               THE SHARED ROOM (this document)
each agent owns its side             one conversation, many participants

 speccer's view   builder's view      ┌──────────────────────────────────┐
 ┌──────────┐     ┌──────────┐        │  #batch-gate                     │
 │ →builder │     │ speccer→ │        │  speccer: FR-3 needs a count     │
 │ builder→ │◀───▶│ →speccer │        │  builder: 41 call sites          │
 │ →builder │     │ speccer→ │        │  you:     use the batch entry    │
 └──────────┘     └──────────┘        │  tester:  equivalence holds      │
                                      └──────────────────────────────────┘
 Conversation.agent = one owner        Conversation.agent = ??
 delivery = routing                    delivery = broadcast
```

The interesting claim is the second half of the operator's sentence: **"when doing specs or
programming you can have multiple agents pitching in."** That is not a messaging feature. It is a
different unit of work — a room where a specification is drafted with several agents present, each
seeing everything, rather than a hub agent relaying between private channels.

## Why it is genuinely harder, not just bigger

`Conversation.agent` is a single `String(64)` column, and it is load-bearing far outside messaging:

- **Turn context** is built per agent from the conversation it belongs to. With many participants,
  whose context is it? Each participant needs its own view of a shared transcript.
- **The composer** targets one agent. A room needs to choose a recipient, or address everyone.
- **Navigation** lists conversations beneath their owning agent (`agent-conversation-workspace`,
  "An agent's conversations are listed beneath it in navigation"). A room has no single parent.
- **Checkpoint and cutover** archive a conversation and open a successor *for its agent*. A room
  where one participant checkpoints and three do not has no defined meaning today.
- **Hop budget** counts message depth. Broadcast changes the arithmetic: one message to N agents is
  N deliveries, and a room of chatty agents is a fan-out, not a chain.
- **Runtime overrides** (model, effort, permission posture) are per conversation. In a room, they
  are plausibly per participant.

None of these are blockers. All of them are decisions, and none has been made.

## What would have to be true first

Rough order, if this is ever picked up:

1. A conversation can have participants, not an owner. Probably a join table, with the current
   single-agent case expressed as a room of one so nothing needs a special path.
2. Per-participant read position — what each agent has and has not seen, since they no longer each
   own a private transcript.
3. A turn-context builder that renders a shared transcript from one participant's point of view,
   including how another agent's message is attributed.
4. A composer that can address the room or one participant.
5. A scheduling answer: when a message lands in a room, which participants run? All of them is a
   fan-out per message and would burn budget fast. One at a time is a turn order nobody has designed.

Step 5 is the one that decides whether this is a good idea. Multiplayer editors solve presence and
merge; they do not solve *who speaks next*, because humans self-arbitrate. Agents do not.

## Open questions

1. Is the room a **conversation** or a **new object**? Making it a conversation with participants
   keeps one surface; making it separate avoids destabilising everything listed above.
2. Who speaks next? Round-robin, a nominated chair, whoever is addressed, or an explicit hand-off?
   Without an answer this is a broadcast storm with a budget cap.
3. Does the operator's own conversation become a room of two, retroactively? That would unify the
   model — an operator is just another participant — and it is exactly the kind of unification that
   sounds elegant and breaks twelve assumptions.
4. Is this actually the same idea as a **task** with several assignees, rather than a conversation
   with several participants? The work-and-traceability plane may already be the right home.
5. Would two-thread continuity (`conversations-continue`) still be needed underneath, or does a room
   make peer binding irrelevant? Probably still needed: direct agent-to-agent messages should not
   have to become rooms.

## Relationship to what is shipping

`conversations-continue` does not close this off. It makes an exchange between two agents stable and
findable, which is a precondition for noticing that a *third* agent should have been in it. If the
room is ever built, the two-thread case is the degenerate one — a room of two — rather than
something to migrate away from.
