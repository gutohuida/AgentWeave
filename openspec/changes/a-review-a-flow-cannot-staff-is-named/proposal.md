## Why

```python
author = await agent_that_completed(session, task.id)
if author is None:
    continue          # records NOTHING
```

`hub/hub/scheduler.py:1364-1368`, the review arm of `decide_firing`'s walk. Not `unstaffed`, not
`deferred`, not `in_flight`, not `gated`; no log line, no persisted event, no SSE broadcast. It is
the quietest line in the flow, and it is where a flow goes to die.

**F142 (severity A), driven 2026-08-30** on `proj-1964cdedffe2` by
`scripts/drive/t_row12_review_leg.py`, three ways on one fixture:

| who moved `in_progress -> completed` | firing 2 |
|---|---|
| the **operator**, by hand | `409` *"loop queue is stalled: no claimable task among 1 open (1 completed)"* |
| the **author agent**, no evidence | `409` *"task … has no recorded evidence, so there is no commit to review …"* |
| the **author agent**, evidence recorded | **`200`** — reviewer staffed, `completed → under_review → approved`, 42s |

Row three is the feature working. Row one is this change. The operator's own transition was read off
the row:

```
sequence  from          to           actor_kind  actor_agent
67        in_progress   completed    operator    None      <-- the operator's own repair
```

`agent_that_completed` (`task_transition_service.py:123-147`) selects `actor_agent` off the most
recent `→ completed` transition and **does not filter on `actor_kind`**, so the operator's row is
selected and yields `None`. The walk drops the task, `unstaffed` stays empty, and F64's fix — which
exists precisely to say *why* a queue is stalled rather than merely *that* it is — never fires. The
operator is handed a sentence about the queue's status histogram, assembled by a `GROUP BY status`
(`scheduler.py:1515-1551`) that knows nothing about why, for a stall whose actual cause is a fact
about one task.

### This breaches a shipped requirement

`agent-flows:189-195` — *"No eligible agent surfaces rather than stalling silently"*:

> - **WHEN** no agent can be resolved or found for a task
> - **THEN** the operator is notified, naming the task
> - **AND** the flow's job remains enabled and scheduled

No agent is resolved or found. The operator is notified of nothing. **The silent drop is
indefensible under every answer to the judgement below, and goes regardless.**

### And there is no way out from the operator's seat

F142 measured this too. `completed` reaches only `rejected` and `under_review`, so the operator
cannot put the task back for an agent to finish properly. Moving it to `under_review` by hand does
not help: the task then matches `WITH_REVIEWER_LOOP_TASK_STATUSES` with the author still in
`assignee`, and the wedged-review recovery on that path (`scheduler.py:1279-1284`) is **gated on the
same function**, which still returns `None` — so the task is recorded as `in_flight`, meaning *"a
reviewer holds this"*, which is false. The operator can push it to `approved` themselves, but that is
not the flow reviewing anything; it is the operator doing the review leg by hand and the flow never
learning it happened.

**`task-lifecycle-governance:313`** — *"A review a flow cannot staff is not reported as staffed"* —
is the requirement that path implements, and it was written assuming an agent name comes back:

> A flow SHALL NOT treat a task in `under_review` as held by a reviewer when that task's assignee is
> the agent **recorded as completing it**.

When nothing is recorded as completing it, the requirement says nothing, and the code falls through
to the branch that reports it as staffed. That is a gap in the requirement, not only in the code.

### The judgement this change has to settle

`None` is **two worlds**, and no caller distinguishes them:

1. **the operator completed it** — provenance exists and is a person;
2. **nothing completed it** — the row was written straight into the status, or predates the
   transition table.

They are separable at zero cost. `Actor.__post_init__` (`task_transitions.py:64-67`) makes an actor
of kind `run` **without** an agent unconstructible, and an actor of kind `operator` **with** one
equally so. Therefore, on a `→ completed` transition, `actor_agent IS NULL` ⟺ *the operator made the
move*. One extra column in a query the walk already runs tells the two worlds apart. No migration, no
new column, no second round trip.

So the question is not *can we tell?* but *what should the flow do about the first world?* This
proposal's position, with both arguments recorded in `design.md` D4 for round 3 to re-derive:

**A flow MAY staff a review for work the operator completed.** The exclusion exists to stop an agent
signing off its own work; an operator's completion creates no agent that could. And
`requirement-traceability:158` already holds that the operator acting in person is *"a supported way
to work, not a degraded one"* — a flow that dead-ends the moment the operator touches a card
contradicts that in the one place it is most likely to happen.

### The trap in doing it naively — and this is round 1's real finding

The review arm calls `resolve_reviewer(..., exclude={author})`. With `author is None` the obvious
repair is `exclude=set()`, and **that is a self-approval route**.

In F140's exact drive, the agent did the work, committed it, recorded evidence, and never called
`update_task`; the operator then marked the card done. The agent that wrote the code is still in
`task.assignee` and is recorded on the task's `→ in_progress` transition — and with an empty
exclusion it is a perfectly eligible reviewer of its own work. Nothing downstream catches it:
`_guard_reviewer_is_not_the_author` and `_guard_author_is_not_reviewer` **both permit** when the
completer is unknown, deliberately and with reasons written at length. That is
`task_is_claimable_by`'s own warning — *"self-approval reached by two permissive defaults
agreeing"* — arriving through a new door.

So allowing it requires a different notion of the author: not *who recorded the completion* but
**which agents worked this task**, read as the distinct non-null `actor_agent` over the task's
transitions. That set contains the builder in F140's scenario and is empty for a task no agent ever
touched. It is what makes the permissive direction safe, and without it this change would ship a
regression worse than the bug.

## What Changes

**One new query, one new arm, and three call sites that stop guessing what `None` meant.**

1. **`completion_attribution(session, task_id)`** in `task_transition_service.py` — the same single
   query, reading `actor_kind` as well as `actor_agent`, returning a frozen record: *was a
   completion recorded at all*, *by which kind of actor*, *by which agent*.
   **`agent_that_completed` keeps its exact signature and semantics** and becomes a wrapper over it
   (design D3). Seven callers read `None` in three different ways; four of them are correct as
   written and this change must not reach them.

2. **`agents_that_worked(session, task_id)`** — the distinct non-null `actor_agent` over a task's
   transitions. The honest answer to *"which agents have acted on this task"* when no completion
   names one.

3. **The review arm splits into three, and none of them is silent.**

   | attribution | today | after |
   |---|---|---|
   | an agent completed it | ladder, `exclude={author}` | unchanged |
   | the **operator** completed it | silent `continue` | ladder, `exclude=agents_that_worked(task)` |
   | **nothing** completed it | silent `continue` | `unstaffed`, naming the task and the remedy |

   The order of the existing gates is untouched, so an operator-completed task with no evidence still
   meets `commit_for_task_review`'s existing, better sentence rather than a new one (design D9).

4. **The wedged-review branch (`scheduler.py:1279-1284`) uses the same attribution.** It is the
   operator's only manual escape from row one, F142 measured it as broken by the same root cause, and
   `task-lifecycle-governance:313` is the requirement it implements.

5. **`task_is_claimable_by` moves with it, or the two walks disagree about the same task.** The flow
   walk and the per-agent walk (`_first_startable_candidate`, which the board also reads) would
   otherwise answer opposite things about one operator-completed task. The function's docstring gives
   the *reason* an unattributable task is claimable by nobody — the author cannot be ruled out — and
   `agents_that_worked` is precisely the thing that rules them out, so the same argument now permits
   it.

6. **The stall-reason substitution is reconciled with `agent-loops:815`.** That requirement says the
   reason SHALL name *"how many tasks are open and in which statuses"*; F64 already replaces it with
   `unstaffed[0][1]` and **no requirement licenses that**. This change makes the override fire on a
   new class of queue, so it is this change's job to write the clause rather than widen an
   undocumented divergence.

**Deliberately not in this change**, each with its reason:

- **Attribution of the flow's own routing transitions.** `enter_selected_task` records
  `completed → under_review` as the operator (pinned by `test_flow_chain_end_to_end.py:344-355`),
  which is F47/F120 and is **foreclosed** by `task-lifecycle-governance:359`'s categorical *"there
  SHALL NOT be a third actor kind"*. This change adds no operator-attributed row and removes none.
- **Widening the exclusion on the attributed path.** Where an agent is recorded as completing a task,
  the product has a *decided* answer to who the author is and the whole corpus is keyed on it
  (`agent-flows:59`, `task-lifecycle-governance`'s two guards). The wider set applies only where
  there is no decided answer (design D6).
- **Anything about evidence acceptance, integration, or `NOTHING_TO_MERGE`.** Changes C and D.
- **Forbidding the operator's `in_progress → completed` inside a flow.** Considered and rejected in
  D11: it punishes the operator for F140, which is change A's subject.

## Impact

- **Specs:**
  - `agent-flows` — **MODIFIED** *"A completed task is claimable by an agent that did not complete
    it"* (:59), which has no clause for a completion no agent made; **ADDED** one requirement for the
    operator-completed arm and its exclusion set.
  - `task-lifecycle-governance` — **MODIFIED** *"A review a flow cannot staff is not reported as
    staffed"* (:313), gaining the clause for an assignee holding work whose completion names no
    agent.
  - `agent-loops` — **MODIFIED** *"A firing is refused while its queue is stalled"* (:815), so a
    stall the walk can attribute to one task names that task instead of the histogram. This
    reconciles F64's shipped behaviour as well as this change's.
- **Code:** `hub/hub/task_transition_service.py` (two new functions, `agent_that_completed` becomes a
  wrapper), `hub/hub/scheduler.py` (the review arm, the wedged-review branch, `task_is_claimable_by`).
- **Tests:** `hub/tests/test_actor_aware_claimability.py`, `test_flow_fires_a_review_turn.py`,
  `test_flow_chain_end_to_end.py`, `test_reviewer_is_not_the_author.py`, plus a new reproduction
  file.
- **Harness:** `scripts/drive/t_row12_review_leg.py` already drives all three rows of the table above
  under `AW_COMPLETE_BY`; row one's expectation inverts.
- **No migration, no schema change, no new column, no UI change, no API surface change.** Everything
  this change reads is already recorded on `task_transitions`.
- **Cost of being wrong:** the enforcement half (item 3, row three) is one appended tuple and is
  reversible in a line. The judgement half (row two) is the one that carries risk, and the risk is
  named above: an exclusion set that is too narrow lets an agent review its own work. That is what
  `agents_that_worked` exists for and what tasks 1.4 and 4.3 measure directly.
