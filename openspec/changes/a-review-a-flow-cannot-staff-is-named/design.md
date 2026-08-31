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
- **The product has already decided this case on its other path.** `agent_trigger.py:444-452` bars
  a manually dispatched reviewer only where an agent is *recorded* as completing the task, so an
  operator-completed task is reviewable by hand **today**. This change removes a disagreement
  between two paths rather than introducing a judgement — **round 3's finding, and now the
  load-bearing argument here; see D15.**
- **`requirement-traceability:158`** — *"Where a project has granted no agent that capability,
  acceptance SHALL fall to the operator. That is a supported way to work, not a degraded one."*
  Supporting colour only. **Round 3 found this citation stretched** — it is scoped to a capability
  the project has not granted, not to an operator acting where an agent could have — and demoted it
  from the argument it used to carry. D15.
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
  `agents_that_worked` and is barred from reviewing work it never wrote. **Round 2 adds the case
  round 1 missed:** an agent that already *reviewed* this task is on the record too, because
  `under_review -> revision_needed` is attributed to the reviewer's run. So a task rejected once,
  reworked, and then completed by the operator cannot go back to the reviewer that knows it best.
  That is the same cost — one eligible reviewer fewer, surfaced at rung 3 — and it is paid on the
  unattributed arm only.

### Why the third bullet against is a cost worth paying

The failure it describes is *one eligible reviewer fewer*, which the ladder already handles: rung 3
surfaces *"could not staff this step"* and the operator resolves it. The failure the exclusion
prevents is an agent approving its own work, which is silent and produces a merged commit nobody
checked. Those are not comparable, and `task_is_claimable_by`'s docstring already chose between them
for the neighbouring case: *"refuse to offer, permit to act"*.

**Round 3 re-derived this rather than confirming it, and the attack landed.**
`requirement-traceability:158` *was* being stretched — it is about evidence acceptance falling to
the operator, not about task completion. The judgement stands on a better ground that neither
earlier round cited. **D15 is that re-derivation and supersedes this section's second bullet.**

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

### Round 2: `assignee` is a member of the set, not a consequence of it

Round 1 closed this section with *"`assignee` is still in the set whenever it matters, because an
agent holding a task moved it to `in_progress` through `apply_transition` and is on the record."*
**That is false, and it is the one sentence in this change that had to be true for the repair to be
safe.**

`bind_run_to_task` (`run_task_binding.py:432-436`) records the `-> in_progress` transition only when
the edge is legal:

```python
if "in_progress" not in allowed_targets(task.status, actor.kind):
    return None
```

`TRANSITIONS["in_progress"]` is `{completed, assigned, blocked, rejected}` — there is **no
`in_progress -> in_progress` edge**. So an agent whose run binds to a task that is already
`in_progress` takes no edge, records no row, and never enters `agents_that_worked`.

Two reachable routes to that state, and the first is ordinary operator behaviour:

1. **The operator moves the card to `in_progress` by hand**, the flow staffs it
   (`enter_selected_task` leaves a non-`pending` status alone, `scheduler.py:794-797`), the agent
   does the work, and the operator marks it done. Every transition on the task is
   operator-attributed. `agents_that_worked` is **empty**, the exclusion is empty, and the agent that
   wrote the code is offered its own work to review. This is exactly the trap D5 exists to close,
   arriving inside the repair.
2. **A task left `in_progress` with its `assignee` cleared or never set**, restaffed to a second
   agent — a state `decide_firing`'s own comment (`scheduler.py:1298-1300`) names as reachable.

So the exclusion is `agents_that_worked(session, task.id) | ({task.assignee} if task.assignee else
set())`. `assignee` is not a *replacement* for the transition set — round 1's three reasons against
that stand, and a task returned for revision still has two authors only the history names — it is the
term that covers the agent the history does not.

**Round 3: that last clause is true of exactly one agent.** The assignee column holds one name, and
`bind_run_to_task` fills it only when it is empty — so the *second* agent to work an already-started
task is named by neither term, and the mechanism that hides it from the history is the same one that
denies it the column. A third term is required. **D14 supersedes this paragraph's two-way union with
a three-way one.**

**The union belongs to the exclusion and not to the wedge predicate.** D8 asks *"is the assignee one
of the agents that worked this?"*, and `assignee` is trivially a member of `worked | {assignee}`,
which would wedge every review in progress. Two questions, two sets; see D8. D14's third term makes
that separation more load-bearing still, not less.

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
assignee is in `agents_that_worked` — **the transitions-only set, never the union D5 hands the
ladder** — the task is wedged. It then carries to the ladder, which now has an arm for it.

The set matters here more than anywhere else in the change, and getting it wrong is the risk task 5.4
measures. With the union the predicate is true of every task that has an assignee at all, so **every
review in flight would be reported unstaffable**, which is worse than the bug. With the
transitions-only set a legitimate flow-staffed reviewer is absent by construction:
`enter_selected_task` writes `completed -> under_review` as the *operator* (`scheduler.py:795`), and
the reviewer's own run then binds to a task already in `under_review`, an edge `TRANSITIONS` does not
offer, so it records nothing. Verified rather than assumed — the reviewer first appears on the record
when it writes its verdict, by which time the task has left `under_review`.

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
resolves and this change staffs a real review.

**Round 2 re-derived this from the function rather than from the paragraph above, and it holds.** The
query selects `RequirementEvidence` joined to `EvidenceFootprint` on `task_id`, orders by
`produced_at`, and filters `naming_a_commit` on `footprint.commit_sha` being non-empty. There is no
`review_state` term anywhere in it. F142's working row having accepted evidence was therefore
incidental, and the judgement half of this change is not confined to projects that have granted an
agent acceptance capability — it fires in a default project, in F140's own shape.

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

## D13 — the ladder's refusal sentences must not assert a completion that did not happen

Found in round 2. `resolve_reviewer` states *why* an agent was excluded, in two places, and both
sentences hard-code the attributed world:

- rung 1b (`scheduler.py:1074-1083`): *"this task names `X` as its reviewer, and that agent is the
  one that completed the work."*
- rung 3 (`scheduler.py:1111-1118`): *"... or is the one that completed this task and so may not
  review it."*

Under D5's exclusion both are **false**: the operator completed the task, and the excluded agent
merely worked it. This is not cosmetic. Rung 3's sentence is the one `decide_firing` promotes to
`stall_reason` (`scheduler.py:1457`) and `_emit_review_unstaffed` broadcasts, so it is the exact text
this change exists to put in front of the operator in place of the histogram. Shipping the fact about
the task in a sentence that misattributes the completion reproduces F142's defect in a new register —
and the spec delta as round 1 wrote it *required* it, by saying the flow surfaces "exactly as it does
when the author is known".

So the clause becomes a parameter:

```python
async def resolve_reviewer(..., exclude: set[str],
                           excluded_because: str = "is the one that completed this task") -> ...
```

used by both messages. The operator-completed arm passes `"has worked on this task"`. Rung 1b's
wording shifts by two words — *"the one that completed the work"* becomes *"the one that completed
this task"* — which is the price of one clause serving both sentences, and is a smaller cost than a
second parameter for a second template.

Rejected: composing the whole reason at the call site and passing it in. `resolve_reviewer` owns the
ladder's vocabulary — rung 1b's *"the flow will not substitute somebody else for a named reviewer"*
is the ladder's argument, not the caller's — and moving the sentences out would let two callers drift
into two accounts of the same rung.

`agent_trigger`'s manual dispatch is untouched: it never calls `resolve_reviewer`, and its own 403
names the completing agent only where one is recorded (`agent_trigger.py:445-455`), which stays true.

## D14 — round 3: the exclusion is still too narrow, and the hole is the *second* agent

Round 2 widened the exclusion from `agents_that_worked` to `agents_that_worked ∪ {task.assignee}`,
on the ground that *"`assignee` is the term that covers the agent the history does not."* Round 3
re-derived that sentence against the code and it is **true of exactly one agent and false of every
one after it**. The union closes the hole for the first agent to work a task and leaves it open for
the second — and the mechanism that hides an agent from the history is the same mechanism that
denies it the assignee column, so the two terms fail together rather than covering for each other.

### The route, and it needs no unusual operator behaviour

1. A flow staffs task `T` on `builder-1`. `enter_selected_task` writes `assignee = builder-1` and
   `pending -> assigned` as the operator; `bind_run_to_task` then takes `assigned -> in_progress`
   as `builder-1`'s run. **`builder-1` is on the record.**
2. `builder-1` stalls, or finishes without calling `update_task` (which is F140, this run's change
   A). The operator starts `builder-2` on the same card.
3. `builder-2`'s run reaches `bind_run_to_task`. `run.task_id` is set. `task.assignee` is already
   `builder-1`, so the assignee is **not** overwritten (`run_task_binding.py:429-430`). The task is
   already `in_progress`, and `TRANSITIONS["in_progress"]` has no `in_progress` target, so the
   binding **records no transition** (`:436-438`).
4. `builder-2` writes the work. The operator marks the card done.

`agents_that_worked` is `{builder-1}`. `task.assignee` is `builder-1`. The union is `{builder-1}`.
**`builder-2` — which wrote the work — is eligible to review it**, which is the precise outcome D5
exists to prevent, surviving inside round 2's repair for it.

**Measured, not argued.** Round 3 built that fixture against the real `bind_run_to_task`,
`apply_transition` and `Actor`, on the suite's own database, and every step held: `builder-1`'s
binding took `assigned -> in_progress`; `builder-2`'s returned `None` and travelled no edge;
`run.task_id` was set on it anyway; `task.assignee` stayed `builder-1`; and after the operator's
`-> completed` the transitions named `{builder-1}` alone, so `worked | {assignee}` did **not**
contain `builder-2` while `SELECT DISTINCT agent FROM runs WHERE task_id = ?` returned both. The
throwaway file was deleted; task 1.5a is its permanent form, and it must reproduce those exact
intermediate assertions rather than only the conclusion.

Nothing in that route is exotic. Starting a second agent on a card the first one left is ordinary
operator behaviour in a multi-agent product, and it is explicitly permitted: `resolve_bound_task`
*"never consults `Task.assignee`"* (`agent_trigger.py:845`), and the only concurrency refusal is on
a turn that is **running right now** (`agent_trigger.py:863-872`), not on one that has ended.

### The third term: the runs recorded as bound to the task

`bind_run_to_task`'s **first statement** is `run.task_id = task.id` (`run_task_binding.py:427`),
above the `blocked` guard and above the legality check. So a run that binds and takes no edge still
records that it was about that task — the one record in the product that names `builder-2` in the
route above. The exclusion becomes:

```
agents_that_worked(task)  ∪  {task.assignee}  ∪  {r.agent for r in runs where r.task_id == task.id}
```

Three sources for one question is not elegant, and the reason it is nonetheless right is that each
one is a *different fact* and each is individually incomplete:

| source | names | misses |
|---|---|---|
| transitions | every agent that **moved** the task | an agent that worked it without moving it |
| `assignee` | the agent that **holds** it now | every previous holder; anyone who worked it without taking the column |
| bound runs | every agent whose run was **about** it | runs predating the column, and runs never bound |

The rule D6 states — *the narrowest set that provably contains the author* — is unachievable on this
arm, because with no completion row the author is not provable from anything. What is achievable is
its honest restatement, and it is the one this change should have been using all along: **exclude
every agent any record associates with the task.** Under that rule the three-way union is not three
patches, it is the complete enumeration of the records that exist.

### Why `Run.task_id`'s measured unreliability does not disqualify it here

`checkpoint_handover.py:87-92` rules it out in the strongest terms — *"**And never from
`run.task_id`.** … of the ten runs that had recorded a `completed` transition, **six carried
`run.task_id = NULL`**"* — and a change that reaches for the column right after that must say why it
is not the same mistake.

It is not, because the two uses have opposite failure directions. `_task_this_run_completed` asks
*which task did this run finish?* and a NULL there produces a **wrong answer**: a handover that
should have happened does not. This change asks *might this agent be the author?* and a NULL
produces a **missing candidate** in a set whose only job is to grow. A source that under-reports
cannot make this exclusion unsafe; it can only fail to make it safer. That is why the column is a
**term** here and never the whole set — dropping the transition set for it would reproduce
`checkpoint_handover`'s bug exactly.

### The wedge predicate is unaffected, and the naming must make that impossible to get wrong

D8's predicate stays `task.assignee in agents_that_worked(task)` — the **transitions-only** set. The
runs term would break it the same way the assignee term does, and more quietly: the assignee's own
run is bound to the task in almost every case, so `assignee ∈ runs-derived` is nearly always true and
every review in flight would again report as unstaffable. Two questions, two sets, and now three
sources on one side and one on the other. Task 2.5's named-helper requirement is what carries this;
round 3 raises it from a preference to the thing that keeps D14 and D8 from colliding.

### What the third term costs

It excludes an agent whose run was bound to the task but which did no work — including, since
2026-08-26, a **previous reviewer**, because review runs bind through `review_task_id`
(`run_task_binding.py:170-186`). Checked rather than assumed: a reviewer that ran and recorded no
verdict leaves the task `under_review` holding it, which reaches the `in_flight` arm and never
consults this exclusion at all; and a reviewer that *did* record a verdict is already in the
transition set. So the extra exclusions this term produces are almost entirely agents that would
have been excluded anyway, and the residue is paid at rung 3, visibly, on the arm this change built
for exactly that.

## D15 — round 3: the judgement re-derived, and its citation corrected

Round 3's first assignment was D4's central citation, and the suspicion was right.

**`requirement-traceability:158` is being stretched.** Read in place, the sentence is scoped by the
one before it: *"Where a project has granted no agent that capability, acceptance SHALL fall to the
operator. That is a supported way to work, not a degraded one."* It is about a **capability the
project has not granted** — the operator acts because no agent is permitted to. It says nothing
about an operator who acts where an agent *could* have, which is this change's case. Generalising it
to *"the operator acting in person is first-class"* is a conclusion the sentence does not carry, and
a round that only checked outcomes would have kept it because the outcome it supports is correct.

**The judgement survives, on a ground neither earlier round cited.** The product has already decided
this exact case, on its other path:

```python
completing_agent = await agent_that_completed(session, task.id)
if completing_agent is not None and completing_agent == reviewer:
    return (403, ...)
```

`agent_trigger.py:444-452`. The manual review-dispatch route bars only the agent **recorded** as
completing the task. On an operator-completed task `completing_agent` is `None`, the guard permits,
and the review runs. **So operator-completed work is reviewable today** — by hand, through the route
an operator actually uses when they notice the flow has stopped. This change does not introduce the
judgement; it removes a disagreement between two paths about one task, and it removes it in the
direction the shipped path already chose.

That is a materially stronger argument than the one it replaces, for three reasons: it is shipped
behaviour rather than an inference from a neighbouring requirement; it is behaviour this change
deliberately leaves untouched (D13's closing paragraph); and `task-lifecycle-governance`'s
*"Dispatching a review staffs the task, whichever path dispatched it"* — with its scenario **"A
review started by hand leaves the reviewer able to record a verdict"**, written for a completed task
and a reviewer that is not its author — establishes path-independence as a stated principle of the
review mechanism, even though its own words govern staffing mechanics rather than eligibility. Round
3 states that limit rather than borrowing the requirement's authority for something it does not say;
that is the error being corrected here, and repeating it one requirement over would be no better.

`requirement-traceability:158` stays in the file as **supporting** colour and is no longer load-
bearing. The corpus does not decide this question; the product does, and the two paths must agree.

### The other half of the assignment: is the exclusion now too wide?

Round 3 was told to ask what round 2's widening costs, and D14 has just widened it again, so the
question is sharper than when it was written. The answer is that **the width cannot regress
anything**, and it is worth stating as a property rather than re-argued case by case:

- **The review arm.** Today the operator-completed branch is `continue` — it staffs **nobody**. Any
  exclusion, of any width, staffs at least as many agents as that. The union cannot make this arm
  worse than it is.
- **`task_is_claimable_by`.** Today it returns `False` for every agent on an operator-completed task
  (`scheduler.py:589-592`). Same argument: a wider exclusion is closer to today, never past it.
- **The wedged branch.** Uses the transitions-only set (D8, D14), unchanged by the widening.
- **The attributed arm.** `exclude={author}`, untouched by D6.

So the whole cost of over-exclusion is an *opportunity* cost — a review that could have been staffed
is surfaced at rung 3 instead — and this change is the one that makes rung 3 reach the operator with
the task's name on it. Weighed against a silent self-approval that produces a merged commit nobody
checked, that is not a close call, and it is the same asymmetry `task_is_claimable_by`'s docstring
already settled for the neighbouring case: **refuse to offer, permit to act.**

The one case worth naming, because it is the honest cost and it should not be discovered in a drive:
a two-agent project where the builder is excluded and the reviewer's run was once bound to the task
now reaches rung 3 where the narrower set would have staffed. The operator is told, by name, with a
remedy. That is the designed outcome of this change, not a failure of it.

## D16 — round 3: does the fix belong in `decide_firing` at all?

The third assignment: whether `bind_run_to_task` should record the agent's turn on a task it did not
move, making `agents_that_worked` true to its name and deleting the assignee term. Round 2 chose the
cheaper repair deliberately; round 3's answer is that the choice was **right, and not because it was
cheaper.**

**The decisive argument is that a recording fix is forward-only, and this change's whole population
already exists.** F142's fixture, F140's drive, and every task an operator has already hand-driven
are in the broken state **now**, with histories that will never gain a row. An exclusion computed
from a record that starts being written today is empty for exactly the tasks this change was written
to make safe. A safety exclusion cannot be built on a mechanism that has no past.

The three recording designs, and why each is rejected on its own terms as well:

- **An `in_progress -> in_progress` self-edge.** Requires a new entry in `TRANSITIONS`, which
  `test_task_transitions.py:55-59` asserts over as a whole, and it contradicts a rule the corpus has
  already stated one status over: *"Staffing SHALL be idempotent. Where the task is already held by
  that reviewer and already in review, dispatching SHALL leave both unchanged and **SHALL travel no
  transition**, so that a task does not accumulate a record of being entered into review more than
  once for one review"* (`task-lifecycle-governance`, *Dispatching a review staffs the task*). A
  self-edge on every re-bind is precisely the accumulation that clause forbids, one band over. It
  would also make `TaskTransition` answer *"who touched this"* rather than *"how did this move"*,
  which is a different table.
- **A participation table.** Forward-only as above, plus a migration and a second record of
  something three existing records already partially answer. The change's *"no migration, no schema
  change"* property is not a virtue in itself, but paying for one to get a strictly worse-covered
  version of D14's union is not a trade.
- **`Run.task_id` as a replacement for the transition set.** Rejected on measurement rather than on
  taste — see D14: `checkpoint_handover.py:87-92` records six of ten NULL. It is a widening term and
  never the set.

So the fix belongs where round 2 put it. What round 3 changes is the *justification*: the reason to
read the exclusion at decision time is not that writing it would be more work, it is that decision
time is the only moment with access to the whole record — including the part written before any of
this shipped.

## D17 — round 3: `task_is_claimable_by`'s docstring argues from two false premises

Found by re-deriving D7 against the function rather than against D7. The docstring is the
change's own licence (task 4.2), and two of its sentences are **untrue**, in the way this round
exists to catch: the argument is wrong while everything it argues about is right.

1. > *"Every task that reaches `completed` through `apply_transition` records its completer, so this
   > is the legacy and hand-written case only."*

   False, and it is the root of F142. A task the **operator** completes reaches `completed` through
   `apply_transition` and records `actor_agent = NULL`, because `Actor(kind="operator")` may not
   carry an agent (`task_transitions.py:64-67`). The `None` population is therefore not "legacy and
   hand-written only" — it includes every task an operator finishes, today, through the supported
   route. The sentence is why the branch above it looked safe to everyone who read it.

2. > *"it stalls the queue and the operator reviews it, which is what happens today and is a state
   > the operator can see and resolve."*

   Both halves measured false by F142. The operator cannot **see** it: the stall reason is the status
   histogram, which names no task. The operator cannot **resolve** it: `completed` reaches only
   `rejected` and `under_review`, and `under_review` by hand lands on D8's bug.

Task 4.2 said *"extend the docstring"*. Extending it leaves both sentences standing, and the second
reader to trust them is how this defect survives its own fix. They must be **corrected**, and the
correction is short: name the operator-completed world as the third case, and say that the stall it
produced was invisible until F142 measured it and is what the new arm exists to end. A docstring that
still claims the operator can see and resolve this state, in the function the change edits to make
that true, is a claim the product will be judged against.

## D18 — found during implementation: the delta's own scenario was wider than its requirement

Round 3 left `task-lifecycle-governance`'s scenario *"A task with no recorded completion is
surfaced, not restaffed"* keyed on nothing but the absence of a completion:

> **WHEN** a task in `under_review` has an assignee and no recorded completion at all
> **THEN** it is not reported as held by a reviewer

Implemented literally, that reports a **real, in-progress review** as one nobody is doing. Reaching
`under_review` with an assignee and no recorded completion is a supported route: `agent_trigger` bars
a manually dispatched reviewer only where an agent is *recorded* as completing the task, so on a task
with no recorded completion any agent may be dispatched by hand -- and `enter_selected_task` staffs
it, which is `task-lifecycle-governance`'s own *"Dispatching a review staffs the task, whichever path
dispatched it"*. That is 5.4's risk arriving through the requirement rather than through the code.

The requirement's **prose** was already right and the scenario disagreed with it. Its opening
sentence is *"when that task's assignee is an agent that produced the work"*, and for a task with no
recorded transitions naming an agent, no record says the assignee produced anything. `tasks.md` 5.1
was right too: `wedged_review` where `task.assignee in agents_that_worked(task)`, transitions only.

So the scenario was corrected to name the assignee condition, and a second scenario added for the
hand-dispatched case that must stay `in_flight`. `test_a_hand_dispatched_review_on_an_unattributed_task_is_still_held`
is its permanent form.

Worth recording *how* it survived three rounds: every round checked that the wedge predicate would
not be reused with the wider exclusion set (D8, D14), which is a real hazard and was caught. Nobody
checked the predicate against the **narrower** direction -- what the requirement says about the case
where the set is empty. The rounds re-derived the exclusion three times and the scenario once.

## D19 — filed, not fixed: `RequirementEvidence.actor` is a fourth record and is not a term

`record_evidence` takes `task_id` as a free parameter and does not require the calling run to be
bound to that task (`mcp_server.py`). So an agent can work a task on an **unbound** run, record
evidence naming its commit, and appear in no record the exclusion reads: no transition (it moved
nothing), no `assignee` (`bind_run_to_task` never ran), no `run.task_id` (the run was never bound).
`RequirementEvidence.actor` names it, and the review arm requires that very row to exist before it
resolves a reviewer at all.

That is the same shape as D14's second agent, one source further out, and D14's own rule --
*exclude every agent any record associates with the task* -- says the term belongs in the union.
It is **not** added here: the spec delta enumerates three sources by name, adding a fourth without a
round re-deriving it is exactly the move this change exists to argue against, and the residual
exposure is narrow (an agent that recorded evidence for a task it never bound to is usually in one of
the three terms already, because the ordinary path binds).

Queued as a question for the operator rather than taken. `AW_COMPLETE_BY=untouched`, added to
`t_row12_review_leg.py` as row four, drives exactly this shape live -- so `DRIVE-1` will show whether
the agent that recorded the evidence is offered its own work to review.
