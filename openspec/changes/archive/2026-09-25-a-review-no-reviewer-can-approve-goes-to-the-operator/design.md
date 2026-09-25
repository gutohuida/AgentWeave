# Design — a review no reviewer can approve goes to the operator

## Operator review, 2026-09-24

The Opus adversarial review and the operator's decision are in
`spec-queue/tracks/reviews/B1-2026-09-24.md` §2 (verdict: approve with fixes). Applied here:

- **MEDIUM, operator decision: "could not ask git" is held for the operator.** Until F424 is repaired,
  a git `TimeoutExpired` or `OSError` inside `evaluate` (`task_integration._git`,
  `task_integration.py:136-145`, `timeout=60`, uncaught) was caught by D1's blanket "a raise is not
  held" and the review was restaffed: F374 again, silently. D1 now has a row for F424's category,
  held for the operator whatever the candidate is granted, and whether it arrives as today's raise
  or as the refusal F424's repair writes ("could not ask git: <reason>",
  `scripts/drive/FINDINGS.md` F424). Any other exception is logged at warning level and is "not
  held"; the fail-open claim is reworded to say exactly that (D1, "What a raise means").
- **MEDIUM: git blocks the event loop.** The predicate is read on the board path (`api/v1/jobs.py:380`)
  and at run end. D1 now bounds each git spawn on the predicate's path at
  `DIAGNOSTIC_GIT_TIMEOUT_SECONDS` (5) and runs them off the loop (D1, "Off the event loop").
- **LOW:** self-acceptance is not modelled (noted under D1's table); the evaluation runs inside a
  savepoint so a database error leaves `evaluate_run_end`'s session usable (D1, test 1.6b).

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
@dataclass(frozen=True)
class ApprovalHold:
    detail: str                       # the gate's own `refusal.detail()`, or the could-not-ask-git sentence
    remedy: str                       # D3's remedy clause for the category that holds it
    refusal: Optional[GateRefusal]    # None only for the could-not-ask-git hold

async def approval_held_for_operator(
    session, task, *, candidate: Optional[str]
) -> Optional[ApprovalHold]
```

In `hub/hub/requirement_gate.py`, beside `evaluate` (`:600-720`), which it calls with
`acting_run_id=None`. Returns a hold where the refusal contains a category the **candidate** cannot
remove, or where git could not be asked (2026-09-24), else `None`. (`ApprovalHold` rather than the
bare `GateRefusal` R1–R3 returned, because the could-not-ask-git hold has no refusal to return until
F424's repair adds one.)

| Category (`GateRefusal`, `:84-118`) | Remedy | Operator-only? |
|---|---|---|
| `unaccepted` (`_check_unaccepted`, `:493-541`) | `ACCEPT_OR_GRANT` (`:77-80`) | yes, unless `candidate` holds `can_accept_evidence` (`requirement_evidence.may_accept`, `:659-674`) |
| `blocking` in state `awaiting_review` | *"accept or reject it"* (`REMEDY`, `:53-55`) | same as above |
| `blocking` in state `drifting` | *"resolve the drift candidate"* (`REMEDY`) | **yes, always** — no grant reaches it: `requirement_evidence.resolve_drift` refuses every non-operator actor (`:1203-1207`, `resolution_is_the_operators`), the route stamps the operator (`api/v1/spec.py:1061-1078`), and no MCP tool resolves drift (R2) |
| `diagnostics` | the requirement is broken as written | yes (the document is the operator's) |
| `blocking` in any other state (`unverified`, `rejected`, `stale`) | record or re-record evidence: the author's | no — a reviewer can record `revision_needed` |
| `unmergeable` | resolve the conflict on a branch: an agent's | no |
| `unfinished` (`_check_live_turn`, `:544`) | wait | no — it clears itself |

| **could not ask git** (F424; today a `subprocess.TimeoutExpired` or `OSError` raised out of `evaluate`, after F424's repair the gate's own "could not ask git: <reason>" refusal) | the operator checks the repository; nobody can approve until git answers | **yes, always** (operator, 2026-09-24): a second reviewer's approval asks the same git and meets the same failure; restaffing it is F374 |

`candidate=None` (nobody left to resolve) treats the grant as absent.

**Self-acceptance is not modelled** (review 2026-09-24, LOW). `decide` also refuses an agent
accepting evidence it recorded (`requirement_evidence.py:712-721`, `self_acceptance`), and the table
reads only `may_accept`. A granted candidate that recorded every awaiting row would be restaffed and
then refused. It does not arise through the resolution, which excludes every evidence author as an
author of the work (`agents_that_recorded_evidence_for`, the exclusion *A flow resolves a reviewer by
declaration, then by availability* already requires), so it is noted rather than tested.

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

**A DB-only short-circuit before any git** (R2, from D3's cost). `evaluate` spawns git
synchronously on the event loop: `_merge_situation` runs `rev-parse --is-inside-work-tree` and
`rev-parse --verify <main>` (`task_integration.py:148-169`), a branch-tip task adds a `rev-parse`,
and `_check_mergeable` one `merge-tree` per commit that would merge (`:427-447`). Timed on this
machine, three such spawns take ~75 ms. The operator-only categories need none of that except the
situation guard: `unaccepted` needs `task_integration.awaiting_targets` (a pure database query,
`:289`) to be non-empty, and `blocking`/`diagnostics` exist only where `_enforced_requirements`
finds a `gate`-rigor document. So the predicate answers `None` **without calling `evaluate`** when
`awaiting_targets(task)` is empty **and** no linked document is at `gate` rigor — the ordinary
wedged review — and pays `evaluate`'s git cost only for a task that can actually be held. Where it
does, the cost is two spawns (the unaccepted case has nothing that would merge, so no
`merge-tree`), ~50 ms per such task per board read. No caching: such tasks are rare, each is a
stall already being reported, and a cache would be a second copy of the gate's answer to keep true.

**What a raise means** (reworded 2026-09-24). The predicate's answer is one of three:

- **git could not be asked** — `subprocess.TimeoutExpired` or `OSError` out of the evaluation, or the
  refusal F424's repair adds. **Held for the operator** (operator, 2026-09-24): the answer carries the
  sentence *"the Hub could not ask git whether this task's work would merge: {reason}"*. This is not
  fail-open: it is the one exception class whose meaning is known, and it means no approval can
  happen, by anyone, until git answers.
- **anything else raised** — logged at **warning** level with the task id and the exception, and the
  answer is `None`: "not held". Only this is fail-open. Its callers then behave exactly as today: the
  run-end boundary (`evaluate_run_end`, its own session, `run_divergence.py:685-876`) restaffs by
  today's rule, and every `decide_firing` caller (the firing; the board, `api/v1/jobs.py:380`;
  `run_job`, `:1335`) shows today's sentence. None of them fails because a diagnostic could not be
  computed.
- **no raise** — the table above.

**In a savepoint** (review, LOW). A SQLAlchemy error inside `evaluate` would leave the caller's
session in a failed transaction, and `evaluate_run_end` goes on to write the `RunDivergence` row in
that session. The predicate runs the evaluation under `session.begin_nested()`; a raise rolls back
to the savepoint, and the caller's session is usable. `evaluate` writes nothing (R2), so the
savepoint costs one `SAVEPOINT`/`RELEASE` pair and changes no data. Test 1.6b raises an
`OperationalError` and asserts the divergence row is still written.

**Off the event loop, and bounded** (review, MEDIUM). `task_integration._git` is a synchronous
`subprocess.run(..., timeout=60)`, and `evaluate` reaches it on the loop through `is_repository`,
`branch_exists` (`requirement_gate.py:409`, `:411`), `task_branch_tip` (`task_integration.py:402`,
inside `merge_targets`) and `would_conflict` (`requirement_gate.py:437`). A hung git on a board read
stalls every request the Hub serves for up to a minute per spawn. Two edits, both confined to what
the predicate reaches:

1. Those four call sites are awaited through `asyncio.to_thread(...)`. A slow git then delays the
   request that asked, not the Hub. They touch no session, so moving them off the loop is safe; the
   transition's own `evaluate` call gets the same benefit for free.
2. `task_integration._git` reads its timeout from a `ContextVar` (`GIT_TIMEOUT_SECONDS`, default 60,
   unchanged for the transition and for `integrate`). The predicate sets it to
   `DIAGNOSTIC_GIT_TIMEOUT_SECONDS = 5` around its evaluation (`asyncio.to_thread` copies the
   context, so the thread reads it). A diagnostic read that cannot get an answer in 5 s gets the
   "could not ask git" hold above, instead of holding a board request for a minute.

*Rejected:* `run_in_executor` around `evaluate` as a whole. It is a coroutine over the caller's
`AsyncSession`, which cannot be driven from another thread. *Rejected:* caching the answer, for
D1's reason (a second copy of the gate's answer to keep true).

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
hold)`, is remedy first:

> *"Approval of {task.id} ({title!r}) waits on you: {remedy}. {reviewer} is named as its reviewer
> and cannot approve it until then. Waiting: {pieces}."*

`remedy` is *"accept or reject the evidence waiting on it, or grant an agent the decision on
evidence"* for the evidence categories and *"a requirement it serves cannot be satisfied as written;
correct the document"* for `diagnostics`, and *"the Hub could not ask git whether its work would
merge ({reason}); check the project's repository, then approve it yourself or send it back"* for the
could-not-ask-git hold (2026-09-24), whose `pieces` are empty. Fitted to `JOB_RUN_ERROR_SUMMARY_CHARS` (500) by trimming
`pieces`, then the title: never the remedy.

**Cost** (R2, by reading and one timing). `decide_firing` is called once per flow job by the jobs
list (`api/v1/jobs.py:380`), by `run_job` (`:1335`) and by the firing. The predicate now runs once
per unattended `under_review` task per walk. With D1's short-circuit, a wedged review with no
evidence waiting and no `gate` document costs two small database reads and no git. A held one costs
`evaluate`: two git spawns (~50 ms on this machine, run off the loop and bounded at 5 s each, D1) plus `requirement_coverage` per
linked document. Not cached (D1).

## D4 — The divergence sentence

> *"{run.agent}'s review of {task.id} ended without a verdict, and no reviewer can approve it until
> you act: {hold.detail} Nobody else has been asked to review it."*

`hold.detail` is `refusal.detail()` (`:129-147`), the gate's own composition, or for the
could-not-ask-git hold its own sentence (D1). The gate's composition which is what the verdict names
(*"surfaces the gate's own sentence"*). It is not bounded: the event payload has no column limit.

## What does not change

- A fresh review is still staffed for a completed task whose approval is gate-held. The reviewer can
  record `revision_needed`, and F357's briefing tells an ungranted reviewer to ask the operator.
  Only the *second* reviewer, after a first gave no verdict, is withheld.
- `_reviewers_that_gave_no_verdict` and the exclusion reasons (`:331-351`, `:448-455`).

## Round log

- **R1, 2026-09-24** (bundle B1): wrote this change from the code at `404c7d5` and the recorded
  `F374-fix` verdict.
- **R2, 2026-09-24** (bundle B1): re-derived against the code. `F374-fix` wording confirmed
  verbatim (`DECISIONS.md:985-991`). Two corrections: D1's table missed `blocking` in `drifting`,
  which is operator-only whatever the grant (`resolve_drift` refuses every non-operator); D1 now
  short-circuits on database facts before `evaluate`'s git spawns, which answers D3's cost question
  (measured: ~25 ms per git spawn here, synchronous on the event loop). Read-only confirmed: no
  `add`/`flush`/`commit` in `requirement_gate.py` or `requirement_coverage.py`; `task_integration`'s
  writers (`record`, `integrate_what_was_waiting_for_this_evidence`) are not on `evaluate`'s path.
- **R3, 2026-09-24** (bundle B1): re-derived against the code. No correction. Held: the short-circuit's premises (`unaccepted` needs `awaiting_targets` non-empty; `blocking`/`diagnostics` land only at `gate` rigor, `contract` goes to `reported`, `requirement_gate.py:639-700`); `may_accept` reads `Agent.can_accept_evidence` (`requirement_evidence.py:659-674`); `_answer_failed_review`'s declared/exclude/resolve/restaff order (`run_divergence.py:425-487`). D3's refused-delivery sentence now has a behind-a-refused-head variant (the attendance change's R3); the gate sentence's position after it is unchanged.
- **Operator review, 2026-09-24** (`spec-queue/tracks/reviews/B1-2026-09-24.md` §2): F424's "could not
  ask git" category added to D1 as held for the operator (operator's decision); any other raise is
  logged at warning and is "not held", and the fail-open wording says only that; the evaluation runs
  in a savepoint; the predicate's git spawns run off the loop with a 5 s diagnostic timeout;
  self-acceptance noted. Re-checked at HEAD `61d553e`: `task_integration.py:136-145`, `:307-323`,
  `:385-408`; `requirement_gate.py:393-419`, `:421-447`, `:600-620`; `requirement_evidence.py:705-721`;
  `run_divergence.py:685-704`; F424 in `scripts/drive/FINDINGS.md`.
