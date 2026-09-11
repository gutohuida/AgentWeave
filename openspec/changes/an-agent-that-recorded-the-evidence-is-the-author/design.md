# Design — an agent that recorded the evidence is the author

The verdict (`spec-queue/DECISIONS.md`, *"F306 and F312, decided 2026-09-10 evening"*) settles
**what** happens. This file records the decisions it deliberately left to a round, each answered by
reading or running the code rather than by preference, and the ones a reader will otherwise re-open.

## D1 — The fourth source is its own function, and the reason is a second consumer

`DECISIONS.md` left open *"whether the fourth source sits beside the other three inside
`agents_that_may_have_authored` or becomes its own function called by it."* It becomes its own
function, `agents_that_recorded_evidence_for(session, task_id)`, and the argument is not symmetry
with `agents_that_worked` and `agents_of_runs_bound_to` — it is D3 below. The guard needs **this term
without the other three**, and a term that has two consumers cannot be an expression inlined in one
of them.

Signature `(session, task_id)` rather than `(session, task)`, matching the other two term functions
and differing from the union's `(session, task)` — the union needs the row because `task.assignee` is
a column on it; a term that reads one table by `task_id` should not demand a loaded ORM object.

## D2 — The filter is `actor_kind = 'agent'` and a non-empty `actor`, and nothing else

`requirement_evidence.record` (`hub/hub/requirement_evidence.py:155-168`) writes
`actor_kind = actor.kind` and `actor = actor.name or ""`. Three consequences, all read off that
line:

- **`actor_kind` must be filtered.** The same table holds the operator's own evidence: `POST
  /spec/evidence` records it as `Actor(kind="operator")`. An operator's name in an exclusion of
  *agents* is a category error, and on a project where an operator credential and an agent share a
  name it would silently un-staff a legitimate reviewer. Filtering it is also what preserves
  `F306`'s own carve-out: *"a truly untouched task is reachable and is not affected"* — an operator
  may supply the evidence naming the commit, and every agent stays eligible.
- **The empty string must be filtered.** `actor.name or ""` means a nameless actor writes `''`, and
  `''` in an exclusion set is a member that matches no agent but is not nothing. `agents_that_worked`
  and `agents_of_runs_bound_to` both already drop falsy values for the same reason; this follows
  them.
- **`review_state` must NOT be filtered.** The operator's verdict, and its reasoning is recorded
  there rather than repeated here: filtering by a review decision would reintroduce the gap one
  status value along, and would make the exclusion depend on the outcome of the review being
  staffed. R2 adds the corpus agreeing with it from the other direction:
  `requirement-traceability`'s *"producing evidence is open, and **accepting** it is the controlled
  act"* (`:141-145`) means the produced row is the agent's own claim and the decision is somebody
  else's — so an exclusion keyed on the claim is keyed on the only part of the row the agent owns,
  and one keyed on the decision would be keyed on the part it does not.

## D3 — The guard falls back to the evidence source **alone**, never to the union

`DECISIONS.md` left open *"the shape of the guard's fallback when `agent_that_completed` is NULL"*,
and `FINDINGS.md` had proposed falling back to `agents_that_may_have_authored`. **That shape is
refuted by measurement**, and the measurement is in `proposal.md` §3: `enter_selected_task` writes
`task.assignee = <reviewer>` before transitioning to `under_review`
(`hub/hub/scheduler.py:811-816`, with its own comment saying it must, or `_guard_reviewer_is_not_the_author`
would refuse the flow's every staffed review). So at the moment the reviewer records its verdict, the
`assignee` term of the union **is the reviewer**, measured as `{'zz-reviewer-g'}`.

The failure would have been total rather than partial: every flow-staffed review of an
operator-completed task refused, which is the whole path this change exists to make safe. And it
would have been invisible to a reviewer who checked only that the author is excluded.

The general point is worth stating because it will come up again: **of the four sources, three are
contaminated by the reviewer's own participation by the time a verdict is recorded** — `assignee` is
the reviewer, the review run is bound to the task, and on a second round the reviewer's earlier
`revision_needed` is in the transitions. Only the evidence row is an authorship assertion that the
act of reviewing does not manufacture. That asymmetry is exactly why the union is right for an
*offer* and wrong for a *refusal*, and it is the same shape as the asymmetry
`task_is_claimable_by` already documents at length: refuse to offer, permit to act.

Rejected: **subtract the assignee from the union.** It restores the flow's path and reopens the
hole for the case an operator assigns the author by hand — assignee is then the author, and
subtracting it empties the set. Rejected: **compare against the union only where the task has no
assignee.** Same hole, reached by a condition instead of a subtraction.

## D4 — The fallback fires whenever no *agent* is recorded as completing, in both worlds

`agent_that_completed` returns `None` for two different worlds, and `completion_attribution`
separates them: the operator completed it (`recorded=True, agent=None`), or nothing is recorded at
all (`recorded=False`). `task_is_claimable_by` must distinguish them and does. **The guard does
not**, and takes the fallback in both.

The reason is that the guard's permissive default was never about the *shape* of the absence. Its
docstring gives the argument: *"a guard that blocked every move it could not attribute would stop
legitimate work over a missing history row."* The fallback does not block over a missing row — it
blocks over a **present** one, an evidence row this agent wrote naming this task. A task with no
completion at all is claimable by nobody, so the flow never staffs it; but an operator may dispatch
a reviewer by hand, and in that world the fallback is the only thing standing between a hand-staffed
author and its own approval. Narrowing the permission to "unless a record says you are the author"
is the same principle the exclusion already states, applied one layer down.

## D5 — Not scoped by evidence `kind`, and the residue is named rather than designed against

`FINDINGS.md` proposed scoping by `kind` *"so a reviewer's own evidence does not exclude the reviewer
that produced it"*. Two measurements retire it:

- **The corpus forbids closing the vocabulary** (R2; R1 argued this from a docstring and missed the
  requirements). `requirement-traceability:123-125`: *"The set of kinds SHALL be open to additions,
  because constraining evidence to what was imaginable at design time is how the record stops
  describing what was actually done."* And `agent-capability-plane:850`: *"Constrained values SHALL
  be constrained identically on both surfaces, and **open ones SHALL stay open**."* Scoping the
  exclusion by `kind` needs a closed set to scope by; producing one is prohibited, not merely
  awkward.
- **A partial vocabulary exists and is unenforced, which R1 stated too strongly.** R1 wrote *"there
  is no vocabulary to scope by"*. There is: `db.models.EVIDENCE_KINDS` — `test_result`,
  `screenshot`, `artifact_diff`, `review_record`, `manual_observation`, `external_reference`.
  Nothing validates against it; `mcp_server.py:1132` says so in its own words (*"`kind` is
  deliberately **not** constrained here: `db.models.EVIDENCE_KINDS` is open at the edges"*), and
  `F306`'s own live reproduction recorded `kind='implementation'` — not one of the six — and it
  stored fine. So the conclusion survives and the sentence does not: there **is** a vocabulary, it
  is advisory by requirement, and scoping on it would fail open on the first word outside it.
  `record_evidence`'s contract says the same to the agent: *"Not a closed list; use a word that
  describes it"* (`hub/hub/mcp_server.py:1365-1366`).
- **The product does not ask a reviewer for evidence.** `_briefing_evidence_lines` returns `[]` when
  `is_review`, with the comment *"A reviewer records a verdict, not evidence for work it did not
  do"* (`hub/hub/scheduler.py:2103-2104`). The review briefing tells the reviewer to end with
  `update_task`, not to record anything.

**The residue, stated** — and it is marginally more reachable than R1 implied, because
`review_record` is one of the six suggested kinds, which is to say the product's own advisory
vocabulary anticipates a reviewer recording something. It appears nowhere else in the tree: no code
writes it, no briefing asks for it, and no test uses it. **The residue:** an agent that reviews a
task *and* calls `record_evidence` against it anyway — the tool is available in a review turn — becomes excluded from a later review of that same
task, and on a two-agent project a second round of review would then be reported as unstaffable.
That is the verdict's accepted direction of error (a review the operator is told about, rather than a
self-approval nobody sees), it needs an agent to act outside its briefing to reach, and it is
*correct* on the reading that whoever recorded evidence claimed authorship. Left as a known cost with
a name, not designed against; if it is ever observed, the fix is a `kind` vocabulary and that is a
larger change than this one.

## D6 — Determinism was measured, and it changes the finding rather than the design

The third open question — *"whether the reviewer ladder picks deterministically when several agents
are eligible"* — is answered **yes**: `_agents_that_are_free` orders by `Agent.name` and rung 2
takes the first eligible candidate, measured stable across repeats and independent of insertion
order (`proposal.md` §1). Nothing in this change depends on it, and nothing in the corpus needs
adding: `agent-flows`' *"A firing determines both the task and the agent"* already requires the
selection to be deterministic, and the measurement is that requirement holding.

What it changes is the **severity argument**, which is why it is recorded rather than dropped:
`F306` had said *"what is not established is how often the reviewer ladder picks the author rather
than another agent when both are eligible."* The answer is that it is not a frequency at all. An
author whose name sorts first among the free agents reviews its own work on every firing for every
task it authored, deterministically, forever.

## D8 — There are **four** places that decide who may review, and R1 found two (R2)

R1's Impact section said *"No other module changes"*, naming `scheduler.py:625` and `:1574`. Both are
correct and neither needs an edit. The claim that they are the only two is false, and the two it
missed are the two where the guard's new refusal arrives **after** something irreversible has
already happened.

| # | where | what it decides | composes the exclusion from | R1 |
|---|---|---|---|---|
| 1 | `scheduler.py:615-625` `task_is_claimable_by` | may this agent be *offered* the review | `completion_attribution`, then the union | named |
| 2 | `scheduler.py:1507-1577` the staffing arm | who the flow staffs | `completion_attribution`, then the union | named |
| 3 | `agent_trigger.py:452-490` `review_dispatch_refusal` | may the operator dispatch this reviewer by hand | `agent_that_completed` **alone** | missed |
| 4 | `run_divergence.py:415-421` `_answer_failed_review` | who replaces a reviewer that said nothing | `agent_that_completed` **alone**, plus the silent reviewers | missed |

**3 — the hand-dispatch route, and the shipped requirement it would breach.** Without an edit here,
an operator may dispatch the evidence author onto an operator-completed task: the dispatch check
finds no completer and permits, `enter_selected_task` finds no completer and permits, the review
turn runs, and the verdict is refused by the new fallback. `task-lifecycle-governance:1719-1722`
already rules that out in terms this change cannot argue with — *"A review that cannot be staffed
SHALL be refused **before a turn is started** … Refusing after a turn has begun is not sufficient:
the cost of the turn has already been paid and the reviewer's conclusion has nowhere to go."*

And the residue is not merely a wasted turn. The task is left in `under_review` assigned to an agent
that **no transition on it names** — the operator did every transition — which
`task-lifecycle-governance:384-389` specifies SHALL be reported as a review genuinely in progress
and SHALL NOT be restaffed. So the flow will never recover it and nothing will report it: the exact
shape of `F45`, `F70` and `F161`, manufactured by a change whose whole subject is preventing a
silent wrong outcome.

So `review_dispatch_refusal` takes the same fallback, at the same place in its sequence (after the
status and holder checks, in place of the completer comparison's `None` branch), and returns 403 —
the code it already uses for the completer case, because this is the same authority refusal reached
by a different record. It stays the *read-only half* of what the transition layer would refuse,
which is what its own docstring says it must be.

**4 — the silent-review re-resolution.** `_answer_failed_review` hands the ladder an exclusion it
builds itself: the reviewers that gave no verdict, this run's agent, and the completer *if one is
recorded*. On an operator-completed task that last term is empty, so the ladder may resolve the
evidence author — and `agent-flows:220-222`, the same sentence R1 used to compel the ladder half,
compels this one identically: *"The Hub SHALL NOT resolve, as a task's reviewer, an agent that could
not record a verdict on it … the resolution SHALL exclude it rather than discover the refusal
afterwards."* A resolution is a resolution whichever function performs it.

The fix is not to add a term to this call site's recomposition — it is to **stop recomposing**. It
takes the two-branch derivation call sites 1 and 2 already share (`completion_attribution`, then
`agents_that_may_have_authored` where no agent completed), unioned with the silent reviewers and this
run's agent, which are facts about the *review* rather than about authorship and stay local.
`task_is_claimable_by`'s own comment is the argument: *"two compositions of the same three terms are
free to drift, and the two walks disagreeing about one task is the failure this function's whole
docstring is about."* There are three compositions. This is the one that drifted, and reducing it to
a call is what stops a fifth source ever needing four edits.

**R3 — and the recomposition has a second half that is not the exclusion.** Reducing the exclusion
to a call fixes *who* is barred and leaves *why* behind. `_answer_failed_review` calls
`resolve_reviewer` without `excluded_because`, so it takes the default *"is the one that completed
this task"* — which is true of the term it passes today (a completer, where one exists) and false
of the term §2.4 makes it pass (every agent any record associates with an **operator**-completed
task). Call site 2 already switches that clause for exactly this reason and the corpus already
requires it: *"A surfaced reason SHALL NOT state that an excluded agent completed the task where no
agent completed it … Where the exclusion is the set of agents that worked the task, the reason
SHALL say so"* (`agent-flows:552-558`), with its own scenario.

Measured rather than argued. A prototype of §1, §2.1, §2.4, §3.1 and §3.5 was applied and an
operator-completed task was driven to a silent review with nobody left to restaff. The
`run_diverged` event the operator is shown carried:

> could not staff this step: no agent is free to take it. Every agent on the roster is either
> running a turn, already holding active work, or **is the one that completed this task** and so
> may not review it.

The operator completed that task. Passing `excluded_because="has worked on this task"` on the same
branch produces the sentence the requirement asks for, and the five suites that cover this code
(`test_review_dispatch_staffs_the_task`, `test_run_divergence`, `test_review_divergence`,
`test_flow_divergence_regime`, `test_a_flow_names_what_it_cannot_staff`) were **88 passed, 0
failed** against the prototype **without** it. Nothing existing defends the sentence, which is why
§2.4a carries its own leg (§4.10a) and its own mutation.

The shape is worth naming because it is this change's own lesson arriving one layer down: R1 got
the union right and missed two call sites; R2 got the two call sites right and missed that one of
them composes a *second* thing. `review_dispatch_refusal` (call site 3) was given its reason
obligation explicitly in the delta — *"SHALL name the evidence as its reason and SHALL NOT state
that any agent completed the task"* — and call site 4 was not. The asymmetry was in the proposal,
not in the code.

**This call site is broken today, before this change, and it is filed as `F316` (A) — and R3 drove
it rather than leaving it derived.** Against today's tree: an operator-completed task, agent
`aa-author` bound to it by a run and named on no transition, reviewer `critic` staffed and silent.
`evaluate_run_end` recorded the divergence `restaffed`, moved `task.assignee` to `aa-author`, and
queued it a `divergence` entry carrying the review checkout — the agent that worked the task made
the reviewer of its own work, with no evidence row involved, so `F316` is reachable independently
of `F306` exactly as R2 claimed. Against the prototype the same fixture records `surfaced`, leaves
the assignee on `critic` and queues nothing. An agent that
worked an operator-completed task — named on its transitions, or by a bound run — is excluded from
the *first* resolution by call site 2 and eligible for the *second* by call site 4, and its approval
is permitted because no completer is recorded. `F142` widened two of the three compositions. Folding
the repair in here rather than leaving `F316` to its own change is the cheaper order and not scope
creep: after this change the call site breaches a shipped requirement, so a change that leaves it
alone does not close.

## D14 — The sibling guard takes the fallback too, and §3.4 is reversed (R4)

**Three rounds said "do not touch `_guard_reviewer_is_not_the_author`". That was wrong, and the
reason it survived three rounds is instructive: every round checked whether the guard was *in
scope*, and none checked what §3.1 did *to* it.** D8 enumerated four places that decide who may
review and repaired the three that resolve or dispatch a reviewer. The fourth defence is not a
resolver — it guards the *entry* to `under_review` — so it sat outside D8's frame and was ruled out
of scope on a distinction that is real and, after §3.1, no longer sufficient.

**The residue this change would otherwise manufacture.** `_guard_reviewer_is_not_the_author` refuses
only when `completing_agent is not None and completing_agent == task.assignee`
(`task_transition_service.py:354-357`). An operator completion records no agent, so the `None` branch
permits. An operator `PATCH /tasks/{id}` carrying `{"assignee": "<evidence author>", "status":
"under_review"}` is therefore accepted — and `api/v1/tasks.py:1266-1275` writes the assignee
*before* the transition is judged (deliberately, per the F70 fix), so the assignee is already in
place when the guard runs.

The task is now in `under_review`, held by the evidence author. §3.1 refuses that agent `approved`,
`rejected` **and** `revision_needed`. No transition on the task names it — the operator did them
all — so `task-lifecycle-governance:384-389` has the flow report it as a review genuinely in
progress and never restaff it. **The task is unmovable by any actor and invisible as a problem.**

Before this change that route produced a silent self-approval. After it, the same route produces a
silent permanent stall. Fail-closed is better than fail-open, but it is still the `F45`/`F70`/`F161`
shape — the exact shape D8 uses as its own argument for §3.5 — manufactured on the one route §3.4
declined to look at. A change whose subject is *a silent wrong outcome* may not ship a new one.

**Why the fallback is safe here.** It is the evidence term alone, as in D3, and for the same reason:
the union would refuse the flow's own reviewer. It cannot fire on the flow's path at all, because
§2.1 has already ensured the ladder never staffs an evidence author — so the only mover it refuses
is a hand-written one. And it binds the operator, which is this guard's existing and deliberate
character (*"Nobody is exempt because the rule is not about who is asking"*). That is the right
outcome rather than a cost: the operator is refused **before** a turn is spent, with a remedy the
existing message already states, which is precisely the property §3.5 is in this change for.

**What is given up.** The base requirement's *"A task whose completer is unknown may enter review"*
becomes conditional. That permission existed to avoid stranding tasks completed before transitions
were recorded — an asymmetry the offer rule shares: refuse to *offer* work whose author cannot be
ruled out, permit an actor to *act* on it. **The asymmetry is sound only while acting remains
possible.** For an evidence author on an operator-completed task, §3.1 removes acting, so permitting
the entry no longer frees the task — it strands it. Every other unattributable case keeps the old
permission untouched, including the historical tasks the rule was written for, which have no
evidence rows at all.

**Rejected: naming the residue in D7 instead.** That was the cheaper option and it is what an
earlier draft of this note did. It is wrong here because the residue is not theoretical — it is
reachable today by one ordinary operator request, it is silent, and it is unrecoverable without a
database edit. D7 is for what this change honestly does not reach; it is not a place to file a
defect the change itself creates.

## D9 — The author refusal precedes the evidence-acceptance refusal, and that ordering is kept

Measured, not chosen: `apply_transition` runs its actor-entitlement guards at `:516-527` and the
evidence gate later, so an agent that may not review at all is told *that* rather than told its
evidence is unaccepted. R2's whole-suite run surfaced this as the one existing expectation that
moves — `test_the_agent_plane_sees_the_refusal` asserts `409` on a request that now answers `403`
(`tasks.md` 4.11).

The ordering is right and is not up for discussion in this change. *"Your evidence has not been
accepted"* states a remedy the asker can act on — get it accepted — and handing that sentence to an
agent that may not record a verdict on this task under any circumstances is a false instruction. The
authority question is answered first because it is the one whose answer does not change when the
other is resolved.

What follows for the implementing run is only that the **fixture** moves, never the rule: the test
keeps asserting that the evidence refusal reaches the agent plane, with an approver that is not the
work's author. A run that changes the assertion to `403` has deleted the test and left the file.

## D7 — What this change does not claim

- **It does not make an agent's authorship provable.** The determination stays over-inclusive by
  construction; a fourth source makes it less incomplete, not complete.
- **It does not touch who may *decide* evidence.** `requirement_evidence.may_accept` is untouched,
  and an agent accepting its own evidence is a different question on a different path.
- **It does not address `F167`**, the adjacent residual on the same repair, which fails closed.
- **It leaves the agent-completed arm exactly as it is** (R2). Where agent `A` is recorded as
  completing a task, both the ladder and the guard compare against `{A}` alone, so an agent `B`
  that recorded evidence for that same task may still be staffed to review it and its verdict is
  not refused. That is outside `F306` and outside the verdict, and the code says so deliberately —
  *"where the product has a decided answer to who the author is, the whole corpus is keyed on it
  and this change does not widen it"* (`scheduler.py:1550-1553`). It is written here because it is
  the first question a reader asks after reading D2, and an unanswered one gets re-proposed.
- **It adds no defence against an agent that records no evidence at all.** An agent that works a
  task, is never bound to it, takes no transition, is never assigned, and records nothing is still
  invisible to all four sources. There is no record left to read, which is the honest end of this
  approach: the exclusion is the union of what the product writes down.
