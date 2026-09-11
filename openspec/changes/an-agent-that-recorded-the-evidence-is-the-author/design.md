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
  staffed.

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

- **There is no closed vocabulary.** `record_evidence`'s documented contract is *"`kind`: What sort
  of thing this is — `test_result`, `manual_observation`, and so on. **Not a closed list**; use a
  word that describes it"* (`hub/hub/mcp_server.py:1365-1366`), and `record()` stores the string
  unvalidated. Any scoping rule would be a guess about free-form agent-authored text, and would fail
  open on the first synonym — a rule that reads as a safeguard and forbids nothing is the failure
  mode this repository names most often.
- **The product does not ask a reviewer for evidence.** `_briefing_evidence_lines` returns `[]` when
  `is_review`, with the comment *"A reviewer records a verdict, not evidence for work it did not
  do"* (`hub/hub/scheduler.py:2103-2104`). The review briefing tells the reviewer to end with
  `update_task`, not to record anything.

**The residue, stated:** an agent that reviews a task *and* calls `record_evidence` against it
anyway — the tool is available in a review turn — becomes excluded from a later review of that same
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

## D7 — What this change does not claim

- **It does not make an agent's authorship provable.** The determination stays over-inclusive by
  construction; a fourth source makes it less incomplete, not complete.
- **It does not touch who may *decide* evidence.** `requirement_evidence.may_accept` is untouched,
  and an agent accepting its own evidence is a different question on a different path.
- **It does not address `F167`**, the adjacent residual on the same repair, which fails closed.
- **It adds no defence against an agent that records no evidence at all.** An agent that works a
  task, is never bound to it, takes no transition, is never assigned, and records nothing is still
  invisible to all four sources. There is no record left to read, which is the honest end of this
  approach: the exclusion is the union of what the product writes down.
