## Context

`POST …/conversations/{conversation_id}/continue` (`hub/hub/api/v1/checkpoints.py:254-277`) exists
so a successor conversation, handed its checkpoint as a queue entry, can be started without the
operator inventing a message to carry it. It is addressed per conversation because that is the
operator's unit of attention — the conversation is what is on screen when they press the button.

The resource it starts is not per conversation. `schedule_agent(project_id, agent)`
(`hub/hub/turn_scheduler.py:78-190`) holds a per-agent lock, refuses if a `Run` for that agent is
`running`, reads `queued_entries(db, project_id, agent)` — every conversation of that agent, ordered
by `InboundQueueEntry.sequence` (`hub/hub/inbound_queue.py:88-91`) — and picks
`controlling = next(entry for entry in entries if entry.hop_depth <= hop_budget)`. The conversation
is then looked up **from that entry** (`:99-101`) and the batch is filtered to it (`:118-131`).

So the endpoint's path parameter reaches `schedule_agent` only as `conversation.agent`. The
conversation itself contributes a 404 and nothing more. The response nonetheless returns the path's
`conversation_id` beside `started`, and the UI renders `'Continuing…'` against the conversation on
screen (`hub/ui/src/components/agents/AgentOutputPanel.tsx:742-756`).

**The Hub has already answered this question once, in this file, for the other direction.**
`TurnRefusal` carries `entry_ids` with a docstring that states the reason exactly:
`schedule_agent` "builds its turn from the oldest eligible entry across the agent's *whole* queue,
so a refusal frequently belongs to a conversation the current caller never mentioned; without the
ids, answering *no* to whoever happened to arrive would report a refusal about somebody else's
input" (`hub/hub/turn_scheduler.py:39-43`). The success path has no equivalent. This design supplies
the missing symmetry rather than inventing a policy.

### Constraints

- Selection order is load-bearing. Designs D1, D2 and D3 all live in the `selected` filter
  (`turn_scheduler.py:110-131`): D1/F5 stops an over-budget entry riding on a shallower one, D2
  fixes `turn_depth` to the controlling entry's depth, D3/F66 stops a review entry and a work entry
  batching into a turn that is neither. Nothing here may perturb that.
- Fifteen call sites reach `schedule_agent`. Fourteen are agent-addressed and have no conversation
  to be wrong about: `accounting.py:72`, `agents.py:1651`, `agents.py:2032`,
  `agent_trigger.py:1344`, `inbound_queue.py:107`, `inbound_queue.py:253`, `messages.py:307`,
  `questions.py:399` and `:504`, `checkpoint_cutover.py:138`, `run_divergence.py:820`,
  `run_reconciliation.py:162`, `scheduler.py:2452` and `:2586`. Only `checkpoints.py:271` is
  conversation-addressed.
- `ScheduleResult` is a dataclass with four fields, all defaulted (`turn_scheduler.py:51-56`). Six
  early returns construct it with `waiting_reason` alone.

## Goals / Non-Goals

**Goals.** A caller of the conversation-addressed start learns which conversation started. The
operator is not shown a confirmation that describes a conversation nothing happened in.

**Non-Goals.**

- Changing which turn runs. The scheduler already runs the right work.
- Scoping selection to the addressed conversation. Rejected below.
- Refusing the mismatch. Rejected below.
- Response-model strictness across the write surface. `hub-api-request-contract` governs request
  bodies; this route has none.
- The same family elsewhere — F128 (a loop runs on an agent its job does not name) is its own
  finding and its own change.

## Decisions

### D1 — Report what started; do not change what starts

**Decision.** `ScheduleResult` gains `started_conversation_id: Optional[str]` and
`started_entry_ids: Tuple[str, ...] = ()`, populated only on the success path, where `conversation`
and `selected` are both already in scope (`turn_scheduler.py:101,119-131`). The endpoint returns the
former as a new response field.

**Why over the alternatives.** It is the smallest change that makes the false claim impossible, it
touches no selection logic, and it restates for success the principle `TurnRefusal.entry_ids`
already states for refusal — so the module ends up with one rule instead of two halves that
disagree. `started_entry_ids` is carried for the same attributability reason as `TurnRefusal`'s and
because a future caller wanting to know *what* was delivered should not have to re-query the queue;
it is not surfaced by this route.

**Alternative — scope the selection to the addressed conversation.** `queued_entries` already takes
`conversation_id: Optional[str]` (`inbound_queue.py:79,86-87`), so this is a one-argument edit and
was the most tempting option found. **Rejected.** It makes the operator's keystroke a queue
reordering: an entry that arrived later would overtake one that arrived earlier because somebody
happened to be looking at its conversation. That is a behaviour change to the scheduler, in the
exact filter D1/D2/D3 were written into, sold as a bug fix. It also starves — a conversation whose
entry is never chosen while another is pressed repeatedly waits indefinitely. And it does not even
remove the honesty problem, only narrows it: with the addressed conversation empty, `started` would
report false where the agent in fact had work.

**Alternative — return the started id *in* `conversation_id`, replacing the echo.** Rejected: it
silently changes an existing field's meaning, so a client that already reads it keeps compiling and
starts lying differently. Two fields make the difference legible.

### D2 — The addressed id keeps its field and its meaning

`conversation_id` continues to carry the conversation the caller addressed. The new field carries
what started. Both present, both named, no field changes meaning. A client that ignores the new
field behaves exactly as today — no worse, and no better, which is the honest characterisation of
not adopting a fix.

### D3 — `started` keeps its current derivation

`started = result.waiting_reason is None` is correct: a turn did begin. The defect was never that
`started` was wrong; it was that `started: true` sat beside an id that implied *which*. Redefining
`started` to mean "the addressed conversation started" would make the common, correct case report
false and is rejected.

### D4 — Refusing the mismatch (409) is rejected

**Considered:** when the agent's next eligible entry is not for the addressed conversation, answer
`409` naming the conversation that is next.

**Rejected.** The operator pressing Continue wants the agent moving; the agent moves; the work that
runs is the work that should run next. Turning that into an error to protect a narrower reading of
intent trades a working action for a failed one. It also needs a force flag to stay usable, and a
refuse-by-default-plus-force pair is over-built for one button. Recorded here so it is not
re-proposed: this was F131's own option 2.

### D5 — The UI names the other conversation rather than suppressing the notice

`handleContinue` currently sets `'Continuing…'` on any success
(`AgentOutputPanel.tsx:746-749`). It gains a third case: started, but elsewhere. The notice states
that another conversation began and names it. Suppressing the notice instead would leave the
operator with no feedback at all from a button they pressed, which is the failure mode this change
exists to remove.

The Continue button's own gate is unchanged: it renders when an undelivered entry names the
conversation on screen and no run is in flight (`AgentOutputPanel.tsx:337-340,1064`). That gate is
correct and is what makes the mismatch uncommon; it is not what makes it impossible, because the
gate reads client-side state that another conversation's older entry does not appear in.

## Risks / Trade-offs

- **The notice can name a conversation the operator cannot navigate to from where they are.** →
  Accepted for this change. Naming it is strictly better than the current silence, and adding
  navigation is a separate, larger UI decision. Recorded as an open question rather than smuggled in.
- **`ScheduleResult` grows, and it is constructed in many places.** → All construction sites use
  keyword defaults; new fields default to `None` and `()`. The success path is the single
  construction site that sets them, and a test asserts the early returns still carry neither.
- **The drive harness `scripts/drive/t_continue_branches.py` asserts the *current* behaviour**, by
  design — F131 states its assertions "in the direction the product actually behaves, so the day it
  is fixed they go red and say why." → Expected. Update it in the same change and record that it was
  the fix, not a regression, that turned it.
- **A test asserting the true case can pass vacuously**, because in a single-conversation project
  the started conversation always equals the addressed one. → The mismatch scenario must be built
  deliberately: two open conversations for one agent, the older entry on the one *not* addressed.

## Migration Plan

No migration. No schema change, no database column, no stored data. The response gains a field; the
UI gains a branch. Rollback is a revert of both halves — they must land together, and
`hub/hub/static/ui` must be rebuilt via `py -3.11 scripts/refresh_ui_bundle.py` and committed with
`hub/ui/src`.

## Open Questions

1. Should the "started elsewhere" notice offer to switch the view to that conversation? Out of scope
   here; it is a navigation decision, not an honesty one.
2. Should `started_entry_ids` be surfaced on the response as well? Not needed by any current client;
   carried on `ScheduleResult` so a future one need not re-query.
