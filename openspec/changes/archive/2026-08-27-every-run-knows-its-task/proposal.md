## Why

A flow's ordinary work firing claims a task, writes its assignee, moves it to `assigned`, and fires
an agent — and the run it starts records **no task at all**. Both staging paths pass
`review_task_id` and nothing else (`hub/hub/scheduler.py:2302`, `hub/hub/scheduler.py:2621`).

Because `run_advanced_its_task` returns `True` for any unbound run, the run boundary check — the
whole enforcement that a turn either moves its work or is recorded as not having — **has never
applied to a flow's own work turns.** Measured on the beta database, 2026-08-26: 61 job-origin queue
entries, **0 carrying `task_id`**; 5 of 59 job-delivered runs bound, all inherited from an earlier
operator turn rather than from the firing; **10 runtime `→ in_progress` transitions in the entire
database across 202 runs.** The flow is the product's main loop and it binds essentially never.

The shipped spec already requires this. `openspec/specs/run-task-binding/spec.md:52`:

> The system SHALL set a run's binding itself, **from the cause that started the run.**

A flow firing is a cause that started a run and it knows the task — it just claimed it. Nothing
carves flows out, and nobody wrote down a reason to leave work runs unbound: the comment beside the
missing line (`hub/hub/scheduler.py:2301`) is about the *checkout*, not the binding. This is a gap,
not a decision. Full measurement and reasoning in
`openspec/explorations/2026-08-26-the-other-half-of-the-binding.md`.

The board compensates at display time with an agent-fallback whose own comment states the price —
it *"can still over-report `working` when an agent is mid-turn on a different task"*. Task 4.7 of
`one-answer-to-what-is-happening` is blocked on exactly this: removing that fallback today would
flip every actively-worked flow task to `held`, because there is no binding for the truthful path to
read.

**Why now, and why with F66.** Binding work runs is what makes finding F66 dangerous. Two rules pick
a task out of one batched turn and they are not the same rule: the workspace takes *any* entry
carrying `review_task_id` (`hub/hub/api/v1/agent_trigger.py:278`), the binding takes the *earliest
queued* entry naming a task (`hub/hub/run_task_binding.py:143`). Today only 6 job entries carry
`review_task_id` and 0 carry `task_id`, so the disagreement is nearly unreachable — yet it already
happened twice (`run-26f0c4702de0`, `run-d7e30a9c650d`), each checked out to review one task while
bound to another, their boundary check running against work they were not looking at. Once every
work entry carries `task_id`, **any** turn mixing a review and work disagrees. The fix must ship
with the binding, not after it.

## What Changes

- **A flow firing binds the run it starts.** Both staging paths write `task_id` for an ordinary work
  selection, mirroring the `review_task_id` line already beside them. A firing that staffs a review
  continues to write `review_task_id` only — group 1 of `one-answer-to-what-is-happening` already
  made that bind through `task_named_by`.
- **A turn never mixes a review and ordinary work.** The batcher stops assembling one: the
  controlling entry's kind decides the turn, and entries of the other kind stay queued for the next
  turn. The trigger additionally refuses a mixed batch it is handed directly, as the product already
  refuses two distinct review tasks with a 409. `agent-flows` already promises *"A firing that staffs
  a review SHALL NOT deliver an ordinary turn"* — that guarantee is enforced per *firing* and broken
  per *delivered turn*, because a turn can batch entries from more than one firing.
- **A divergence's event severity is derived from whether the condition is actionable**, replacing
  the hardcoded `severity="warn"` at `hub/hub/run_divergence.py:738`. A task still held by the same
  agent under a live flow is work that is simply not finished yet — `info`. An agent that released
  the task, a run that failed, or a terminal task is nobody coming back — `warn`. This is the same
  distinction `resolve_divergences_for_task`'s docstring already draws in prose
  (`hub/hub/run_divergence.py:64`) but that never reached the operator's log.
- **Resolving a divergence emits an event.** `resolve_divergences_for_task`
  (`hub/hub/run_divergence.py:61`) writes `resolved_at` and emits nothing today, so an open
  condition is announced and its answer is silent. The close becomes as visible as the open.
- **`retry` does not answer a flow work divergence while the loop is live.** The flow re-fires the
  task on its next tick — the flow *is* the retry, and applying `retry` on top means two runs for
  one task. `escalate` and `surface` continue to apply unchanged.

## Non-Goals

- **Removing the board's agent-fallback.** That is task 4.7 of `one-answer-to-what-is-happening`,
  which is being held open for it. This change makes the data true; 4.7 then removes the compensation
  that existed because it was false. Landing them in the wrong order flips every actively-worked flow
  task to `held`.
- **Changing what `divergence_policy` means for delegated or operator-started runs.** Only the
  flow-work path gains a constraint.
- **Reworking the divergence response chain.** `_may_escalate`'s hop rule
  (`hub/hub/run_divergence.py:84`) is unchanged.
- **`dev`'s 36 firings against an empty queue in `toolkit-sandbox`.** A loop fired 36 times with
  nothing to claim; `_loop_stall_reason` is supposed to be what the operator sees for that. A
  separate finding, recorded in the exploration, not addressed here.
- **Backfilling `task_id` onto historical runs.** Bindings are set from the cause that started the
  run; a run that has ended has no such cause to consult.
- **Any change to the review checkout itself.** The comment that ordinary work acquires no checkout
  is correct and stays.

## Capabilities

### New Capabilities

None. Every behaviour here belongs to a capability that already exists.

### Modified Capabilities

- `run-task-binding`: a flow firing that claims a task SHALL bind the run it starts; a divergence
  event's severity SHALL be derived from whether the condition is actionable rather than fixed;
  resolving a divergence SHALL be as visible as opening one; `retry` SHALL NOT answer a flow work
  divergence while the loop is live.
- `agent-conversation-workspace`: the existing *"A review turn has exactly one workspace"* guarantee
  SHALL hold over the whole delivered turn — a turn given a review checkout SHALL NOT also carry
  another task's work.
- `agent-flows`: the existing *"A firing that staffs a review SHALL NOT deliver an ordinary turn"*
  requirement SHALL be enforced at the delivered turn, not only at the firing, so that batching two
  firings cannot produce what a single firing is forbidden to produce.

## Impact

**Code**

- `hub/hub/scheduler.py` — the two staging paths (`2302`, `2621`): one line each.
- `hub/hub/turn_scheduler.py` — the batch selection at `~72`, where the D1/F5 comment already
  records this exact bug shape: *"nothing used to ask which entries may ride on it"*.
- `hub/hub/api/v1/agent_trigger.py` — `_review_task_from_entries` and its caller: refuse a mixed
  batch handed in directly.
- `hub/hub/run_task_binding.py` — `binding_from_entries`' docstring currently states the rule this
  change removes (*"a turn batching work and a review must bind by arrival"*); the mixed case ceases
  to exist.
- `hub/hub/run_divergence.py` — derived severity at the emission site; a resolution event in
  `resolve_divergences_for_task`; the `retry` suppression for flow work.

**Behaviour the operator sees**

- `assigned → in_progress` becomes a runtime transition the firing causes, at flow scale, for the
  first time. Today a flow's task sits at `assigned` while an agent works it.
- Every flow work turn enters the divergence boundary. Scoped to projects that actually hold loop
  tasks, 9 of 19 job-origin work runs ended with no actor transition — not the 45 of 55 an unscoped
  count suggests, which is dominated by `toolkit-sandbox`, a project with zero loop tasks whose
  firings claimed nothing and would therefore never bind.
- The activity log gains a resolution event and loses the warning on healthy multi-turn work.

**Not affected**

- No new column: `InboundQueueEntry.task_id` and `Run.task_id` already exist and are already written
  by the delegation and operator-start paths. **One migration is required** — `run_divergences.
  policy_applied` carries a CHECK constraint, so recording the flow régime widens it, exactly as
  `0092` did for the review régime.
- Flows run `session_mode: new`, so each firing gets a fresh conversation and the conversation
  rebinding that follows a bound run stays contained to that firing.
