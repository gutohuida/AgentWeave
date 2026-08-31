## Context

Three findings from the 2026-08-31 drives share one cause and one repair, and shipping any of them
alone makes another worse.

**F162** (driven, `scripts/drive/t_f162_window.py`, lanes 11/11 and 4/4): between
`update_task(completed)` — written mid-turn — and `worktrees.snapshot_worktree`, which commits the
agent's edits when the turn ends (`hub/hub/api/v1/agent_trigger.py:1993`), the task's branch points
at the commit it was cut from. `task_integration.task_branch_tip` (`task_integration.py:307`)
answers with that base commit, `integrate` records `ALREADY_INTEGRATED`, and `is_retryable`
classifies it as not retryable (`task_integration.py:112`). Board says `approved`; work is unmerged;
no button. Measured **10.5s** on an ordinary three-step turn; the agent sizes it.

**F161**: a loop that declared its work needs no evidence stalls with *"there is no commit to
review"*, emitted at `scheduler.py:1472` from `requirement_evidence.commit_for_task_review`, which
resolves a review commit from evidence rows and nothing else.

**F163**: landing a loop's work costs three hand transitions, two of which begin as refusals — a
`403` (still held by its author) then a `409` (`completed` reaches only `rejected` and
`under_review`, `task_transitions.py:137`).

The drive fired all three of F163's hops in **640ms**, well inside F162's window. So shortening the
route without closing the window makes the strand more likely, not less.

The product has met this window before, on the other route.
`requirement_evidence.restamp_run_footprints` (`requirement_evidence.py:846`) says so:
*"The window is structural — there is no moment at which recording could observe the right sha — so
the record is corrected once the commit exists."* The evidence route carries three defences (that
restamp; a human acceptance step; coverage's `verified, not integrated`). The branch-tip route
added by `a-loop-declares-whether-it-needs-evidence` inherited none, and coverage cannot even
describe it: `requirement_coverage` selects from `SpecRequirement` (`requirement_coverage.py:219`)
and a documentless loop's task serves none.

## Goals / Non-Goals

**Goals:**

- Approval never resolves a merge target from a live turn.
- A loop stops asking for a review it structurally cannot staff.
- Landing a loop's work is one operator action whose refusals are the same refusals approval has.
- `approved` keeps meaning *the work is in the product*.

**Non-Goals:**

- Changing what `approved` means. Deferring the merge to turn-end was considered and rejected — see
  D2.
- Widening `TRANSITIONS`. See D6.
- Touching `is_retryable` or `ALREADY_INTEGRATED`'s classification.
- Any deferred-merge queue, turn-end merge trigger, or new asynchronous screen state.
- F154 and F155, both severity A, both filed with reproductions. Different subject: what a flow's
  machinery *tells* an agent to do.

## Decisions

### D1 — the refusal lives in `requirement_gate`, as a fifth `GateRefusal` category

`GateRefusal` already carries `blocking`, `diagnostics`, `unmergeable` and `unaccepted`
(`requirement_gate.py:84-113`), and its own comments justify each as *a different kind of claim*.
This is a fifth: not "unproven", not "cannot go in", not "something is waiting to be judged", but
**"what would go in is not knowable yet."**

`evaluate(session, task)` (`:384`) is already the single question asked before the transition, and
its two repository-aware checks sit **above** the early return for projects with no gating document
— deliberately, because that return fires for every default project. The new check belongs in the
same place for the same reason: a documentless loop is exactly the population that reaches that
early return.

**But not inside the same block** — round 2's correction. Those two checks are nested under
`if situation is not None`, and `_merge_situation` returns `None` for any project with no configured
main branch, an unresolvable workspace, a non-repository directory, or no branch by that name
(`requirement_gate.py:255-283`). Liveness is not a question about the repository, so nesting it there
would make the refusal silently absent from exactly the projects whose state is least understood.
The check is a third statement in `evaluate`, above the early return and beside the
`situation is not None` block rather than within it.

**Round 3: that placement departs from a principle the code states in words, and the departure has
to be argued rather than assumed.** `_MergeSituation`'s own docstring says of the four preconditions:
*"Each is **a reason to not know, never a reason to refuse**, and they have to be the same four
rather than two lists that can drift, because a refusal that fired where the merge would have been
skipped anyway would block every task in such a project behind a remedy that changes nothing"*
(`requirement_gate.py:230-238`). Placing the liveness check outside the block makes it fire in
exactly those projects. Three reasons it is nonetheless right, and they are the reasons the comment
beside it must give:

1. **It is not one of the four.** The docstring's rule binds checks that ask *what would merge*.
   Liveness asks whether the work exists yet, which is answerable in a directory that is not a
   repository at all.
2. **The remedy is not "a remedy that changes nothing".** The clause exists to prevent a refusal
   whose stated fix is unavailable; this one clears itself when the turn ends, without anybody doing
   anything.
3. **`approved` is a judgement about work, not only an instruction to merge.** Where nothing can
   merge, approving mid-turn still records that unfinished work is good. That statement is false in
   a non-repository project exactly as it is in a repository one.

**And round 3 checked the corpus rather than assuming, because this is the likeliest place the
change breaches it.** `task-lifecycle-governance:720` — *"An integration that cannot proceed does not
block approval"* — closes with *"A project that is not a repository SHALL be no less approvable than
before this capability existed"*, and its scenarios state flatly that approval succeeds with no
configured main branch. Read alone that forbids this change. It does not, and the evidence is in the
same function: `evaluate`'s enforced-requirements walk (`requirement_gate.py:399-410`) is
unconditional on `situation`, so `blocking` and `diagnostics` **already** refuse approval in projects
`_merge_situation` cannot resolve, and have since the gate shipped. The corpus therefore already
tolerates non-integration refusals there, which fixes `:720`'s scope: it governs *integration* as a
blocker of approval, and its scenarios speak about their own cause rather than promising that
nothing else may ever refuse. No delta against it is needed. A scenario pinning the behaviour is
added to this change's delta so the next reader does not have to re-derive this.

`task_transition_service` evaluates the gate **before** `task.status = to_status` and before the
`TaskTransition` row is added (`task_transition_service.py:552-572`), and integration runs later
still — so the delta's *"status is unchanged, no integration attempted or recorded"* is a property of
where the gate already sits, not something this change has to arrange.

The category must be added in **four** places, not one: the `GateRefusal` field, the `refuses`
property (`:112`), `detail()`'s composition (`:120`), and `to_dict()` (`:193`). A field added without
`refuses` is a category that never refuses; one added without `to_dict` is a refusal no surface can
render.

Precedent is explicit. `2026-08-13-approved-means-it-is-in-the-product`: *"Mergeability joins the
gate. A branch that conflicts with main is refused before approval, in the same typed refusal… not
discovered halfway through a merge."*

*Alternatives:* a guard in `task_transition_service` (rejected — the gate is where preconditions on
approval already live, and a second location is how two answers to one question drift); refusing at
the API route (rejected — MCP and HTTP would each need it, and
`task-lifecycle-governance:339` requires governance to hold identically over both).

### D2 — refuse during the turn; do not defer the merge to turn-end

The three candidates were: refuse while the run is live; resolve the merge target after the turn;
make `ALREADY_INTEGRATED` retryable.

Deferring is what the *evidence* route does (`restamp_run_footprints`), so it is not architecturally
novel, and `Run.snapshot_commit_sha` (`agent_trigger.py:2043`) is a ready hook. It is rejected
anyway because it changes what `approved` promises: from *the work is in the product* to *the work
will be*. That sentence is the title of a shipped change. It also requires machinery this repair
does not otherwise need — a deferred-merge trigger, a story for a turn that crashes and therefore
never fires it, and a screen state for "approved, merging shortly" that does not exist.

Retryability is rejected because it leaves the board's claim false and puts the recovery behind a
button the operator has no reason to press. `TaskIntegrationNote.tsx` renders "Try again"; nothing
tells the operator the skip was wrong rather than correct.

*The objection that was raised against refusing — "approval would depend on run state, which nothing
else in the product does" — is false as stated.* `project_lifecycle.py:207` refuses project deletion
with *"project cannot be deleted while a run is active"*, and `_guard_relocation` refuses relocation
on the same condition. A new place, not a new idea.

### D3 — liveness is tested against the process, and `pid_alive` alone is not sufficient

`reconcile_interrupted_runs` runs **only** in `lifespan()` startup (`main.py:350`; stated at
`pty_runner.py:150` and `run_reconciliation.py:143`). A crashed agent leaves `Run.status ==
"running"` until the Hub restarts, so a refusal reading the column alone wedges approval
indefinitely on one crash. The column is necessary and not sufficient.

**`pid_alive` alone is also not sufficient, and its own docstring says so:**

> *"on POSIX `os.kill(pid, 0)` succeeds for a **zombie**… The single caller cannot reach that state
> — `reconcile_interrupted_runs` runs once in `lifespan()` startup, against pids recorded by a
> previous Hub process… **If a future caller checks liveness of a process this same Hub killed, it
> needs `waitpid(WNOHANG)` or a `/proc/<pid>/stat` state check — do not assume this function alone
> is enough there.**"* (`pty_runner.py:140-156`)

The gate **is** that future caller: it checks the liveness of a process this same Hub spawned and
may have just terminated. It also inherits the pid-reuse limitation the same docstring names.

**Decision: ask the in-process registry first, and treat its absence as not-live.**
`agent_trigger._active_ptys` (`:148`) holds a session handle per live run in *this* Hub process, and
`PtySession.isalive()` (`pty_runner.py:287`) answers directly. A run this process owns is in the
registry; a run recorded `running` by a *previous* Hub process is not, and is by definition no
longer live. That answers both limitations without a `waitpid` dance, and it fails in the safe
direction — the absent case permits approval rather than blocking it.

`_active_app_server_runs` (`:153`) must be consulted too, or a Codex run answers "not live" while
still working.

*Alternative:* `pid_alive` alone (rejected on its own docstring). *Alternative:* a heartbeat freshness
test via `agent_status.heartbeat_is_stale` (rejected here but worth R2's attention — it is a third
existing answer to "is this agent working", and three answers is one more than the product should
have).

**Import direction is a live risk:** `requirement_gate` currently imports only
`requirement_coverage`, `spec_rigor` and models (`:33-34`). Importing `api/v1/agent_trigger` from it
would invert the layering and probably cycle.

**Open question 2 is answered: a new module, `hub/hub/run_liveness.py`, which owns the two
registries.** `agent_trigger` registers into it instead of holding them itself; `requirement_gate`
imports it directly. Round 2 checked the graph rather than assuming it: `pty_runner` imports only
stdlib and `subprocess_windows` (`pty_runner.py:19-30`), and `requirement_gate` already imports
`db.models`, so `run_liveness` → (`pty_runner`, `db.models`) closes no cycle and no function-local
import is needed. The registries are referenced nowhere outside `agent_trigger` and five test files
(`test_agent_trigger`, `test_agent_trigger_overrides`, `test_conversation_contract`,
`test_lifespan_shutdown`), whose references move with them.

*Rejected: `agent_lifecycle`.* It asks a similar question and answers it the way this change must
not — `archivable` reads `Run.status == "running"` alone (`agent_lifecycle.py:34-42`), which is the
crash-wedge D3 exists to avoid. Putting a process-tested predicate beside a column-read one, both
about liveness, is how two answers to one question drift. (That `archivable` carries the same
exposure is a separate, unqueued observation — an agent whose Hub crashed mid-run cannot be archived
until the Hub restarts. Not fixed here.)

*Not a fourth answer.* The risk list below worried that this would make three answers to *"is this
agent working"* into four. It does not: `agent_status.heartbeat_is_stale` (`agent_status.py:15-25`)
tests an `AgentHeartbeat` row against a watchdog health window — a question about whether an agent
process is *reporting in*, not about whether a run is live — and takes no run at all. The answers
that are genuinely about a run are two, `Run.status` and the registry, and this predicate is the one
place that combines them.

### D10 — the acting run is excluded from the predicate, or this change breaks every flow review

**Round 2's finding, and the one that would have shipped a regression worse than the defect.**

A reviewer approves the work it has just read by calling `update_task(approved)` **from inside its
own turn**. Since migration `0092_review_divergence_regime`, that turn is bound to the very task it
is approving: `run_task_binding.task_named_by` returns `entry.task_id or entry.review_task_id`
(`run_task_binding.py:170-189`) and `_bind` writes `run.task_id = task.id` (`:427`). The migration's
own note says why it had to — *"Until now every review run was unbound… no run records having caused"*
those `under_review → approved` transitions.

So a predicate reading *"a run bound to this task, status `running`, process alive"* matches the
reviewer's own run, and the gate refuses the approval the review exists to produce. Every flow review
in the product dies — including the one path that has ever been observed carrying a flow's work to a
main branch (F153, 2026-08-31). The change would close a 10.5-second window by permanently closing
the door beside it.

It is also **F155's failure mode exactly**, which D4 already names as the standing warning: the
refusal's only remedy is *wait for the turn to end*, handed to the turn that would have to end. There
is no action the refused actor can take. A refusal that cannot be cleared by the party it is given to
is the defect this project has already driven an agent into `git reset --hard` over.

**Decision: `evaluate` takes the acting run's id and excludes it.** `transition_task` already holds
it — `actor.run_id` is on the actor it builds every transition from
(`task_transition_service.py:571`) — so the signature widens by one keyword-only argument with a
`None` default, and the operator routes that pass nothing get today's behaviour with nothing
excluded. The rule states cleanly: **a turn is never blocked by itself.**

*Alternative considered and rejected for scope:* excluding review-bound runs structurally, by joining
`InboundQueueEntry.review_task_id`. It cannot be done from the `Run` row — `review_task_id` lives on
`InboundQueueEntry` (`db/models.py:618`) and `Run` carries only the collapsed `task_id`
(`:1102`) — so it costs a join and a second place that decides what a review binding is. The residual
it would remove is small and self-clearing: an **operator** approving while some *other* run bound to
the task is live gets a refusal that lasts until that run ends. Where that run is a reviewer, waiting
is arguably the right answer anyway. Named here so it is a known gap rather than an oversight.

**Round 3 re-derived D10 independently — it is right, it is necessary, and it has a second residual
that is F162 through its own carve-out.** The exclusion is unconditional on what the acting run is
*for*, and the product does not require the acting run to be a reviewer:

- `_bind` writes `run.task_id = task.id` before it decides whether the task can move
  (`run_task_binding.py:427-437`), so a **working** turn's run is bound to its task exactly as a
  review turn's is. The `Run` row cannot tell them apart, which is the same fact that made the
  structural alternative above expensive.
- `_guard_author_is_not_reviewer` refuses only where a completing agent is *recorded*: `if
  completing_agent is not None and completing_agent == actor.agent`
  (`task_transition_service.py:304-305`). An **unattributable** completion — the operator marking a
  card done, which `task-lifecycle-governance:264` and F142 both record as a real and supported
  case — is permitted to act on, by the corpus's own *"refuse to offer, permit to act"* asymmetry.

Put together: an agent mid-turn on task T, whose run is bound to T, whose completion the **operator**
recorded and whose assignee the operator cleared, may call `update_task(T, approved)` from inside its
own still-running turn. The author guard permits it, D10 excludes its run, the gate says nothing, and
`task_branch_tip` resolves the pre-turn commit. That is F162 exactly, reached through the carve-out
built to protect reviewers.

It is narrow — it needs the operator to complete *and* unassign a task an agent is still working —
and it is not a reason to drop D10, whose absence breaks every flow review the product has. But it is
the defect's own central case surviving inside the exception, so it is named here rather than
discovered later. Closing it costs the `InboundQueueEntry.review_task_id` join rejected above; round 3
confirms that trade rather than reversing it, and records the residual as the price. Task 2.6 asserts
the residual's shape in a test, so a later change that makes the join cheap knows what it is closing.

### D4 — the refusal names the agent and says nothing about the work

Sentence shape follows `_merge_detail`'s: state the fact, then the remedy. The remedy here is
**waiting**, and the refusal must say so, because an operator told only "refused" will look for
something to fix. It must not read as a defect in the work.

F155 is the standing warning about this: a refusal that names a remedy which cannot clear it drove a
Haiku reviewer to `git reset --hard` on a branch holding the only copy of an agent's work. A refusal
that clears itself must say *that* it clears itself.

### D5 — a loop never enters the review arm, decided at the selection site

Implement where the review is *selected* (`scheduler.py:1440-1500`), not inside
`commit_for_task_review`.

Teaching `commit_for_task_review` about branch tips would make F161's sentence *true* rather than
*never said*, and would entrench a review leg for a mode with one agent and no second party — every
reviewer it could resolve is the author, whom `_guard_reviewer_is_not_the_author` refuses on
arrival. The operator's answer to D21 was that a loop should not staff reviews of its own agent's
work at all.

The flow's arm is untouched. The requirements governing reviewer resolution are already written
about a flow (`agent-flows:134`, whose scenarios all begin *"WHEN a flow fires"*).

**Round 3 replaces the argument from silence with an affirmative prohibition, and it is the single
most important correction of this round.** Rounds 1 and 2 both reasoned *"nothing in the corpus says
a loop staffs a review"* — an argument from absence, which is the weakest kind a proposal can rest a
removal on, and which round 2 had already been forced to narrow once (`agent-loops:970`). The corpus
does not merely fail to require this. It **forbids** it. `agent-flows:13` — *"A flow is a loop that
declares a specification document"* — states: *"A loop that declares no document SHALL be unaffected
by [this capability's requirements] and SHALL behave exactly as it does today."* And that capability's
own Purpose enumerates what it owns: *"firing-time agent resolution, **reviewer resolution, review
dispatch and its handover briefings**, flow width, and the checkpoint lineage"*
(`openspec/specs/agent-flows/spec.md:5-9`). `decide_firing`'s review arm applies all three of those to
a documentless loop. So this is not code exceeding a silence — it is code **breaching a shipped
requirement**, and D5 restores the corpus rather than trimming behaviour the corpus never covered.

The scenario is explicit about the baseline too: *"A loop without a document is unchanged — WHEN a
loop declares no specification document THEN every firing fires the job's own agent, as before."*
A firing that resolves a *second* agent to review is not firing the job's own agent.

**Round 3 answers task 5.4, and round 2's characterisation of the population was wrong in scale.**
Round 2 called it *"narrow and specific: a documentless loop, in a project with a second eligible
agent, whose agent recorded evidence naming a commit"*. Every clause of that is right, and the
conclusion drawn from it — that little exists — is not. That description is the suite's **default
fixture**. Five test files construct `Loop(...)` with no `spec_document_id` and then exercise the
review arm through `decide_firing`:

| File | Tests | What it asserts |
|---|---|---|
| `test_actor_aware_claimability.py` | 14 | `:428` — *"the ladder staffs a review, not the job's own agent"*, and `selections[0].is_review is True` |
| `test_a_flow_names_what_it_cannot_staff.py` | 24 | F142's three arms and the `unstaffed` sentences |
| `test_review_leaves_the_pool.py` | 9 | F45 — a dispatched review leaves the recruitment pool |
| `test_a_review_needs_something_to_review.py` | 5 | `commit_for_task_review` gating the arm |
| `test_review_dispatch_staffs_the_task.py` | 12 | `:1481` staffing |

Every one of those loops is documentless (`grep -c spec_document_id` → 0 in all five). So the
population exists, is reachable, and is covered — and the coverage is of **flow** requirements
written against a **loop** fixture. That is the finding: the tests have been standing in for flows
with rows the product does not treat as flows, which is why nobody noticed the arm was being applied
outside its capability.

**The repair is to declare a document on the fixtures whose subject is a flow, not to weaken the
exclusion.** Where a test's subject genuinely is a loop, its expectation changes with this
requirement and the test changes with it. Task 5.5 carries this, and it is real work rather than
a footnote.

**Round 3: the arm serves two populations, and only one of them may be excluded.** The block at
`scheduler.py:1440-1500` is reached by two different kinds of candidate:

1. a task in `REVIEWABLE_LOOP_TASK_STATUSES` (`completed`) — a **fresh** review, which is what D5
   removes; and
2. a task in `under_review` whose assignee is its own author, carried past the ordinary-work arm by
   `wedged_review` (`scheduler.py:1299-1356`) — the **F70 recovery**, which routes the row back
   through the ladder so a real reviewer replaces the author.

An exclusion written at the top of the arm removes both. And the second failure is silent: on the
`wedged_review` path the `in_flight` record is deliberately *not* written (`if not wedged_review:
in_flight.append(...)`, `:1349`), so a loop's wedged row would fall out of the walk recording
nothing at all — no `in_flight`, no `unstaffed`, no `gated`. That is F23's and F142's silence
arriving through a third door, in a change whose whole purpose is to stop a stall nobody can see.
**The exclusion is on the fresh-review branch only.** A loop's `under_review` row still recovers,
because it is already in review and only *who holds it* was ever wrong — which is what
`task-lifecycle-governance:317` says recovery is: *"a reassignment [that] SHALL NOT move the task to
another status."*

**The unstaffed report must also stay quiet.** `unstaffed` entries surface to the operator as steps
the flow could not take (`scheduler.py:1445-1480`); a loop's completed task is not a step anything
failed at, so it must not appear there.

**Round 3: but quiet is not the same as absent, and the difference is F142 itself.** With the arm
gone and `unstaffed` empty, a loop whose only open task is `completed` walks to the end and falls to
`_stall_reason_from_walk`, which emits *"loop queue is stalled: no claimable task among 1 open (1
completed)"* (`scheduler.py:1668`). That is, word for word, the sentence the review arm's own comment
records as measured-live-and-wrong on 2026-08-30: *"a flow whose only task the operator had marked
finished reported that on every firing, forever, while the actual cause was a property of that one
task and had a remedy."* This change would re-earn it for loops on the same day it removes it for
flows. The difference is that here the cause is fully known and the remedy is D6's landing action, so
the firing SHALL say so — a stall reason naming the completed work as waiting for the operator to
land it. That is a statement about the loop's queue, not a review it could not staff, so it belongs
in the stall reason and not in `unstaffed`.

**Round 3: the operator's by-hand review of a loop's task survives, and the delta has to say so.**
`task-lifecycle-governance:1481` requires every path that *dispatches* a review to staff the task,
and names the operator's by-hand dispatch first among its scenarios. D5 removes a loop's
**selection**, never the operator's dispatch. Without that sentence, *"a loop does not staff a
review"* reads as *"a loop's task cannot be reviewed"*, and the next change to touch this removes a
path the corpus requires.

### D6 — the landing action composes existing transitions; `TRANSITIONS` is not widened

Adding `completed -> approved` to the map would let *every* task in the product skip review, with
only a guard standing in the way. That trades a structural guarantee for one saved hop on one mode.

Instead, one operator action performs the sequence the product already requires: release the
author's hold, `-> under_review`, `-> approved`. The operator taking that action **is** the
reviewer, which is exactly what the existing 403 offers — *"clear the assignee to review it
yourself."* Each transition is recorded, so the history stays true.

`update_task_for_actor` already applies `assignee` **before** the status transition in the same
request (the F70 fix, `api/v1/tasks.py:1258-1270`), so the first two steps are already expressible
in one call. The action is a small composition, not new lifecycle machinery.

*Alternative:* have the UI issue the three calls (rejected — the operator sees two 4xx responses
before a success, which is F163 with a nicer wrapper).

**Round 3 cleared this against the two requirements it most plausibly breaches, and it survives
both.** `task-lifecycle-governance:117` — *"the operator SHALL NOT have permission to make a move the
map does not declare… Operator authority is expressed as additional legal transitions rather than as
a bypass, so every recorded history describes a legal sequence"* — is satisfied because both edges
this composes are already declared for the operator: `TRANSITIONS["completed"]["under_review"]` and
`TRANSITIONS["under_review"]["approved"]` are both `_BOTH` (`task_transitions.py:134-141`). Nothing
is widened and nothing is bypassed. `:168` is satisfied because each of the three steps goes through
`apply_transition`, which writes its own `TaskTransition` row. And `:264` — *"A task entering review
must not still name its author as its holder"*, which *"binds every actor, including the operator"* —
is satisfied by ordering: the hold is released first, and `_guard_reviewer_is_not_the_author` returns
immediately for a task with no assignee (`task_transition_service.py:357`), which is the requirement's
own first permitted case.

**One thing `:168` demands that the delta did not say.** It requires the recorded cause to
*"distinguish a transition an actor asked for from one the system made on that actor's behalf"*. The
landing action is one operator intent producing three records, so it has to decide which those are.
They are **actor-caused, all three**: `ORIGIN_RUNTIME` exists for moves the runtime makes as a
consequence of something it observed, and nothing here is observed — the operator asked for every
step of this, in one word instead of three. The delta now says so.

**Implementation found one thing D6 and the delta both asserted and the schema cannot hold.** The
delta said the history records *"the release of its author's hold, the move into review, and the
approval"*, and task 6.5 said to record *all three* as actor-caused. There is no third row and there
cannot be: `TaskTransition` records a move from one **status** to another (`db/models.py:768-799`),
and `assignee` has no history table at all. The release is a column write folded into the same
handler, exactly as the ordinary PATCH route folds it into the same request (F70's ordering,
`api/v1/tasks.py:1262`). So two rows are recorded, both actor-caused, and what remains checkable
about the release is the task itself. The delta now says that; `test_the_history_records_every_
transition_as_the_operators_own` asserts the two rows and the cleared holder together.

**And one consequence of the ordering that is worth stating rather than rediscovering.** Because the
hold is released *first*, `_guard_reviewer_is_not_the_author` can never refuse step two of this
composition — it returns immediately for a task nobody holds, which is that guard's own first
permitted case. Task 6.3 asked for a test of a refusal raised by that guard; through the real route
there is no such refusal to raise. The test forces one instead, which is the stronger reading of what
the delta claims anyway: *for any reason*, not for the reasons the composition can foresee.

### D7 — a refused landing leaves nothing half-applied, and one transaction is what guarantees it

Refused means nothing happened: no cleared assignee, no review row, no integration record. A
partially-applied landing would leave a task in `under_review` with no reviewer and no author hold,
which is worse than the three hops it replaces.

**Round 3: pre-evaluating the gate does not deliver that, and the delta already promises more than
it.** The delta's scenario says *"WHEN the landing action is refused **for any reason**"*, and the
gate is only one of the ways this composition can be refused: `apply_transition`'s legality check
refuses, `_guard_reviewer_is_not_the_author` refuses `-> under_review` on its own terms, and
`_guard_run_holds_the_task` and `_guard_author_is_not_reviewer` are in the same chain. A landing
that pre-checked the gate and then met one of those on step two would leave the author's hold
already released.

**What actually guarantees it is the transaction.** `apply_transition` and `transition_task` do not
commit — every route in `api/v1/tasks.py` commits for itself (`:1173`, `:1397`, `:1564`). So the
landing action performs all three transitions in one handler under one commit, and any exception
raised by any of them leaves the session uncommitted with nothing written. The gate pre-check is
kept, and its purpose is stated correctly: it is what makes the *refusal message* the one approval
would have given, rather than a failure discovered two steps in. Atomicity is the transaction's job;
the pre-check is the message's.

**Measured at implementation: the pre-check is invisible from outside, and both halves of that
sentence matter.** Removing the three lines that evaluate the gate before the composition starts
leaves a gate-refused landing answering with the *identical* body — step three evaluates the same
gate, raises the same `GateUnsatisfiedError`, and the transaction rolls the staged `under_review`
back. Every black-box assertion in `test_one_action_lands_the_work.py` passes with the pre-check
deleted; only `test_the_gate_is_decided_before_anything_is_attempted`, which observes the call
sequence, fails. So D7's claim that the pre-check *"is what makes the refusal message the one
approval would have given"* is, as built, already true without it.

It is kept, and the reason is ordering rather than the response: the moment a fourth step joins the
sequence, or a step that can refuse on non-gate terms is added before the approval, the difference
between "refused before anything moved" and "refused two steps in" becomes visible. An unobserved
line rots, so the ordering test and the code comment both say what it does and what it does not.

### D8 — the reproduction is written before the fix, in the drive's shape

`t_f162_window.py` lane 1 is the specimen: poll until the task reads `completed`, then transition
with no settle, and assert the refusal — not a stranded `approved`. A unit-level reproduction must
reproduce the *window*, not merely a state, or it will pass against code that still resolves the
base commit.

### D9 — the evidence route shares the exposure. Answered by round 2: **yes.**

Round 1 left this as a hypothesis. Read at the source, it holds, and round 1's *other* sentence — that
the evidence route "survives the window because it has three defences" — does not.

- `_targets` (`task_integration.py:219-266`) filters on `TaskRequirementLink.task_id`,
  `review_state`, `kind == "git"` and a non-empty `commit_sha`. It does **not** filter on
  `reachable_from_main`. So an accepted footprint's sha goes to `integrate` whatever it points at.
- A footprint recorded mid-turn points at the pre-turn commit *by construction* —
  `restamp_run_footprints`' own docstring: *"`read_footprint` can only ever name the commit the
  branch pointed at when the turn started"* (`requirement_evidence.py:856`).
- The restamp that corrects it runs at turn **end**, inside `_execute_run`'s finalize block
  (`agent_trigger.py:2041-2050`), and re-points rows. It merges nothing and re-attempts no
  integration. An approval that landed before it fires has already merged the stale sha and recorded
  the outcome.
- Nothing sequences acceptance after the turn. `decide_evidence` is callable at any moment, so
  "a human acceptance step" is a step in the *order of states*, not in the order of *time*, and it
  is time that this window is made of.

The docstring even states the consequence in the words of the defect: *"the pre-turn commit is
usually already on the main line, so the row is written `reachable_from_main=True` and evidence for
code that does not exist reads as already shipped."* Handed to `integrate`, that is
`ALREADY_INTEGRATED` — F162 reached by the other door.

**Consequences.** The refusal stays unconditional, which it would have anyway (D2 of the operator's
answers). The requirement's rationale names both routes rather than the branch-tip one. Task 4 stops
being a determination and becomes a test: the same refusal, exercised through an accepted-evidence
task. And the difference between the routes is stated accurately — the evidence route recovers its
*record*, it never prevented the *merge*.

One incidental, filed rather than chased: `restamp_run_footprints` says
*"`task_integration.integration_targets` merges on exactly this field"* of `reachable_from_main`.
`_targets` does not read that field at all. The docstring is stale about the code beneath it.

## Risks / Trade-offs

- **A zombie or reused pid reads as alive → approval wedged.** → D3's registry-first predicate; the
  absent case permits approval. Do not ship `pid_alive` as the sole test.
- **A long turn holds the refusal open for as long as the agent works.** → `stop_agent_run`
  (`agent_trigger.py:1500-1541`) already lets the operator stop a run, so the refusal is never a
  dead end. The refusal's sentence should be checked against that route existing.
- **Removing the loop's review arm strands tasks that are being reviewed today.** → F161 shows the
  arm already stalls for the declared-no-evidence population. R2 must check the *other* loop
  populations (a loop with a document is a flow by definition, `agent-flows:13`) before assuming
  nothing is lost.
- **The composed landing action multiplies the surfaces a refusal can come from.** → D7: gate first,
  then transitions, nothing half-applied.
- **An unbound run doing a task's work is not covered** by a `Run.task_id == task.id` predicate. Same
  residual exposure D18 named for evidence authorship. Narrow: the ordinary path binds the run.
- ~~**Three answers to "is this agent working"**~~ → **answered in D3.** `heartbeat_is_stale` is a
  different question (a watchdog window on an `AgentHeartbeat` row, taking no run), so the answers
  genuinely about a run are two, and the predicate is the single place that combines them.
- **The reviewer's own turn is bound to the task it approves**, so the predicate would refuse the
  review leg it was never aimed at. → D10: the acting run is excluded. This is the change's largest
  regression risk and `t_drive1_flow_lands.py` is what proves it did not happen.
- **The predicate is silent for a project `_merge_situation` cannot resolve** if it is nested under
  that block. → D1: it is a separate statement in `evaluate`, not nested.
- **Round 1 credited the evidence route with defences it does not have.** → D9. The lesson is the
  one CLAUDE.md records: an argument can be wrong while everything it argues about is right, and
  only a round that re-derives the argument finds it.
- **Removing the arm takes the F70 wedged-review recovery with it, silently.** → D5, round 3. The
  exclusion is on the fresh-review branch only; the `wedged_review` path records nothing on its way
  out, so a wholesale exclusion would make a loop's wedged row vanish from the walk entirely.
- **The loop's stall sentence becomes F142's sentence again.** → D5, round 3. `unstaffed` staying
  empty is right and not sufficient; the stall reason has to name the completed work as waiting for
  the operator's landing action.
- **A landing refused on step two leaves the author's hold already released.** → D7, round 3. One
  handler, one commit; the gate pre-check is for the message, not for atomicity.
- **D10's exclusion re-opens F162 for an agent working an unattributably-completed task.** → D10,
  round 3. Narrow, named, and priced: closing it costs the `review_task_id` join.
- **Five test files assert the review arm on documentless loops.** → D5, round 3. They are flow
  requirements tested through loop fixtures; the fixtures gain a document rather than the exclusion
  being weakened. Task 5.5.

## Migration Plan

None. No column, no schema change, no backfill. The behaviour change is a refusal that did not fire
before; nothing recorded needs reinterpreting.

Rollback is removing the check — the gate composes its categories, so a removed category leaves the
other four unchanged (`GateRefusal.detail`, `:115-124`).

## Open Questions

1. ~~**Does the evidence route share the window?**~~ **Answered by round 2: yes.** See D9. Task group
   4 becomes a test rather than a determination.
2. ~~**Where does the liveness predicate live?**~~ **Answered by round 2: a new module,
   `hub/hub/run_liveness.py`, owning the registries.** See D3; the import graph was checked, not
   assumed, and `agent_lifecycle` was rejected with a reason.
3. **Should the landing action exist for a flow's task too?** The three-hop cost is a loop's because
   a flow staffs its own reviewer. If a flow's review is unstaffable, the operator is in the same
   position — but that is F142's territory, already shipped, and widening scope here is how a change
   stops being reviewable.
