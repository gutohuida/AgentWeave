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
