## Why

**Every review turn this product has ever run is unbound.** Measured on the live trial database:
`inbound_queue_entries` carries `task_id` on 34 work deliveries and `review_task_id` on 9 review
dispatches, with **zero overlap**, and `run_task_binding.binding_from_entries` reads only
`entry.task_id` (`hub/hub/run_task_binding.py:106`). So a review run records no link to the task it
is reviewing — 5 of 7 delivered review entries landed in a run with `run.task_id` NULL, and two
`under_review → approved` transitions were made by runs holding no reference to the work they
approved.

This is not a decision. `review_task_id` is a *checkout instruction* — it exists so a reviewer is
not fired into its own worktree where the author's unmerged work does not exist (finding F10,
`hub/hub/scheduler.py:2611`) — and it carries a task id only because that is how the commit is
found. `binding_from_entries` arrived in `0b71b47`; `review_task_id` arrived much later in `ce923ce`
(migration `0086`). Two features each needed "the task" and each grew its own field. Both
resolutions now sit in the same function, seventy lines apart, reading different columns
(`hub/hub/api/v1/agent_trigger.py:468` and `:538`).

The cost lands on the board. Because `run.task_id` cannot be trusted, `hub/hub/api/v1/jobs.py`
falls back to matching on the *agent*, with its own comment conceding the fallback "can still
over-report `working` when an agent is mid-turn on a different task". That fallback sits inside a
~90-line derivation in an API renderer carrying five findings of archaeology — F23, F26, F45, F49,
F63 — each a minimal repair to the previous one's blind spot. The underlying collision is that
`FiringDecision.in_flight` means *"this firing cannot staff anybody onto this"*
(`hub/hub/scheduler.py:1221`) and was rendered as *"this agent is mid-turn on it"*.

Explored in `openspec/explorations/2026-08-26-one-answer-to-what-is-happening-now.md`, where the
event-sourcing framing was considered and rejected: it addresses the vocabulary collision only, and
the binding gap is a missing column read.

## What Changes

**The run/task edge**

- A review turn's run binds to the task it is reviewing. `binding_from_entries` learns
  `review_task_id` alongside `task_id`.
- Binding a review is inert for the task itself — `allowed_targets('under_review', run)` yields
  `approved`/`rejected`/`revision_needed` and no `in_progress`, so `bind_run_to_task` binds and
  moves nothing — but it brings review runs inside the run-boundary check for the first time.
  `run_advanced_its_task` currently returns `True` for any unbound run
  (`hub/hub/run_task_binding.py:497`), which is how reviews escape it today.
- **A review run that ends without recording a verdict records a `RunDivergence`.** The fact stops
  being inferred from absence: F45 withdrew a briefing that was re-staffed forever, and F63 invented
  a `held` role for a card reading `working` with no run alive. Both are the Hub guessing.

**How a verdict-less review is answered**

- **Reviews are not governed by `divergence_policy`.** Its three values are work-run policies and
  none does useful work here. `retry` duplicates an existing mechanism: a *failed* run's entries are
  already returned to the queue and re-delivered (`hub/hub/inbound_queue.py:177`) with the boundary
  check skipped, which is why all 23 `run_divergences` rows carry `run_exit_status = 'completed'`
  and none carry `failed`. `escalate` would need `task.escalation_agent`, a second reviewer
  resolution path that `agent-flows` forbids in terms. `surface` is what the divergence row already
  is.
- A verdict-less review is answered by the reviewer-resolution rule that already exists: where the
  reviewer was **declared**, surface and never substitute; where it was picked by **availability**,
  resolve again excluding the one that failed.
- **A divergence response entry carries the review checkout.** `run_divergence._queue_response`
  builds `new_entry(..., task_id=task_id)` with no `review_task_id`
  (`hub/hub/run_divergence.py:165`), so a responding reviewer would be fired into its own worktree —
  finding F10, reproduced by the mechanism meant to rescue a failed review.
- **An escalation target must be able to legally review.** An agent cannot approve work it completed
  (`hub/hub/task_transition_service.py`, `_agent_that_completed`), so escalating to a task's own
  author is a guaranteed 403. Neither this nor the preceding item has ever fired, because
  `escalation_agent` is NULL on all 40 tasks and `_decide` surfaces when nobody is named.

**One answer to what an agent is doing**

- The capacity a surface renders is determined in exactly one place, and the values it is derived
  from are not reachable by the surfaces that render it. The scheduler stops handing out raw
  collections for other modules to interpret.
- `held` is specced. It shipped in code on 2026-08-26 (F63) and appears in no requirement today.
- The agent-fallback in `hub/hub/api/v1/jobs.py` is removed — the binding fix makes it unnecessary.
- Which `Run.status == "running"` call sites are genuinely the same question is **audited, not
  assumed**. An earlier draft asserted eight should collapse; `hub/hub/agent_auth.py` asks whether
  there is a live run to mint credentials for, which is a security question with legitimately
  different scoping from a board question.

- **`agent_role` is renamed `agent_capacity`.** `agent-loops` already calls this concept *capacity*
  — *"An agent attributed to a task SHALL be attributed in a stated capacity"* — while the wire
  field calls it `role`, a word that already means a charter (optional, absent on 6 of 17 agents),
  a turn kind, and the deleted role subsystem. **BREAKING** nominally; materially not, since the
  only consumer is `hub/ui`, which ships from this repository as a committed build artefact. The
  four values are unchanged.

## Capabilities

### New Capabilities

None. The behaviour already has owners; inventing a capability for a refactor would add a spec
surface without adding a contract.

### Modified Capabilities

- `run-task-binding`: a run started to review a task binds to that task. The capability's own list
  of legitimate unbound runs — *"exploration, conversation, questions, and scheduled work"* — does
  not include reviews, and reviews are none of those things. Adds what the run boundary means for a
  review run.
- `agent-flows`: a review run that ends without a verdict records a divergence, and how that
  divergence is answered — by the existing reviewer resolution, not by `divergence_policy`. Extends
  *A flow resolves a reviewer by declaration, then by availability* to cover a reviewer that was
  resolved and then failed.
- `agent-loops`: strengthens *An agent attributed to a task SHALL be attributed in a stated
  capacity* — the capacity is determined in one place and its inputs are not reachable by renderers.
  Adds the `held` capacity.

## Impact

**Code**

- `hub/hub/run_task_binding.py` — `binding_from_entries`, and what the boundary check means for a
  review run
- `hub/hub/run_divergence.py` — `_queue_response` carries the review checkout; `_decide` and
  `_apply_policy` stop applying work-run policy to reviews
- `hub/hub/scheduler.py` — `FiringDecision`'s raw collections become private to the owning
  derivation; reviewer re-resolution for a failed review
- `hub/hub/api/v1/jobs.py` — the ~90-line derivation and the agent-fallback leave the renderer
- `hub/hub/api/v1/agent_trigger.py` — the two resolutions of "which task" stop being independent
- new module for the owned derivation, with Python tests over the derivation itself

**Data.** No migration. `run.task_id` begins being written for review runs going forward;
**backfill is deliberately not done** — the 154 unbound runs on the trial database are test data.

**Behaviour visible to an operator.** A review that ends without a verdict becomes a recorded, named
fact instead of a card the board reasoned about from absence. A task whose `divergence_policy` is
`retry` or `escalate` no longer has that policy silently applied to its reviews — today it would be,
the moment L1 lands, because one column would govern two different failures against the same task.

**Risk.** This repository's dominant failure mode is fixes that pass their tests and cannot fire;
F49 was a five-line derivation bug that lived in production from the day it shipped, with five
vitest cases over the renderer and zero Python tests over the derivation. The derivation must be
tested in Python, each capacity branch mutation-checked by name, and the result live-verified against
the trial Hub — the only thing in this repository's history that has ever caught one of these.

## Non-Goals

- **Event-sourcing the state core.** Considered and rejected in the exploration: it addresses the
  vocabulary collision only, while the binding gap is a missing column read and the runner-refusal
  gap is outside the process boundary entirely.
- **Detecting runner-side refusals (F52).** Measured as not currently implementable: zero
  `tool_result` rows carry a refusal, and the per-run tool failure rate does not separate F52's runs
  (0.26 and 0.36 against a median of 0.25 and a maximum of 0.76). The consequence half — a run that
  claims completion having produced nothing — is covered by the boundary work above.
- **A `divergence_policy` rule table.** The right eventual model, deferred on evidence rather than
  effort: there is one consumer distinction today and this change decides reviewers use none of the
  rules, so the table would model a distinction with one populated side. The spec must therefore say
  reviews are *not governed by* the policy rather than that reviews *have* a policy value, so the
  table can arrive later without unpicking anything.
- **Conversation titles and F61.** Not a state-truthfulness defect. AI titling already exists
  (`conversation_title_mode`, migration `0037`) and is `truncate` with a NULL runner on all five
  projects because **no UI control renders it**. That belongs with configuration visibility.
- **Backfilling the 154 existing unbound runs.**
- **Changing F65's fix.** *No evidence → `revision_needed`* is a better answer than withdrawing the
  briefing, but only where evidence is possible — 21 of 40 tasks carry a requirement link and 19
  cannot — and F65's refusal happens at trigger time before a run exists, which is a different code
  path.
- **A second policy column** (`review_divergence_policy`). `escalation_agent` is the cautionary
  tale: added for a policy nobody set, NULL on all 40 tasks, superseded before it ever fired.
