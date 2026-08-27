## Context

`one-answer-to-what-is-happening` closed the run→task edge for **reviews**. Group 1 taught
`binding_from_entries` to read `review_task_id` through a new `task_named_by`
(`hub/hub/run_task_binding.py:143`), so a review run finally records the task it is reviewing.

This change closes the other half. A flow's ordinary work firing writes no task at all, so
`run_advanced_its_task` waves every flow work run through on *"no task to have neglected"*. The
measurement is in `openspec/explorations/2026-08-26-the-other-half-of-the-binding.md` and the
proposal; the short form is **61 job-origin entries, 0 carrying `task_id`, and 10 runtime
`→ in_progress` transitions in the entire database.**

Three constraints shape the design.

**The binding mechanism already exists and must not be duplicated.** Delegation and operator-start
both bind by naming a task on the queue entry; the run picks it up when the entry is delivered. A
flow firing is the third cause and belongs on the same path.

**Binding work runs is what makes finding F66 dangerous.** Two rules pick a task out of one batched
turn — the workspace takes any entry carrying `review_task_id`
(`hub/hub/api/v1/agent_trigger.py:278`), the binding takes the earliest queued entry naming a task
(`hub/hub/run_task_binding.py:143`). With 0 work entries carrying a task the disagreement is nearly
unreachable, and it still happened twice. Once every work entry carries one, any mixed turn
disagrees.

**This repository's dominant failure mode is a fix that passes its tests and cannot fire in
production.** Every decision below is written to be checkable against the live database, not only
against a fixture.

## Goals / Non-Goals

**Goals:**

- A flow work run records the task it is working, by the same mechanism every other cause uses.
- A turn is a review or ordinary work, never both, and the rule is enforced where the batch is
  assembled rather than only where it is consumed.
- The divergence boundary applying to flow work does not bury the events that need the operator.
- An operator can tell a resolved divergence from a standing one.
- `retry` cannot double-fire a task the flow is already going to fire again.

**Non-Goals:**

- Removing the board's agent-fallback. That is task 4.7 of `one-answer-to-what-is-happening`; see
  D8.
- Backfilling historical runs.
- Changing the divergence response chain (`_may_escalate`, `hub/hub/run_divergence.py:84`).
- `dev`'s 36 firings against an empty queue in `toolkit-sandbox` — a separate finding.

## Decisions

### D1 — The firing writes the task on the queue entry, not on the run

Both staging paths gain one line beside the `review_task_id` line already there
(`hub/hub/scheduler.py:2302`, `hub/hub/scheduler.py:2621`): `task_id` for a selection the ladder made
as ordinary work. `binding_from_entries` then binds the run when the entry is delivered, unchanged.

*Rejected:* setting `run.task_id` at the trigger for job-origin turns. That is a second binding
mechanism running beside the first, and the spec is explicit that the system binds *"from the cause
that started the run"* — the cause is the firing, and the entry is how a firing speaks to the run it
starts. Two mechanisms is how the two rules in F66 came to disagree in the first place.

### D2 — Work and review stay separate fields

`task_id` means "work this"; `review_task_id` means "review this". A firing sets exactly one.
`task_named_by` (group 1) already reads both for binding, so nothing downstream needs a third
concept.

*Rejected:* a single `task_id` plus an `is_review` flag on the entry. That is one word carrying two
meanings, decided against for the same reason `POLICY_REVIEW` was kept out of `POLICIES` — and it
would make `review_task_for_run` (`hub/hub/run_task_binding.py:167`) read a flag instead of the fact
it currently reads directly.

### D3 — The batcher stops assembling a mixed turn; the trigger refuses one handed to it

The primary fix is in `hub/hub/turn_scheduler.py`, where `selected` is narrowed from the agent's
queued entries. Today it filters by conversation and hop depth. It gains one more narrowing: **the
controlling entry's kind decides the turn**, and entries of the other kind are left queued.

That file already records this exact bug shape one comment above, from design D1 / finding F5:

> `can_start` asks whether the turn may begin; nothing used to ask which entries may ride on it, so
> an over-budget entry was bundled into a turn admitted by a shallower one and delivered anyway.

F66 is the same sentence with "over-budget" replaced by "of the other kind". Using `controlling` —
the earliest admitted entry — is the idiom the file already uses to pick `turn_depth`, and it makes
the outcome deterministic by arrival order rather than by which column happened to be set.

The trigger's refusal stays as defence in depth, for a caller that hand-assembles `queue_entry_ids`.
It extends `_review_task_from_entries`' existing 409 rather than inventing a second status.

*Rejected:* refusing at the trigger **only**. The entries stay queued after a refusal, so the next
scheduling attempt reassembles the same batch and refuses again — a permanent wedge, and precisely
what `agent-conversation-workspace`'s *"Repeated delivery failure does not wedge an agent"* exists to
prevent. Narrowing the batch loses nothing: the deferred entry rides the next turn.

*Rejected:* reconciling instead of separating — making the binding follow the review whenever both
are present. The work item would then be delivered in the prompt while nothing bound it or tracked
it, which is a silent drop dressed as a fix.

### D4 — One owned predicate answers "was this a live flow's own work turn"

Both the severity derivation (D6) and the `retry` suppression (D7) need the same fact. It is computed
once, in one named function, and both read it.

Writing the check inline at both sites is the exact defect `one-answer-to-what-is-happening` exists to
end: one question, two answers, free to drift. `task_attribution.py`'s module docstring is the
statement of that principle and this follows it — though the predicate does **not** live in that
module, because `attribute` answers a batched board question from a `FiringDecision`, which the run
boundary does not have.

### D5 — The flow is found through `loop_for_conversation`, not a new column

`hub/hub/checkpoints.py:138` already owns the join `JobRun.conversation_id → job_id → Loop.job_id`,
and notes that `_batch_loop_summaries` uses the same one. "Live" means the loop exists and carries
neither `stopped_at` nor `archived_at`.

*Rejected:* adding `job_id` to `InboundQueueEntry`. It would be a more direct fact, and the firing
does know the value — but it restates something two existing joins already reach, and a restated fact
is one that can disagree with its source. That is this change's own principle, and it costs a
migration to violate it.

### D6 — Severity is derived; resolution gets its own event kind

`hub/hub/run_divergence.py:738` hardcodes `severity="warn"` with a comment explaining why warn is
right — written when the only divergences were delegated and operator-started runs, where it is.

Severity now comes from the condition: a task still held by the same agent, under a live flow, after
a cleanly-ended run, is announced at `info`; anything else stays `warn`. This is the distinction
`resolve_divergences_for_task`'s docstring already draws — *"an open condition, not a verdict"*,
existing so the policy does not *"read as an accusation against an agent that is simply not finished
yet"* (`hub/hub/run_divergence.py:64`) — finally reaching the operator's log.

`resolve_divergences_for_task` emits a new `run_divergence_resolved` event naming the task and the
count closed, and only when the count is non-zero.

*Rejected:* re-emitting `run_diverged` with a `resolved` flag in the payload. Any consumer filtering
on the event kind — the activity log, the SSE client, a future count — would tally the resolution as
a new divergence. A different fact gets a different kind.

*Rejected:* suppressing the first silent turn and emitting only on the second. It is a heuristic
rather than a derivation, and an agent that genuinely stalls on its first turn goes unreported until
a second turn that a stopped flow never fires.

### D7 — A suppressed retry is recorded as the flow régime, not as `retry`

`retry` does not answer a divergence of a live flow's own work turn. The flow fires the task again on
its next tick, so `retry` would start a second run racing the flow's own — the shape
`run_advanced_its_task` already refuses for returned queue input, for the same reason.

The record says so: a new `POLICY_FLOW = "flow"`, deliberately absent from `POLICIES` so no task can
ever carry it, exactly as group 2 did with `POLICY_REVIEW`. `outcome` stays `surfaced`.

`escalate` continues to apply. An escalation moves the work to a *different* agent, which is not
something the flow's next firing does, so it is not a duplicate of anything.

*Rejected:* recording `policy_applied='retry'` with `outcome='surfaced'`. That shows `retry` beside
an outcome nothing retried — the one-word-two-meanings defect again.

*Rejected:* a full carve-out making flow work answer only to a régime, as reviews do. It would make
`divergence_policy` mean nothing for the product's main loop, and `escalate` on flow work is
meaningful.

### D8 — Task 4.7 lands after this change, in the change that owns it

`one-answer-to-what-is-happening` is being held open. This change makes the binding true; 4.7 then
removes the agent-fallback that compensated for it being false. Landing 4.7 first flips every
actively-worked flow task to `held`, which is the same lie pointed the other way.

**Built, with no behavioural deviation.** All eight decisions landed exactly as designed — D1's
`task_id` line beside each staging path's `review_task_id`, D2's separate fields, D3's
`selected`-narrowing in `turn_scheduler.py` plus the trigger's defence-in-depth refusal, D4's single
`is_live_flow_work_turn` predicate feeding both D6 and D7, D5's read through `loop_for_conversation`
rather than a new column, D6's derived severity and dedicated `run_divergence_resolved` event, and
D7's `POLICY_FLOW` kept out of `POLICIES`. Confirmed twice: once by the unit suite (`tasks.md`
3.1-3.4/4.1-4.10/5.1-5.10) and again by group 6's live drive against `proj-18e5d4e0`, which produced
every one of D1/D2/D6/D7/D3's outcomes against a real scheduler tick rather than a fixture.

**Two citations drifted, corrected here rather than in the prose above** (both are the ordinary kind
of drift this document's own citations warn about — line numbers move as surrounding code changes,
not the decisions). D6's `hardcode="warn"` was cited at `run_divergence.py:738` when this document
was written; group 4's insertions above it (`is_live_flow_work_turn`, the resolution's own event
block) shifted it to line 813 by the time it was replaced. D1's second staging path was cited at
`scheduler.py:2621`; it is `scheduler.py:2630` today. Neither changes what either decision says.

## Risks / Trade-offs

**Every flow work turn now enters the divergence boundary; 9 of 19 measured job-origin work runs
ended with no actor transition** → D6's derived severity and resolution event are the mitigation, and
the measurement is repeatable: the same query that produced 9/19 is re-run after the change to see
what the log actually looks like. The unscoped figure of 45/55 is not the number to design against —
36 of those are `dev` in `toolkit-sandbox`, a project with zero loop tasks, whose firings claim
nothing and would therefore never bind.

**`assigned → in_progress` becomes a runtime transition at flow scale for the first time** → this is
the mechanism working as designed, but it changes what the board shows and when. It must be driven
live against the trial Hub, not only unit-tested, and 4.7 must not land before it (D8).

**A batch narrowed by D3 defers work rather than dropping it — but a review that keeps arriving first
could starve the work entry** → the deferred entry retains its position and rides the next turn;
pinned by a test that a work entry deferred once is delivered next.

**`loop_for_conversation` returns a loop for an archived or stopped flow** → the predicate checks
`stopped_at` and `archived_at` explicitly rather than treating a non-None loop as live.

**The trial database is the only place these paths have ever run** → every claim in this design that
cites a count is re-measurable against `~/.agentweave/hub/profiles/beta/agentweave.db`, and the
change is not complete until it has been driven live there.

## Migration Plan

One migration, `0094`, widening the `run_divergences.policy_applied` CHECK constraint to admit
`flow` — the same shape as `0092`, which widened it for `review`. No new column and no data
migration: `InboundQueueEntry.task_id` and `Run.task_id` already exist and are already written by two
other causes.

The head assertions in `hub/tests/test_migrations.py` and `hub/tests/test_project_persistence.py`
move `0093 → 0094`.

Rollback is the migration's own downgrade plus reverting the two `scheduler.py` lines; nothing
written by this change is depended on by anything outside it.

## Open Questions

1. **Should a work entry deferred by D3 be re-prioritised, or simply keep its place?** Keeping its
   place is the assumption above and is the smaller change; a flow that reviews often could in
   principle keep pushing it back.
2. ~~**Does `info` reach the operator's activity log at all today?**~~ **Answered by measurement,
   not assumption.** It does. `ActivityLog.tsx:76` initialises `severityFilter` to `'all'` and
   `:163` renders every event unless the operator picks a chip; `EventRow.tsx:53` treats a missing
   severity as `info` and gives it its own border and chip. The API filters only when a `severity`
   query parameter is supplied and not `"all"` (`hub/hub/api/v1/events.py:42`). So D6 makes healthy
   multi-turn work quieter without making it invisible, which is what it was chosen to do.
