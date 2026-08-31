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

## Iteration 10 — 2026-08-31 02:39 to 03:1x (+01:00) — `DRIVE-1`: **the flow lands its work**

**Item:** `DRIVE-1`. **Status: done, and it passed.** Both tasks reached `approved` and both commits
are on the project's main branch. It cost two severity-A findings to get there and neither is small,
but the headline is the one this whole run was armed to produce: **the loop closes.**

### The Hub on 8011 was serving 2026-08-30 code, and the restart is how that was caught

PID 25908, started **2026-08-30 11:01**, command line
`python -m uvicorn hub.main:app --port 8011 --host 127.0.0.1` with no `DATABASE_URL`. Killed and
restarted from `hub/` with the beta-profile URL at **02:40**; the new process ran
`0098 -> 0099, a question records the deadline of the wait it started` on startup, which proves the
old one predated this branch's migrations. Confirmed afterwards that no `.py` under `hub/hub` or
`src` is newer than the process start time. The state file's warning was right and would have cost
the whole drive: an 8011 on 0098 would have shown the pre-C behaviour and read as a regression.

Also measured: the beta profile is the only database written since 2026-08-30, so
`~/.agentweave/hub/profiles/beta/agentweave.db` is still the live one, as CLAUDE.md's corrected row
says. The `setup/token` key that `aw.py` defaults to answered `401` against the *old* process and
`200` against the new one — worth knowing, because a `401` from a drive harness reads as a bad key
and was actually a stale server.

### The fixture

New project **`drive-2026-08-31` = `proj-3175994d03ce`** at `C:\Users\huida\Documents\drive-2026-08-31`
— a fresh `git init -b master` with one commit (`calc.py` with `add`), plus a `.gitignore` for
`.agentweave/` (the first preflight caught the untracked marker directory immediately, which is the
check earning its keep). `POST /projects/open` **adopted `master` as the main branch by itself** —
`_adopt_detected_main_branch` driven, no settings round trip. Runner `Haiku (cheap)` =
`claude-haiku-4-5-20251001`, agents `alpha` and `beta` bound to it. Neither forbidden project touched.

### The harness: `scripts/drive/t_drive1_flow_lands.py`, two lanes on one document

Two independent tasks on one `change-spec`, and the two lanes are the point. `modulo` is the CLEAN
lane — the operator accepts its evidence before the review firing. `power` is the STALL lane — its
evidence is left `awaiting` so change C's refusal has something to refuse. Ancestry is checked with
`git merge-base --is-ancestor` against the repository, never by reading the Hub's own
`TaskIntegration` rows: the run's purpose is written as *did the work reach the main branch*, and
taking the Hub's word for that would answer a different question. `agent_output_text` reads
`payload` as well as `content`, because a tool **result** — where a refusal lands — is carried in
`payload`, and reading only `content` would have answered "the agent never saw it" for a refusal
sitting one field over.

**14 of 20 checks held on the first pass**, and every one that did not traces to a single event: the
clean lane's reviewer never recorded its verdict.

### What held — three changes driven, not asserted

- **A driven.** Both tasks went `pending -> in_progress -> completed` inside firing 1, ~24 seconds
  in, with **no operator transition at all**. F140 was exactly this not happening.
- **A's evidence half driven.** Both agents recorded evidence naming a commit without the drive
  asking; `_briefing_evidence_lines` is the only place they were told.
- **B driven.** Firing 2 staffed both reviews and neither reviewer was its author — `alpha -> beta`
  on power, `beta -> alpha` on modulo.
- **C driven.** The `awaiting` lane was refused at `approved` in a live agent turn; the accepted lane
  was not.
- **F152 driven.** `beta` read the refusal as a sentence — no brace, no `'code':` — and *stopped*,
  thinking *"I see. The task can't be approved yet because there's evidence"*. The `ACCEPT_OR_GRANT`
  clause's own comment claims naming an untakeable remedy is what stops an agent retrying. Measured:
  it does. That contrast becomes the sharpest thing in the drive once F155 shows the same model
  retrying a *takeable* remedy five times.

### `master` afterwards

```
6b938d7 Integrate approved work db8fc6a7c47e     <- task-5ae53e9b339c ("modulo")
961f605 Integrate approved work 4e722fa04088     <- task-7f11b87f3d36 ("power")
```

with both functions in `drive1_024543.py` and both shas ancestors of `master`.

### F154 (A) — a review that ends without a verdict wedges the task forever, and the flow says "nothing is wrong"

`alpha` reviewed `modulo`, concluded in its own transcript that the work was correct, and its turn
ended without `update_task`. From then on every firing answered **409 "Every task on this loop's
queue is already being worked. Nothing was started, and nothing is wrong — the next firing picks up
whatever finishes."** — with both agents `idle`, no run live, `firing_active: false`,
`stall_reason: null`, and `agent_capacity: "held"` on an idle agent. Fired three times over several
minutes; identical every time.

`decide_firing`'s `WITH_REVIEWER` branch records `in_flight` on the strength of `task.assignee`
alone. Its own comment claims this is what makes a verdictless review *visible to an operator*; the
row is visible and what is said about it is false. The distinction is already computed —
`held = tasks_held_by_a_running_turn(...)` sits in scope and the ordinary-work arm next door uses it
— and this branch never looks at it. That is F142 one door over, breaching the same requirement B
was just fixed against, and worse in kind: the operator is not uninformed, they are told the flow is
healthy.

The *cause* here was the spawned Claude harness presenting the MCP tools as **deferred**: `alpha`
called `ToolSearch` eleven times, each returning "tool completed", and never emitted the
`update_task` call it kept announcing. The other three turns in the same drive called their tools
first try, so it is intermittent, not structural, and it is not the Hub's to fix. **What the Hub owns
is what happens afterwards**, and afterwards is F154.

### F155 (A) — "Resolve the conflict on the branch, then approve" cannot be followed, by anybody

Re-triggered on `modulo` after `power` had already landed on `master`, `alpha` called `update_task`
at once — so the ToolSearch loop really was intermittent — and got a **different** refusal:
*"This task's work does not merge cleanly into master: drive1_024543.py. Resolve the conflict on the
branch, then approve."* Both tasks created the same file, so the add/add conflict was inevitable the
moment the first one merged.

The agent then did **exactly what it says**: merged `master` in, resolved by hand keeping both
functions, committed `17aac8e`, verified with `git diff master...HEAD`, approved — **identical
refusal**. Read the file, the log, the spec document, approved again — **identical refusal**. Then
`git reset --hard 5f07663` and `git rebase master`, resolving the same conflict a second time.

`_check_mergeable` never looks at the branch. It asks
`would_conflict(root, target.commit_sha, main_branch)` for each **commit named by accepted evidence**
— `git merge-tree --write-tree master <that exact commit>`. Resolving on the branch makes a new
commit no evidence names, so the answer cannot change. The operator has no route either: approving
by hand returned the same 409, naming `source_branch: agentweave/task/task-5ae53e9b339c` for a commit
that the agent's rebase had just detached from that branch.

**What actually clears it, and the product never says so:** record *fresh evidence naming the merged
commit*. Driven — `alpha` recorded `ev-a2a689ef080d` with footprint `db8fc6a`,
`integration_targets`' per-branch reduction picked the newer row, the operator accepted it, and the
approval went through and merged immediately (`tint-e097e09de620`, outcome `merged`). One tool call
that neither the refusal, nor the drawer, nor the briefing mentions.

Two separable defects: the sentence points at the wrong place (it carries `commit_sha` in its
structured half and drops it from the prose), and **a product instruction invited `git reset --hard`
on a branch holding the only copy of an agent's work.** It came out fine. The next one may not.

This fires only where a second task has already landed and touched the same paths — which is to say
exactly in the multi-task flows the feature exists for, and never in a single-task fixture. That is
why three spec rounds and 3,555 unit tests did not have it.

### F156 (B) — `integration-preview` says `will_merge: true` for a task approval refuses

Same task, same minute: the drawer meant to state what approving will do returned
`{"will_merge": true, "reason": ""}` for the commit the gate was refusing. `will_merge` is
`bool(main_branch and targets)`. The handler's docstring is candid that it runs no conflict probe on
purpose, and that reasoning is sound — the **word** is not. Cheap repair is vocabulary
(`will_attempt_merge`), not a probe.

### tasks.md 8.3 confirmed live, and it is quieter than expected

`approval_report` has no UI consumer, so the mixed case's advisory reaches the API and the agent and
never a screen. Not separately reproduced here because this drive never produced a mixed case: the
stall lane held exactly one piece of evidence, so the refusal fired rather than the advisory. The
grep result stands and 8.3 stays open.

### Fixture left clean

Job disabled and archived (`jobs: []`), both agents `idle`, both tasks `approved`, no question
pending, every queue entry `delivered`, no permission card, no rebase in progress, fixture repo tree
clean. The two review worktrees remain detached under `.agentweave/reviews/`, which is their ordinary
resting state. `spec/` added to the fixture's `.gitignore` so a re-drive's preflight passes.

### Next

**`D-R1`** — round 1 of `a-loop-declares-whether-it-needs-evidence` (breaks 1 and 7; F124), the last
unproposed change and the one carrying operator decision D-B. Before it: F154 and F155 are both
severity A, both found by driving, and both sit squarely in this run's stated purpose — *fix the flow
end to end until a flow's approved work actually reaches the main branch*. F155 in particular is a
product instruction that cannot be followed and that invited a destructive git command, and it is
reachable only from a multi-task flow, which is the shape D is about. Whether D still comes first, or
whether F155 earns its own spec loop ahead of it, is queued for the operator as **D19**.

---

## Iteration 11 — 2026-08-31 03:04 to 03:2x (+01:00) — `D-R1`: propose `a-loop-declares-whether-it-needs-evidence`

Branch and `git log` matched STATE.json at start (`c326743`, clean tree). Nothing to reconcile.

**D19 was honoured, and this is the sentence it asked for.** F155 is a severity-A instruction that
cannot be followed and that invited `git reset --hard` on a branch holding the only copy of an
agent's work, it sits inside this run's stated purpose, and **it was passed over.** The queue kept
its order, per D19's pre-authorised default: reordering on the strength of a finding made forty
minutes earlier is the move the round discipline exists to prevent. F155 stays filed with a full
reproduction and the remedy that actually works.

### What round 1 produced

`openspec/changes/a-loop-declares-whether-it-needs-evidence/` — proposal, design, tasks, and spec
deltas against **two** capabilities. `openspec validate --all --strict`: 48 passed, 0 failed.

The change covers breaks 1 and 7 and carries operator decision D-B with its two pre-authorised
follow-ons (D4, the default; D5, what is merged).

**Break 1, restated more strongly than F124 did.** F124 said loop tasks *happen to* lack requirement
links. `create_loop` refuses `spec_document_id` outright, so a loop mints no requirements, so
`record_evidence` 404s, so `integration_targets` is empty, so the only `git merge` into a main branch
in the tree has no input — **for every loop task that has ever existed.** Not a gap; a definition.

**Break 7, and it is worse than "a useless button".** `TaskIntegrationNote.tsx:87` renders "Try
again" for every non-`merged` outcome whose reason does not contain `no main branch set`. The default
is *offer it*, decided by string-matching prose in the browser, so the two genuinely terminal reasons
— nothing to merge, already integrated — are exactly the ones that get a button. This change adds a
*new* terminal reason, so shipping break 1's fix without break 7's would put a second unclearable
button on screen.

### The five decisions round 1 had to take, and the two it should be attacked on

- **D1** — D5 made the per-task-branch guarantee a *condition* of relying on it, since
  `work-is-isolated-per-task` was written about flows. **Verified, not assumed:**
  `resolve_turn_workspace_inputs` and `takes_task_workspace` key on `Task.workspace_scheme` and a
  writing agent, and neither mentions a loop, a flow or a document. Three shapes still reach approval
  with no task branch (grandfathered by `0095`, read-only agent, non-repository) and each gets a
  stated skip rather than a fallback — **falling back to the agent branch is F58 exactly.**
- **D2** — one nullable Boolean, NULL meaning "the current default", on `Loop.control`'s own recorded
  reasoning nine columns up. Rejected: an enum naming the merge source; deriving it from
  `spec_document_id is None`, which is the implicit-requirements answer D-B already rejected.
- **D3** — declared at creation, refused on edit. The pending-edit machinery cannot help: its whole
  rationale is that *a firing keeps the definition it was briefed with*, and this field is never read
  by a firing — it is read at approval, per task. A staged edit would land on whichever task was
  approved next, which is the one property staging exists to prevent.
- **D5** — a second resolver taking a repository root, `merge_targets(session, task, root)`;
  `integration_targets` is left untouched and pure. Its four call sites were **grepped, not
  recalled**: three move, `_prerequisite_commits` stays on accepted evidence.
- **D7** — retryability is classified at the source and rides on the integration row; the UI reads a
  field instead of matching a sentence. **The default inverts:** an unclassified reason is not
  retryable. The retry *route* is deliberately not narrowed — the shipped requirement says retrying
  is available to operators and agents, and this change constrains what is **offered**.

Two things round 1 wrote down for later rounds to hit rather than smoothing over:

1. **The default.** D4's rationale is that no loop merges anything today, so evidence-free regresses
   nothing. That is true of history and silent about tomorrow: from this change on, approving any
   loop task in a project with a configured main branch writes to that branch — including a loop that
   only ever wrote notes, because `snapshot_worktree` commits whatever the turn left dirty. Recorded
   as design.md's open question.
2. **`integration-preview` overriding its own docstring.** It says *"no git subprocess, no conflict
   probe"*. Round 1 keeps the second and breaks the first, because a drawer that reports no target
   for the one task shape whose target is not in the database would say "nothing will merge" beside
   an approve button that merges. Stated as an override rather than quietly done.

An inconsistency round 1 caught in itself: D5's first draft said the preview *keeps* asking
`integration_targets` and then, one bullet later, that it gains the branch-tip target. Both cannot be
true. Rewritten.

### F157 filed (C) — found by reading, not by driving

`PATCH /jobs/{id}` refuses a loop field on a job that is not a loop, naming the remedy
(`jobs.py:856-876`). `POST /jobs` does not: `create_job` reads `spec_document_id` only inside
`if _loop_opts_in(...)`, so a create supplying it without a stop condition returns `201` and silently
drops it. Two write paths, one field, opposite answers, and the silent one is what a caller reaches
first. Filed rather than fixed — extending the refusal is a behaviour change on a shipped route. It
matters here because this change deliberately does **not** inherit the precedent for its own field
(design D4): a dropped `spec_document_id` shows up as a loop that never fills, while a dropped
"does this loop's work need evidence" is invisible until an approval writes, or fails to write, to
the operator's main branch.

### Verification

A spec round has no product to drive, so what was verifiable was verified:

- `openspec validate --all --strict` → 48 passed, 0 failed.
- **Every file and line the artefacts cite was opened or grepped, not recalled.** Iteration 9's
  lesson (`tasks.md` 7.2 named a test file that does not exist, copied through three rounds because
  no round ran a command) was applied literally: `test_task_integration.py`,
  `test_task_integration_retry.py`, `test_jobs_crud.py`, `test_migrations.py`,
  `test_project_persistence.py`, `test_task_release.py`, `test_tool_surface_matches_server.py`,
  `test_mcp_tool_schemas.py` and `taskIntegrationRetry.test.tsx` all exist; the fixture helpers named
  in task 1.2 were read out of the file.
- Three cited line ranges were **wrong and were corrected** after checking: the `git merge` is at
  `task_integration.py:300-372` (the exploration's `:289-300` predates change C's insertions),
  `Loop.control` is `models.py:1405-1412`, and `test_release_happens_after_integration` lives in
  `hub/tests/test_task_release.py:278`.
- No product code was touched, so no suite was run. Migration head is still `0099`; this change plans
  `0100`.

### Next

**`D-R2`** — round 2 of `a-loop-declares-whether-it-needs-evidence`. A fresh comparison against the
code, not a re-read of this reasoning. The two places round 1 is most likely to be wrong are named
above and in design.md's open question; the third is the prerequisite chain in D5's last bullet,
which rests on three shipped mechanisms interacting rather than on one line of code.

---

## Iteration 12 — 2026-08-31 03:49 to 04:0x (+01:00) — `D-R2`: round 2 of `a-loop-declares-whether-it-needs-evidence`

Branch and `git log` matched STATE.json at start (`773a8d6`, tree dirty only in `STATE.json`:
iteration 11's heartbeat plus mojibake it had reintroduced into `carried_open_questions` — the em
dashes were repaired in place, not left). Nothing to reconcile.

### The severity-A defect round 2 found, and it is the shape this round exists for

**`Loop` is the row for a flow as well as a loop.** `create_flow`'s own docstring says it — *"a flow
differs from a loop in what it does with its queue, not in what it is"* — and `spec_document_id` is
the only thing separating them (`models.py:1377-1388`; `scheduler.py:2043` already computes
`is_flow=bool(loop.spec_document_id)`). Round 1 put `work_needs_evidence` on `Loop`, resolved NULL
with `False if ... is None else ...` (design D2), and then — correctly, in task 7.5 — decided
`create_flow` does **not** take the parameter. Those three decisions are individually right and
together they say:

```
every flow's row is NULL, forever
  -> the default resolves to "needs no evidence"
  -> merge_targets returns the branch tip for every flow task
  -> requirement_gate._check_unaccepted's refusal arm is `if situation.accepted: advisory`
     (requirement_gate.py:351-354), and now always has a target
  -> approval-refuses-unaccepted-evidence, implemented in iteration 9 of THIS run, degrades to an
     advisory for every flow task in the product, and F58's "merge the commit evidence names" with it
```

Round 1 was not careless anywhere; it never asked what its own field means on the other kind of row
that carries it. **An argument can be wrong while everything it argues about is right** — the exact
failure the third round was added for, caught by the second.

**The repair** is design D10: the question is *does evidence govern this task's merge*, and it has
three answers — no loop → evidence governs; a declaration was made → the operator wins; NULL →
`loop.spec_document_id is not None`. That is **not** D2's rejected "derive it from
`spec_document_id`": the field still exists and still wins where it was set, and what is derived is
only the *default*, which D2 already insisted must be resolved at the point of use. Both spec deltas
now state the default in words, because "the product's current default" is not something a reader can
check, and both gained a flow scenario. `openspec validate --all --strict`: 48 passed, 0 failed.

Task 1.7 gained the guard that would have caught it — a flow task with accepted evidence and a
*different* commit at its branch tip, written against today's code where it passes, failing the
moment 4.3 is implemented with a flat default.

### The open question, answered — the default stands, and round 1's scope made it a defect

Five mechanisms already stand between the default and a surprise, each read rather than assumed:
`_check_mergeable` conflict-tests first; `merge --no-ff` cannot rewrite history and `rode_along`
reports the ancestry; `integrate` refuses unless the primary checkout is **on the main branch and
clean** (`task_integration.py:329-335`), so the write lands in a checkout the operator is looking at;
the preview states it before; `TaskIntegrationNote` states it after.

Against that, one measured fact settles it: **`JobForm.tsx` is the operator's loop-creation surface**
— loop toggle at `:90-99`, fields at `:300-330` — and round 1 gave the declaration to `create_loop`
(an agent tool) and `POST /jobs` (an API) and to no screen at all. An agent could declare; the
operator whose main branch is written could not, and was never told the default. So the answer is not
a different default: it is task **6.8**, the declaration on the form that creates loops, with one
sentence saying what it decides. Not optional.

### Three more corrections, all from reading the code

- **D5's preview bullet.** Round 1 accounted for the `rev-parse` and not for the root:
  `resolve_project_workspace` writes `project.directory_state` and `project.last_seen_at` and
  validates the on-disk marker (`project_workspace.py:198-234`), so the `GET` acquires a write.
  **Checked before calling it a defect — and it is not one:** `GET /projects` already does exactly
  this per project through `_refresh_project_observation` (`projects.py:268-276`). Kept, with the
  cost stated and two conditions: an unresolvable workspace answers "no target, here is why" rather
  than 500, and no workspace is resolved at all where evidence governs the task.
- **D5's prerequisite chain.** Every link read. The chain holds on the loop-dispatched path
  (`candidate_is_startable` gates selection; `_integration_base` returns `Project.main_branch`;
  `ensure_task_worktree` cuts from it) and round 1 stated as unconditional something that has three
  conditions. Two are pre-existing and are now **F158**; the third — that the main-branch merge
  actually happened — is *created by this change*, because an evidence-free loop task has no second
  route home. Round 2 recommends extending `_prerequisite_commits` and **deliberately does not take
  it**; it is left as the one open decision for round 3.
- **D7's classification.** "A single mapping" cannot be keyed on the reason: `CHECKOUT_ELSEWHERE`
  and `ALREADY_INTEGRATED` are `.format()` templates (`:67-74`, applied at `:326`/`:334`) and a
  `FAILED` row carries git's stderr (`:365`). Three of nine rows would fall into "unclassified",
  which under this design's *inverted* default means **no button on a dirty checkout and none on a
  failed merge** — the two most retryable outcomes there are, i.e. the fixed defect reproduced one
  layer down. So `FAILED` is answered on the outcome, the templates on their stems, and task 6.2a
  adds a `SKIP_REASONS` tuple with a **totality test** so a tenth reason cannot be added without a
  classification. A `reason_code` column was considered and rejected in writing. The spec's
  "carried with the record of the attempt" was reworded so it does not promise a column nothing
  builds.

Also recorded in Impact rather than closed: `TaskCreate.loop_id` is caller-supplied and
agent-reachable (`tasks.py:771`, `schemas/tasks.py:63`) and `TaskUpdate.loop_id` is write-once rather
than immutable, so a task can be attached to an evidence-free loop after it exists, changing what
approval writes. Approval stays gated and conflict-tested, so it widens what can be *offered*.

### F158 filed (B) — and it is a product defect, not a proposal one

A task branch is cut at **dispatch** (`pending -> assigned`) and prerequisites are merged **only at
creation** (`worktrees.py:447-449`, `:481-487`), while the dependency gate fires one edge later, on
`-> in_progress`. `candidate_is_startable` closes this on the scheduler's path;
**`agent_trigger` consults no dependency gate at all** (grepped: no call site). So an operator
triggering an agent on a task whose prerequisite is unapproved cuts its branch permanently without
that work, and `POST /tasks/{id}/dependencies` can add an edge after a branch exists. The evidence
route has this today; the evidence-free route makes it worse because the main branch is its only
route home and that merge is best-effort.

### Verification

- `openspec validate --all --strict` → **48 passed, 0 failed**, after every edit.
- **Every citation added this round was opened or grepped.** Confirmed live: migration head is
  `0099` (`test_migrations.py:40`, `test_project_persistence.py:227`);
  `test_migration_0098_is_guarded_when_the_queue_table_does_not_exist` at `test_migrations.py:3062`;
  all nine fixtures in `test_task_integration.py` (`make_repo`:47 … `integrations`:178);
  `test_a_conflicting_branch_refuses_approval` at `:389`; `test_release_happens_after_integration` at
  `test_task_release.py:278`; `_loop_opts_in` at `jobs.py:103-105`; `integration_targets` at
  `task_transition_service.py:773` with the ordering comment at `:606-615`.
- **One citation corrected:** the `create_loop` tool-inventory prose is `agents.py:965-971`, not
  `:960-975`.
- No product code touched. No suite run, and none was warranted.

### Next

**`D-R3`** — the second *independent* re-derivation. It has one decision waiting rather than a blank
page: whether `_prerequisite_commits` moves to `merge_targets`' question for `approved`
prerequisites (F158's repair, and the third condition D5 now admits to). Its own brief still stands —
re-derive whether the declaration belongs on the `Loop` at all, given D10 has now proved that row is
two things wearing one name.

## Iteration 13 — 2026-08-31 04:04 to 04:2x (+01:00) — `D-R3`: round 3 of `a-loop-declares-whether-it-needs-evidence`

Round 3 re-derived the proposal against the code independently of round 2 — not a review of it.
**It found a second severity-A defect, and it is decision D4's own `raise_it_if` condition firing.**
It also took the decision round 2 left open, found that decision is not a decision at all (a shipped
requirement already mandates it), and corrected one claim round 2 carried from a comment rather than
from the route.

### D11 — a loop task that carries requirement links merges TODAY, so the kind-aware default is still a regression

`decisions_for_user` D4 says in as many words: *raise it if "round 2 or 3 finds an existing loop path
that DOES merge today, which would make this a behaviour change rather than a new capability."*
There is one. Every step opened, not reasoned about:

```
create_task(loop_id=<documentless loop>, requirement_ids=["FR-8"], spec_document="x.md")
  tasks.py:748-753   spec_document_id resolved from the requirements' agreed document
  tasks.py:771       loop_id stored — _authorize_loop_task_creation gates WHO, never WHAT
  tasks.py:790       link(...)  ->  TaskRequirementLink rows exist
record_evidence("FR-8", commit=…)
  agent_actions.py:1031-1044   resolves against the PROJECT's requirement index. Nothing
                               consults the task's loop. It does NOT 404.
decide_evidence(accepted)
  _targets joins TaskRequirementLink -> integration_targets NON-EMPTY -> integrate_task MERGES.
```

The proposal's Why says *"A loop has no requirements to link"* — true of the tasks a loop's
**document** would mint, of which there are none, and false of the tasks a caller creates with
`requirement_ids`, which `TaskCreate` supports on purpose and which D10 itself acknowledges exist.
D4's rationale — *"a loop today can never merge anything at all, so defaulting to evidence-free …
regresses nothing"* — has a counterexample, and rounds 1 and 2 turn that counterexample into silent
behaviour change.

**And it is worse than substituting one commit for another.** `_targets`' docstring states the
property and the join at `task_integration.py:182-186` makes it true: *"evidence recorded by another
task against a shared requirement is in scope here… it is this task's integration that would merge
its commit."* A per-task branch tip **cannot** carry another task's branch's work — D1's isolation
guarantee, working against us — so that commit is not merged elsewhere, it is not merged at all,
while the integration record says `merged`. Silent, and in the direction that loses work. Plus
`approval-refuses-unaccepted-evidence` degrades for the same task by the same mechanism D10
described for flows.

**The repair is one more arm**, and the resolver now has five, in order: no loop → evidence;
the loop row does not resolve → evidence; the field is set → **the operator wins**;
`spec_document_id is not None` → evidence (a flow, round 2's D10); otherwise
`task_has_requirement_links(session, task)`. The branch tip is the default for exactly one
population — a task on a documentless loop with **no requirement link of any kind** — which is the
set for which `integration_targets` is structurally empty forever, and the set the proposal's Why
actually describes.

**Why neither arm alone will do**, and this is the part only a fresh read finds:

- **Not the link test alone.** `spec_tasks.materialise` links requirements only under
  `if requirements:` (`spec_tasks.py:221-222`) — a flow task whose declared identifiers did not
  resolve has **no** links, so a link-only default would start merging its branch tip. D10's defect,
  re-entered through the door D10 closed.
- **Not `spec_document_id` alone (D10 as written).** `Task.spec_document_id` is set only where the
  named requirements agree on **one** document (`tasks.py:752-753`, a singleton set), and
  `PATCH /tasks/{id}` adds links without ever assigning it (`tasks.py:1347-1362`).

**And it is not D10's rejected timing-dependent alternative.** Links can be added after creation, but
the flip is one-way and conservative (toward evidence-governed, i.e. toward "nothing merged" rather
than "the wrong thing merged"), and it fires on a deliberate act naming a requirement rather than on
a review verdict landing. One consequence named rather than left to be discovered: `absorb_free_text`
(`tasks.py:793`) can make a loop task evidence-governed from an agent's prose — but only where the
identifier **resolves** (`requirement_links.py:225-230`), so in a project with no documents, the
ordinary shape for a loop, nothing is linked.

### D12 — the decision round 2 left open, taken; and it was never a decision

Round 2 framed `_prerequisite_commits` as *"the honest options are (a) leave it and say so, (b)
make it ask the same question"*, recommended (b), and put it to round 3. **There is no option (a).**
`openspec/specs/task-dependencies/spec.md:335`, shipped:

> **A task's isolated checkout SHALL contain the work of every prerequisite the task was permitted
> to start on, *whether or not that work reached the project's main branch*.**

Its rationale at `:337` enumerates the conditions round 2 discovered independently — *"the operator's
own checkout may be mid-edit or parked elsewhere, or the merge may have failed outright"* — as
reasons the requirement exists. So leaving `_prerequisite_commits` on `integration_targets` would
make this change **breach a shipped requirement** for every evidence-free loop task.

Two consequences round 2 could not have drawn without that sentence:

1. **A third spec delta.** `:339`'s mechanism sentence names *"each direct prerequisite's accepted
   evidence commit"*, because evidence was the only source when it was written. It is MODIFIED to
   name whatever the system would integrate for that prerequisite, or the capability's normative
   sentence and its mechanism sentence disagree about the one task shape this change introduces.
   `specs/task-dependencies/spec.md` is new in this round and is not optional.
2. **Round 3's own first draft of D12 was wrong** and is corrected in place. It called the
   all-or-nothing unwind refusing a turn (`worktrees.py:451-452`, `:492-493`) *"a new failure mode
   … accepted on the grounds that loud beats silent"*. It is not new: it is `task-dependencies:341`
   verbatim, with its own scenario. This change puts one more task shape under a rule that already
   exists.

The `approved` restriction is kept and is load-bearing rather than belt-and-braces:
`_prerequisite_commits`' docstring defends `integration_targets` by saying the alternative *"would
carry work nobody accepted into a checkout an agent is about to write in"*. On the evidence route
that filter is automatic; on the branch-tip route an in-progress prerequisite's tip is a real commit
and there is no filter at all. `dependency_gate.MET_STATUS` is `"approved"` (`dependency_gate.py:39`).
Mechanically cheap: `resolve_turn_workspace_inputs` already holds `repo_root` (`task_workspace.py:62`)
and already passes it to `_integration_base` on the line above the call being changed.

**Rejected and recorded:** gating the successor on the prerequisite's integration having actually
*merged* — it converts an ordinary dirty checkout into a stalled queue and contradicts both "approval
is never blocked by what integration could not do" and `task-dependencies`' own "whether or not".

### D13 — one round-2 claim was wrong, and it made the proposal overstate a risk

Round 2 carried *"`TaskUpdate.loop_id` is write-once rather than immutable"* into the proposal's
Impact and into `carried_open_questions`. It read the schema's comment (`schemas/tasks.py:146-151`,
which does say "write-once") and not the route. `tasks.py:1215-1223` refuses the field
**unconditionally** whenever supplied, without consulting the current value. Grepped for every write
to the column rather than recalled: `tasks.py:771`, `jobs.py:685` (both creation), `jobs.py:233`
(`_adopt_document_tasks`), `spec_tasks.py:216` (`materialise`). There is no fifth. **An existing task
cannot be attached to a loop at all.** The one remaining route is a single `create_task` supplying
both — which D11 closes on its own terms rather than by narrowing `loop_id`. Impact corrected.

Also confirmed rather than assumed: `_adopt_document_tasks` returns `0` unless
`loop.spec_document_id is not None` (`jobs.py:225-226`) and its `UPDATE` is restricted to
`Task.loop_id.is_(None)` (`jobs.py:231`), so it back-fills only for flows and only onto unowned
tasks — the incoherent state the round's brief worried about cannot arise. And `agents.py:965` is
the `create_loop` inventory line; round 2's correction of round 1 stands.

### D14 and D15 — the two questions the brief asked, answered

**(a) The declaration stays on `Loop`.** Moving it to `Task` contradicts D-B's words, is per-card
where the operator asked for per-loop, and needs a control on every task-creation path to be
discoverable. Moving it to `Project` reintroduces D10's defect at a larger radius, since a project
runs flows and loops side by side. What D10 and D11 *do* change is the shape of the answer, and it is
worth naming rather than treating as a smell: the resolver reads the **loop** for the declaration and
the **task** for the default. The loop is where a person states an intent; the task is where the
product observes whether this work is wired into the chain.

**(c) D3 stands.** `pending_edit_at`'s invariant is *"non-NULL iff at least one of the three
pending_\* fields above is set"* (`models.py:1428-1431`) — read carefully, that "three" excludes
`pending_edit_actor`, which is attribution. Not editing leaves it untouched. And the pending
machinery would be the wrong home anyway: it defers an edit to a **firing** boundary, and this field
is never read by a firing — it is read at approval, per task. Staging it would apply a decision about
the operator's main branch at a boundary chosen by the scheduler's clock.

### Verification

- `openspec validate a-loop-declares-whether-it-needs-evidence --strict` → **valid**;
  `openspec validate --all --strict` → **48 passed, 0 failed**.
- **Every citation added this round was opened or grepped**, including re-checking three of round 2's.
  Line numbers corrected against the files: `worktrees.py:451-452` (not `:450-452`), `:481-486`
  (not `:479-486`), `_merge_prerequisites` at `:491` with the unwind at `:492-493`.
- Checked by listing every `openspec/changes/*/specs/`: **no other in-flight change touches
  `task-dependencies`**, so the new delta carries no archive-order constraint. C-before-D still
  applies to `task-lifecycle-governance`.
- No product code touched. No suite run, and none was warranted.

### Next

**`D-IMPL`** — implement the change, reproduction tests first, and 1.7/1.7a are the two guards that
must be written **against today's code where they pass**: they are what would have caught D10 and
D11 respectively. Note the round's one open item for the operator, now in `decisions_for_user` as
D6: an explicit `work_needs_evidence=False` merges the branch tip even for a task linked to
requirements with accepted evidence. That is D-B read literally and the design keeps it, but it is
the operator's to confirm.


## Iteration 14 — 2026-08-31 04:19 to 05:1x (+01:00) — `D-IMPL`: implement `a-loop-declares-whether-it-needs-evidence`

**Every group is done but the drive.** Groups 1, 2, 3, 4, 5, 6 and 7 landed in four commits, each
at a group boundary with the tree clean and the touched tests green. Task 8.5 — driving it against
a live Hub — is the only unticked item and belongs to `DRIVE-2`.

`4ce13c9` groups 1-2 · `eeab0d3` groups 4-5 · `c1bb982` group 3 · `5522597` groups 6-7

### The reproduction was committed before the fix, and it mattered twice

Group 1's five cases were written against unmodified code and **passed there**, which is the whole
point: `4ce13c9` is where the defect is measured, not asserted. Two of them then flipped in
`eeab0d3` — an evidence-free loop task's commit now reaches the main branch, and its retry says
`already integrated` instead of repeating a skip nothing could clear.

The other three are guards and still pass unchanged. Two are the ones rounds 2 and 3 added:

- **1.7** — a task on a **flow** merges the commit its accepted evidence names, with a *different*
  commit at its branch tip. This is what would have caught D10.
- **1.7a** — the same for a **documentless-loop** task carrying a requirement link. This is what
  would have caught D11, and it is the population D-B's `raise_it_if` fired on.

Both write a different commit to the tip than the evidence names, so "merged the evidence" and
"merged the tip" cannot be confused. A guard where the two answers coincide proves nothing.

### F159 — the round-3 decision was wrong by one predicate, and implementing it is what found that

Design D12 specified `_prerequisite_commits` as an **unconditional** `approved` filter. Its whole
justification is about the branch-tip route — *"on the branch-tip route there is no automatic filter
at all"* — and applied to the **evidence** route it stops prerequisite work that reaches successors
today. A shipped test caught it within a minute of the change landing:
`test_a_prerequisites_accepted_commits_are_in_the_task_checkout` constructs an `in_progress`
prerequisite with accepted evidence and asserts its commit is in the successor's checkout.

And F158 is why it is the ordinary case rather than the fixture's artifice: a task branch is cut at
**dispatch**, one edge before the dependency gate fires, and prerequisites are merged only at branch
creation. At the one moment `_prerequisite_commits` is consulted, an unapproved prerequisite is
common. The blanket check would have breached `task-dependencies:335` in the opposite direction to
the one D12 exists to close.

Scoped to the branch-tip route, which is exactly what D12's own justification argues for. Design
D12 corrected in place; F159 filed with the transferable lesson, which is that "compare the proposal
against the code" was applied only to the code the change is *about*. **A round that had asked
"which existing test does this line change the answer for?" would have found it in one grep.**

Three rounds did not find this. A shipped test did, in 105 seconds.

### What each group actually did

**2 — the column.** `Loop.work_needs_evidence`, nullable, no `default=` and no `server_default=`.
Migration `0100`, guarded for a missing `loops` table. Its no-backfill test inserts a **flow** row
and asserts NULL after upgrade: `loops` holds flows too, and an explicit value wins over the
kind-aware default, so a server default would have answered for every existing flow silently. Both
head assertions bumped.

**4 — the merge target.** `merge_targets(session, task, root)` beside `integration_targets`, which
is not modified and stays a pure DB query. `evidence_governs` is the five-arm resolver, extracted as
its own function so the preview can ask the governance question *before* deciding whether to resolve
a workspace — which is the condition design D5 put on moving that route. `NO_TASK_BRANCH` is a
second empty-case reason, because `NOTHING_TO_MERGE` is a statement about evidence and would be a
lie for a task whose merge evidence does not govern.

**5 — the gate.** `_MergeSituation.accepted` became `will_merge`: what the list is *for*, not where
it came from. `_check_unaccepted`'s `if situation.will_merge:` arm needed no second rule, which is
D8, and now says so in a comment.

**6 — retryability.** `is_retryable` answers `FAILED` on the **outcome** before the reason is
consulted, matches the two templates on their invariant stems, and inverts the default. `SKIP_REASONS`
plus a totality test is what makes the inversion safe rather than merely stricter. The UI's
`NO_MAIN_BRANCH` constant is deleted; `retryable` is optional in the TS type so an older Hub's
response offers nothing to press.

**7 — the tool surface.** `create_flow` does not get the *capability*, per 7.5, but it does keep the
parameter and **refuse** it — the pattern `create_loop` already uses for `spec_document_id`, and
required anyway by the schema parity test. The field went onto `AgentJobCreate` too, without which
the MCP path would have dropped it silently.

### Three things checked that the tasks asked about

- **6.5's question.** "Keep the missing-main-branch case pointing at the setting — check whether
  that text exists on screen today." It does not exist in the component: the sentence *"choose one
  in the project's settings"* is part of the **reason the Hub records**, rendered as the row's own
  text. So nothing was added, as the task instructed.
- **7.4's question.** Neither guard catches a stale inventory line for an *optional* argument.
  Filed as **F160**, not fixed — the repair will make several existing lines fail at once and is its
  own piece of work.
- **F157 stays open and is now referenced in code.** `create_job` still drops `spec_document_id`
  silently while refusing `work_needs_evidence`; the comment at the refusal states the asymmetry and
  why this change does not sweep it in.

### Verification

- Task 8.1's list plus the three tool-surface files: **310 passed, 3 skipped**.
- Broader sweep, `integration|workspace|release|gate|loop|dependenc|worktree|approval`: **685
  passed, 15 skipped**. Everything matching `job|loop`: **297 passed, 14 skipped**.
- Full UI suite: **1460 passed across 141 files**. `npm run lint` clean. `npm run build` +
  `scripts/refresh_ui_bundle.py`; `hub/ui/src` and `hub/hub/static/ui` committed together.
- `ruff check src/ hub/ tests/`, `black --check --target-version py311`, `mypy src/` — all clean.
- `openspec validate a-loop-declares-whether-it-needs-evidence --strict` — valid.
- One incidental catch worth knowing: `test_task_workspace_scheme.py` scans **source comments** for
  writes to the column, so a comment containing the literal `workspace_scheme='agent'` fails it. The
  comment was reworded.

### Next

**`DRIVE-2`** — and task 8.5 is its first item, because until the drive nothing has proved this
outside a fixture. A fresh project, a loop created through `create_loop` with the declaration
omitted, one Haiku turn that writes a file, approval, and then `git merge-base --is-ancestor`
against the repository itself — not the `TaskIntegration` row, which is what the product *claims*.
Then the same loop declaring `work_needs_evidence=True` and confirming nothing merges. Then re-drive
the flow, because groups 4 and 5 moved the code every flow's approval runs through.

---

## Iteration 15 — 2026-08-31 05:09 to 05:4x (+01:00) — `DRIVE-2`: **a loop lands its work too**

**Item:** `DRIVE-2`, all four parts. **Status: done, and the headline held.** Task 8.5 —
the only unticked item in `a-loop-declares-whether-it-needs-evidence` — is driven and ticked, so
that change is complete. `git log master` in the fixture now carries a commit that got there by
approving a **loop's** task, which is the thing F124 said could never happen.

### The Hub on 8011 was stale again, and again the restart is how that was caught

PID 9476, started **02:40**, and twelve `.py` files under `hub/hub` were newer than it — every file
D-IMPL touched. Killed and restarted from `hub/` with the beta-profile `DATABASE_URL`; the new
process ran `0099 -> 0100, a loop declares whether its work needs evidence before it reaches the
main branch` on startup, which is the proof the old one predated the change being driven. Second
run in a row where the state file's warning was load-bearing.

### The fixture

New project **`drive2-2026-08-31` = `proj-60c8c49372ce`** at `C:\Users\huida\Documents\drive2-2026-08-31`
— `git init -b master`, one commit (`calc.py`, `.gitignore` for `.agentweave/`), `master` adopted as
the main branch by `POST /projects/open` with no settings round trip. Runner `Haiku (cheap)`, agents
`alpha` and `beta` bound to it, and **`allow_agent_jobs` turned on**, without which `create_loop` is
not in an agent's inventory at all and task 8.5's named route is unreachable. Neither forbidden
project touched.

### `t_drive2_loop_lands.py` — 29/29 held on the third run

Three lanes and the operator's route:

- **the operator's route** (item 2): `POST /jobs` with `work_needs_evidence` on a job that is not
  becoming a loop → **400** *"give this job a purpose or a stop condition to make it one"*, leaving
  no row behind. `PATCH /jobs/{id}` → **400** naming the create-a-new-loop remedy, changing nothing.
- **LANE A**, declaration omitted: `create_loop` called by a real `alpha` turn, `work_needs_evidence`
  **NULL** on the row — not False. One Haiku turn wrote the file, the Hub auto-snapshotted it onto
  `agentweave/task/<id>`, and approval merged `8534ede` into `master`. `git show master:<file>`
  answers `def power(a, b): return a ** b`.
- **LANE A′**, the retry button (item 4): the operator's checkout was made dirty on a **tracked**
  file before approving. The integration skipped with `CHECKOUT_DIRTY`, `retryable: true`, nothing
  on `master`; cleaning the checkout and pressing retry appended a **second** row with outcome
  `merged`. Both halves of item 4 in one lane.
- **LANE B**, declaration `True`: the same shape, `work_needs_evidence: true` carried through
  `create_loop` to the row. Approval was **not** refused — there is no evidence to be unaccepted —
  and nothing merged, with the reason `"no accepted evidence names a commit, so there is nothing to
  merge"` and `retryable: false`. The **evidence** empty answer, not `NO_TASK_BRANCH`: the two
  callers keeping their empty cases apart is exactly what group 4 was for, and it is now driven.

**The first two runs failed 11 and 11 of 29, and both were the harness.** They are worth recording
because one of them became a finding. Run 1 read the task branch tip the moment the task said
`completed` and got the *base commit*; run 2 measured the same thing deliberately and got
`3a0c5a2 -> eabc80c` across the turn boundary. That is **F162**. Run 1 and 2 also tried to approve in
one PATCH and met a 409, then a 403 — **F163**.

### Item 3 — the flow re-driven, because groups 4 and 5 moved its approval path

`t_drive1_flow_lands.py` re-run against the same fresh project. **14/19**, and the question it was
re-run to answer is answered: `modulo` went document → materialised task → staffed → worked →
evidence naming a commit → reviewed by a non-author → `approved` **by its reviewer with nobody's
hand on it** → `6e1dbac` merged into `master`. Changes A and B still driven on the moved code.

The five that did not hold are **F154's cause for the second consecutive drive** (this time `beta`
looping on `ToolSearch`, writing *"Verdict: APPROVED"* in prose and never calling `update_task`,
after which every firing answers the false-healthy 409), and **F155** (`power` and `modulo` both
append to one file; `modulo` landed first, so `power` no longer merges cleanly and the operator's
approval is refused with a remedy nobody can follow). Neither is the moved code, and both were
already filed. Recorded as **F164**, with the correction that F155 is far more ordinary than DRIVE-1
suggested: two parallel tasks touching one file is the *shape* of a flow's work, not an accident of
a stalled lane.

### Findings filed

- **F161** — a loop that declared its work needs no evidence still stalls with *"has no recorded
  evidence, so there is no commit to review"*. `commit_for_task_review` resolves the review commit
  from evidence and nothing else, and its docstring's rejected alternative (*"there is nothing to
  review anyway"*) is now false: `merge_targets` knows a second answer for exactly this population.
  Not fixed — whether a loop should staff reviews of its own single agent's work at all is a design
  question about the loop/flow split.
- **F162** — the window between `update_task(completed)` mid-turn and the auto-snapshot at turn end.
  Measured twice. The consequence read from the code and **not driven**: an approval inside it
  resolves the base commit, records `ALREADY_INTEGRATED`, and that skip is deliberately not
  retryable, so the work would be stranded.
- **F163** — landing a loop's work costs three operator transitions (`assignee → null`,
  `→ under_review`, `→ approved`), two of them discovered as refusals. A flow never meets the first.
- **F164** — the flow re-drive above.

### Verification

- `t_drive2_loop_lands.py` **29/29**; `t_drive1_flow_lands.py` **14/19** with every failure traced.
- `openspec validate a-loop-declares-whether-it-needs-evidence --strict` — valid, and every task in
  it now ticked.
- The fixture is clean: no job enabled (all archived), both agents idle, checkout clean, nothing
  queued, no permission card pending.

### `SUITE` — green, on the second attempt, and the first attempt is worth recording

**`py -3.11 -m pytest hub/tests/ -q` → 3751 passed, 84 skipped, 1 xpassed in 20:43.**
`py -3.11 -m pytest tests/ -q` → 440 passed, 3 skipped. `ruff check src/ hub/ tests/`,
`black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/` and `mypy src/` all clean.

The **first** attempt stalled. It reached 95% (~3646 of 3836) and then stopped — not slowly, but
completely: measured 912.6 seconds of CPU on the pytest process, and 912.6 seconds again forty
seconds later. Nothing had failed; it simply stopped advancing, and sat there twelve minutes before
it was killed. That is **F109**, the known flake the state file describes as "the hub suite shares
one database connection per session and the retry chain can stall on it", and it is the first firing
of it in three full runs.

Two things were done rather than assumed. The stall point was located by index — 95% of 3836 puts it
in `test_task_worktrees.py`/`test_tasks.py` — and then **every file from there to the end was run
standing alone: 235 passed, 2 skipped, in 84 seconds.** So the tail is not broken; it stalls only
behind the other 3600. Then the whole suite was run again from scratch, and that run is the green
one above. A single green full run is the claim, not two partial ones stitched together.

---

## Iteration 16 — 2026-08-31 06:39 to 07:0x (+01:00) — `F162-DRIVE`: **the window is real, and the agent sizes it**

**Item:** `F162-DRIVE`, the last thing in the queue. **Status: done. Outcome: REPRODUCED** — the
consequence F162 read off the code happens exactly as read, and lane 2 found the finding's own
likelihood assessment had been too kind to the product.

### The Hub on 8011 was fresh, for the first time in three iterations

PID 28908, started **05:10**, and **zero** `.py` files under `hub/hub` or `src/` are newer than it.
Iteration 15 restarted it after D-IMPL and nothing has touched product code since. Checked first,
as the state file demands; this time it was already right.

### `t_f162_window.py` — two lanes, 11/11 and 4/4

New harness, reusing `t_drive2_loop_lands.py`'s helpers, against the same fresh project
`proj-60c8c49372ce`. Both lanes on a loop with the declaration **omitted**, because that is the
population where `merge_targets` resolves the branch tip — which is exactly the thing F162 says is
stale inside the window.

**LANE 1 — the consequence. `REPRODUCED`.** `create_loop` driven by a real `alpha` turn, one task,
fired by hand, `GET /tasks` polled every **1 second**, and the instant the task read `completed` the
three transitions F163 documents were fired back to back with no settle in between:

```
t+ 45.78s  task reads 'completed'  tip=4be8dba25c1d (== the base commit)  busy=['alpha']
t+ 45.81s  hop 1 assignee -> null   200
t+ 45.84s  hop 2 -> under_review    200
t+ 46.42s  hop 3 -> approved        200      <- the transition that integrates
```

**Nothing refused it.** All three answered 200 with `alpha` still mid-turn, so the second of the
three possible outcomes — *the product already guards this* — is dead. The 403/409 pair that
blocked the two earlier attempts came from doing the hops in one PATCH, not from a guard on a live
run. The integration row the approval wrote names `4be8dba25c1d`, which **is** the base commit:
`"outcome": "skipped", "reason": "4be8dba25c1d is already in master; there was nothing to merge",
"retryable": false`. Then the turn ended, the snapshot landed, and the **repository** was asked
rather than the row: branch tip `26978ce7bd78`, `git show master:f162_064157.py` → **absent**. The
task sits at `approved`, and there is no button. The work is stranded, silently, behind a screen
that says approved.

**LANE 2 — how wide is the window, which nobody had measured.** Lane 1's window was under a second,
because there the agent's *last* act was `update_task` and the snapshot followed immediately. That
is the narrow end and it is not the interesting one. The window runs from `update_task(completed)`
to the **end of the turn**, so its width is whatever the agent does next — and the product
constrains that not at all. Lane 2 asked for an ordinary three-step turn (build the file, mark the
task done, *then* write a second file and read both back) and polled the git ref every second:

```
t+  17.48s  task reads 'completed'   tip=4be8dba25c1d (== base)   busy=['alpha']
t+  27.95s  the snapshot arrived     tip 60a227c0e9cf
```

**10.5 seconds**, every one of them with the task readable as `completed` and approvable by anyone
looking at the board. Approving after the turn ended merged `60a227c0e9cf` normally, so the ordinary
path is untouched — the defect lives entirely in the window.

### What that changes about the finding

F162's own paragraph said an approval in the window was *"by hand, unlikely"*. That was written when
the window was assumed to be one turn-teardown wide. It is not: it is **agent-sized**, and an agent
that marks its task done and then spends two minutes tidying holds it open for two minutes. Any
automation that approves on a status change hits it every time. The finding is rewritten with both
lanes' evidence and three candidate repairs, **none driven and none implemented** — where the repair
belongs is a design question (refuse the transition while a run is live / resolve the merge target
after the snapshot / make `ALREADY_INTEGRATED` retryable when the source branch has moved), and this
run does not have the rounds left to settle it.

### Housekeeping

`openspec validate --strict` is valid on **all four** changes on this branch. Two genuinely-done
bookkeeping tasks were ticked (`approval-refuses-unaccepted-evidence` 7.8 *Commit*, and
`a-review-a-flow-cannot-staff-is-named` 8.6 *Commit naming F142* — both commits exist on the
branch). The three items still unticked in `approval-refuses-unaccepted-evidence` section 8 are
**deliberate scope markers** headed *"Not in this change"*, not unfinished work; 8.3 is the one with
anything left in it, and it is an observation to make during a UI drive.

Fixture left clean: both jobs archived, both agents idle, checkout clean, nothing queued, no
permission card pending, and `master` in the fixture carries the lane-2 merge.

---

## The branch, offered

**`autonomous/2026-08-31-the-flow-lands-its-work` is ready for the operator.** Everything queued is
done, the suite is green, and the headline is driven rather than argued.

**What it does.** The exploration `openspec/explorations/2026-08-30-why-a-flow-cannot-land-its-work.md`
named seven breaks between a flow's approval and the main branch. This branch closes all seven,
across four openspec changes, each through the full three-round discipline before a line was
implemented:

| Change | Breaks | Findings |
|---|---|---|
| `a-flow-briefing-names-its-contract` | 2, 3 | F140, F143 |
| `a-review-a-flow-cannot-staff-is-named` | 4 | F142 |
| `approval-refuses-unaccepted-evidence` | 5, 6 | F122, F152 |
| `a-loop-declares-whether-it-needs-evidence` | 1, 7 | F124 |

All four validate `--strict`. Every task is ticked except three deliberate *"not in this change"*
markers.

**What was proven, in the repository rather than in the Hub's account of itself.** Two end-to-end
drives on fresh projects, every real agent turn on Haiku:

- **A flow lands its work.** `t_drive1_flow_lands.py`: document → materialised task → staffed →
  worked → evidence naming a commit → reviewed by a **non-author** → approved by its reviewer with
  nobody's hand on it → merged into `master`.
- **A loop lands its work.** `t_drive2_loop_lands.py`, 29/29: declaration omitted → `NULL` on the
  row → branch tip merged → `def power` present in `git show master:...`; declaration `True` →
  nothing merges and the reason is the **evidence** one, not the no-branch one; the operator's route
  refuses the field on a non-loop and on any PATCH; and the retry button driven **both** ways in one
  lane. F124 is dead.

**Suite at the offer.** `hub/tests/` 3751 passed / 84 skipped / 1 xpassed (20:43); `tests/` 440
passed / 3 skipped; `ruff`, `black --target-version py311` and `mypy src/` clean. Green on the
second attempt — the first stalled at 95% with zero CPU movement, which is **F109**, the known
flake, firing for the first time in three full runs.

**What the operator inherits, unfixed and filed with evidence.** None of these is a regression this
branch introduced; all were found by driving it.

- **F154** — a reviewer that loops on `ToolSearch`, writes its verdict in prose and never calls
  `update_task`, after which every firing answers a false-healthy 409 with both agents idle and the
  task wedged at `under_review`. **Two consecutive drives**, so its cause is no longer fairly called
  intermittent.
- **F155** — two parallel tasks appending to one file is the *shape* of a flow's work. Whichever
  lands first makes the other unmergeable, and the refusal's remedy (*"resolve the conflict on the
  branch, then approve"*) cannot be followed by anybody.
- **F162** — driven this iteration, above. Agent-sized window, silent strand.
- **F161** — a loop declaring its work needs no evidence still stalls staffing a review, because
  `commit_for_task_review` resolves the review commit from evidence and nothing else.
- **F163** — landing a loop's work costs three hand transitions, two discovered as refusals.
- **F156**, **F157**, **F158**, **F164** — as filed.

**This run does not merge.** The branch is pushed; the merge is the operator's.
