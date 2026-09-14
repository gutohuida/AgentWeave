# A review can wait on the operator

**2026-09-14, day window, I-1 brief 3 of 11.** This is an improvement brief, not a proposal: there
is no change directory and no tasks. Source: `spec-queue/observations/2026-09-14-LoopEngine.md`,
`## Improvements` item 3 and `### Architect` items 4, 5 and 7.

## What we saw

**A review waiting on a person looks like a review nobody started.**
- The Architect's review of `task-9e89a55ccc84` was delivered three times at 21:00. The second and
  third deliveries hit the provider's session limit (F355), and it was never delivered again.
- From 21:05 to 08:40 the job recorded, 64 times, that the Architect *"is named on
  task-9e89a55ccc84 … as its reviewer and is not reviewing it … Ask Architect again, review it
  yourself, or send it back with revision_needed"*.
- Meanwhile the Architect had told the operator twice in chat (`d6e79412` 21:42, `a9f394ad` 22:05)
  what the review was really waiting for: the operator's own decision about a run on another
  machine.

**Why the flow cannot tell the two apart.** The sentence comes from `_wedged_review_reason`
(`hub/hub/scheduler.py:1732-1748`). A named reviewer counts as "on it" only if a bound run is live
or an entry is queued for the task (`scheduler.py:1310`, `:1377-1393`;
`run_task_binding.py:267-309`). Nothing else is consulted:
- A question does not count. `Question` has no task link beyond `blocked_task_id`
  (`db/models.py:970`).
- The wait is not recorded anywhere. `ask_user` can park a task as `blocked`
  (`run_task_binding.py:680-717`), but only from `in_progress`, and `under_review` has no `blocked`
  edge (`task_transitions.py:138`). When the wait expires, `/questions/wait-ended` *releases* the
  block (`agent_actions.py:642-712`, `run_task_binding.py:825-867`). An expired wait therefore
  leaves nothing a later pass could read as "awaits the operator".

**Autonomous turns asked in prose.** Five of the Architect's autonomous turns ended by asking the
operator to reassign or close tasks (`e56fa1a8` 23:50 and 00:06; `4712e387` 04:00, 04:12 and
04:23). They are stored as ordinary chat output.

## What would change

An agent could **declare** that a piece of work waits on the operator. That means an `ask_user`
question bound to the task, or an explicit "this waits on you" record, and the declaration would
outlive the tool call's wait. While it stands:
- the flow reads it as the reason, and says *"waiting on the operator's answer to q-…"* instead of
  *"is not reviewing it"*;
- it neither restaffs nor nags;
- the operator sees one waiting item, not 64 events.

When the operator answers, the wait ends and the task is delivered back to its reviewer, which is
what F356 needs for late answers anyway.

**This is not detection.** Nothing reads trailing prose to guess that a turn is waiting. That
backstop was retired on 2026-08-20 at the operator's request, and `CLAUDE.md` forbids reintroducing
it. The improvement gives the agent a declaration to make, and makes the declaration last.

## Why it matters

It matters for the operator who steps away. On LoopEngine, overnight, the review and 64 events stood
where one line would have done: "the Architect is waiting for your decision on the work-PC run". The
same mechanism would give the Architect's five prose endings somewhere real to go. A waiting review
would also stop counting its reviewer as unaccountably idle, which is the other half of the F352
staffing picture.

## Rough cost — a code-read estimate

- **Files:**
  - `hub/hub/scheduler.py`: `_wedged_review_reason` and the `on_it` set;
  - `hub/hub/run_task_binding.py`: `block_task_for_question` and `release_block_for_expired_wait`;
  - `hub/hub/api/v1/agent_actions.py`, the ask and wait-ended routes;
  - `hub/hub/api/v1/questions.py`, delivery on answer, which is shared with F356;
  - the MCP `ask_user` in `hub/hub/mcp_server.py`, if it gains a task argument. **F354 keeps that
    file out today.**
- **Capabilities:** `openspec/specs/agent-flows` (review staffing), `task-lifecycle-governance`
  (whether `under_review` gains a waiting edge or a flag), `agent-capability-plane` (`ask_user`),
  and `turn-outcome-visibility`.
- **Migration:** probably one, for a task-wait record or a question-to-task link that survives the
  wait's end. Reusing `blocked_task_id` might avoid it.
- **UI:** the waiting item, which means a bundle.

## Risks and open questions

- **A status or a flag?** Adding `under_review → blocked` changes the lifecycle every consumer
  reads. A flag leaves the status alone but adds a second place to look. That is R1's first choice,
  and possibly the operator's.
- **A wait that never ends.** An agent could declare waits to avoid work. That needs a cap, or a
  sentence on the operator's side that makes the wait obvious.
- **Order.** It must come after the f352 change, which rewrites the same unstaffed sentence today,
  and it should share F356's delivery-on-answer path rather than invent a second one.
- **The corpus still says the retired thing.** `openspec/specs/agent-capability-plane` still states
  *"A turn that ends on an unasked question is surfaced to the operator"* (`:281`) and its
  companion requirement. Both describe the feature migration `0082` dropped. This was recorded and
  put to the operator in the archived change
  `2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing`, and it is still unresolved. A spec
  loop here should REMOVE both, so no round cites them as current behaviour.

## The decision, in one line

Approve a spec loop, after f352 and f356 are built, for *an agent can declare that work waits on
the operator, and the flow says so*. Choose between a flag and a new lifecycle edge when R1 lays
them out.
