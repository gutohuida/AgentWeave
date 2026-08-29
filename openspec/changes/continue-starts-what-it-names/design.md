## Context

`POST …/conversations/{conversation_id}/continue` (`hub/hub/api/v1/checkpoints.py:254-277`) exists
so a successor conversation, handed its checkpoint as a queue entry, can be started without the
operator inventing a message to carry it. It is addressed per conversation because that is the
operator's unit of attention.

The resource it starts is not per conversation. `schedule_agent(project_id, agent)`
(`hub/hub/turn_scheduler.py:78-290`) holds a per-agent lock, refuses if a `Run` for that agent is
`running`, reads `queued_entries(db, project_id, agent)` — every conversation of that agent, ordered
by `InboundQueueEntry.sequence` (`hub/hub/inbound_queue.py:88-91`) — and picks
`controlling = next(entry for entry in entries if entry.hop_depth <= hop_budget)`. The conversation
is looked up **from that entry** (`:99-101`) and the batch filtered to it (`:118-131`). The path
parameter reaches the scheduler only as `conversation.agent`.

### The rule already exists, and one of its two halves was never written down

`agent-conversation-workspace` requires that **"A refusal is reported only to the input it is
about"** (`openspec/specs/agent-conversation-workspace/spec.md:1888-1908`), including: *"Where a
request's own input was not part of the refused turn, the system SHALL report that the input is
waiting behind other input rather than repeating a refusal about it."*

`POST /agent/trigger` satisfies it in both directions (`agent_trigger.py:1344-1368`): on success it
returns the scheduler's response **only when** `scheduled.response.conversation_id ==
conversation.id`, and otherwise answers this request's own conversation as queued; on refusal it
answers only when `entry.id in refusal.entry_ids`. `TurnRefusal.entry_ids` exists to make that
possible and its docstring gives the same reason (`turn_scheduler.py:39-43`).

`continue` is the second conversation-addressed caller and implements neither half. It could be
added without them because the requirement's text is about refusals, so nothing stated the
start-direction obligation the trigger route nonetheless honours. This change writes that half down
and applies it.

### Constraints

- Selection order is load-bearing. Designs D1, D2 and D3 live in the `selected` filter
  (`turn_scheduler.py:110-131`): D1/F5 stops an over-budget entry riding on a shallower one, D2 fixes
  `turn_depth` to the controlling entry's depth, D3/F66 stops a review entry and a work entry
  batching into a turn that is neither. Nothing here may perturb that.
- Fifteen call sites reach `schedule_agent`. **Three are conversation-addressed** —
  `agent_trigger.py:1344` (already correct), `checkpoints.py:271` (this defect), and
  `checkpoint_cutover.py:138` (log-only, below). The other twelve are agent-addressed and have no
  conversation to be wrong about: `accounting.py:72`, `agents.py:1651`, `agents.py:2032`,
  `inbound_queue.py:107`, `inbound_queue.py:253`, `messages.py:307`, `questions.py:399` and `:504`,
  `run_divergence.py:820`, `run_reconciliation.py:162`, `scheduler.py:2452` and `:2586`.
- `TriggerAgentResponse.conversation_id: str` is required (`agent_trigger.py:228-234`), so on the
  success path the started conversation is already on `ScheduleResult.response`.

## Goals / Non-Goals

**Goals.** The conversation-addressed start obeys the same rule the conversation-addressed trigger
already obeys. The operator is not shown a confirmation describing a conversation nothing happened
in. The rule is written down for both directions so a fourth caller cannot be added without it.

**Non-Goals.** Changing which turn runs. Scoping selection to the addressed conversation. Refusing
the mismatch as an error. The refusal direction, already satisfied on both routes. F128, the same
family for loops.

## Decisions

### D1 — Report against the addressed conversation, matching `agent_trigger.py:1353`

**Decision.** `continue` compares `result.response.conversation_id` to the addressed
`conversation_id`. Equal → `started: true`. Different → `started: false`, a `waiting_reason` saying
the input is waiting behind other input, and `started_conversation_id` naming what did run. No
scheduler change.

**Why.** It is the answer the shipped requirement prescribes, expressed with the comparison the
product already performs one route over. A second, differently-shaped answer to the same question
would be the inconsistency this change exists to remove.

**Rejected — round 1's design: keep `started: true` and add a field naming the other conversation.**
Truthful about *what ran*, and still wrong about *what the caller asked*: `started: true` against a
request naming conversation A remains a claim that A started. It also contradicts the shipped
requirement's chosen answer for the symmetric case, which is *waiting*, not *started elsewhere*.
Round 2 rejected it; recorded so round 3 does not restore it.

**Rejected — new `ScheduleResult` fields.** Round 1 proposed `started_conversation_id` and
`started_entry_ids`. Unnecessary: `response.conversation_id` is already required and already read
this way at `agent_trigger.py:1353`. Adding parallel fields would give the module two ways to answer
one question.

**Rejected — scope the selection to the addressed conversation.** `queued_entries` takes a
`conversation_id` parameter (`inbound_queue.py:79,86-87`) that **no caller passes** — verified across
`hub/hub` and `hub/tests`; the scheduler's own call omits it. Passing it here would make the
operator's keystroke a queue reordering: an entry that arrived later overtakes one that arrived
earlier because somebody was looking at its conversation. That is a behaviour change to the
scheduler, inside the filter D1/D2/D3 were written into, sold as a bug fix — and it starves a quiet
conversation while a busy one is pressed.

**Rejected — 409 on mismatch.** The requirement's answer to "your input was not the input carried"
is *accepted, waiting*, not an error. A 409 also needs a force flag to stay usable, and a
refuse-by-default-plus-force pair is over-built for one button. This was F131's own option 2.

### D2 — `started` changes meaning, deliberately, and that is the fix

`started = result.waiting_reason is None` answers "did a turn begin for this agent". The caller
asked "did my conversation's work begin". Those differ exactly in the case that matters. Redefining
`started` is therefore not a side effect of the fix; it *is* the fix. The alternative — a second
boolean beside the first — leaves the misleading one in place for any client that reads it.

### D3 — `checkpoint_cutover.py:138` is corrected in the same change

The auto-continue after a cutover logs `"successor %s did not start immediately: %s"` against
`successor.id` for a `waiting_reason` `schedule_agent` may have produced about a different
conversation (`checkpoint_cutover.py:131-145`). Log-only: no operator-facing claim, no response
field. Corrected here rather than deferred because it is the same rule, two lines, and the fourth
scenario of the new requirement covers diagnostics for exactly this reason. Deferring it would leave
the rule true of the API and false of the log the moment somebody reads it.

### D4 — The UI states waiting, and names what ran

`handleContinue` (`AgentOutputPanel.tsx:742-756`) today reads **only** `result.started` and
`result.waiting_reason`; it never reads `result.conversation_id`. So the misleading confirmation
comes from rendering a success notice in whatever conversation is on screen, not from the echoed
field. **A backend-only fix would therefore change nothing an operator sees** — until `started`
turns false, at which point the existing `Not started — ${waiting_reason}` branch carries the
correct message for free. The UI work is to add the third case that names the conversation that ran.

The button gate is unchanged: it renders when an undelivered entry names the conversation on screen
and no run is in flight (`AgentOutputPanel.tsx:337-340,1064`). That gate is what makes the mismatch
uncommon; it is not what makes it impossible, because it reads client-side state in which another
conversation's older entry does not appear.

### D5 — `ScheduleResult.response` stays typed `object`

Reading `.conversation_id` off `Optional[object]` is untyped, and typing it
`Optional[TriggerAgentResponse]` would be cleaner in isolation. It is not done here: `turn_scheduler`
imports `agent_trigger` inside the function precisely because `agent_trigger` imports
`turn_scheduler`, so the annotation needs a `TYPE_CHECKING` import and touches a module this change
otherwise leaves alone. `mypy` covers `src/` only, so nothing is being evaded. Recorded as an open
question, not smuggled in.

## Risks / Trade-offs

- **`started` changes meaning for existing callers.** → The only reader is `handleContinue`, changed
  here. The drive harnesses are updated in the same change. No external install base exists.
- **A test asserting the equal case passes vacuously** in a single-conversation project. → The
  mismatch must be built deliberately: two open conversations for one agent, the **older** entry on
  the one *not* addressed. Asserted by querying `Run` by `conversation_id`, never by recency.
- **`scripts/drive/t_continue_branches.py` asserts the current behaviour on purpose** — F131 wrote
  its assertions "in the direction the product actually behaves, so the day it is fixed they go red
  and say why." → Expected; flip them here and record that the fix, not a regression, turned them.
- **The waiting answer is indistinguishable from "queue is empty" if worded loosely.** → The reason
  must name the other input, not merely say "waiting".

## Migration Plan

No migration: no schema change, no column, no stored data. Rollback is a revert of both halves. They
must land together, and `hub/hub/static/ui` must be rebuilt with
`py -3.11 scripts/refresh_ui_bundle.py` and committed alongside `hub/ui/src`.

## Open Questions

1. Should `ScheduleResult.response` be typed `Optional[TriggerAgentResponse]` under `TYPE_CHECKING`?
   Out of scope here (D5); worth its own small change.
2. Should the waiting notice offer to switch the view to the conversation that ran? A navigation
   decision, not an honesty one.
3. `agent_trigger.py:1344` satisfies the new requirement already. Should the change add a test
   pinning that, so the two conversation-addressed routes cannot drift apart again? Proposed as
   task 2.4; cheap, and it is how this defect would have been caught.
