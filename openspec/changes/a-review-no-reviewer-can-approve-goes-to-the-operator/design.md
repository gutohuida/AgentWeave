# Design — a review no reviewer can approve goes to the operator

**Built on the operator's recorded answer to D9**: `spec-queue/DECISIONS.md` `F374-fix`
(2026-09-19). A gate-refused approval is not "no verdict", and no refusal whose remedy only the
operator can apply re-staffs. ROUNDS.md still lists D9 as open (`:354`); that row is stale and
should be struck to point here. If the operator now answers otherwise, this change is withdrawn
whole: nothing else in bundle B1 depends on it, and `a-flow-stages-its-review-in-the-dispatch`
edits the restaff independently of the branch this adds.

Ordered **after** `a-task-is-attended-only-by-a-turn-that-will-reach-it` (D3 below adds a sentence
at the reason choice that change's D2 writes) and **before** `a-flow-stages-its-review-in-the-dispatch`
(both edit `_answer_failed_review`; this one adds an early branch, that one removes the assignee
write at the end).

## D1 — One predicate, over the gate's own evaluation

```python
async def approval_held_for_operator(
    session, task, *, candidate: Optional[str]
) -> Optional[GateRefusal]
```

In `hub/hub/requirement_gate.py`, beside `evaluate` (`:600-720`), which it calls with
`acting_run_id=None`. Returns the refusal where it contains a category the **candidate** cannot
remove, else `None`:

| Category (`GateRefusal`, `:84-118`) | Remedy | Operator-only? |
|---|---|---|
| `unaccepted` (`_check_unaccepted`, `:493-541`) | `ACCEPT_OR_GRANT` (`:77-80`) | yes, unless `candidate` holds `can_accept_evidence` (`requirement_evidence.may_accept`, `:659-674`) |
| `blocking` in state `awaiting_review` | *"accept or reject it"* (`REMEDY`, `:53-55`) | same as above |
| `diagnostics` | the requirement is broken as written | yes (the document is the operator's) |
| `blocking` in any other state | record or re-record evidence: the author's | no — a reviewer can record `revision_needed` |
| `unmergeable` | resolve the conflict on a branch: an agent's | no |
| `unfinished` (`_check_live_turn`, `:544`) | wait | no — it clears itself |

`candidate=None` (nobody left to resolve) treats the grant as absent.

**Why `evaluate`, not F357's `verdict_evidence_sentence`.** That sentence says approval *"can be
refused"*, deliberately (`review_turn.py:189-194`): the gate's mixed case lets approval through
where something else of the task's would merge. This decision needs *is* refused, which only the
gate's own evaluation answers. Asking the same function the transition asks (`task_transition_service.py:667`)
is what keeps the two from disagreeing.

**Re-derived at the boundary, not remembered from the 409.** The verdict says *"any 409 naming a
remedy only the operator can apply"*. No refusal is recorded against the run that met it: the
transition handler turns it into a response and nothing else (`main.py:533-543`). So the boundary
asks the gate again. That is the verdict's case and one more: a reviewer that read F357's briefing,
saw the evidence waiting, and ended without trying `approved` at all. A second reviewer would meet
the same refusal there too, so the verdict's reason applies unchanged. Recording the refusal per run
instead would need a column or an event read, and would still miss that case.

**Read-only.** `evaluate` is called inside the transition today and writes nothing; its repository
checks go through `_merge_situation` (`:393-419`), whose docstring treats every unknown as *"a reason
to not know, never a reason to refuse"*. R2 should confirm no write on any path
(`task_integration.awaiting_targets`, `merge_targets`, `requirement_coverage.requirement_coverage`).

**A raise is "not held".** The predicate catches any exception from the evaluation, logs it, and
answers `None`. Its callers then behave exactly as today. That is the answer to *what does each
caller return when this raises*: the run-end boundary (`evaluate_run_end`, its own session,
`run_divergence.py:685-876`) and every `decide_firing` caller (the firing; the board,
`api/v1/jobs.py:380`; `run_job`, `:1335`) must not fail because a diagnostic could not be computed.

## D2 — The restaff asks it

`_answer_failed_review` (`run_divergence.py:375-487`) today: declared → surface (`:425-433`);
otherwise build `exclude` (`:435-455`), `resolve_reviewer` (`:457-462`), surface rung 3 if nobody
(`:463-467`), else reassign and queue (`:469-487`).

After:

1. `held_any = await approval_held_for_operator(session, task, candidate=None)`. `None` → today's
   code, unchanged.
2. Declared: where `approval_held_for_operator(..., candidate=run.agent)` is set, surface with D4's
   divergence sentence instead of the declared sentence. (A declared reviewer that holds the grant
   and still gave no verdict is not stopped by the gate, so today's sentence stands.)
3. Availability: resolve as today. Where `choice.agent` is set and
   `approval_held_for_operator(..., candidate=choice.agent)` is `None`, restaff as today — that agent
   can decide the evidence itself. Otherwise surface with D4's sentence, whether or not anybody
   resolved. Nobody is reassigned and nothing is queued.

The `RunDivergence` row is still written (`:814-826`), `policy_applied=review`, `outcome=surfaced`,
and the `run_diverged` payload's `reason` carries the sentence (`:848`).

## D3 — The flow's later surfacing asks it

After the change above, the task stays `under_review` with the silent reviewer named, and no turn.
`decide_firing` surfaces it on every firing as *a review nobody is doing*. Its sentence
(`_wedged_review_reason`, `scheduler.py:2195-2225`) offers *"Ask {reviewer} again"*, which meets the
same refusal.

At the reason choice change 1 introduces (the F154 branch, `scheduler.py:1796` today), the order
becomes: a refused delivery (change 1's D4) → **approval held for the operator, for the named
reviewer** → `_wedged_review_reason`. The new sentence, `_approval_held_reason(task, reviewer,
refusal)`, is remedy first:

> *"Approval of {task.id} ({title!r}) waits on you: {remedy}. {reviewer} is named as its reviewer
> and cannot approve it until then. Waiting: {pieces}."*

`remedy` is *"accept or reject the evidence waiting on it, or grant an agent the decision on
evidence"* for the evidence categories and *"a requirement it serves cannot be satisfied as written;
correct the document"* for `diagnostics`. Fitted to `JOB_RUN_ERROR_SUMMARY_CHARS` (500) by trimming
`pieces`, then the title: never the remedy.

**Cost.** `evaluate` now runs inside `decide_firing` once per unattended `under_review` task per
walk, and `decide_firing` is also the board's read (`jobs.py:380`). Such tasks are rare and each is
already a stall the operator is being told about. R2 should measure one board read with one such
task on a project with a `gate`-rigor document, and say whether it needs caching.

## D4 — The divergence sentence

> *"{run.agent}'s review of {task.id} ended without a verdict, and no reviewer can approve it until
> you act: {refusal.detail()} Nobody else has been asked to review it."*

`refusal.detail()` (`:129-147`) is the gate's own composition, which is what the verdict names
(*"surfaces the gate's own sentence"*). It is not bounded: the event payload has no column limit.

## What does not change

- A fresh review is still staffed for a completed task whose approval is gate-held. The reviewer can
  record `revision_needed`, and F357's briefing tells an ungranted reviewer to ask the operator.
  Only the *second* reviewer, after a first gave no verdict, is withheld.
- `_reviewers_that_gave_no_verdict` and the exclusion reasons (`:331-351`, `:448-455`).

## Round log

- **R1, 2026-09-24** (bundle B1): wrote this change from the code at `404c7d5` and the recorded
  `F374-fix` verdict.
