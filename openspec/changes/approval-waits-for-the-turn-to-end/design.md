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
about a flow (`agent-flows:134`, whose scenarios all begin *"WHEN a flow fires"*); nothing in the
corpus says a loop staffs a review. This is code being brought back inside its spec.

**What round 2 observed about the populations, for round 3 to confirm or overturn (task 5.4).** The
discriminator is `loop.spec_document_id` — the scheduler already uses exactly it
(`scheduler.py:2043`, `is_flow=bool(loop.spec_document_id)`), so the exclusion has a discriminator to
hand and does not need a new one. Reaching a *staffed* review today requires all three of
`completion_attribution.recorded` (`:1444`), `commit_for_task_review(...).resolved` — which reads
evidence rows and nothing else (`:1472`) — and a reviewer the ladder can resolve excluding the
author. A single-agent loop fails the third by construction, and a loop that declared it needs no
evidence fails the second, which is F161. **The population that could lose something is therefore
narrow and specific: a documentless loop, in a project with a second eligible agent, whose agent
recorded evidence naming a commit.** Round 3 is to establish whether that population exists in the
corpus's own terms and whether any test covers it; this is an observation, not a clearance.

**The unstaffed report must also stay quiet.** `unstaffed` entries surface to the operator as steps
the flow could not take (`scheduler.py:1445-1480`); a loop's completed task is not a step anything
failed at, so it must not appear there.

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

### D7 — the landing action evaluates the gate before performing anything

Refused means nothing happened: no cleared assignee, no review row, no integration record. A
partially-applied landing would leave a task in `under_review` with no reviewer and no author hold,
which is worse than the three hops it replaces.

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
