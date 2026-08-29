## Why

`POST /api/v1/projects/{project_id}/conversations/{conversation_id}/continue` is addressed to one
conversation and answers as if it acted on that conversation, but it does not act on it. It resolves
the conversation only far enough to 404 on it, then calls the agent-scoped scheduler
(`hub/hub/api/v1/checkpoints.py:268-277`):

```python
conversation = await _conversation_or_404(session, project_id, conversation_id)
result = await schedule_agent(project_id, conversation.agent)
return {"agent": ..., "conversation_id": conversation_id, "started": result.waiting_reason is None, ...}
```

`schedule_agent` selects the oldest eligible entry across the agent's **whole** queue —
`queued_entries(db, project_id, agent)` ordered by `InboundQueueEntry.sequence`
(`hub/hub/inbound_queue.py:88-91`), then `controlling = next(entry for entry in entries if
entry.hop_depth <= hop_budget)` (`hub/hub/turn_scheduler.py:91-98`) — and derives the conversation
*from that entry*. The `conversation_id` in the path contributes the agent's name and a 404, nothing
else.

The response then echoes the path's `conversation_id` beside `started: true`. That pair is a claim
about the pressed conversation, and it can be false: a different conversation's turn began. The UI
acts on it verbatim, rendering `'Continuing…'` on the pressed conversation
(`hub/ui/src/components/agents/AgentOutputPanel.tsx:746-749`). The operator watches that
conversation, no run appears, no output, no error — and the obvious next act is to press it again.

This is the response-side half of the shape `hub-api-request-contract` already governs on the
request side: there an undeclared input was silently discarded; here a declared input is silently
substituted, and the answer names the input back either way. The Hub has already decided this
question once, in the same module, for the *refusal* path: `TurnRefusal` carries `entry_ids`
precisely because "`schedule_agent` builds its turn from the oldest eligible entry across the
agent's *whole* queue, so a refusal frequently belongs to a conversation the current caller never
mentioned; without the ids, answering *no* to whoever happened to arrive would report a refusal
about somebody else's input" (`hub/hub/turn_scheduler.py:39-43`). The success path has no equivalent
field. This change gives it one.

**Why now.** F131 was driven live on 2026-08-29 (16/16 assertions,
`scripts/drive/t_continue_branches.py`): with gamma idle and one entry queued for successor
`conv-7e15b83ad8b5`, Continue was pressed on unrelated `conv-766a9eee3bfc`; the call answered `200`,
`started: true`, `conversation_id: conv-766a9eee3bfc`, the successor's entry was consumed, and the
one new run was on `conv-7e15b83ad8b5`.

**One correction to that finding, established while writing this proposal.** F131's own reproduction
pressed Continue on a conversation with *nothing* queued for it, and that exact path is not reachable
from the shipped UI: the button renders only when `queuedEntries.some(entry => entry.conversation_id
=== currentConversationId)` (`hub/ui/src/components/agents/AgentOutputPanel.tsx:337-340,1064`). The
defect is nonetheless reachable from the UI by a path F131 does not describe — when the pressed
conversation has a queued entry **and another conversation of the same agent has an older one**, the
button renders correctly, `controlling` resolves to the older entry, and the substitution happens
with every client-side gate satisfied. The severity is therefore what F131 says; the reproduction it
gives is not the one that matters.

## What Changes

- `ScheduleResult` gains the identity of what it actually started: the conversation whose entries
  were selected, and the ids of those entries. Populated on the success path only; every early
  return already answers with `waiting_reason` and started nothing.
- `POST …/conversations/{id}/continue` returns the started conversation's id in a field distinct
  from the one addressed, so `started: true` is never attached to a conversation that did not start.
  The addressed id is still echoed, unchanged, so a caller can correlate request to response.
- The Continue control reports the conversation that began. When it is not the one on screen, the
  notice says so and names it rather than saying `'Continuing…'`.
- **No change to which turn is scheduled.** Selection stays agent-scoped and arrival-ordered. The
  right work already runs; only the report of it is wrong.

**Not a breaking change.** The response gains a field and keeps every existing one with its current
meaning. `hub-api-request-contract`'s rule governs request bodies, not response bodies, and this
route takes no body.

## Capabilities

### New Capabilities

- `conversation-turn-start`: what an action addressed to a single conversation promises about which
  conversation it started, when the underlying resource — a turn — is owned by the agent rather than
  by the conversation.

### Modified Capabilities

None. `agent-conversation-handoff` governs the *message-driven* resume of a successor
(`openspec/specs/agent-conversation-handoff/spec.md:97`) and says nothing about the Continue
endpoint; `conversation-checkpoint` governs the checkpoint record and its lineage, not turn start.
Neither has a requirement whose text changes.

## Non-Goals

- **Making turn selection conversation-scoped.** `queued_entries` already accepts a
  `conversation_id` filter (`hub/hub/inbound_queue.py:79,86-87`), so scoping the selection to the
  pressed conversation is a small edit — and it is the wrong one. It would let a later-arriving
  entry overtake an older one at the operator's keystroke, breaking the arrival ordering that
  designs D1, D2 and D3 rest on (`hub/hub/turn_scheduler.py:118-131`), and starve a quiet
  conversation for as long as a busy one is being pressed. Rejected in design.md.
- **Refusing the mismatch with a 409.** Considered and rejected in design.md: it converts a working
  request into an error for an operator whose actual intent — get this agent moving — was served.
- **Changing `schedule_agent`'s selection, batching, hop-budget or kind filtering** in any way.
- **Auditing every other route that echoes an identifier it did not act on.** F128 is the same
  family for loops and stays its own finding.

## Impact

- `hub/hub/turn_scheduler.py` — `ScheduleResult` gains two optional fields; the success path
  populates them. Every existing early return is unchanged and keeps its defaults.
- `hub/hub/api/v1/checkpoints.py:254-277` — the response gains the started conversation's id.
- `hub/ui/src/api/checkpoints.ts:88-96` — `ContinueResult` gains the field.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx:742-756` — the notice distinguishes the two
  cases.
- The eight other `schedule_agent` call sites are agent-addressed and unaffected; they ignore the
  new fields. Enumerated in design.md so the claim is checkable.
- `hub/hub/static/ui` must be rebuilt and committed with the source.
