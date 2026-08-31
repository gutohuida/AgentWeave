# Autonomous run — the flow lands its work

**Branch:** `autonomous/2026-08-31-the-flow-lands-its-work`, cut from `master` at `3a274a2`
**Stop:** 2026-08-31T08:00:00+01:00 · **Runner:** claude (Opus 5) · **Posture:**
`unattended-full-access`

Newest entry at the **bottom**.

---

## Iteration 0 — 2026-08-30 22:45–23:05 (+01:00) — preparation, operator awake

### The operator's instruction, verbatim

> do an autonomos run untill 8AM. Drive everything untill you solve all the issues with the flow
> and things are wortking. Fix what you already know it's broken then test the flow fix again and
> go on untill done

Preceded, in the same session, by: *"Okay let's run a explore on who to fix once and for all the
flow. Let's explore the code base what we know that is wrong... potential fixes once and for all.
I want to get this done on the flow."*

So the target is not a list of findings closed. It is **a flow that lands its work, proven by
driving it.**

### What was done while the operator was awake

**A deep exploration of the flow machinery**, four parallel readers plus direct verification, now
committed as `openspec/explorations/2026-08-30-why-a-flow-cannot-land-its-work.md` (`3a274a2`).
This is the single most valuable thing in this run's inputs: it names seven breaks with
`file:line`, establishes which shipped requirements they breach, and records the traps. **Read it
first, every iteration.** Nothing in it needs re-deriving.

Its headline: *the flow's definition of "done" is the task lifecycle's definition of "decided", and
those are not the same thing.* `hub/hub/scheduler.py` contains **zero** references to integration,
so the module that decides a flow is finished has never heard of the module that decides whether
work landed.

**Two operator decisions were taken** rather than left for the run to guess:

- **D-A — approval is REFUSED while evidence sits unaccepted.** Chosen over seeding a granted agent
  per project, over a flow granting its own resolved reviewer, and over leaving the machinery alone
  while surfacing "approved but unmerged" (that last was rejected because it leaves
  `task-lifecycle-governance:638` breached). The consequence is deliberate: a default project's
  first flow will **stall loudly** instead of finishing silently wrong.
- **D-B — a loop declares at creation whether its work needs evidence.** This was not one of the
  four options offered; the operator wrote it themselves. It makes loops a real working mode rather
  than a structural dead end.

### The stall hunt

| Category | Found | Removed |
|---|---|---|
| Operator decisions | 2 blocking (evidence acceptance; what a loop is) | Both asked and answered before arming |
| Missing artifacts | The whole analysis existed only in a chat session | Written to `openspec/explorations/` and committed |
| Environment | 8010 and 8011 both healthy; `claude` on PATH; py 3.11.9 | Verified, not assumed. **8011 serves whatever code it was started from — the run must restart it from the branch before trusting a drive.** |
| Unstated constraints | — | 20 limits carried verbatim into `STATE.json` |
| Vague queue | — | 19 items, each written for a stranger with no memory of this session |

Seven further decisions the run may hit were **pre-authorised** with a default and a stated cost
(`decisions_for_user` D1–D7), the sharpest being D5: an evidence-free loop task must merge its
**task** branch, never an agent branch — merging an agent branch is finding F58 exactly, and F58 is
severity A.

### Queue shape, and why this order

Four changes, each a full spec loop (R1/R2/R3/IMPL, never collapsed), with drives interleaved:

```
A  a-flow-briefing-names-its-contract        F140, F143   ← cheapest, stops the waste loop
B  a-review-a-flow-cannot-staff-is-named     F142         ← enforcement of agent-flows:134
C  approval-refuses-unaccepted-evidence      F122         ← operator decision D-A
DRIVE-1  prove a flow lands work end to end               ← THE POINT OF THE RUN
D  a-loop-declares-whether-it-needs-evidence F124         ← operator decision D-B
DRIVE-2  both loop modes, and re-drive the flow
SUITE    full uncontended suite, push, do not merge
```

A, B and C together are what make a **flow** work; D is about **loops**, a separate mode. Hence
the drive between them: the flow is proven before the loop work starts, so stopping anywhere leaves
complete changes rather than half-written proposals.

An **05:30 rule** parks spec work at a clean boundary and hands the remaining time to whichever
drive is next — so the run ends having proven something.

### State at arming

- `master` = `3a274a2`, tree clean, nothing in flight.
- CI green on `c6cdf9e` (all nine jobs, run `33310555286`); the only commits since are docs.
- The full hub suite was **not** re-run at arming — ~14 minutes, and green at `894d5b2` with no
  product code moved since. It runs in the `SUITE` item, uncontended, before the branch is offered.
- One change already in flight and **not** this run's job:
  `openspec/changes/a-write-outside-the-workspace-is-recorded` (F115), proposed, unimplemented.

### Next

Iteration 1: read the exploration, cut the branch, begin `A-R1`.

---

## Iteration 1 — 2026-08-30 23:24 → 2026-08-31 00:2x (+01:00) — change A, all four items

**Queue items closed:** `A-R1`, `A-R2`, `A-R3`, `A-IMPL`.
**Commits:** `7da91a3` (R1), `e828add` (R2), `fae6939` (R3), `1b4c730` (IMPL).

Branch was already cut at `ddbcc3a` and clean; `git log` matched `STATE.json`. Nothing to
reconcile.

### What the three rounds actually found

The discipline earned its cost again, and this time each round found something the one before it
could not have.

**Round 1** wrote the proposal from the exploration without re-exploring, as briefed. Two ADDED
requirements in `agent-flows`, because the corpus is genuinely silent: **no requirement anywhere
defines what causes `in_progress → completed`.**

**Round 2 killed one of round 1's claims outright.** Round 1 said a claimed task arrives at
`assigned` or `in_progress`, so the briefing should name both hops from the first and one from the
second. There are **three** arrival states: `CLAIMABLE_STATUSES` is `_statuses_in(BAND_AGENT_ACTIONABLE)`
= `{pending, assigned, in_progress, revision_needed}`, and `enter_selected_task` moves only
`pending → assigned`. A task returned for revision is briefed **at `revision_needed`**, from which
`TRANSITIONS` offers `in_progress` and nothing else. A briefing written to round 1's rule would have
named `completed` as the next call from `revision_needed` — *describing a call the machine refuses,
which is the exact defect the change exists to remove, reintroduced by the fix.*

Round 2 also found three constraints round 1 did not know about: the briefing is **not** the whole
delivered text (`job.message` follows it on both paths, and in F143's own transcript that message
said *"Work the task you have been given"* — to a reviewer); `test_flow_width.py` asserts the words
`"review"` and `"flow"` are absent from a *whole* document-less loop briefing, so every added word
had to clear both; and round 1's evidence wording would have become **false** the moment change C
ships.

And it found the harness wanting the wrong thing: `t_row12_review_leg.py` asserts *"the briefing
names the commit under review"*. It must not. The commit is resolved one step later, at spawn, by
`commit_for_task_review`, and `ReviewContext.work_moved` already exists for the case where the two
disagree. **That check was corrected rather than satisfied.**

**Round 3 found the consequence nobody had asked about: what *else* depends on the transition that
never happens.** `consider_handover` declines at its second gate when `_task_this_run_completed`
finds no `completed` transition attributed to the run. So in F140's drive, both agents called
`submit_checkpoint_notes`, both tasks stayed `in_progress`, and **no handover checkpoint was ever
generated** — the notes are unconsumed to this day. `agent-flows:379` (*"A flow generates the
author's handover briefing"*) and `agent-flows:412` (*"A reviewer is briefed by the author"*) are
both shipped, both tested, and **both unreachable in a real flow.**

The sharpest form of it: the briefing's own sentence *"Record what a reviewer will need … somebody
else reads it"* **was false**. Nobody read it. The briefing asked for a record and never asked for
the thing that delivers it. That is one defect, not two, and it made the change's case far better
than rounds 1 or 2 had.

Round 3 also strengthened the central argument. The strongest objection to fixing prose is that the
defect is structural — there is no `finish_turn`, so progress hangs on an agent choosing to call a
general-purpose tool. Round 1 answered *"it already does, unavoidably"*, which says the alternative
is unavailable rather than that this one is right. The better answer is that **the product already
decided this exact question in writing**, about `ask_user`: *"An agent that needs an answer calls
`ask_user`; a turn that ends without calling it has ended."* Two halves. **This change is the
first.** The second — a turn that ends without the call being *visible* rather than silently
re-briefed — is `loop-firing-accountability`'s, and the proposal now says so in those terms rather
than filing it as a nice-to-have.

And it found round 2's **own** new requirement over-reaching: telling a reviewer that the loop's
message *"does not describe this turn"* is wrong exactly where its author thought hardest, since a
standing message may itself be written to address a review. Narrowed to identifying what the text
is, with instructing the agent to disregard it now forbidden.

Rejected alternatives are recorded so they are not re-proposed: a `finish_turn` tool (a second
writer of a fact `apply_transition` owns — and it does not solve the problem, since an agent never
told to call `update_task` would not be told to call `finish_turn` either); the Hub concluding
completion from a clean turn end (**foreclosed**, not merely undesirable: it must author a
`TaskTransition` with an actor, and `task-lifecycle-governance:359` forbids a third actor kind); and
a separate `_compose_review_briefing` function (three shared sections duplicated to avoid one
conditional).

### The reproduction, run against unmodified code before anything was written

```
--- F143: review briefing vs implementation briefing ---
identical: True
--- F140: what the briefing names ---
  submit_checkpoint_notes    present=True
  update_task                present=False
  record_evidence            present=False
  the word 'completed'       present=False
```

Both defects, exactly as filed. The permanent tests are that reproduction with its assertions turned
around.

### What shipped

`_compose_loop_briefing` takes a keyword-only `is_review` with **no default** — a default is what
would let a future call site reintroduce F143 — plus three helpers. What an agent is now handed:

```
**Finishing means moving the task.** It is `assigned` now; call
`update_task("task-9c1f2a", status="in_progress")` when you start and
`update_task("task-9c1f2a", status="completed")` when the work is done. Nothing else moves
it, and a turn that ends with the task unmoved leaves the next firing to claim the same task
and ask somebody to do the same work again. Record what whoever checks this work will need
before you move it (see `submit_checkpoint_notes`) -- those notes are delivered only when the
task reaches `completed`.

**This task serves `FR-1`.** Record what demonstrates it with `record_evidence("FR-1", summary)`.
What you record enters `awaiting`: somebody else decides on it, and the work cannot land until
they do.
```

and a reviewer, instead of *"Finish the task below and stop"* over the implementation description:

```
**This turn is a review.** Somebody else finished the task below; you are checking their work,
not doing it. …

**End the review with a verdict, using `update_task`.** The task is `under_review`: set it to
`approved` if the work is right, or `revision_needed` if it is not. …

## Under review: Add power(a, b) to calc.py

What the author was asked to build. This is the standard you check their work against, not an
instruction to you.

…

Below this line is the loop's standing message, delivered on every firing. It was not written
for this turn in particular.
```

Both were read end to end as delivered — briefing plus `job.message` — not merely asserted against.

### Verification

- `hub/tests/test_briefing_names_its_contract.py` — 18 new tests, all green.
- `pytest hub/tests/ -k "flow or loop or brief or scheduler or handover or divergence or job"` —
  **451 passed, 14 skipped, 0 failed** (5m57s).
- `ruff check src/ hub/ tests/` clean; `black --check --target-version py311` clean over all 525
  files.
- Six existing call sites now state `is_review=False` explicitly. They failed loudly first, which is
  the no-default decision working.

**What is not proven.** Whether a real agent acts on the text. String assertions cannot settle that
— `DRIVE-1` is the question, and `t_row12_flows.py` now carries a mechanical pass condition for it
(every task the flow worked has left the active band) rather than a transcript to read.

### Next

`B-R1`: propose `a-review-a-flow-cannot-staff-is-named` (break 4, F142).

---

## Iteration 2 — 2026-08-31 00:04–00:2x (+01:00) — B-R1, round 1 of `a-review-a-flow-cannot-staff-is-named`

**Reconciliation.** `STATE.json` claimed iteration 1 complete on `b34ece5` with `next_action =
B-R1`. Branch, `git log` and working tree all agreed; nothing to reconcile. Heartbeat claimed at
00:04 and the branch taken.

### One item, one round

`B-R1` only. The proposal is written; **no code was touched**, which is the round discipline working
rather than a shortfall. `openspec validate a-review-a-flow-cannot-staff-is-named --strict` passes.

### What round 1 establishes

The queue item named the minimum repair — `scheduler.py:1364-1368` drops an unattributable task with
a bare `continue` and that breaches `agent-flows:189-195` — and left the judgement half open. Both
are now settled on the page for rounds 2 and 3 to attack.

**The enforcement half is not a judgement.** `agent-flows`' *"No eligible agent surfaces rather than
stalling silently"* scenario requires the operator to be notified naming the task when no agent can
be resolved or found for one. Nothing is recorded, so nothing is notified. It goes under either
answer below.

**The judgement half, and this proposal's position: a flow MAY staff a review for work the operator
completed.** Recorded with the argument *against* stated at equal length in `design.md` D4, because
round 3's job is to re-derive it rather than inherit it — and D4 names the specific weakness to
attack, that `requirement-traceability:158` is about *evidence acceptance* falling to the operator
and is being stretched to cover task completion.

### The two things round 1 found that the queue item did not name

**1. `None` is two worlds and they cost nothing to separate.** `Actor.__post_init__`
(`task_transitions.py:64-67`) makes an actor of kind `run` without an agent unconstructible, and one
of kind `operator` with an agent equally so. `task_transition_service.py:431` is the only production
writer of the table. So on a `→ completed` row, `actor_agent IS NULL` ⟺ *the operator made the move*
— one extra column in a query the walk already runs. No migration, no column, no second round trip.

Recorded as a rejected alternative because it looks like the fix and is not: filtering the existing
query to `actor_kind = 'run'` is a **no-op**, since a run row always carries an agent. That is itself
the proof the ambiguity lives in what the *caller* concludes from `None`, not in the query.

**2. The obvious repair is a self-approval route — this is round 1's real finding.** The arm calls
`resolve_reviewer(..., exclude={author})`, so `author is None` invites `exclude=set()`. In F140's own
drive the builder did the work, recorded evidence, never called `update_task`, and is still in
`task.assignee` — with an empty exclusion it is an eligible reviewer of its own work, and **nothing
downstream catches it**: `_guard_author_is_not_reviewer` and `_guard_reviewer_is_not_the_author` both
permit when the completer is unknown, deliberately and at length. That is `task_is_claimable_by`'s
own warning — *"self-approval reached by two permissive defaults agreeing"* — arriving through a new
door.

So the change carries `agents_that_worked()` (distinct non-null `actor_agent` over the task's
transitions) as the exclusion for that arm. Without it this change would ship a regression worse than
the bug it fixes. Task 1.4 writes that trap as a reproduction *before* building the arm that would
walk into it.

### All seven callers, enumerated in round 1 rather than deferred to round 2

The queue item asked round 2 to do this. Doing it in round 1 is what decided the shape: four of the
seven read `None` correctly and are argued at length in their own docstrings, so
`agent_that_completed` keeps its exact signature and becomes a wrapper over a new
`completion_attribution()`. Changing a return type four correct callers depend on, to serve three, is
the wrong direction. Round 2 still owns verifying the table.

| # | Site | Reads `None` as | Change |
|---|---|---|---|
| 1 | `_guard_author_is_not_reviewer` (`task_transition_service.py:168`) | permit | none |
| 2 | `_guard_reviewer_is_not_the_author` (`:220`) | permit | none |
| 3 | `task_is_claimable_by` (`scheduler.py:589`) | refuse to offer | **yes** |
| 4 | wedged-review branch (`scheduler.py:1280`) | not wedged → `in_flight` | **yes** |
| 5 | review arm (`scheduler.py:1364`) | drop silently | **yes** |
| 6 | `run_divergence.py:415` | nobody to bar | none |
| 7 | `agent_trigger.py:445` | permit the dispatch | none |

### Scope the round grew, each for a reason in the code

- **`task_is_claimable_by`** moves with the review arm, or the flow walk and the per-agent walk
  answer opposite things about one task — which `agent-flows:59`'s third scenario, *"Claimability and
  the approval guard agree"*, forbids.
- **The wedged-review branch** (`scheduler.py:1279-1284`) moves too. F142 measured it as the
  operator's only manual escape and it is gated on the same function; a task in `under_review` whose
  assignee is the agent that wrote the code is recorded `in_flight` — *"a reviewer holds this"* —
  which is exactly the false statement `task-lifecycle-governance:313` exists to prevent.

### A shipped, undocumented divergence found on the way

`agent-loops:815` requires a stall reason to *"name how many tasks are open and in which statuses"*.
`scheduler.py:1438-1457` replaces that with `unstaffed[0][1]` whenever the walk named an unstaffable
task — F64's fix, which is right, and **no requirement licenses it.** The corpus was searched; the
only neighbouring clause is the gated-stall carve-out, which is about dependency gates.

This change makes that override fire on a new class of queue, so reconciling it is this change's job
rather than a tidy-up someone else inherits. `agent-loops` gets the general clause: the histogram is
the reason of last resort, and where the walk attributed the stall to a specific task with a remedy,
that names the stall.

### Verification

- `openspec validate a-review-a-flow-cannot-staff-is-named --strict` — valid.
- Every requirement citation in the proposal was opened and read, not recalled. One was wrong and was
  corrected: the *"a supported way to work, not a degraded one"* clause is
  `requirement-traceability:158`, not `:117` as the exploration has it.
- `task_transition_service.py:431` confirmed as the only production writer of `task_transitions`, so
  D2's invariant holds in production. Tests construct rows directly
  (`test_project_delete_api.py:390`, `test_task_transition_service.py:213`), which is why task 2.3
  asserts the invariant through `Actor.__post_init__` rather than through the table.
- No code changed, so no suite was run. That is correct for a round-1 item.

### Next

`B-R2`: a fresh comparison of this proposal against the code. The queue item's own list still stands
— re-verify all seven callers rather than accepting the table above, and check the wedged-review
recovery at `scheduler.py:1280`. Two things round 1 asks round 2 to attack specifically:

1. **`commit_for_task_review` does not require acceptance** (`requirement_evidence.py:736-795`) — it
   needs an evidence row with a non-empty `commit_sha` on its footprint. If that reads correctly,
   then in F140's own shape (agent records evidence, operator completes the card) this change staffs
   a **real** review in a default project. F142's working row happened to have *accepted* evidence,
   and concluding acceptance was load-bearing when it was incidental is the easy mistake here.
2. **Whether the wedged-review widening is safe.** A flow that starts reporting reviews in progress
   as unstaffable would be worse than the bug. Task 5.4 is the guard; check the predicate reaches
   only the intended rows.

## Iteration 3 — 2026-08-31 00:19–01:0x (+01:00) — B-R2, round 2 of `a-review-a-flow-cannot-staff-is-named`

**Reconciliation.** `STATE.json` claimed iteration 2 complete on `8a5a7d6` with `next_action = B-R2`.
Branch, `git log` and working tree all agreed; nothing to reconcile. Heartbeat claimed at 00:19.

### One item, one round

`B-R2` only. **No code was touched** — this is a spec round. Six files changed, all inside
`openspec/changes/a-review-a-flow-cannot-staff-is-named/`. `openspec validate --strict` passes.

Round 2 was run as the discipline asks: a fresh comparison of the proposal against what the code
does, opening each cited function rather than re-reading round 1's argument. Every one of round 1's
seven callers was re-derived from `grep` rather than from `design.md` D3's table.

### What held

- **All seven callers of `agent_that_completed`, verified independently.** The table is right on
  sites, line numbers, and how each reads `None`. Sites 1, 2 (`task_transition_service.py:168`,
  `:220`), 6 (`run_divergence.py:415`) and 7 (`agent_trigger.py:445`) all read `None` as *permit* and
  are correct as written; 3, 4, 5 change. No eighth caller exists.
- **`commit_for_task_review` does not require acceptance** — the thing round 1 asked round 2 to
  attack first. `requirement_evidence.py:736-795` joins `RequirementEvidence` to `EvidenceFootprint`
  on `task_id` and filters on a non-empty `commit_sha`; there is no `review_state` term in the query.
  So F142's working row having *accepted* evidence was incidental, and this change staffs a real
  review in F140's own shape, in a default project. D9 was right and now says so from the code.
- **D2's invariant.** `Actor.__post_init__` (`task_transitions.py:58-67`) raises for `run` without an
  agent and for `operator` with one. `actor_agent IS NULL ⟺ operator` holds on any `→ completed` row.
- **The `unstaffed` event fires whatever the firing does.** `_do_fire_job` loops
  `decision.unstaffed` at `scheduler.py:2402-2405`, before it branches on `decision.kind`. Task 6.1's
  "no code change expected" is correct.
- **Every test line reference cited in D12 and in tasks 1.2/4.3/4.4 resolves to what it claims.**

### Finding 1 — the safety argument had a hole, and it is the one the change turns on

Round 1's D5 ended: *"`assignee` is still in the set whenever it matters, because an agent holding a
task moved it to `in_progress` through `apply_transition` and is on the record."* **That sentence is
false**, and it is the sentence the whole permissive direction rests on.

`bind_run_to_task` (`run_task_binding.py:432-436`) records `→ in_progress` only if the edge is legal,
and `TRANSITIONS["in_progress"]` is `{completed, assigned, blocked, rejected}` — **there is no
`in_progress → in_progress` edge**. An agent whose run binds to a task already `in_progress` takes no
edge and records nothing.

So: the operator moves a card to `in_progress` by hand, the flow staffs it (`enter_selected_task`
leaves a non-`pending` status alone), the agent writes every line of the work, the operator marks it
done. Every transition on that task is operator-attributed. `agents_that_worked` is **empty**, the
exclusion is empty, and the arm this change adds offers the agent its own work to review — the exact
self-approval route round 1 identified as its "real finding", surviving inside the repair for it.
And it lands in the change's own target fixture: an operator hand-driving the board is why F140's
card was completed by hand in the first place.

The correction: the exclusion is `agents_that_worked | {task.assignee}`. `assignee` is not a
replacement for the transition set — round 1's three reasons against that all stand — it is the term
that covers the agent the history does not.

**And the union must not reach the wedge predicate.** D8 asks *"is the assignee one of the agents
that worked this?"*; with the union that is true of every task with an assignee, so every review in
flight would be reported unstaffable — which is precisely the "worse than the bug" outcome the queue
item told round 2 to check for. Two questions, two sets, and tasks 2.5/5.1 now name which is which.
Verified that the transitions-only set is safe there: a legitimately staffed reviewer is absent by
construction, because `enter_selected_task` writes `completed → under_review` as the *operator*
(`scheduler.py:795`) and the reviewer's own binding onto an `under_review` task is not a legal edge
either, so it records nothing until it writes its verdict.

### Finding 2 — the change would have shipped its headline sentence untrue

`resolve_reviewer` hard-codes why an agent was excluded, twice: rung 1b says *"that agent is the one
that completed the work"* (`scheduler.py:1074-1083`), rung 3 says *"or is the one that completed this
task and so may not review it"* (`:1111-1118`). Under a wider exclusion both are **false** — the
operator completed it and the excluded agent merely worked it.

Rung 3's is not any sentence. It is the one `decide_firing` promotes to `stall_reason`
(`scheduler.py:1457`) and `_emit_review_unstaffed` broadcasts — the exact text this change exists to
put in front of the operator in place of F142's histogram. And round 1's spec delta *required* the
falsehood, by saying the flow surfaces "exactly as it does when the author is known".

Fixed as design D13: `excluded_because` becomes a parameter with today's clause as its default, the
operator arm passes `"has worked on this task"`, and `agent-flows` gains a requirement that a
surfaced reason SHALL NOT say an agent completed a task no agent completed, with a scenario asserting
the absence of the claim rather than only the presence of the new one.

### Finding 3 — a delta clause that retroactively made shipped behaviour non-compliant

`agent-loops`' new clause required an attributed stall reason to have *"named what the operator can
do about it"*. F64's shipped rung-3 sentence names causes, not a remedy, so as written the delta made
correct shipped code fail its own reconciliation. Narrowed to attribution alone; the remedy demand
stays in `agent-flows`, where task 3.2 implements it.

### Also recorded, not fixed

`_emit_review_unstaffed` persists an event on **every** firing with no dedup. This change routes a
*permanently* unresolvable condition through it (a task with no provenance can never gain any), so a
cron-ticking flow will accrue one row per tick forever. Pre-existing for rung 3 and out of scope for
`agent-loops`' "records only what is new", which is scoped to execution history rather than the event
log — but new in kind, because the other cases can all be resolved. Carried as an open question.

### Verification

- `openspec validate a-review-a-flow-cannot-staff-is-named --strict` — valid.
- `git status` shows six files, all inside the change directory. No code, no tests, no suite run —
  correct for a round-2 item.
- Every claim above was read off the code in this session. The three MODIFIED deltas were diffed
  against the originals in `openspec/specs/` to confirm they restate rather than silently drop.

### Next

`B-R3`: the second **independent** re-derivation, not a review of round 2. The failure it exists to
catch is an argument that is wrong while everything it argues about is right — and round 2 just found
exactly that shape twice, so the round is earning its keep on this change specifically. What round 3
should attack, in order:

1. **The judgement itself, re-derived rather than inherited.** D4 says a flow MAY staff a review for
   operator-completed work. The specific weakness named for round 3 stands untouched by round 2:
   whether `requirement-traceability:158` is being stretched, since it is about *evidence acceptance*
   falling to the operator and not about task completion.
2. **Whether `worked ∪ {assignee}` is now too wide.** Round 2 widened the exclusion; round 3 should
   ask what it costs. A reviewer that rejected the task once is already in the set via
   `under_review → revision_needed`, and the assignee term adds anyone the operator parked the card
   on. A single-agent-plus-reviewer project may now reach rung 3 where it used to staff.
3. **Whether the whole thing belongs in `decide_firing` at all**, or whether the honest fix is that
   `bind_run_to_task` should record the agent's turn on a task it did not move — which would make
   `agents_that_worked` true to its name and delete the assignee term. Round 2 chose the cheaper
   repair deliberately; round 3 should say whether that was right.

---

## Iteration 4 — 2026-08-31 00:34 to 00:46 (+01:00)

Branch `autonomous/2026-08-31-the-flow-lands-its-work` at `d4402aa`, tree clean, `git log` matching
STATE.json exactly. Nothing to reconcile. Heartbeat claimed at 00:34.

### One item, one round

`B-R3` only. **No product code was touched.** Five files changed, all inside
`openspec/changes/a-review-a-flow-cannot-staff-is-named/`. `openspec validate --strict` passes.

Round 3 was run as an independent re-derivation, not a review of round 2: the three attack points
the queue named were taken in order and each was carried back to the code rather than to `design.md`.
All three landed, and one of them is the change's central safety property.

### Finding 1 — round 2's repair closes the hole for the *first* agent and leaves it open for every one after

Round 2 widened the exclusion to `agents_that_worked ∪ {task.assignee}` with the sentence *"`assignee`
is the term that covers the agent the history does not."* That is true of **exactly one agent**. The
assignee column holds one name and `bind_run_to_task` fills it only when it is **empty**
(`run_task_binding.py:429-430`) — so the same mechanism that hides an agent from the transition
history also denies it the column, and the two terms fail together rather than covering for each
other.

The route needs no unusual operator behaviour:

1. A flow staffs `builder-1` the ordinary way — assignee written, `pending → assigned` as operator,
   `assigned → in_progress` by `builder-1`'s run. `builder-1` is on the record and in `assignee`.
2. `builder-1` stalls, or finishes without calling `update_task` (**which is F140, this run's change
   A**). The operator starts `builder-2` on the same card. That is permitted:
   `resolve_bound_task` *"never consults `Task.assignee`"* (`agent_trigger.py:845`) and the only
   concurrency refusal is against a turn running **right now** (`:863-872`).
3. `builder-2`'s binding leaves the assignee alone (already set) and travels no edge (no
   `in_progress → in_progress` in `TRANSITIONS`).
4. `builder-2` writes the work; the operator marks the card done.

`worked ∪ {assignee}` is `{builder-1}`. **The agent that wrote the work is offered it to review** —
the exact self-approval D5 exists to prevent, surviving inside the repair for it, one agent over.

**Measured rather than argued.** Built as a throwaway pytest against the real `bind_run_to_task`,
`apply_transition` and `Actor`, on the suite's own database. Every intermediate assertion held:
`moved2 is None`, `r2.task_id == task.id`, `task.assignee == "builder-1"`, transitions naming
`{builder-1}` alone, and `SELECT DISTINCT agent FROM runs WHERE task_id = ?` returning both. Passed
first run, file deleted; task **1.5a** is its permanent form and must assert the intermediates, not
only the conclusion.

**The fix (design D14):** a third term, `agents_of_runs_bound_to(task)`. `bind_run_to_task`'s *first
statement* is `run.task_id = task.id` (`:427`), above every guard — the one record in the product
that names `builder-2`. The exclusion becomes transitions ∪ assignee ∪ bound runs, and the design
now states the rule that makes three terms right rather than three patches: with no completion row
the author is not provable from anything, so **exclude every agent any record associates with the
task**, and treat a source's silence as a missing candidate rather than as evidence of innocence.

`checkpoint_handover.py:87-92` forbids reading `run.task_id` in the strongest terms (*"of the ten
runs that had recorded a `completed` transition, six carried `run.task_id = NULL`"*), so D14 says why
this is not the same mistake: there a NULL produces a **wrong answer**, here a **missing candidate**
in a set whose only job is to grow. It is a term and never the set.

### Finding 2 — D4's central citation was stretched, and the judgement stands on better ground

The attack the queue named was right. `requirement-traceability:158` is scoped by the sentence before
it — *"Where a project has granted no agent that capability"* — and is about the operator acting where
**no agent is permitted to**. This change is about the operator acting where an agent **could** have.
Generalising it to *"the operator acting in person is first-class"* is a conclusion the sentence does
not carry, and a round that only checked outcomes would have kept it, because the outcome is right.

The judgement survives on a ground neither earlier round cited: **the product has already decided this
case on its other path.** `agent_trigger.py:444-452` bars a manually dispatched reviewer only where an
agent is *recorded* as completing the task, so an operator-completed task is reviewable **by hand
today**. The change removes a disagreement between two paths about one task, in the direction the
shipped path already chose — and it is a path this change deliberately leaves untouched (D13).
`task-lifecycle-governance`'s *"Dispatching a review staffs the task, whichever path dispatched it"*,
with its scenario *"A review started by hand leaves the reviewer able to record a verdict"*, makes
path-independence a stated principle; D15 records the limit that its words govern staffing mechanics
rather than eligibility, rather than borrowing its authority for something it does not say — which
would be the same error one requirement over. `:158` stays as supporting colour, demoted.

**And the other half of that attack — is the union too wide? — is answered as a property**, which
matters more now that D14 has widened it again: it **cannot regress anything**. Every path it touches
produces "nobody" today. The review arm is `continue`; `task_is_claimable_by` returns `False` for all;
the wedge branch uses the transitions-only set; the attributed arm is untouched. So the whole cost of
over-exclusion is a review surfaced at rung 3 instead of staffed — by name, with a remedy, through the
machinery this change builds — weighed against a silent self-approval that merges a commit nobody
checked.

### Finding 3 — where the fix belongs, and the third assignment answered

Round 2 chose to read the exclusion at decision time rather than make `bind_run_to_task` record the
turn. That was **right, and not because it was cheaper** (D16):

- **A recording fix is forward-only, and this change's whole population already exists.** F142's
  fixture, F140's drive, and every hand-driven card are in the broken state now with histories that
  will never gain a row. A safety exclusion cannot be built on a mechanism with no past.
- An `in_progress → in_progress` self-edge contradicts a rule the corpus already states one band
  over — *"dispatching SHALL leave both unchanged and **SHALL travel no transition**, so that a task
  does not accumulate a record of being entered into review more than once"* — and would make
  `TaskTransition` answer *"who touched this"* rather than *"how did this move"*.
- A participation table is forward-only plus a migration, for strictly worse coverage than D14's
  union.

### Finding 4 — `task_is_claimable_by`'s docstring argues from two false premises

Found by re-deriving D7 against the function rather than against D7, and it is this round's shape
exactly: the argument is wrong while everything it argues about is right.

1. *"Every task that reaches `completed` through `apply_transition` records its completer, so this is
   the legacy and hand-written case only."* **False, and it is the root of F142.** An operator
   completion reaches `completed` through `apply_transition` and records `actor_agent = NULL`. The
   `None` population includes every task an operator finishes through the supported route. This
   sentence is why the branch above it looked safe to everyone who read it.
2. *"it stalls the queue and the operator reviews it, which is … a state the operator can see and
   resolve."* **Both halves measured false by F142.** The stall reason is the status histogram, which
   names no task; and `completed` has no exit that returns the work to an agent.

Task 4.2 said "extend the docstring", which leaves both standing. New task **4.2a** corrects them:
the second reader to trust those sentences is how this defect survived its own fix.

### What changed on the page

- `design.md` — **D14** (the second-agent hole, the third term, the `checkpoint_handover` distinction,
  the measurement), **D15** (the judgement re-derived, citation corrected, over-width answered as a
  property), **D16** (where the fix belongs; three recording designs rejected with reasons),
  **D17** (the two false docstring sentences). D4, D5 and D8 amended to point at them rather than
  leaving superseded arguments to be inherited.
- `proposal.md` — the exclusion is three terms; the *Why*'s judgement paragraph now cites the shipped
  manual path instead of `requirement-traceability:158`; the trap section carries the `builder-2`
  route.
- `specs/agent-flows/spec.md` — the determination is over **every record that associates an agent with
  the task**, with the reason each term is individually incomplete, plus an explicit
  over-inclusiveness clause (a source's silence is not evidence) and a new scenario for the second
  agent.
- `specs/task-lifecycle-governance/spec.md` — the wedge determination is now *transitions alone*,
  excluding the assignee **and** the bound runs, with the reason the wider set cannot be reused.
- `tasks.md` — new 1.5a (the measured reproduction), 2.4a (the runs query and its
  `checkpoint_handover` justification), 3.3b (must fail against a two-term exclusion first), 4.2a
  (the docstring correction); 2.5, 2.6, 4.1, 4.3 rewritten for three terms and five fixtures.

### Verification

- `openspec validate a-review-a-flow-cannot-staff-is-named --strict` — valid.
- The D14 fixture executed and passed on the hub suite's database; scratch file deleted, tree clean.
- `git status` shows five files, all inside the change directory. No product code, no suite run —
  correct for a spec round.

### Next

**`B-IMPL`.** Change B has had all three rounds and every one of them found a real defect in the
proposal, which is the discipline's sixth consecutive outing with a hit. Implement it reproduction-
first, in the task order above, and note that **1.5a and 3.3b are the two tests that must fail
against round 2's two-term exclusion before the third term is added** — a green run of either without
that check proves nothing. Then DRIVE-1.

Carried, unfixed: `_emit_review_unstaffed` has no dedup and change B routes a permanently
unresolvable condition through it (iteration 3's finding, still open).

## Iteration 5 — 2026-08-31 00:49 to 01:19 (+01:00)

Branch `autonomous/2026-08-31-the-flow-lands-its-work` at `2163fd8`, tree clean, `git log` matching
STATE.json. Nothing to reconcile. Heartbeat claimed at 00:49.

### One item: `B-IMPL`

`a-review-a-flow-cannot-staff-is-named` implemented reproduction-first, in `tasks.md`'s order. 46 of
47 tasks closed; the open one is 8.6, the commit itself. Group 7's harness edits are written and
compiled but **not driven** — that is `DRIVE-1`, and `tasks.md` now says so above group 7 rather
than leaving a checked box to imply otherwise.

### The reproductions were run first, against unmodified code, and all seven passed

Written as a transient `test_zz_repro_f142.py` asserting **today's** behaviour, run, then deleted;
its permanent form is the inverted assertions in `test_a_flow_names_what_it_cannot_staff.py`. It
inlined its own transitions query rather than importing `agents_that_worked`, so it did not depend
on the correctness of anything this change was about to add.

- **1.3** — fixture (b), operator-completed with accepted evidence: `selections == ()`,
  `unstaffed == ()`, `deferred == ()`, `_cannot_staff == ()`, stall reason
  `"no claimable task among"`. The silent drop, measured.
- **1.3b** — fixture (c), same silence.
- **1.5** — fixture (d): `agents_that_worked` empty while an agent wrote every line.
- **1.5a** — fixture (e): `worked | {assignee}` is `{builder}`; the bound runs are
  `{builder, builder-2}`; **`builder-2` is in neither of round 2's two terms.**
- **1.5a's consequence**, and this is the round-3 gate the queue named: with round 2's exact
  two-term exclusion passed to `resolve_reviewer`, **the ladder returns `builder-2` for its own
  work.** Seen to happen, not argued. That is what the third term closes.
- **1.6** — (b) moved to `under_review` by hand lands in `_cannot_staff`: a false *"a reviewer holds
  this"*.
- claimability refuses (b) outright.

Two fixture defects were found by running them, and fixed before anything was asserted on behaviour:
(e) had no `Run` row for the first agent (its transitions were faked with a bare actor rather than a
binding), and both (d) and (e) left their runs `status='running'`, which would have excluded the
agent from the free pool and made every exclusion assertion below pass **without the exclusion
existing**. Both fixtures now go through `bind_run_to_task` and end their runs.

### What shipped

`task_transition_service.py` — `CompletionAttribution` + `completion_attribution()`;
`agent_that_completed` is now a wrapper with its signature and semantics unchanged;
`agents_that_worked`, `agents_of_runs_bound_to`, and the union behind one named helper,
`agents_that_may_have_authored`. The two set-valued functions' docstrings state **which question
each answers** — *"which agents moved this task?"* versus *"might this agent be the author?"* —
because a call site picking the wrong one is how round 2's union nearly shipped a self-approval and
how D8's predicate would wedge every review in flight.

`scheduler.py` — the review arm's three-way split; `resolve_reviewer` gains `excluded_because`, used
by both refusal sentences; the wedged-review predicate reads the completion where one names an agent
and the **transitions-only** set where it does not; `task_is_claimable_by` gains the operator arm and
calls the same helper the arm excludes with, rather than recomposing three terms a second time.

`task_is_claimable_by`'s two false docstring sentences are **corrected**, not extended (4.2a / D17).

### Three suite tests changed deliberately, each because this change's specified behaviour moved

Not discovered in the run — grepped for first (3a.4), then read, then changed with the reason written
into the test:

1. `test_scheduler.py::test_loop_whose_tasks_are_all_completed_but_unapproved_skips_instead_of_spinning`
   asserted `"stalled"` and `"2 completed"` in `error_summary`. Its two tasks are built directly at
   `completed` — case (c) — so the walk now names the first of them with the remedy. This is
   `agent-loops`' *"An attributed stall names its task rather than the queue"*, which is the
   requirement this change wrote.
2. `test_firing_decision_is_shared.py` — the same substitution, twice. The property under test is
   unchanged: the board's label is the same string the firing would refuse with, whichever reason
   that is.
3. `test_loop_stall_ticks_in_place.py::test_a_stall_whose_reason_changes_starts_a_new_row` changed
   its reason by adding a second unclaimable task, which used to move the histogram's count. The
   histogram is now the reason of last resort, so a second unstaffable task leaves the first one's
   sentence identical and the row correctly increments. The reason is now changed the way it
   actually changes — by changing what is true of the task the reason is about.

`test_flow_chain_end_to_end.py:344-355`'s set equality (tripwire 8.3) is **untouched** and green.

### Finding, fixed: the delta's own scenario was wider than its requirement (D18)

`task-lifecycle-governance`'s scenario *"A task with no recorded completion is surfaced, not
restaffed"* was keyed on nothing but the absence of a completion. Implemented literally it reports a
**real, in-progress review** as one nobody is doing: reaching `under_review` with an assignee and no
recorded completion is a *supported* route, because `agent_trigger` bars a hand-dispatched reviewer
only where an agent is *recorded* as completing the task, and dispatching staffs it. That is 5.4's
own risk arriving through the requirement instead of through the code.

The requirement's prose was already right — *"when that task's assignee is an agent that produced
the work"* — and `tasks.md` 5.1 was right. Only the scenario disagreed. Corrected, plus a second
scenario for the hand-dispatched case, plus
`test_a_hand_dispatched_review_on_an_unattributed_task_is_still_held`.

Worth recording *how it survived three rounds*: every round checked the wedge predicate against being
given the **wider** set (D8, D14), which is a real hazard and was caught three times. Nobody checked
it against the narrower direction — what the requirement says when the set is empty. The exclusion
was re-derived three times and the scenario once.

### Finding, filed not fixed: `RequirementEvidence.actor` is a fourth record (D19)

`record_evidence` takes `task_id` as a free parameter and does not require the calling run to be
bound to it. So an agent can work a task on an **unbound** run, record evidence naming its commit,
and appear in none of the three terms — no transition, no `assignee`, no `run.task_id` — while
`RequirementEvidence.actor` names it, and the review arm requires that very row to exist before it
resolves a reviewer at all. The same shape as D14's second agent, one source further out.

**Not added.** The delta enumerates three sources by name, and adding a fourth that no round
re-derived is precisely the move this change exists to argue against. Queued for the operator, and
row four of the drive harness (`AW_COMPLETE_BY=untouched`) drives exactly this shape live, so
`DRIVE-1` will show whether the agent that recorded the evidence is offered its own work.

### Harness (group 7)

`t_row12_review_leg.py`: the stale docstring claim that the two modes disagree is now history rather
than the finding; row one's expectation inverts with **specific strings** — the refusal must not
contain `"no claimable task among"`, and where there is a refusal it must name the task; and row
four (`AW_COMPLETE_BY=untouched`) is added, running the agent on a turn triggered **without**
`task_id` so no run binds, then walking the task by hand. Compiled, not driven.

### Verification

- The seven reproductions, green against unmodified code, before a line of the fix.
- `test_a_flow_names_what_it_cannot_staff.py` — 24 tests, green.
- Task 8.1's file list plus the three changed suite files and `test_reviewer_ladder.py` —
  **220 passed**.
- Task 8.2, `-k "flow or loop or review or transition or scheduler or claim"` —
  **669 passed, 11 skipped**.
- `ruff check src/ hub/ tests/` clean; `black --check --target-version py311` clean.
- `openspec validate a-review-a-flow-cannot-staff-is-named --strict` — valid.
- 8.5a's grep: the only surviving *"the one that completed"* strings are the default parameter, the
  attributed arm that passes it, and the test asserting it stays on that arm.
- The full hub suite was **not** run — that is the `SUITE` item, and running it beside anything else
  is what STATE.json forbids.

### Next

**`C-R1`.** Change B is implemented and committed; change A is implemented and undriven. The queue's
order puts C's three rounds before `DRIVE-1`, and `DRIVE-1` is the item that settles the judgement
half of both A and B — string assertions do not.

## Iteration 6 — 2026-08-31 01:24 to 01:3x (+01:00)

Branch `autonomous/2026-08-31-the-flow-lands-its-work` at `e4e7646`, tree clean, `git log` matching
STATE.json (iteration 5 done and released). Nothing to reconcile. Heartbeat claimed at 01:24.

### One item: `C-R1`

`approval-refuses-unaccepted-evidence` proposed — `proposal.md`, `design.md` (D1–D11), `tasks.md`
(49 items in 8 groups), and a `task-lifecycle-governance` delta of two ADDED requirements and one
MODIFIED. `openspec validate --strict` passes. The MODIFIED block was diffed against the live spec
to confirm only the intended sentences moved.

### The three pre-authorised defaults, checked against the code rather than adopted

**D1 — where the refusal lives — survives.** Both escape conditions were tested rather than
asserted. No cycle: `_check_mergeable` already imports `task_integration` locally, and
`task_integration` already imports `requirement_evidence` at module level, so the new query adds
*nothing* to `requirement_gate`'s imports. And `apply_transition` reaches every approval — verified
by enumerating all nine call sites (`tasks.py:1309`, `run_task_binding.py` ×4, `scheduler.py` ×2,
`agent_trigger.py:728`) and observing that **exactly one can pass `approved`**, and it is the one
route both planes share (`agent_actions.py:275-289` delegates to `update_task_for_actor`).

**D2 — what counts as "unaccepted" — is NARROWED, and this is round 1's finding.** The default said
"evidence rows for this task in review_state 'awaiting'". Taken literally that refuses approval on an
awaiting row whose footprint is `paths` or absent — evidence that could never have merged anything,
because `integration_targets` requires `kind == "git"` and a non-null `commit_sha`. The refusal
would be **unclearable**: accept it, and approval is refused again for the same reason, forever. And
it lands on exactly the research, docs and decision tasks the operator's own scoping constraint
exists to protect. Adopted predicate: awaiting **and naming a git commit** — refuse only where
accepting would change what integration merges.

**D3 — the mixed case — keeps ALLOW, but not for the reason given, and only conditionally.** The
default's reason ("integration will merge it and approval keeps its meaning") is incomplete:
`integration_targets` merges the newest *accepted* footprint per branch, so the newer unaccepted
commit is genuinely left outside the product. What makes ALLOW right is the **second half of this
change** — acceptance triggering integration makes the sequence converge. Stated as a coupling: were
half 2 dropped, the mixed case would have to become a refusal. Rounds 2 and 3 should check the
coupling rather than agree with the sentence.

The queue said D3 was "the one most likely to be wrong". It is not wrong; its *argument* was. That
is the failure mode round 3 exists for, arriving in round 1.

### New in round 1, absent from every default: D4

**The refusal must be silent wherever integration could not have been attempted anyway** — no main
branch, no repository, no branch by that name. `integrate_task` skips at `NO_MAIN_BRANCH`
(`task_transition_service.py:740-745`) before it ever asks for targets, so accepting the evidence in
such a project merges nothing; refusing would block **every task in an unconfigured project** behind
a remedy that changes nothing, and `task-lifecycle-governance` says in terms that *"a project that is
not a repository SHALL be no less approvable than before this capability existed."* `_check_mergeable`
already has exactly these four preconditions and already calls them "a reason to not know, never a
reason to refuse". The new check shares them by construction, not by copying.

### The half the refusal alone does not fix, and why it is in the same change

Both decision routes (`spec.py:864-891`, `agent_actions.py:1164-1201`) call
`requirement_evidence.decide`, commit, and return; `hub/hub/api/v1/spec.py` has zero references to
integration. So the sentence the refusal asks the reader to act on — *accept the evidence* — merges
nothing today. The product already solved this shape once, for a different cause:
`_integrate_what_was_waiting_for_a_branch` (`projects.py:533-566`) under the requirement *Naming the
main branch attempts the integrations that wanted one*. The delta adds the sibling, and `tasks.md`
group 4 is written against that function as its template, carrying its two restrictions (most recent
attempt; only that one reason) and adding two the sibling does not need (only on `accepted`; only
where the accepted evidence names a commit, or the retry records a second identical skip).

### Facts checked in the code, not carried from the exploration

- `GRANT_FIELDS` (`agents.py:1750`) and the PATCH loop at `:2007` are the single writer of
  `can_accept_evidence`, and a UI toggle exists (`AgentSettingsControls.tsx:448`). So D8's second
  remedy — "grant an agent" — is **reachable**, which is what the corpus's *"point at the remedy that
  works"* demands. The grant is ungranted by default, not ungrantable.
- `main.py:406-415` serialises `refusal.to_dict()` for every `TransitionRefusedError`, and the UI
  reads `message` off the structured detail (`ui/src/__tests__/taskIntegration.test.ts`). **No
  component change is needed**, so no `npm run build` and `hub/hub/static/ui` must not move.
- `approval_report` (`TaskResponse`) has **no UI consumer at all** — grepping `hub/ui/src` returns
  nothing. So D3's advisory reaches the API and the agent but not the operator's screen; named as a
  gap in design D3 and as `tasks.md` 8.3 rather than fixed here.
- `GateRefusal.detail()` has an early return for the `unmergeable`-only case. A third category
  appended carelessly is dropped from the sentence in precisely the case that matters most. Written
  as tripwire D11 and as task 3.3.

### Decisions recorded so they are not re-proposed

Refusing per branch rather than globally (D3); refusing on rejected evidence (D2); auto-accepting a
flow's own evidence; putting the trigger inside `requirement_evidence.decide` (it neither commits nor
knows about tasks, and integration must run after the commit); splitting `NOTHING_TO_MERGE` here
rather than in change D.

### Consequence stated plainly, because it is the decision and not a defect

In a default project the flow's review leg now **deadlocks**: the reviewer agent's approval is
refused, and its remedy — accept the evidence — is refused too, because no agent has the grant. That
is D-A verbatim. It also resolves the exploration's one genuine requirement-vs-requirement conflict
in favour of `requirement-traceability`'s *"acceptance SHALL fall to the operator… a supported way to
work, not a degraded one"* and against `loop-becomes-a-flow` design D11. D11 is an archived change's
design note; grepping `agent-flows` and `agent-loops` found no shipped requirement claiming an
unattended drain, so **no delta is owed to either spec**.

### Verification

- `openspec validate approval-refuses-unaccepted-evidence --strict` — valid.
- The MODIFIED requirement diffed line-by-line against the live spec: only the enumeration's new
  clause, its explanatory paragraph, and one added scenario.
- Every `file:line` in the proposal and design was read in the code this iteration. Two citations
  were wrong on first writing and were corrected (`agent_actions.py:315-319`,
  `task_transition_service.py:740-745`).
- No code changed, so no test run. That is `C-IMPL`'s.

### Next

**`C-R2`.** Round 2 re-derives C against the code independently. The two things round 1 most wants
checked: the D3 coupling above (is half 2 really what licenses the mixed case, and does it converge
in the multi-branch shape too?), and D6 — the link-based scope means awaiting evidence recorded by
*another* task against a *shared* requirement refuses this task's approval. Round 1's position is
that consistency with the merge beats a narrower refusal; round 2 should find out how common a
shared `TaskRequirementLink` actually is before that is taken as settled.

## Iteration 7 — 2026-08-31 01:39 to 01:5x (+01:00)

Branch `autonomous/2026-08-31-the-flow-lands-its-work` at `7c8c1ed`, tree clean, `git log` matching
STATE.json (iteration 6 done and released). Nothing to reconcile. Heartbeat claimed at 01:39.

### One item: `C-R2`

Round 2 of `approval-refuses-unaccepted-evidence`, a fresh comparison against the code. Round 1's
`file:line` claims were re-read rather than trusted; the ones that survive are not restated here.
Four defects found, three in the proposal and one in the product.

### The headline: D3's coupling was real, and half 2 as specified does not carry it

Round 1 named the mixed case's ALLOW as *conditional* on half 2 and asked rounds 2 and 3 to check
the coupling rather than agree with the sentence. Checked, it **fails** — and not in the
multi-branch shape the queue asked about. In every shape, including the simplest.

Half 2's predicate as round 1 wrote it (D7, `tasks.md` 4.1) was copied from
`tasks_skipped_for_want_of_a_main_branch`: approved tasks whose **most recent** `TaskIntegration` is
`SKIPPED` with `reason == NOTHING_TO_MERGE`. In the mixed case the most recent integration is not a
skip — approval merged the accepted target, so the newest row is `MERGED`, no reason filter can
match it, and the awaiting commit stays outside the product permanently while the task sits terminal
at `approved`.

| accepted | awaiting | approval merges | newest row | round 1's retry |
|---|---|---|---|---|
| A on `X` | — | nothing | `SKIPPED/NOTHING_TO_MERGE` | fires |
| A on `X` | B on `X` (newer) | A | `MERGED` | **does not fire** |
| A on `X` | B on `Y` | A | `MERGED` | **does not fire** |

Row 2 is the ordinary one and the worst: `integration_targets` returns the newest *accepted*
footprint per branch, so approval merges the older commit and strands the task's actual final work.

**Measured, not inferred.** `hub/tests/test_task_integration.py:377-379` is a shipped, passing
assertion that the newest row after such an approval reads `merged`. The suite already contains the
row that proves round 1's predicate cannot match.

**Why the borrowed proxy was wrong.** Naming a main branch changes the world in exactly one way, so
"most recent skip was `NO_MAIN_BRANCH`" *is* the proposition "this action created something
mergeable". Accepting evidence adds a **target**, and a task can acquire one whatever its last
attempt did. Round 1 inherited a proxy from a case where it happened to be exact.

**The repair, and its licence.** The trigger becomes *a commit that is not in the product* rather
than *a previous attempt's reason*: approved tasks linked to the evidence's requirement, excluding
any that already recorded a merge of that commit. Correctness does not depend on the predicate being
exact — only noise does — because `retry_integration` self-guards with `ALREADY_INTEGRATED` by
asking the repository rather than the attempt log, and says so in its own docstring
(`task_transition_service.py:699-702`). Multi-branch converges by construction; same-branch
converges because merging the newer commit carries the older one's ancestry.

D3's ALLOW is **right**, after the repair. Round 1 reached a correct answer through an argument that
did not hold — the failure mode round 3 exists for, arriving in round 2 for the second change
running. The cost is named rather than hidden: a task whose last attempt skipped `CHECKOUT_DIRTY` is
now attempted again on an acceptance and records a second dirty skip. Accepted, and the difference
is causal — the branch sibling fires on a settings save that says nothing about the checkout; this
fires on an acceptance that produced a commit nobody has merged.

### D6 measured: sharing a requirement is ordinary, so the refusal's *wording* changes

Round 1 asked how common a shared `TaskRequirementLink` is before its scope was taken as settled.
Three places say many-tasks-per-requirement is first-class: `tasks_for_requirement` returns a
**list** and `spec.py:767` serves it; `spec_tasks.materialise` scopes duplicate suppression to
*hand-made* tasks and states in a comment that a later decomposition entry naming an
already-declared requirement **is still created**; `absorb_free_text` from `tasks.py:795` lets any
agent's `create_task` name any identifier.

The link-based scope still stands — narrowing it to `RequirementEvidence.task_id` would make the
refusal disagree with the merge — but an operator refused over a row their own task never recorded
needs a route back to its cause. Each named row now carries **the task that recorded it**, and says
so where that is not the task being approved. `RequirementEvidence.task_id` is populated even when
an agent omits it (`requirement_evidence.py:125-129`), and is nullable, so absence is tolerated.

### Scenarios re-derived, not just the argument (B-IMPL's lesson)

- **Two WHENs were wider than their own requirement.** "Evidence naming no commit does not refuse"
  and "Rejected evidence does not refuse" both omitted *only* — as written, a task carrying awaiting
  evidence *and* a `paths` row would satisfy the scenario while the requirement demands a refusal.
  The MODIFIED requirement's own rejected-evidence scenario already said "only"; the ADDED ones now
  match it.
- **The "already there" scenario contradicted the new predicate.** Excluding tasks that already
  recorded a merge means no attempt and no row, while the scenario demanded an `ALREADY_INTEGRATED`
  record. Split into the two genuinely different cases: this task already merged it (no attempt), or
  it reached the branch some other way (attempt, and record the fact the reader does not otherwise
  have).
- One scenario added per new clause: the refusal saying whose evidence it is; the partial merge's
  leftover merging on acceptance; an attempt that cannot proceed recording why.

### The enumeration this change argues from was not actually closed

The proposal's *Why* argues that `NOTHING_TO_MERGE` "is not in that list". Diffed against the live
spec, the list also omits **an unresolvable working directory**, which `integrate_task` has always
skipped on (`task_transition_service.py:746-753`). Added to the MODIFIED requirement, and requirement
1's precondition enumeration corrected to match `_check_mergeable`'s four rather than three. An
argument from a list that is not closed is worth nothing.

### F152 — the product defect this round found

`main.py:406-415` sends `refusal.to_dict()` as the response `detail`, so an agent's `update_task`
receives a **dict**. `mcp_server._readable_detail` special-cases a `list` and falls through to
`str(detail)` for everything else — so every gate refusal has reached every agent since the gate
shipped as a Python dict repr, with the sentence buried in braces. That is exactly what that
function's docstring says it exists to prevent, for the other shape. The two evidence-decision
refusals D8 makes load-bearing (`acceptance_not_granted`, `self_acceptance`) arrive the same way.

Pre-existing, and in scope anyway: this change's whole value is a sentence an agent must act on, and
D8 makes that sentence the only thing between the agent and a deadlock it has to escalate. Three
stdlib-only lines, carried as `tasks.md` 6.3.

### Four facts checked so `C-IMPL` need not (design D13)

1. Two unrelated `Actor` types. Both decision routes hold `spec_lifecycle.Actor`;
   `retry_integration` takes `task_transitions.Actor`, which admits only `run`/`operator` and
   requires both `run_id` and `agent` for `run`. Task 4.6 is reachable, but only through an explicit
   conversion — passing the `spec_lifecycle` actor raises `ValueError`.
2. `task_integration.record` constrains nothing: no `CheckConstraint` on `actor_kind` in the model
   or any migration. The constraint that bites is (1).
3. `expire_on_commit=False` (`db/engine.py:40`), so committing again after the route's own commit
   cannot expire the objects it then serialises. The usual `MissingGreenlet` hazard is absent; do
   not add a defensive refresh.
4. Evidence the **operator** records is born `accepted` (`requirement_evidence.py:167`). So the
   refusal can only ever fire on agent-produced evidence, which is why F122 is flow-shaped and why
   D8's deadlock is exactly as narrow as D8 claims.

Also: `resolve_project_workspace` is not a pure read — it writes `directory_state` and
`last_seen_at` — which is a third reason for task 3.7's hoist beyond the two round 1 gave.

### Verification

- `openspec validate approval-refuses-unaccepted-evidence --strict` — valid, after each edit.
- The MODIFIED requirement re-diffed line-by-line against `openspec/specs/`: the intended sentence,
  the two new paragraphs, the one added scenario, nothing else.
- Every claim above was read in the code this iteration; four cited line ranges were wrong on first
  writing and were corrected against the files.
- No code changed, so no test run. That is `C-IMPL`'s.

### Next

**`C-R3`.** A second *independent* re-derivation, not a review of round 2. Round 2 most wants
attacked: (a) is "not already recorded as merged for that task" the right predicate, or does the
honest question belong to the repository — is this commit reachable from main — with the DB row only
a cheap pre-filter? (b) does the refusal belong at approval at all, given that `integration_targets`
is link-based and a shared requirement now couples two tasks' approvals? (c) F152's fix returns
`detail["message"]` — check nothing else depends on the dict repr reaching an agent, and that the
`list` branch still wins for validation errors. And re-derive the scenarios again: round 2 found two
whose WHEN was wider than the requirement and one that contradicted its own predicate.

## Iteration 8 — 2026-08-31 01:54 to 02:0x (+01:00)

Branch `autonomous/2026-08-31-the-flow-lands-its-work` at `0646ac8`, tree clean, `git log` matching
STATE.json (iteration 7 done and released, `fce2867` carrying round 2). Nothing to reconcile.
Heartbeat claimed at 01:54.

### One item: `C-R3`

Round 3 of `approval-refuses-unaccepted-evidence`. An independent re-derivation against the code, not
a review of round 2. Three defects found — two in the proposal's mechanism, one between the two
requirements this change ships together — and the three things round 2 asked to be attacked were each
answered with a measurement rather than a reading.

### The headline: the two SHALLs contradicted each other, and the reconciliation was in prose (D14)

Not in the code at all. Round 2 corrected the MODIFIED enumeration and added *"or when no accepted
evidence for the task names a commit to merge"* — unqualified, under a lead sentence reading *"The
transition into `approved` SHALL still succeed where integration cannot be attempted."* The ADDED
requirement refuses where the task has awaiting evidence naming a commit **and no accepted evidence
naming one**, which is a strict subset of that. So on the same facts, in a configured repository, one
SHALL said succeed and the other said refuse.

Round 2 knew the case had to be excluded — it wrote *"The last of them is narrower than it reads"* in
the paragraph beneath. **That is the defect.** A normative sentence is what a reader implements and
what `--strict` reads; a narrowing that lives only in surrounding prose is a note, not a rule. This
change exists because an enumeration did not say what the product did, and round 2 shipped a second
one.

Repaired in the sentence — *"…and no evidence awaiting review names one either"* — and checked
against all four worlds rather than asserted:

| the task's evidence | accepted names a commit | awaiting names a commit | in the skip list? |
|---|---|---|---|
| none at all | no | no | yes — MODIFIED |
| `paths` footprint only | no | no | yes — MODIFIED |
| rejected, named a commit | no | no | yes — MODIFIED |
| awaiting, names a commit | no | **yes** | no — ADDED refuses |

The two requirements now partition the world instead of overlapping it.

### D5 shared the wrong half of the query, and the change's own requirement catches it

Rounds 1 and 2 both wrote task 2.1 as *extract the body of `integration_targets`*. That body is two
things:

1. the **filter** — the join through `TaskRequirementLink` → `RequirementEvidence` →
   `EvidenceFootprint`, project scope, review state, `kind == "git"`, the `commit_sha` guard;
2. the **reduction** — `newest: Dict[Optional[str], Target]` keyed by branch, so only the newest
   footprint per branch survives (`task_integration.py:178-185`).

The reduction answers *what do I merge*. `awaiting_targets` is not deciding anything about merging —
it enumerates what has not been judged. Inheriting the reduction breaches this change's **own**
requirement 1: *"SHALL name each piece of evidence that is waiting rather than only how many there
are."* Two awaiting rows on one branch — one agent, one task, two commits, the ordinary shape of a
task worked in more than one sitting — collapse to one, and the refusal names one of the two. Round 2
made that naming load-bearing (each row must carry the task that recorded it); a reduction that
discards rows defeats exactly that.

**And nothing is lost by splitting.** D5's property is about *non-emptiness* — the refusal fires
precisely when acceptance would produce a target that is not there now — and a per-branch dedup of a
non-empty list is non-empty. The property survives whole; the reduction was never carrying any of it.
Tasks 2.1–2.3 rewritten, 2.5 added (both rows returned, one merged), 5.2a added (the sentence names
both commits).

### The identifier is not in `task_integration`'s reach

Task 2.3 asked `_targets` to return "its requirement identifier". `RequirementEvidence.requirement_id`
is the `spec_requirements.id` FK (`models.py:2334-2336`); the human identifier lives on
`SpecRequirement`, which `task_integration` does not import. Reaching it means adding a join to the
**merge** query for a field only the refusal's sentence uses — the drift D5 exists to prevent.
`requirement_gate` already imports `SpecRequirement` at module level, so the resolution belongs where
the sentence is composed. Tasks 2.3 and 3.4 corrected.

### The three questions round 2 posed, each answered by measurement

**(a) Is the DB row the right pre-filter, or should the repository be asked?** The licence is
`integrate()` reaching `ALREADY_INTEGRATED` before every skip that could pre-empt it. Read
(`task_integration.py:255-276`): the order is `branch_exists`, reachability, dirty, wrong-branch —
and it is not only a reading, `test_already_integrated_wins_over_a_dirty_checkout`
(`test_task_integration.py:566`) asserts that ordering and passes today. Only `branch_exists`
precedes, and it cannot mis-fire. Both error directions weighed: a false positive costs one honest
skip row (already accepted in D7); a false negative — a `MERGED` row for a commit main no longer
contains — costs a missed retry, with "Try again" and the next acceptance still available. Round 2's
answer stands, now for a measured reason.

**(b) Does the refusal belong at approval, given the coupling?** Yes, and **D6 overstated its own
cost**. The refusal needs `awaiting_targets` non-empty *and* `integration_targets` empty, both
link-based over the same requirements. So a sibling task is refused only when the shared requirement
carries **no accepted commit at all** — precisely when its own approval would merge nothing either.
The moment any accepted commit exists, D3's mixed-case ALLOW applies and the sibling's awaiting row
arrives as an advisory. The rule: *a task is never refused over a sibling's evidence while it has work
of its own to merge.* Materially smaller than round 2 recorded, and the reason the coupling is
tolerable rather than merely accepted.

**(c) F152's `detail["message"]`.** Clean, and three checks say so rather than one. The `list` branch
returns inside its own block (`mcp_server.py:119-134`) so a dict branch cannot pre-empt it. The
reachable producers are narrower than round 2 implied: `_hub_request` builds every URL as
`/api/v1/agent-actions{path}` (`mcp_server.py:147`), so `spec.py`'s two dozen dict details never
arrive — the set is six `HTTPException(detail={...})` sites in `agent_actions.py`, `main.py`'s
`TransitionRefusedError` handler (`to_dict()`, carries `message`) and its `TaskBindingError` handler
(a plain `str`). All six carry `message` as the whole sentence. And the one field that could be lost,
`field`, is **already inside the message**: `PayloadError.__init__` composes
`f"{field}: {message}"` (`spec_payload.py:53-55`) and `spec_service` builds its `SaveRefusedError`
from `str(exc)`. Task 6.3 stands as written; its guard is the right shape rather than a precaution.

### Two facts and a measurement added for `C-IMPL`

- **One footprint per evidence.** `UniqueConstraint("evidence_id")` (`models.py:2450-2453`), so
  tasks 4.1/4.2 speaking of *"this evidence's commit"* in the singular is well-defined rather than a
  simplification.
- **`evaluate`'s early return is a live trap.** `if not enforced: return refusal, ""` sits two
  statements after the `_check_mergeable` call (`requirement_gate.py:205-209`). A check placed after
  it is dead in every default project — the same trap that let F122 survive, one layer down. Task 3.6
  now says "beside" means *before* it.
- **Blast radius measured, not feared.** Only a test that configures a main branch on a real
  repository *and* leaves evidence awaiting can newly refuse. Grepping `main_branch` across
  `hub/tests/` gives ten files; five never reach `approved`. The candidates are five:
  `test_evidence_footprint_root`, `test_evidence_restamp`, `test_task_integration`,
  `test_task_integration_retry`, `test_task_release`. `test_flow_chain_end_to_end.py` is **not**
  among them, because it configures no main branch — which also means the flow suite cannot prove
  this change and only a drive can.

### Scenarios re-derived a third time

Round 2's two `only` repairs and its split of the "already there" case were re-read against the
predicate and are right. Requirement 1 enumerated four silent preconditions and scenarioed one, so a
**not-a-repository** scenario was added; and the D5 defect got the scenario that would have caught it
(*every waiting piece is named, not just one per branch*). The delta now carries 26 scenarios.

### Verification

- `openspec validate approval-refuses-unaccepted-evidence --strict` — valid, after each edit.
- The MODIFIED requirement re-diffed line-by-line against `openspec/specs/` **independently of round
  2**: the intended sentence, two paragraphs, one added scenario, nothing else.
- Every `file:line` cited above was opened this iteration; four ranges were wrong on first writing
  (`task_integration.py` dedup, `integrate()` preconditions, `mcp_server.py` list branch,
  `requirement_gate.py` early return) and were corrected against the files.
- The blast-radius list was corrected once: the first intersection named seven files, and counting
  `approved` occurrences per file showed two of them never reach it.
- No code changed, so no test run. That is `C-IMPL`'s.

### Next

**`C-IMPL`.** Three rounds are done and the change is implementable as written. Work group by group,
1 through 8; group 1's reproductions must pass against unmodified code before anything is fixed.
Round 3's rewrites are in tasks 2.1–2.3, 2.5, 3.4, 3.6 and 5.2a — read those before starting group 2,
because the naive "extract the body" is the version that breaches requirement 1. Expect the five
named test files to move, and nothing outside them; if a sixth starts refusing, that is a finding
about the predicate, not a test to edit.

---

## Iteration 9 — 2026-08-31 02:09 to 02:38 (+01:00) — `C-IMPL`: implement `approval-refuses-unaccepted-evidence`

**Item:** `C-IMPL`. **Status: done.** Groups 1 through 7 of `tasks.md` are implemented, verified and
pushed; group 8 is the "not in this change" list and stays open by design.

Five commits: `8028636` (group 1, reproductions), `d4c1467` (group 2, the query split), `2a53a27`
(groups 3–5 and 6.2/6.3, the refusal and the acceptance), `9ca6ab9` (6.1, the UI case), `8e21cbd`
(tasks.md).

### Group 1 — the reproductions passed against unmodified code first

Four tests in the new `hub/tests/test_approval_refuses_unaccepted_evidence.py`, green on untouched
code before a line was changed: awaiting evidence naming a commit **approves** and records
`NOTHING_TO_MERGE`; accepting it afterwards **merges nothing at all**; a `paths` footprint approves;
a task with no evidence approves. The fixture reads the rows back — awaiting, `git` footprint, the
named commit, the requirement link, the recording task — before asserting behaviour, which caught a
real fixture defect immediately: evidence recorded *before* the task exists on a run bound to nothing
lands with `task_id = NULL`. That is the product's real behaviour and the refusal has to tolerate it,
but it is not the ordinary shape, so the fixture now creates the task first and names it, and one
test deliberately keeps the null case.

### Group 2 — the split round 3 called for, and the test that proves it

`_targets(session, task, review_state)` holds the **filter**; `integration_targets` keeps the
per-branch reduction and `awaiting_targets` returns every waiting row. The empty-`commit_sha` guard
moved out of the reduction loop into the filter, where it belongs — left where it was,
`awaiting_targets` would have refused on a footprint the merge silently ignores.

`test_two_awaiting_commits_on_one_branch_are_both_returned` is the regression round 3 asked for and
it discriminates: two awaiting rows on one branch return **two**, the same two accepted return
**one**. `Target` widened with `evidence_id`, `requirement_id` and `task_id`; the human identifier is
resolved in `requirement_gate`, which already imports `SpecRequirement`.

### Group 3 — three tripwires closed by construction rather than by care

- `unaccepted` is in `refuses` **and** in `to_dict()`.
- `detail()` is now a composition of one sentence per category. The early return it replaced
  (`if self.unmergeable and not (blocking or diagnostics)`) would have dropped the new sentence in
  precisely the case that matters most — an otherwise-clean task. The text for both pre-existing
  shapes is byte-identical; `_unverified_detail()` and `_merge_detail()` return `""` when they have
  nothing to say and the join does the rest.
- `_check_unaccepted` sits **above** `evaluate`'s `if not enforced: return`, beside
  `_check_mergeable`. Proven by `test_the_refusal_fires_at_sketch_rigor`, which asserts the
  document's rigor is a sketch before asserting the refusal.

D4's preconditions are now shared **by construction**: one `_merge_situation` resolves project, main
branch, workspace, `is_repository`, `branch_exists` and the accepted targets, and both checks take
it. So the refusal cannot fire where the merge would have been skipped anyway, and
`resolve_project_workspace` — which writes `directory_state` and `last_seen_at` — runs once per
approval instead of twice.

The mixed case populates `advisory`, carried out beside `reported` on `reported_advisories`. Each
entry now carries a `kind`, stamped on the reported copy only so `blocking`'s shape is untouched.

### Group 4 — the second half, on the predicate round 2 rewrote

`tasks_awaiting_this_commit` excludes only *this task's own recorded merge of this commit*, asked of
the database as a pre-filter with the repository as the authority.
`integrate_what_was_waiting_for_this_evidence` is wrapped and called after each route's commit, on
both planes, with the actor that actually decided — `run_actor(...)` on the agent route,
`operator()` on the operator's. `test_a_granted_agent_accepting_merges_the_work_too` asserts the
integration row reads `actor_kind: run, actor: reviewer`, not the operator.

The pair that is D3's whole argument passes in both shapes: accepted A merged at approval with
awaiting B reported, then B merged when accepted — B on A's branch, and B on a second branch.

### Group 6 — F152 fixed and asserted, and the UI needed no component

`_readable_detail` returns `message` where a dict carries a non-empty one. Two tests: a real
`to_dict()` payload reduces to exactly `refusal.detail()` with no brace or `'code'` in it, and a
plain-string detail plus a messageless dict keep today's behaviour verbatim.
`test_the_agent_plane_sees_the_refusal` drives the agent PATCH and reads `gate_unsatisfied` off it.
The UI test gained a case; no component moved, so `hub/hub/static/ui` did not.

### One existing test moved, and it was inside the predicted five

Round 3 named five candidate files. Measured: **exactly one test** newly refused,
`test_task_integration.py::test_evidence_awaiting_review_merges_nothing` — which was F122's own shape
asserted as intended behaviour ("approval succeeds, records `NOTHING_TO_MERGE`"). Its real property,
nothing reaching `main` on unreviewed evidence, is kept verbatim and now stated more strongly as a
refusal. The reason is written into its docstring, as 7.4 requires.

### Two small inaccuracies in the change, recorded rather than smoothed over

- **`tasks.md` 7.2 names `hub/tests/test_spec_evidence.py`, which does not exist.** Written from
  memory across three rounds and never checked, because no round ran a command. Substituted
  `test_requirement_evidence.py`, `test_agent_evidence_grant.py` and `test_agent_evidence_plane.py`.
  Small, and exactly the class of thing only implementation finds.
- **Task 6.2 could not be written as stated without first walking the task to `under_review`.** The
  agent plane returned a *string* detail — `"Cannot move a task from 'pending' to 'approved'"` — and
  the assertion `detail["code"]` raised `TypeError`. The test now drives the task to `under_review`
  as the operator and then approves as the agent. Worth noting because a test that had asserted only
  "409" would have passed on the wrong refusal.

### Verification

- `test_approval_refuses_unaccepted_evidence.py` — 31 passed.
- The blast-radius candidates plus the evidence plane —
  `test_evidence_footprint_root`, `test_evidence_restamp`, `test_task_release`,
  `test_task_transitions`, `test_task_transition_service`, `test_requirement_evidence`,
  `test_agent_evidence_grant`, `test_agent_evidence_plane` — 200 passed.
- 7.3's selection, `-k "integration or evidence or approve or approval or gate"` — **418 passed, 3
  skipped**.
- The flow, scheduler, handover and divergence suites — **245 passed**, unchanged. Round 3 predicted
  this exactly, and it is the same fact as *only a drive can prove this change*: `test_flow_chain_
  end_to_end.py` configures no main branch, so the refusal's preconditions are never met there.
- `hub/ui`: `npm run lint` clean, `vitest src/__tests__/taskIntegration.test.ts` 5 passed.
- `ruff check src/ hub/ tests/` and `black --check --target-version py311 src/ hub/hub/ hub/tests/
  tests/` — clean over the paths CI covers.
- `openspec validate approval-refuses-unaccepted-evidence --strict` — valid.

### Next

**`DRIVE-1`** — the point of the whole run. Restart 8011 from this branch and confirm it serves this
code before drawing any conclusion. Fresh project, fresh document, two independent tasks, Haiku
agents. Expect C's refusal to stall the flow until evidence is accepted; accept it as the operator
and record whether the product told you that was what to do. Three things this iteration leaves for
the drive to answer, because no test can: whether the refusal's sentence actually reaches the agent
in a live turn rather than in a unit test of `_readable_detail`; whether the advisory in the mixed
case reaches the operator's screen at all (`approval_report` has no UI consumer — tasks.md 8.3);
and whether the stall is legible on the board or merely correct in the API.
