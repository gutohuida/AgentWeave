## Why

The hop budget is the only guard against a runaway agent-to-agent chain, and it stops working the
moment the operator says anything. Measured live on 2026-08-23 with `hop_budget = 1`
(`scripts/drive/FINDINGS.md`, F5).

1. Operator triggers `builder` → `run-693eb7cd`, `turn_depth 0`.
2. `builder` messages `relay` → entry at hop 1, within budget, delivered.
3. `relay` messages `builder` → entry at hop **2**, over budget. Correctly held: `state = queued`
   across four polls while every agent sat idle. **The guard works when the entry is alone.**
4. Operator sends one ordinary message into the same conversation.

```
entry-d41e4213  operator  hop 0  delivered  run-a6683c96
entry-5d572a6b  agent     hop 2  delivered  run-a6683c96   <- over budget, delivered anyway
run-a6683c96    builder   turn_depth = 0                   <- not 2
```

Two defects, both in `turn_scheduler.schedule_agent`:

- **Delivery is not filtered by depth.** `can_start` returns true when *any* entry is within budget
  (`inbound_queue.py:91`), and the batch that follows applies no `hop_depth` filter at all
  (`turn_scheduler.py:65`). The blocked entry rides along.
- **The counter resets downward.** The turn takes `min(hop_depth)` across the batch
  (`turn_scheduler.py:91`) and the next hop is `turn_depth + 1` (`agents.py:1400`). Batching a hop-0
  entry with a hop-2 entry produces a turn at depth 0, so the chain restarts its count from zero.

This is defeated by ordinary use, not by an adversarial case: the intended way to use the product is
an operator supervising agents that talk to each other, and every operator message resets the guard
for that conversation.

## What Changes

**The budget bounds delivery, not just admission.**

- An entry whose `hop_depth` exceeds the project's budget SHALL NOT be delivered, whatever else is
  in the batch alongside it.
- A turn's depth SHALL be the depth of the entry that admitted it, not the minimum across the batch,
  so the counter cannot run backwards.

**And because a bound with no exit is a wedge, continuation becomes explicit.**

Filtering alone would be worse than today in one specific way: the blocked entry would sit queued
forever while the agent starts a fresh chain around it, so a real message from another agent is
never read. The operator therefore gets a stated choice on that entry:

- **Continue** — re-base the entry to depth 0 and deliver it. The deliberate version of what
  currently happens by accident.
- **Discard** — already exists (`DELETE /queue/entries/{entry_id}`).
- Raising the project's budget also releases it, through the existing `redrain_queued_agents`.

The principle is the one the product already states about questions: an agent that needs an answer
calls `ask_user`, and the product does not guess on the operator's behalf. When a chain reaches its
bound, the Hub does not guess whether that is runaway or productive either.

## Impact

- Affected specs: `agent-conversation-workspace` (delivery and depth), `agent-tool-surface`
- Affected code: `hub/hub/turn_scheduler.py`, `hub/hub/inbound_queue.py`,
  `hub/hub/api/v1/inbound_queue.py`, and the queue surface in the UI
- Much of the surfacing already exists: `hop_budget_exceeded` is computed per entry
  (`agent_chat.py:187`) and already rendered (`AgentTimeline.tsx:174`,
  `AgentOutputPanel.tsx:629`), and queue status already reports `"hop budget exhausted"`.

## Rejected alternative

**An operator message forgives the chain, but loudly** — recorded as an event, shown in the
timeline, the released entry marked as delivered-by-forgiveness rather than quietly bundled in.
Defensible: the budget exists to stop *unsupervised* recursion, and a replying operator is
supervision.

Rejected because the reset would be per-conversation and unlimited, and in practice an operator does
say something occasionally. The budget would stop being a bound and become "how long agents may run
between your messages" — a rate limit wearing a bound's name. A number that does not mean what it
says is worse than no number.
