# Design

## D1 — the silent `continue` becomes a recorded outcome, under every answer to D4

`scheduler.py:1364-1368` records nothing. `agent-flows:189-195` requires the operator to be notified,
naming the task, when no agent can be resolved or found for one. Whatever is decided about whether
operator-completed work is reviewable, a task the walk declines to staff must leave a trace.

`unstaffed` is the right list rather than `deferred` or `in_flight`, and the distinction is already
written into `FiringDecision`:

- `in_flight` claims *"somebody holds this right now"* — false here, and the false version is
  precisely today's wedged-review bug (D8).
- `deferred` means *"nothing is wrong and nothing needs doing; the next firing picks it up"*
  (`resolve_reviewer`'s own wording). False: the next firing repeats this one exactly.
- `unstaffed` means *"the operator has something to fix"*, is broadcast as a `review_unstaffed`
  event, is persisted, and becomes the stall reason. That is the fact.

Verified: `_do_fire_job` emits `decision.unstaffed` **before** it branches on `decision.kind`
(`scheduler.py:2402-2405`), so the event fires whatever else the firing does — including on a firing
that goes on to claim other work. Nothing further is needed to surface it.

## D2 — `None` is two worlds, and they are separable with no new state

`Actor.__post_init__` (`task_transitions.py:64-67`) raises for an actor of kind `run` carrying no
agent, and for an actor of kind `operator` carrying one. `record_transition` is the only writer.
Therefore, on any `→ completed` row:

```
actor_kind = 'run'       ⟹ actor_agent is NOT NULL
actor_agent IS NULL      ⟺ actor_kind = 'operator'
```

So `agent_that_completed(...) is None` means exactly one of:

1. a `→ completed` row exists and the operator wrote it;
2. no `→ completed` row exists at all.

Reading `actor_kind` in the same `SELECT` separates them. **No migration, no column, no second
query.** The ambiguity was never in the data; it was in the projection.

### Rejected: filtering the existing query to `actor_kind = 'run'`

It is a **no-op**. A run row always carries an agent, so `WHERE actor_kind = 'run'` removes exactly
the rows whose `actor_agent` is already `NULL`, and the function returns `None` for the same inputs.
Recorded because it looks like a fix and is not — which is itself the proof that the defect lives in
what the *caller* concludes from `None`, not in the query.

## D3 — a new function, not a changed return type

Seven call sites read `agent_that_completed`, and they read `None` in three different ways. All
seven, and what this change does to each:

| # | Site | Reads `None` as | Change |
|---|---|---|---|
| 1 | `_guard_author_is_not_reviewer` (`task_transition_service.py:168`) | permit | **none** |
| 2 | `_guard_reviewer_is_not_the_author` (`:220`) | permit | **none** |
| 3 | `task_is_claimable_by` (`scheduler.py:589`) | refuse to offer | **yes** — D7 |
| 4 | wedged-review branch (`scheduler.py:1280`) | not wedged → `in_flight` | **yes** — D8 |
| 5 | review arm (`scheduler.py:1364`) | drop silently | **yes** — D1, D4 |
| 6 | `run_divergence.py:415` | nobody to bar | **none** |
| 7 | `agent_trigger.py:445` | permit the dispatch | **none** |

Four are correct as written and their correctness is argued at length in their own docstrings —
sites 1, 2 and 7 are the *refuse to offer, permit to act* asymmetry, and site 6 adds the author to a
`barred` set where `None` simply adds nobody. Changing the return type of a function four correct
callers depend on, to serve three, is the wrong direction.

So: `completion_attribution(session, task_id) -> CompletionAttribution`, a frozen dataclass
(`recorded: bool`, `actor_kind: Optional[str]`, `agent: Optional[str]`), and `agent_that_completed`
becomes a wrapper returning `attribution.agent`. **One query, one rule, two projections.** The
docstring that argues why the read is from history and by `sequence` moves to the new function and is
not duplicated.

## D4 — may a flow staff a review for work the operator completed?

**Both arguments, recorded in full, because round 3's job is to re-derive this rather than inherit
it.**

### For (this proposal's position)

- **The exclusion protects against a specific harm that is absent here.** Author/reviewer separation
  exists so an agent does not sign off its own work. An operator's completion introduces no agent
  that could. Refusing to staff the review does not prevent a self-approval; it prevents a review.
- **`requirement-traceability:158`** — *"Where a project has granted no agent that capability,
  acceptance SHALL fall to the operator. That is a supported way to work, not a degraded one."* The
  corpus already holds that an operator acting in person is first-class. A flow that dead-ends the
  moment the operator touches a card says the opposite, in the one situation where they are most
  likely to.
- **F142 measured the alternative and it is a dead end with no exit.** `completed` reaches only
  `rejected` and `under_review`; `under_review` by hand hits D8's bug; the only remaining move is the
  operator approving it themselves, which is the flow's own job done by hand with the flow never
  learning it happened.
- **The operator's completion is a judgement about *doneness*, not about *correctness*.** Marking a
  card done says the work is finished. Review asks whether it is right. Those are different
  questions and the second is not answered by the first.

### Against

- **The operator has already made a judgement, and staffing a review second-guesses it.** An operator
  who wanted the flow to review the work would have let the agent complete it.
- **It creates work the operator did not ask for.** A flow that fires a provider turn because the
  operator tidied a board is spending tokens on an inference.
- **The provenance is genuinely thinner.** With an agent completion the Hub knows who did the work.
  With an operator completion it is *inferring* authorship from transition history, and that
  inference can be wrong — an agent that moved a task to `in_progress` and then did nothing is in
  `agents_that_worked` and is barred from reviewing work it never wrote.

### Why the third bullet against is a cost worth paying

The failure it describes is *one eligible reviewer fewer*, which the ladder already handles: rung 3
surfaces *"could not staff this step"* and the operator resolves it. The failure the exclusion
prevents is an agent approving its own work, which is silent and produces a merged commit nobody
checked. Those are not comparable, and `task_is_claimable_by`'s docstring already chose between them
for the neighbouring case: *"refuse to offer, permit to act"*.

**Round 3 must re-derive this rather than confirm it.** The specific thing to attack: whether
`requirement-traceability:158` is being stretched. It is about *evidence acceptance* falling to the
operator, not about task completion, and a round that only checks outcomes would not notice the
difference.

## D5 — with no completer, "the author" is every agent that worked the task

`resolve_reviewer(..., exclude={author})` with `exclude=set()` is a **self-approval route**, and it
is reachable by F140's exact drive: the builder did the work, recorded evidence, never called
`update_task`, and is still in `task.assignee`. Nothing downstream catches it — sites 1 and 2 in D3's
table both permit when the completer is unknown, deliberately.

So the operator-completed arm excludes `agents_that_worked(session, task.id)`: the distinct non-null
`actor_agent` over every transition of that task.

Why that set and not `{task.assignee}`:

- `assignee` is a single mutable column and is overwritten by every restaff — the same reason
  `TaskTransition` exists at all, argued in the model's own docstring.
- A task returned for revision and picked up by a second agent has two authors. `assignee` names one.
- It is empty exactly when it should be: a task no agent ever touched excludes nobody, and every
  agent is eligible, which is correct.

`assignee` is still *in* the set whenever it matters, because an agent holding a task moved it to
`in_progress` through `apply_transition` and is on the record.

## D6 — the wider exclusion applies only to the unattributed arm

The attributed path keeps `exclude={author}` exactly as today. This asymmetry is deliberate:

- Where an agent is recorded as completing a task, the product has a **decided** answer to who the
  author is. `agent-flows:59`, `agent-flows:215-218`, and both transition guards are keyed to that
  answer, and `agent-flows:59` requires claimability and the approval guard to use *the same
  determination* so that a task offered to an agent is never one it would then be refused for
  approving. Widening the offer side and not the guard side would break that agreement in the
  direction that matters least — refusing offers the guard would permit — but it would break it.
- Where nothing is recorded, there **is** no decided answer, and the safe direction of an *offer* is
  to exclude everyone who might be the author.

Stated as a rule rather than an exception: *the exclusion is the narrowest set that provably contains
the author.* With a completion row that set is a single name. Without one it is everyone who acted.

## D7 — `task_is_claimable_by` moves with it, or the two walks disagree

`task_is_claimable_by` returns `False` for a `completed` task with no recorded completer, and
`_first_startable_candidate` filters every candidate through it (`scheduler.py:721`). If the flow arm
starts staffing operator-completed reviews and this does not, the two walks answer opposite questions
about one task — and `agent-flows:59`'s third scenario, *"Claimability and the approval guard
agree"*, is what forbids exactly that class of disagreement.

The function's docstring gives the *reason* for refusing: *"Handing finished work to an agent the Hub
cannot rule out as its author, when the guard will then also fail to rule it out, is self-approval
reached by two permissive defaults agreeing."* `agents_that_worked` **is** the thing that rules them
out. So the same argument, unchanged, now permits the offer — which is why this is a change the
docstring's own reasoning licenses rather than an exception carved out of it.

After this change:

```
completed, an agent completed it   -> claimable by anyone except that agent      (unchanged)
completed, the operator did        -> claimable by anyone that did not work it   (new)
completed, nothing recorded        -> claimable by nobody                        (unchanged)
```

The third row is the legacy and hand-written case the docstring already scopes itself to, and it
keeps today's behaviour exactly.

## D8 — the wedged-review branch is the operator's only manual escape, and it is broken the same way

`scheduler.py:1279-1284`:

```python
wedged_author = await agent_that_completed(session, task.id)
if wedged_author is not None and wedged_author == task.assignee:
    wedged_review = True
else:
    in_flight.append((task.id, task.assignee))
```

With an operator completion, `wedged_author` is `None`, so a task in `under_review` whose assignee is
the agent that wrote the code is recorded as `in_flight` — *"a reviewer holds this"* — which is
false, and is the exact condition `task-lifecycle-governance:313` exists to stop being reported as
staffed. F142 measured this as the reason moving the task to `under_review` by hand does not help.

Repaired with the same attribution: where no agent is recorded as completing the task and the
assignee is in `agents_that_worked`, the task is wedged. It then carries to the ladder, which now has
an arm for it.

Note the interaction: for the *nothing recorded* world the task is wedged, carries to the ladder, and
the ladder records it `unstaffed` with the reason from D1. That is the right outcome —
`task-lifecycle-governance:313` says such a task is *"claimable by nobody and its assignee counts as
holding active work"*, and telling the operator so is better than reporting a reviewer that is not
there.

## D9 — the gate order is unchanged, so the better message wins

The review arm asks `commit_for_task_review` **before** it resolves a reviewer, and that order is
kept. An operator-completed task with no evidence therefore meets the existing sentence — *"task …
has no recorded evidence, so there is no commit to review. Evidence naming a commit is what a review
turn is given."* — rather than a new one about attribution. That is the more specific and more
actionable fact, and the existing wording is already driven.

Verified by reading `commit_for_task_review` (`requirement_evidence.py:736-795`): it requires an
evidence row with a non-empty `commit_sha` on its footprint and **does not require acceptance**. So
in F140's own scenario — agent records evidence, operator completes the card — the review target
resolves and this change staffs a real review. Round 2 must confirm this against the code rather than
inherit it, because F142's working row happened to have accepted evidence and it is easy to conclude
acceptance was load-bearing when it was incidental.

## D10 — the stall reason override has no requirement, and this change widens it

`agent-loops:815` — *"A firing is refused while its queue is stalled"*:

> Where nothing is claimable and no dependency gate is involved, that reason SHALL name how many
> tasks are open and in which statuses.

`scheduler.py:1438-1457` overrides that with `unstaffed[0][1]` whenever the walk named an unstaffable
task. That is F64's fix, it is right, and **no requirement licenses it** — the corpus was searched
and the only neighbouring clause is the gated-stall carve-out two paragraphs down, which is about
dependency gates.

This change makes the override fire for a new class of queue, so reconciling it is this change's job
rather than a tidy-up. The requirement gains the general clause: the histogram is the reason of last
resort, and where the walk can attribute the stall to a specific task with a remedy, that names the
stall instead. The reason is the requirement's own: *"the operator's remedy there is the
prerequisite, not the queue's own status breakdown"* — the same argument, one case over.

## D11 — rejected alternatives, recorded so they are not re-proposed

- **Make the operator's completion write `actor_agent = task.assignee`.** Forges provenance. The
  integrity record would state that an agent moved a task it did not move, in the one table whose
  entire purpose is to answer *"who did this?"* without depending on a mutable column.
- **A third actor kind for "the flow acting on the operator's behalf".** Foreclosed by
  `task-lifecycle-governance:359`, whose scenario enumerates the actor kinds and is asserted over the
  whole transition map by `test_task_transitions.py:55-59`.
- **Refuse the operator's `in_progress → completed` while the task belongs to a flow.** Punishes the
  operator for F140 — they marked the card done because the agent would not. Change A is the fix for
  that; refusing the repair while the defect stands would make the product worse.
- **Leave the judgement out and ship only the `unstaffed` line.** Considered seriously: it is the
  minimum that clears `agent-flows:189-195`, and F142 itself proposed exactly that. Rejected because
  F142's own filing says why — *"filed rather than fixed only because the surrounding decision is the
  operator's and a lone diagnostic would read as endorsing the dead end."* The operator has now made
  the neighbouring decisions (D-A, D-B, 2026-08-30) and the dead end is the thing to remove.
- **Give `FiringDecision` a fifth list for "unattributable".** A fourth flavour of *"this task was not
  staffed"* whose remedy is the same as `unstaffed`'s — the operator does something. The lists are
  distinguished by what the operator must do, not by what the code noticed.

## D12 — tripwires

- **`test_flow_chain_end_to_end.py:344-355`** pins the flow's operator-attributed transitions with a
  **set equality**, written so that *"fixing it, or a genuine operator action appearing, both fail
  here."* This change adds no operator-attributed transition and removes none, so the set should be
  unchanged — if it moves, something happened that this change did not intend.
- **`test_actor_aware_claimability.py:169`** asserts an unattributed completed task is claimable by
  nobody. Under D7 that assertion stays true for the *nothing recorded* world and needs a sibling for
  the *operator completed* one. The fixture must construct the two differently, and a fixture that
  writes the status directly produces the first, not the second.
- **`test_flow_fires_a_review_turn.py:78`** records that a fixture must walk the task through
  `apply_transition` to give it provenance. The new tests need the opposite fixture on purpose.
- **`_loop_candidates` order** decides which `unstaffed` entry becomes the stall reason
  (`unstaffed[0][1]`). A test asserting a specific sentence on a multi-task queue is asserting the
  queue order too.
