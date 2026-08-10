# Tasks

Ordered by dependency. Sections 1–3 are the data model and the binding; 4–5 the divergence machine;
6 the operator's surface; 7 the spec and the hook rule; 8 verification.

## 1. Schema

- [x] 1.1 Add `Run.task_id` (nullable, `String(64)`, indexed) and `Run.divergence_source_run_id`
      (nullable, `String(64)`) to `hub/hub/db/models.py`, with a docstring stating that the binding
      is set by the runtime and that NULL means unbound and unchecked
- [x] 1.2 Migration `0054` for both columns, guarded for a missing `runs` table in the manner of
      `0052`/`0053`
- [x] 1.3 Add `InboundQueueEntry.task_id` (nullable) with a comment stating why it lives on the entry
      rather than passing through the scheduler call — the same reason `spec_document` does
- [x] 1.4 Migration `0055` for the queue column, guarded
- [x] 1.5 Add `Task.divergence_policy` (`String(16)`, server default `'surface'`) and
      `Task.escalation_agent` (nullable `String(64)`). **No CHECK constraint** — see 1.6
- [x] 1.6 Add `TaskTransition.origin` (`String(16)`, server default `'actor'`), with the docstring
      explaining that without it the runtime's own auto-transition satisfies the divergence check
      (design D5). **No CHECK constraint, deviating from the plan:** a table-level CHECK naming a
      column makes that column undroppable in SQLite, so it made `0056` irreversible — caught by
      `test_migration_0052_downgrade_drops_the_history`. It is also the consistent choice: the
      neighbouring `actor_kind`, `tasks.status` and `tasks.priority` carry no CHECK either. The
      values are declared in `task_transition_service.ORIGINS` and enforced there, with a test. The
      CHECKs on the new `run_divergences` table are kept — a new table is dropped whole, so the
      problem does not arise, and `runs.initiator` sets that precedent
- [x] 1.7 Migration `0056` for 1.5 and 1.6, guarded; no backfill — the server defaults are the values
      that are true for every pre-existing row (D12)
- [x] 1.8 Add the `RunDivergence` model per design D10, keyed on an autoincrement `sequence` primary
      key with a separate `id` string, following `TaskTransition`
- [x] 1.9 Migration `0057` for `run_divergences`, guarded for missing `runs`, `tasks` and `projects`
- [x] 1.10 Bump the head assertion to `0057` in **both** `hub/tests/test_migrations.py` and
      `hub/tests/test_project_persistence.py`, and add per-migration tests following the three `0052`
      tests

## 2. The transition origin

- [x] 2.1 Add an `origin` parameter to `task_transition_service.apply_transition`, defaulting to
      `actor`, and write it onto the `TaskTransition` row
- [x] 2.2 Assert in `hub/tests/test_task_transitions.py` that no call site outside the binding module
      passes `origin='runtime'` — a source scan, in the manner of the existing append-only scan
- [x] 2.3 Confirm `Actor` and `ACTOR_KINDS` are unchanged, and add a test asserting the actor kinds
      remain exactly `run` and `operator` (D5, and the spec's "actor kinds remain unchanged")

## 3. Binding a run

- [x] 3.1 New `hub/hub/run_task_binding.py`: resolve a binding from a trigger cause, apply the
      automatic transition through `apply_transition(..., origin='runtime')`, and answer "did this run
      move its task?" — no HTTP, no spawn logic, mirroring how `task_transitions.py` stays inert
- [x] 3.2 Validate a delegated `task_id` against the sending run's project in the agent plane; refuse
      with a message naming the failing id, and keep the delegation deliverable unbound rather than
      losing it
- [x] 3.3 Carry `task_id` from the delegation onto the `InboundQueueEntry` in `hub/hub/inbound_queue.py`
- [x] 3.4 Resolve the binding at the single `Run(` creation site (`agent_trigger.py:474`): earliest
      queued entry naming a task wins (D3), else the trigger request's explicit task id, else unbound
- [x] 3.5 Accept an explicit task id on the operator trigger request schema, validated against the
      project
- [x] 3.6 Apply the automatic transition inside the same commit as the `Run` insert, so a bound run
      whose task never moved cannot exist as a partial write
- [x] 3.7 Leave `request_agent`'s free-text `task` alone, and add a test asserting it grants no
      binding (D3)

## 4. Detecting divergence

- [x] 4.1 Implement the check per design D6: bound, ended, and no `origin='actor'` transition by this
      run on this task
- [x] 4.2 Call it at the run-end path in `agent_trigger.py`, for every exit status
- [x] 4.3 Call it from `run_reconciliation.reconcile_interrupted_runs` so a crash does not lose a
      divergence. **Narrowed while implementing:** a run whose delivered input was returned to the
      queue is *not* divergent — that input is about to be handed to a new run bound to the same
      task, so nothing was dropped, and under `retry` a divergence there would spawn a run racing
      the redelivery. Spec amended with a scenario
- [x] 4.4 Write the `RunDivergence` row: task status at end, run exit status, policy applied, outcome
- [x] 4.5 Resolve open divergences for a task when any later `origin='actor'` transition lands on it —
      inside `apply_transition`, so no caller can reach a transition without it
- [x] 4.6 Persist an event and broadcast over SSE, using an operator-facing severity the operator's
      view understands

## 5. Answering divergence

- [x] 5.1 `surface`: record, event, broadcast. Start nothing
- [x] 5.2 `retry`: start one further run of the same agent bound to the same task, setting
      `divergence_source_run_id`; skip entirely when the diverging run already carries one (D8)
- [x] 5.3 `escalate`: set `task.assignee = escalation_agent`, record the previous assignee, start a
      bound run of the escalation agent (D9)
- [x] 5.4 `escalate` with no escalation agent named falls back to `surface`
- [x] 5.5 A `retry` run that itself diverges falls through to `escalate` when the task names an agent,
      else `surface`. **Found while implementing:** the bound as planned covered only retry, so an
      `escalate` run that diverged escalated to the same agent again, forever — the task still
      carries the same policy and the same escalation agent. A run may now escalate only if it is
      not itself the product of an escalation, read from the causing divergence's recorded outcome.
      Spec amended; `test_an_escalation_that_diverges_does_not_escalate_again` holds it
- [x] 5.6 Compose the response prompt: the task, its current status, the transitions available to the
      run, and — for escalation — the diverging run's identity
- [x] 5.7 Route the response run through the existing trigger path, so hop budget, queue limits, and
      turn depth all apply unchanged. Queued rather than spawned, so a response arriving while the
      agent is busy waits instead of failing. **Needed migration `0058`:** a divergence response is
      none of the four existing queue origins, and borrowing `operator` would put the operator's
      name on work they did not ask for, in the queue they read — the same argument `checkpoint`
      already makes in `models.py`. `0058` also carries `divergence_source_run_id` onto the entry,
      since the retry bound lives on the run and a queued answer becomes a run in a later call

## 6. The operator's surface

- [ ] 6.1 Expose `divergence_policy`, `escalation_agent`, and open-divergence state on the task schema
- [ ] 6.2 `GET` the project's divergences, and a hook in `hub/ui/src/api/`
- [ ] 6.3 Policy and escalation-agent controls on the task card, the escalation agent chosen from the
      project's agents
- [ ] 6.4 Divergence indicator on the task card that clears on resolution
- [ ] 6.5 Start a bound run from a task card, naming the agent
- [ ] 6.6 Show a run's bound task where runs are displayed
- [ ] 6.7 `npm run build`, `rm -rf hub/hub/static/ui`, copy `hub/ui/dist` over it, confirm with
      `diff -rq`

## 7. Specs

- [ ] 7.1 Add the `no capability may exist only in a hook` requirement to
      `openspec/specs/agent-capability-plane/spec.md` (D13)
- [ ] 7.2 Apply the `task-lifecycle-governance` deltas
- [ ] 7.3 Create `openspec/specs/run-task-binding/spec.md` from the delta
- [ ] 7.4 `npx openspec validate --specs --strict` and `--changes --strict`

## 8. Verification

### 8a. Agent-verifiable — expected behaviour stated, run by the agent

- [ ] 8.1 `pytest hub/tests/ -q` — all pass, count no lower than the 1384 at this change's start
- [ ] 8.2 `pytest tests/ -q` — all pass
- [ ] 8.3 `cd hub/ui && npx vitest run` and `npx tsc --noEmit` — pass and clean
- [ ] 8.4 `ruff check hub/hub/ hub/tests/` clean; `black` applied
- [ ] 8.5 Unit: a delegation naming a task produces a bound run; naming a foreign task is refused;
      naming nothing produces an unbound run
- [ ] 8.6 Unit: binding a `pending` task records one `origin='runtime'` transition to `in_progress`;
      binding an `in_progress` task records none; binding an `approved` task binds and records none
- [ ] 8.7 Unit: a run whose only transition is the runtime's is divergent; one that also completed the
      task is not; an unbound run is not
- [ ] 8.8 Unit: `retry` starts exactly one run; that run diverging starts none; with an escalation
      agent it escalates instead; escalation reassigns and records the previous assignee
- [ ] 8.9 Unit: an interrupted run is checked by reconciliation
- [ ] 8.10 Unit: a later actor transition resolves an open divergence and retains the record
- [ ] 8.11 Live against `testbed/`: delegate a task between two agents and confirm from the database
      that the receiving run carries `task_id` and the task moved to `in_progress` with
      `origin='runtime'` — a behavioural probe, not an HTTP 200 (handoff 0030's dead end)
- [ ] 8.12 Live: confirm the serving process is the new code before believing any live result —
      restart by exact PID and verify the new process bound to the port

### 8b. Human-only — the operator runs these

- [ ] 8.13 Does starting work from a card feel like the obvious way to begin a task, or like a second
      path competing with the composer?
- [ ] 8.14 Is a divergence legible on the board — can you tell at a glance which tasks were dropped?
- [ ] 8.15 Does the policy control read as a routing decision rather than as a settings field?
- [ ] 8.16 Judgement call on design's Open Question 1: over a day's real use, does a divergence per
      intermediate run of long work read as noise?

### 8c. User test guide

**Setup.** In `testbed/`, one project with two agents — a cheap one (`worker`) and a stronger one
(`reviewer`). Confirm the Hub is serving the new code before starting.

1. **Binding and auto-start.** Create a task, leave it `pending`, and start work on it from its card
   with `worker`.
   *Expect:* the task moves to `in_progress` by itself, without the agent being asked.
   *Failure looks like:* the task stays `pending` while a run is clearly working, or it moves but the
   history says an actor asked for it.

2. **The clean case.** Let `worker` finish and move the task to `completed`.
   *Expect:* no divergence anywhere.
   *Failure looks like:* a divergence indicator on a task that was properly completed.

3. **Divergence, default policy.** Start a bound run and interrupt or end it without the agent
   touching the task.
   *Expect:* the task shows an open divergence; nothing new runs; no tokens are spent.
   *Failure looks like:* a run starting that you did not ask for.

4. **Divergence resolving.** Move that task yourself.
   *Expect:* the indicator clears; the divergence is still listed as having happened.
   *Failure looks like:* the record disappearing, or the indicator persisting.

5. **Retry.** Set a task's policy to `retry`, start a bound run with `worker`, end it without moving
   the task.
   *Expect:* exactly one new `worker` run, bound to the same task, told what the task is and what it
   may do next.
   *Failure looks like:* two or more runs, or a run with no idea why it started.

6. **Escalation, and the pattern you asked for.** Set the policy to `escalate` with `reviewer` as the
   escalation agent, assign to `worker`, and let a bound `worker` run end without moving the task.
   *Expect:* the task's assignee becomes `reviewer`, a `reviewer` run starts bound to it, and the card
   still shows that `worker` had it.
   *Failure looks like:* the assignee unchanged, or `worker` re-run instead.

7. **The bound.** With policy `retry` and an escalation agent set, let the retry run also end without
   moving the task.
   *Expect:* one escalation, then nothing further.
   *Failure looks like:* a third, fourth, or endless run.

8. **Unbound runs are untouched.** Talk to an agent normally, with no task.
   *Expect:* nothing about divergence appears anywhere.
   *Failure looks like:* a divergence recorded against ordinary conversation.
