## Context

Three surfaces answer "what is happening with this task right now" and they disagree, because the
edge that would let them agree is not written.

`review_task_id` on an inbound queue entry drives a *workspace checkout* — design D9, finding F10 —
and nothing else (`hub/hub/scheduler.py:2611`, consumed at `hub/hub/api/v1/agent_trigger.py:471`).
`task_id` on the same row drives the *run binding* (`hub/hub/run_task_binding.py:106`, consumed at
`agent_trigger.py:538`). On the trial database the two columns are perfectly disjoint — 34 rows with
`task_id`, 9 with `review_task_id`, no row with both — so every review run in the product's history
has `run.task_id` NULL.

The board compensates. `hub/hub/api/v1/jobs.py` matches on `Run.task_id` where it is set and on
`Run.agent` where it is not, and its own comment states the cost: the fallback "can still
over-report `working` when an agent is mid-turn on a *different* task". Around that fallback sits a
~90-line derivation inside an API renderer, merging `decide_firing`'s output, the task rows and the
runs table, with F23, F26, F45, F49 and F63 layered into its comments.

The root collision: `FiringDecision.in_flight` is a public tuple meaning *"this firing cannot staff
anybody onto this"* (`hub/hub/scheduler.py:1221`, appended unconditionally for an `under_review`
task with an assignee so a verdict-less review stays visible — F23, F45). Any consumer may pick it
up and read it as anything. One did.

Full investigation, including the options considered and rejected:
`openspec/explorations/2026-08-26-one-answer-to-what-is-happening-now.md`.

## Goals / Non-Goals

**Goals:**

- A run started to review a task records which task it is reviewing.
- A review that ends without a verdict is a recorded fact rather than something a surface infers
  from absence.
- Exactly one computation answers what an agent is doing on a task, and the values it derives from
  are not reachable by the surfaces that render it — enforced, not merely documented.
- The existing reviewer-resolution rule answers a failed review, rather than a second mechanism.

**Non-Goals:**

- Event-sourcing the state core (addresses the vocabulary collision only; see the exploration).
- Detecting runner-side refusals — F52's cause is measured as not currently detectable.
- A `divergence_policy` rule table (deferred on evidence; one populated side today).
- Backfilling the 154 existing unbound runs.
- Conversation titles and F61 (configuration visibility, not state truthfulness).
- Changing F65's trigger-time refusal.

## Decisions

### D1 — `binding_from_entries` learns `review_task_id`; the checkout column stays what it is

`binding_from_entries` selects the earliest queued entry naming a task. It gains `review_task_id` as
a second source of "names a task", keeping the same earliest-wins ordering so a turn delivering both
a work item and a review binds deterministically.

`review_task_id` is **not** repurposed and **not** merged into `task_id`. It means "check out this
commit" and it will keep meaning that; the change is that binding stops being blind to it.

*Alternatives.* Setting `task_id` on review entries as well was rejected: `task_id` is also read by
`format_turn_prompt` ordering and by `binding_from_entries`' divergence-source pairing, and
overloading it would make an entry's two purposes inseparable again — the exact defect being fixed,
inverted.

### D2 — binding a review is inert for the task and live at the boundary

Verified, not assumed:

| | |
|---|---|
| status | `allowed_targets('under_review', run)` = `approved`/`rejected`/`revision_needed`. No `in_progress`, so `bind_run_to_task` binds and returns `None`. |
| assignee | already set by the scheduler when it staffed the review; the `not task.assignee` guard makes it a no-op. |
| | **Confirmed by task 1.6, and it holds for a second reason the design did not have.** `_enter_selected_task` (`scheduler.py:769`) writes `task.assignee = agent` for every staged selection, review included, so the guard is a no-op on the flow path. The operator path has no such staging — a review triggered by `review_task_id` alone reaches binding on a task that may still be `completed` — and it is inert there too, because `allowed_targets('completed', run)` is `['under_review']` and offers no `in_progress` edge either. So the status half rests on the transition map at **both** entry statuses, not on the scheduler having gone first. `bind_run_to_task` needs no change; the two statuses are pinned by test rather than left to the argument. |
| conversation | no unique constraint on `conversations.task_id`; author's and reviewer's threads may both bind. |

What changes is the boundary. `run_advanced_its_task` returns `True` for any unbound run — *"no task
to have neglected"* (`hub/hub/run_task_binding.py:497`) — which is how reviews escape it today. Bound
reviews are checked: all 14 observed verdict transitions carry `origin='actor'`, so a review that
records a verdict passes; one that does not records a `RunDivergence`.

Knock-on: F38's `note_turn_that_produced_nothing` fires for review runs today *because* they are
unbound, and will stop, taking the divergence branch instead. That is the intended replacement, not
a regression.

### D3 — reviews are not governed by `divergence_policy`

A run's exit status already splits two cases into different machinery:

```
final_status == "failed"      →  return_run_entries(): entries go back to `queued`,
                                 boundary check SKIPPED, a new run binds to the same task
final_status == "completed",  →  evaluate_run_end(): RunDivergence recorded
task did not move
```

Confirmed in the data: all 23 `run_divergences` rows carry `run_exit_status = 'completed'`; none of
the 16 `failed` runs produced one. **A crashed run already retries**, via re-queueing, and that
predates `divergence_policy`.

So `retry` means *the agent had its full turn and moved nothing* — defensible for a work run,
close to indefensible for a review, where re-running the same reviewer on the same evidence and the
same briefing is the least likely intervention to change the outcome, and the observed causes (F65's
refused briefing, F52's wall, the F38 family) are deterministic rather than flaky. `escalate` would
require `task.escalation_agent`, a second reviewer resolution that `agent-flows` forbids in terms:
*"by the same resolution the rest of the product already uses for a declared reviewer, never a second
one."* `surface` is what the divergence row already is.

The spec states reviews are **not governed by** `divergence_policy` rather than assigning reviews a
policy value, so the eventual rule table can arrive without unpicking this.

**Deviation found during implementation: this needs a migration after all, `0092`.** The Migration
Plan below says "no database migration; no schema change", written from reading the columns. Both
`run_divergences.policy_applied` and `run_divergences.outcome` carry CHECK constraints
(`ck_run_divergences_policy`, `ck_run_divergences_outcome`) that the design did not account for, so
recording the review régime at all requires widening them — SQLite cannot alter a CHECK in place,
so the table is recreated, following `0058`'s idiom for the identical kind of widening.

Two values are added and neither is a policy a task can hold. `policy_applied = 'review'` names the
régime that governed, which is the only truthful thing to write: recording the task's own policy
would show `retry` beside an outcome nothing retried. `outcome = 'restaffed'` is a failed review
answered by resolving the reviewer again — distinct from `retried` (the same agent) and `escalated`
(`task.escalation_agent`). `POLICY_REVIEW` is deliberately kept out of `run_task_binding.POLICIES`,
which is what stops an operator setting it on a task.

**Re-resolution is bounded by derivation, not by a hop count.** Excluding only the agent that just
failed would let `A → B → A → B` run forever on a two-agent roster. The exclusion is instead every
agent holding an *unresolved* review divergence on this task, read from the rows themselves — which
terminates against a finite roster and reaches the spec's own "a second failure with nobody left
surfaces" by the general rule. Scoping to unresolved is what lets a task that was revised and came
back reach the same reviewer again: `resolve_divergences_for_task` closes them when an actor
transition lands.

*Alternatives.* A `review_divergence_policy` column was rejected on evidence: `escalation_agent` is
NULL on all 40 tasks and was superseded before it ever fired. One policy governing both was rejected
because it is the collision this change exists to end — after D1, one column would silently govern
two different failures against the same task.

### D4 — a failed review is answered by re-resolving the reviewer

```
review run completes with no verdict
        │
        ├── reviewer was DECLARED  ──▶ surface. Never substitute.
        │        Firing someone else tells the operator the named reviewer checked
        │        the work when it did not — the requirement's own reasoning.
        │
        └── reviewer was picked by AVAILABILITY ──▶ resolve again, excluding the one that failed
```

Three properties fall out: no entry price (nobody populates `escalation_agent`, consistent with
AgentWeave not demanding setup before use); the D6 eligibility problem cannot arise, because the
resolver already excludes ineligible agents; and a spec-time declaration is what gets honoured.

### D5 — a divergence response entry carries the review checkout

`run_divergence._queue_response` builds `new_entry(..., task_id=task_id)` with no `review_task_id`
(`hub/hub/run_divergence.py:165`). A responding reviewer would be fired into its own worktree where
the work under review does not exist — **finding F10, reproduced by the mechanism meant to rescue a
failed review.** The response entry carries `review_task_id` when the diverged run was itself a
review.

This has never fired, because escalation requires `escalation_agent` and it is NULL everywhere. D4
makes the path reachable, which is what makes this a prerequisite rather than a cleanup.

### D6 — an escalation target must be able to legally review

An agent cannot approve work it completed (`hub/hub/task_transition_service.py`,
`_agent_that_completed`, a 403 by design). Escalating a review to the task's own author is therefore
a guaranteed refusal on arrival. Under D4 the reviewer resolver already excludes ineligible agents,
so this is enforced by construction for reviews; the requirement exists so a future path cannot
reintroduce it.

### D7 — the crash path and the F45 withdrawal path are already disjoint; a test pins it

Flagged during exploration as needing reconciliation. Reading both: they cannot collide.
`return_run_entries` (`hub/hub/inbound_queue.py:177`) acts only on entries in state `delivered` for a
run whose `final_status == "failed"`, counts `delivery_attempts`, and at `DELIVERY_ATTEMPT_LIMIT`
withdraws the entry with an `abandoned_reason` — so re-delivery is already bounded and cannot loop.
F45's withdrawal acts on a *completed* run. The two are separated by exit status, and
`evaluate_run_end` is skipped when entries were returned.

A re-delivered review entry keeps its columns, so `review_task_id` survives requeue and the checkout
is not lost. No change is needed; the change adds a test asserting the two paths stay disjoint,
because nothing currently states it and a future edit could merge them.

### D8 — `agent_role` is renamed to `agent_capacity`

`agent-loops` already calls this concept **capacity** — *"An agent attributed to a task SHALL be
attributed in a stated capacity"* — while the wire field and the code call it `role`. Meanwhile
"role" means three other things in this codebase: a charter (a behaviour contract, optional and
absent on 6 of 17 agents), work-versus-review as a turn kind, and the deleted role subsystem. Adding
a fourth meaning to a field this change is rewriting would repeat the mistake it exists to end.

Nominally breaking, materially not: the only consumer is `hub/ui`, which ships from this repository
as a committed build artefact, and there is no external API contract. The values are unchanged.

*Alternative.* Keeping `agent_role` was considered for compatibility and rejected — the compatibility
is with ourselves, and the proposal's "non-breaking" claim is corrected by this decision rather than
preserved by it.

### D9 — the derivation is owned, and the ownership is enforced by test

New module `hub/hub/task_attribution.py`, taking the spec's own vocabulary. One entry point
answering, for a `(task, agent)` pair, which capacity applies:

```
  working   ← the runs table                      (trustworthy for reviews only after D1)
  held      ← claimed or under_review, no run, and the firing cannot staff it
  next      ← the firing's selection
  assigned  ← the task's own assignee
```

Each capacity has its own source. The bug being fixed is not "two inputs" — it is **one input asked
a question it does not answer**.

`FiringDecision` stops exposing the merged collection publicly; `task_attribution` is the only
module that reads it. Python cannot enforce that, so it is enforced the way this repository already
enforces `task_integration.py`'s never-push guarantee — `test_nothing_pushes` scans the module source
for `"push"`, `"fetch"`, `"remote"`. A source-scanning test asserts no module outside
`task_attribution.py` reads the scheduler's raw in-flight collection.

The agent-fallback in `jobs.py` is removed. `jobs.py` renders.

*Alternatives.* A derivation module alone (no encapsulation) leaves a tested module a future surface
can bypass. Splitting `FiringDecision`'s field alone (no owned derivation) is a rename — `jobs.py`
could misread `cannot_staff` tomorrow. Materialising the answer in a column was rejected as the only
option introducing a genuinely new failure mode, drift between stored and computed.

### D10 — the "is it running" call sites are audited, not assumed

At least eight modules compute `Run.status == "running"` with differing scope. They are **not** all
the same question: `hub/hub/agent_auth.py` asks whether there is a live run to mint credentials for,
which is a security check, and `hub/hub/conversation_titles.py` documents deliberately *not*
recording a `Run` so a titling spawn does not make an agent look busy. The audit is a task with a
written outcome per site — same question, or legitimately different, and why — and only the first
kind moves.

## Risks / Trade-offs

**Bound reviews enter divergence machinery for the first time** → all 40 tasks are
`divergence_policy: surface` today, so nothing acts. D3 removes reviews from the policy entirely
before the policy can reach them. Test asserts a `retry` task's failed review does not retry.

**A refactor is a larger surface for this repository's dominant failure mode** — fixes that pass
their tests and cannot fire. F49 was a five-line derivation bug live from the day it shipped, with
five vitest cases over the renderer and zero Python tests over the derivation → the derivation is
tested in Python; each capacity branch is mutation-checked by name, as F63 and F64 were; and the
result is live-verified against the trial Hub, the only thing that has ever caught one of these.

**A review's divergence could read as blaming the author for a Hub failure** → a review that could
not see the work mostly never starts: `prepare_review_turn` refusing yields a 409 and no run, so it
never reaches the boundary. The exception is F52, where the run starts and hits the wall mid-turn.
The divergence records what happened, not fault, and D4 routes it to a reviewer rather than to the
author.

**Renaming `agent_role` touches the UI bundle** → `hub/hub/static/ui` is a committed artefact;
source and bundle are committed together with `make ui` per CLAUDE.md.

**F45 could return if re-delivery and withdrawal are later merged** → D7's disjointness test.

## Migration Plan

No database migration; no schema change. `run.task_id` begins being written for review runs going
forward. **No backfill** — the 154 unbound runs on the trial database are test data.

Order, each step independently revertable:

1. D1 + D2 — binding and what the boundary means. Verifiable alone: a review run acquires
   `run.task_id`, and a verdict-less review produces a divergence row.
2. D3 + D4 + D5 + D6 — how a verdict-less review is answered. Must land before any task is given a
   non-`surface` policy.
3. D8 + D9 + D10 — the owned derivation, the rename, the audit. Depends on (1) for `working` to be
   trustworthy.

Rollback: reverting (1) restores unbound review runs and the agent-fallback; (3) is inert without
(1) but not incorrect, since the fallback only leaves in (3).

## Open Questions

- **What the audit in D10 finds.** Unknown until performed. If a site turns out to be the same
  question with different scoping, it moves; if it is a different question, it stays and the reason
  is written down. Neither outcome changes the rest of the design.
- **Whether `held` and a recorded divergence are one fact or two on the card.** After D1 a
  verdict-less review has both a capacity (`held`) and a `RunDivergence` row. The spec requires the
  capacity; whether the card also surfaces the divergence is a rendering decision left to
  implementation.
