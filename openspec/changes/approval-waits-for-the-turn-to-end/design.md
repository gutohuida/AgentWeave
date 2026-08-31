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
would invert the layering and probably cycle. The predicate belongs in a small module both can
import, or on `agent_lifecycle`, which already asks a similar question (`agent_lifecycle.py:39`).

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

### D9 — whether the evidence route shares the exposure is for R2/R3 to determine

Hypothesis: approving mid-turn on the evidence route merges the **stale pre-turn commit** named by
an accepted evidence row, with `restamp_run_footprints` correcting the row only after the merge has
happened. `_targets` (`task_integration.py:219`) does not filter on `reachable_from_main`, so the
stale sha would be handed straight to `integrate`.

The refusal is unconditional either way — it is a statement about when work is knowable, not about
which route resolves it. What the answer changes is whether a second reproduction is owed and
whether the requirement's rationale should name both routes.

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
- **Three answers to "is this agent working"** would exist after this (`_active_ptys`, `Run.status`,
  `agent_status.heartbeat_is_stale`). → R2 should decide whether the predicate belongs beside one of
  them rather than becoming a fourth.

## Migration Plan

None. No column, no schema change, no backfill. The behaviour change is a refusal that did not fire
before; nothing recorded needs reinterpreting.

Rollback is removing the check — the gate composes its categories, so a removed category leaves the
other four unchanged (`GateRefusal.detail`, `:115-124`).

## Open Questions

1. **Does the evidence route share the window?** (D9.) R2 or R3 answers by reading `_targets` and
   `restamp_run_footprints` together; a drive answers it definitively.
2. **Where does the liveness predicate live** so that `requirement_gate` need not import
   `api/v1/agent_trigger`? (D3.) Candidates: a new small module, or `agent_lifecycle`.
3. **Should the landing action exist for a flow's task too?** The three-hop cost is a loop's because
   a flow staffs its own reviewer. If a flow's review is unstaffable, the operator is in the same
   position — but that is F142's territory, already shipped, and widening scope here is how a change
   stops being reviewable.
