## Why

`POST /api/v1/projects/{project_id}/conversations/{conversation_id}/continue` is addressed to one
conversation and answers as if it acted on that conversation, but it does not act on it. It resolves
the conversation only far enough to 404 on it, then calls the agent-scoped scheduler
(`hub/hub/api/v1/checkpoints.py:254-277`):

```python
conversation = await _conversation_or_404(session, project_id, conversation_id)
result = await schedule_agent(project_id, conversation.agent)
return {"agent": ..., "conversation_id": conversation_id, "started": result.waiting_reason is None, ...}
```

`schedule_agent` selects the oldest eligible entry across the agent's **whole** queue —
`queued_entries(db, project_id, agent)` ordered by `InboundQueueEntry.sequence`
(`hub/hub/inbound_queue.py:88-91`), then `controlling = next(entry for entry in entries if
entry.hop_depth <= hop_budget)` (`hub/hub/turn_scheduler.py:91-98`) — and derives the conversation
*from that entry* (`:99-101`). The `conversation_id` in the path contributes the agent's name and a
404, nothing else.

So `started: true` can mean "a turn began, in a conversation you did not name". The UI acts on it
verbatim, rendering `'Continuing…'` (`hub/ui/src/components/agents/AgentOutputPanel.tsx:742-756`).
The operator watches the conversation they pressed, no run appears, no output, no error — and the
obvious next act is to press it again.

## This is a rule the product has already decided, and this route is the one place that breaks it

`agent-conversation-workspace` carries a shipped requirement, **"A refusal is reported only to the
input it is about"** (`openspec/specs/agent-conversation-workspace/spec.md:1888-1908`):

> Where the system refuses to start a turn, it SHALL attribute that refusal to the specific inputs
> the refused turn would have carried, and SHALL report it only to a request that submitted one of
> them. […] Where a request's own input was not part of the refused turn, the system SHALL report
> that the input is waiting behind other input rather than repeating a refusal about it.

`POST /agent/trigger` implements exactly that, in both directions, and says so
(`hub/hub/api/v1/agent_trigger.py:1344-1358`):

```python
scheduled = await schedule_agent(project_id, body.agent)
# The scheduler picks the conversation of the *oldest* eligible entry across this
# agent's whole queue, which is not necessarily the conversation this request just
# appended to … When it picked a different one, this caller's input is still queued:
# report that, and this request's own conversation, rather than another conversation's run
if scheduled.response is not None and scheduled.response.conversation_id == conversation.id:
    return response          # started — and it is *this* conversation that started
…                            # otherwise: answered as queued, against this conversation
```

`continue` is the second conversation-addressed caller of `schedule_agent` and it does none of this.
The requirement is written about refusals; the same reasoning governs starts, and the product's own
implementation of it already compares the started conversation to the addressed one. **The gap is
that the rule was stated for one direction and the honest half of it — a start is reported only to
the input it is about — was never written down, so a second route could be added without it.**

**Why now.** F131 was driven live on 2026-08-29 (16/16 assertions,
`scripts/drive/t_continue_branches.py`): with gamma idle and one entry queued for successor
`conv-7e15b83ad8b5`, Continue was pressed on unrelated `conv-766a9eee3bfc`; the call answered `200`,
`started: true`, `conversation_id: conv-766a9eee3bfc`, the successor's entry was consumed, and the
one new run was on `conv-7e15b83ad8b5`.

**One correction to that finding.** F131's reproduction pressed Continue on a conversation with
*nothing* queued for it, and that exact path is not reachable from the shipped UI: the button
renders only when `queuedEntries.some(entry => entry.conversation_id === currentConversationId)`
(`AgentOutputPanel.tsx:337-340,1064`). The defect is reachable from the UI by a path F131 does not
describe — the pressed conversation has a queued entry **and another conversation of the same agent
has an older one**, so the button renders correctly and the substitution happens with every
client-side gate satisfied. The severity is what F131 says; the reproduction it gives is not the one
that matters.

## What Changes

- `started` comes to mean what the caller asked about: the **addressed** conversation's input
  started. It is derived by comparing the started conversation to the addressed one, the same
  comparison `agent_trigger.py:1353` already makes.
- When the agent's turn went to a different conversation, the response says the addressed
  conversation's input is **waiting behind other input** — `started: false` with a stated reason —
  rather than claiming a start. This is the answer the shipped requirement already prescribes for
  the refusal direction.
- The started conversation's identifier is returned as its own field, so the caller can see what did
  run instead of inferring it.
- The Continue control reports the three cases distinctly: continuing this conversation, waiting
  behind other input (naming what started), and not started for a stated reason.
- **No new field on `ScheduleResult`, and no change to which turn is scheduled.** The started
  conversation is already available as `result.response.conversation_id`
  (`TriggerAgentResponse.conversation_id`, `agent_trigger.py:228-234`) on the success path. Selection
  stays agent-scoped and arrival-ordered; the right work already runs.

**Behaviour change, not merely additive.** A caller that today reads `started: true` when another
conversation ran will read `started: false` with a reason. That is the point: the previous value was
false. No client depends on the old meaning — the only reader is `handleContinue`
(`AgentOutputPanel.tsx:746-749`), changed here.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-conversation-workspace`: adds the start-direction counterpart of the shipped requirement
  "A refusal is reported only to the input it is about" (`spec.md:1888`) — a *start* is likewise
  reported only to the input it is about, and a request whose input was not carried is told it is
  waiting behind other input. Also adds the operator-facing half, since the existing requirement
  governs the API answer and not what the interface renders from it.

**Rejected: a new `conversation-turn-start` capability.** Round 1 proposed one. It would have
restated, in a second capability, a rule this capability already holds for the refusal direction —
leaving two places to look for one principle, and the newer one silently inconsistent with the older
in exactly the way this change exists to fix.

## Non-Goals

- **Making turn selection conversation-scoped.** `queued_entries` accepts a `conversation_id`
  parameter (`hub/hub/inbound_queue.py:79,86-87`) that **no caller passes** — not the scheduler, not
  the tests. Using it here would make the operator's keystroke a queue reordering: a later-arriving
  entry overtakes an earlier one because somebody was looking at its conversation. That perturbs the
  arrival ordering designs D1, D2 and D3 are written into (`turn_scheduler.py:110-131`), and starves
  a quiet conversation while a busy one is pressed. Rejected in design.md.
- **Refusing the mismatch with a 409.** The shipped requirement's answer to "your input was not the
  input carried" is *accepted, waiting* — not an error. Rejected in design.md.
- **Changing `schedule_agent`'s selection, batching, hop-budget or kind filtering.**
- **The refusal direction**, which already satisfies the requirement on both routes.
- **Auditing every route that echoes an identifier it did not act on.** F128 (a loop runs on an
  agent its job does not name) is the same family and stays its own finding.

## Impact

- `hub/hub/api/v1/checkpoints.py:254-277` — `started` is derived from a comparison rather than from
  `waiting_reason` alone; the response gains the started conversation's id and a reason for the
  waiting case.
- `hub/hub/turn_scheduler.py` — **unchanged.** Round 1 proposed two new `ScheduleResult` fields;
  they are unnecessary.
- `hub/hub/checkpoint_cutover.py:131-145` — the auto-continue after a cutover is the **third**
  conversation-addressed use, and its diagnostic logs `"successor %s did not start immediately: %s"`
  against `successor.id` for a `waiting_reason` that may belong to another conversation. Same rule,
  log-only exposure; corrected here because it is two lines and leaving it would reintroduce the
  inconsistency the moment somebody reads that log.
- `hub/ui/src/api/checkpoints.ts:90-95` and
  `hub/ui/src/components/agents/AgentOutputPanel.tsx:742-756` — the three cases.
- The other twelve `schedule_agent` call sites are agent-addressed and unaffected; enumerated in
  design.md so the claim is checkable.
- `hub/hub/static/ui` must be rebuilt and committed with the source.
