# Design — a refused review leaves nothing behind

Everything below was measured on 2026-09-12 against `autonomous/2026-09-12-daily` at `87dfbf4`,
unless it is labelled **read** (a `file:line` was read, not run) or **inferred**. The hub code at
`87dfbf4` is identical to `6468aed`, because `87dfbf4` changed one `.claude/loops` file.

**Scratch, all gitignored, all under `testbed/scratch/r1f319/`:**
- `test_zz_r1f319_scratch.py` holds the legs on the unmodified tree, the pending-state inventory,
  F320, the savepoint probes, and the rollback and loop prototypes as wrappers.
- `test_zz_r1f319_probe.py` records what a rollback expires.
- `test_zz_r1f319_ckout.py` records the checkout that a post-provisioning refusal leaves behind.

Re-run any of them with
`cp testbed/scratch/r1f319/test_zz_r1f319_*.py hub/tests/ && py -3.11 -m pytest hub/tests/test_zz_r1f319_scratch.py -q -s -p no:cacheprovider`,
then delete the copies. `_ckout.py` imports from `_scratch.py`, so copy both.

**The prototype** is `testbed/scratch/r1f319/turn_scheduler.proto.py`, a full copy of
`hub/hub/turn_scheduler.py` with D1, D3 and D4 applied. To reproduce R1's suite numbers:
1. `git worktree add --detach testbed/scratch/r1f319/wt HEAD`.
2. Copy the prototype over `wt/hub/hub/turn_scheduler.py`.
3. From `wt/`, run the test files listed in `testbed/scratch/r1f319/files.txt`. When pytest is
   run from `wt/`, `hub` resolves to `wt/hub/hub`. That was checked by printing `hub.__file__`.

**It is a design aid, not the implementation.** It returns tuples, it keeps an `if True:` where the
old `async with` stood, and it has none of the comments the implementation owes.

## D0 — The blast radius

**One place stages a review and then can refuse in the caller's session, and one caller commits
it.** Everything below comes from reading, and grep confirms the call sites.

**The commit points that make a refused dispatch's staging durable.** All three are in
`turn_scheduler.schedule_agent`'s `except TriggerAgentError` branch, and all use the dispatch's
own session `db`:
- `:349`, `await db.commit()` after writing `waiting_reason`. This is the one F319 names.
- `:357` and `:484`, `persist_event(...)`. Its `commit=True` default commits the session
  (`utils.py:71-72`). These are reached only for `queue_agent_paused` and `queue_entry_abandoned`.
- `:471`, `await db.commit()` after counting.

The rollback in D1 precedes all of them.

**The staging, inside the dispatch.** `agent_trigger.py:836` calls
`enter_selected_task(session, review_task, agent=agent, is_review=True)`.
- `scheduler.py:816` sets `task.assignee = agent`.
- `scheduler.py:828` calls `apply_transition(session, task, "under_review", operator())`.
- That sets `task.status` and adds a `TaskTransition` row (`task_transition_service.py:673-691`).
- It also calls `resolve_divergences_for_task` (`:701-703`). That call sets `resolved_at` on
  open divergences, stages an `EventLog` row (`commit=False`), and **broadcasts SSE immediately**
  (`run_divergence.py:91-103`). See D8.

**Every refusal the dispatch can raise after that staging.** Each is a `TriggerAgentError` into the
scheduler.

| site | refusal | flags | reach |
|---|---|---|---|
| `agent_trigger.py:843` | entry guard (`_guard_reviewer_is_not_the_author`, incl. §3.4 `:454-464`), 403 | request_level | **leg A** (measured) |
| `:858` ← `review_turn.py:195` | task not in project | request_level | read: the route resolves the task first |
| `:858` ← `review_turn.py:199` | no commit named (database) | request_level | the route pre-checks it (`agent_trigger.py:1438-1440`); the delivery-time timing gap is inferred |
| `:858` ← `review_turn.py:202` | not a git repository | request_level | **B0** (measured) |
| `:858` ← `review_turn.py:218` / `worktrees.py:546` | commit absent from the repository | request_level | **B1** (measured; live in F319) |
| `:858` ← `review_turn.py:220` / `worktrees.py:599-604` | review checkout path obstructed, or a git error | request_level | **B2** (measured; live in F319) |
| `:1049` | canonical context could not be written (`OSError`) | none | read; needs a filesystem failure |
| `:1105` | `UnsupportedRunnerError`, 501 | request_level | read; likely unreachable behind `:678`'s `SUPPORTED_RUNNERS` check (inferred) |
| `:1146` | the Hub does not know its own address | **transient** | **T** (measured); the startup re-drain, per `:1152-1157` |

**Every raise above `:836` precedes the staging.** Those are `:607`, `:616`, `:627`, `:637`,
`:651`, `:658`, `:679`, `:688`, `:700`, `:718`, `:774`, `:797`, `:810` and `:828`, plus
`_review_task_from_entries`'s two batching refusals (`:428`, `:443`, called at `:770`). For non-review
turns, `:860-965` (work_dir, the D8 collision, the workspace errors) also precede any write.
**Measured:** a non-review turn refused at `:1146`, the last raise site, has nothing flushed and
nothing pending in the session, and no commit happens inside the dispatch. A review turn refused
at `:1146` has flushed exactly `Task` (dirty) and `TaskTransition` (new). No `Run`, no binding and
no conversation write precedes a refusal. `bind_run_to_task` (`:1222`), `rebind_conversation`
(`:1219`) and `record_response_run` (`:1214`) all follow the last raise.

**Callers.**
- `trigger_agent_directly` has one production caller, `turn_scheduler.py:322`. Grep over `hub/hub`
  finds no other. Twenty-five test files call it directly.
- `enter_selected_task` has three callers.
  - `agent_trigger.py:836`, the dispatch. It is uncommitted, and it is the one this change governs.
  - `scheduler.py:2794`, `_do_fire_job`. It is committed with the queue entry at `:2891`, **before**
    `schedule_agent` at `:2918`.
  - `scheduler.py:3156`, `_fire_additional_selection`. Its own session commits before
    `_start_additional_turns`.
- `run_divergence.py:458` writes `task.assignee` directly. `_queue_response` queues the entry, and
  the caller commits before `schedule_agent` at `:840`.

The last three are **pre-dispatch** staging (D7).

**Other commits after a refused status move, checked and not affected.** A refused `PATCH /tasks`
leaves the task untouched. That is measured by the passing
`test_the_evidence_author_cannot_be_entered_as_the_reviewer`. `agent_actions.py:708` rolls back.

**Who consumes `ScheduleResult`, and so is affected by D4 and D5.**
- `agent_trigger.py:1511-1580`, the route's started, refused and queued answers.
- `scheduler.py:2919` and `:3058`. Each marks its `JobRun` failed on
  `waiting_reason and terminal_failure`.
- `checkpoint_cutover.py:156-175`, which logs the result.
- `checkpoints.py:283`, the `continue` route.

Every other caller discards the result. They are `accounting.py:72`, `agents.py:2140`, `:2521`,
`inbound_queue.py:107`, `:253`, `messages.py:307`, `questions.py:399`, `:504`,
`run_divergence.py:840`, `run_reconciliation.py:162` and `turn_scheduler.py:538`.

## D1 — The scheduler discards the refused dispatch's transaction before it records the refusal

The refusal branch of `schedule_agent` begins with `await db.rollback()`. It then re-reads what it
needs (D3), and does exactly what it does today: write `waiting_reason`, classify, count or abandon,
emit, and build the `TurnRefusal`.

**This is the mechanism the shipped design already claimed, made true where it was false.**
`2026-08-28-a-review-started-by-hand-can-finish` design D10 put the staffing before
`prepare_review_turn`, so that a refused request provisions nothing. It argued that *"the staffing
therefore joins the dispatch's transaction as pending state, and any refusal raised later …
abandons the transaction before the commit"*. The comment at `agent_trigger.py:788-793` repeats it.
Every clause is true of `trigger_agent_directly`, and its caller then commits that transaction. The
same change's D11 found the scheduler catching the refusal. It fixed the *answer* the operator got
and not the commit. The two F306 tests that assert the holder is empty after a refusal pass only
because their sessions close without committing, and their own docstrings (`:474-480`, `:517-520`)
now say so.

**Why the whole transaction, and not only the review's rows.**
- It does not depend on the refusal. It covers all six refusals after the staging, including the
  transient one (T) and the two that need a filesystem failure. The verdict says *whichever
  refusal*.
- It does not depend on the staging being the review's. The next write anyone adds above a raise
  site in `trigger_agent_directly` is discarded by the same line. Today there is none, as measured
  in D0.
- It costs nothing the scheduler wanted. Measured: its session holds nothing pending when it makes
  the call. Every read it made before the call is re-made in D3.

**Leg A is closed without touching the guard.** `enter_selected_task` must write the assignee
first, or the flow refuses itself (F70, `scheduler.py:810-815`). So the guard judges a staged
assignee. The guard's refusal is correct. What was wrong was that the assignee it judged became
durable. After D1 the guard is still the authority, and the §3.4 fallback is unchanged.

**F97's reason for the commit is kept.** The refusal's words are written to the entries *after*
the rollback, and committed. Measured: B1 and A leave the sentence on the entry on every pass. At
the third pass the entry is `withdrawn`, with `abandoned_reason` naming it, and
`queue_entry_abandoned` is persisted.

## D2 — Alternatives rejected

**(a) Ask the repository-reading refusals before `enter_selected_task` stages anything.** These
are `is_git_repo`, `resolve_review_commit` (`git rev-parse --verify`), and `review_path(...)`
existing without `existing_review_checkout`. All three can be asked read-only, so this is
feasible for B0, B1 and B2. It was rejected for four reasons.
- **It does not close A**, which is a refusal *inside* the staging. To close A the dispatch would
  also have to call `review_dispatch_refusal` before staging. That is a second place asking the
  guard's question in the same function, with the guard behind it.
- **It does not close T** (`:1146`), or the `OSError` and 501 refusals. Those are raised after the
  checkout is provisioned, and they can only be learned by doing the work, not by asking first.
- **It restates `ensure_review_checkout`'s own tests beside it.** That is two statements of one
  rule, and the product's own comments warn against that shape
  (`scheduler.py:801-804`, `_loop_queue_order`).
- **It races.** A commit pruned between the probe and `git worktree add` still refuses after the
  staging.

`DIRECTION.md` 2026-09-13 anticipated this: *"a fix that reorders the repository checks does not,
on its own, close A"*.

**(b) A savepoint around the staging** (`session.begin_nested()`). Measured, SP and SP2 in the
scratch file:
- A savepoint that is **rolled back** behaves as expected.
- A savepoint that **succeeds**, and was opened when only a `SELECT` had run, **commits**. Another
  session read `assignee='released'` before the outer commit, and the outer `rollback()` did not
  undo it.

That is SQLite's documented behaviour: releasing the outermost savepoint commits. It is also
pysqlite's known defect: no `BEGIN` is emitted before a `SELECT`, so the savepoint becomes the
outermost one. Using savepoints safely would need SQLAlchemy's documented pysqlite/aiosqlite hook
(`isolation_level=None` plus an emitted `BEGIN`) on `engine.py`. That changes the transaction
behaviour of every session in the Hub to fix one branch. No code in `hub/hub` uses `begin_nested`
today (grep).

**(c) Compensate: put `assignee` and `status` back, and delete or reverse the transition row.**
The history is append-only (`task-lifecycle-governance`, *"Every accepted transition is recorded
append-only"*). There is no `under_review -> completed` edge to reverse through
(`task_transitions.py:134-140`: `completed` reaches `under_review` and `rejected`, and
`under_review` reaches the verdicts). And the shipped D10
already rejected compensation, for its own reason: *"a compensating delete is a second thing to get
right"*.

**(d) Stage last.** Move `enter_selected_task` below every raise site, just before the binding,
and ask `review_dispatch_refusal` read-only before provisioning, so D10's order still holds. This
was rejected for three reasons.
- It moves the staging below `_render_hub_agent_context` (`:1007`), so the reviewer's canonical
  context would be rendered from the task as it was before it entered review. That is inferred, not
  measured. The review block itself renders from `ReviewContext`, not from the task row
  (`agents.py:1620`, read). R1 did not read whether `_get_session_data` renders task status.
- It is a larger reorder of a 700-line function, which D10 and D8 of two earlier changes arranged
  deliberately.
- It leaves the hazard in place. The scheduler would still commit whatever the dispatch left
  pending.

It would avoid D8's escaping SSE broadcast, and that is its one advantage.

**(e) Roll back inside `trigger_agent_directly`**, wrapping its body so that any
`TriggerAgentError` rolls back the session before re-raising. With one caller, the effect is the
same. It was rejected because the session and its commit belong to the scheduler. A callee that
rolls back its caller's session discards state it cannot see, and the scheduler would still have to
re-read its expired rows (D3). The one-caller premise is made durable instead, with a source-scan
test (tasks §2.4). A second caller has to meet the reason.

**(f) Roll back only when the refused turn was a review.** This was rejected because it depends on
the staging being the review's, which is the property (b) of D1 buys.

## D3 — What a rollback does to the scheduler's rows, and why they are re-read

**Measured (`_probe.py`):** after `rollback()`, all 26 column attributes of a loaded
`InboundQueueEntry` are expired. The session's `expire_on_commit=False` (`engine.py:163`) does not
cover a rollback.

- **The `selected` entries happen to recover.** Measured: setting `waiting_reason` and committing
  reloads the row inside the commit, leaving 0 attributes expired. A naive rollback prototype,
  one that re-reads nothing, passed B1 over three passes.
- **The rest do not.** `entries` outside `selected`, and `conversation`, are still expired, and
  `other_input_would_have_run_elsewhere` reads them (`turn_scheduler.py:153-222`, reached only for
  `agent_workspace_unavailable`). **Measured:** the naive rollback fails five tests with
  `sqlalchemy.exc.MissingGreenlet`:
  - `test_a_blocked_agent_workspace_holds_its_input.py::test_a_blocked_agent_workspace_holds_the_operators_message`
  - `test_a_blocked_workspace_counts_where_input_could_run.py::test_a_binding_inherited_from_the_thread_spends_the_heads_attempts`
  - `…::test_a_second_unbound_conversation_does_not_make_the_head_expendable`
  - `…::test_a_task_bound_entry_waiting_elsewhere_spends_the_heads_attempts`
  - `…::test_an_entry_in_the_refused_batch_naming_a_vanished_task_does_not_count`

So the implementation does not rely on the incidental reload.
- It captures `selected_ids` and `conversation_id` **before** the call.
- After the rollback, it re-reads `selected` with `InboundQueueEntry.id.in_(selected_ids)`, in
  the captured order.
- It re-reads `entries` with `queued_entries(db, project_id, agent)`.
- It passes `conversation_id` wherever `conversation.id` was read.

A newly arrived entry can appear in the re-read `entries`. It is harmless there:
`other_input_would_have_run_elsewhere` then answers about the queue as it now is.

## D4 — F320: the pass goes on only after it gave up on something

**Shape.** `schedule_agent`'s body becomes one attempt, `_attempt_turn(db, project_id, agent)`.
It returns the `ScheduleResult`, whether a dispatch was attempted, and the entries it gave up on.
`schedule_agent` holds the same per-agent lock and the same session, and repeats the attempt
**only while the previous attempt gave up on at least one entry**.

**Why only then.** Giving up is the one outcome that changes what the next attempt would select:
the head has left the queue. Every other outcome would repeat identically, or has its own release.
- A **started turn** ends the pass, as today.
- A **transient** refusal does not count (the D8 collision at `agent_trigger.py:928-935`, and
  `:1146`). Repeating it would busy-loop. The run-end re-drain (`agent_trigger.py:2422-2451`,
  F90) is its release. Measured, `transient_head`: one call, and the head's attempts are
  unchanged.
- An **agent-wide** refusal (`agent_wide`, F114) holds every entry. Repeating it would count
  nothing and deliver nothing.
- An attempt **counted and not given up on** must not repeat. If it did, one pass would spend all
  three of an entry's attempts, which is F114's failure: the operator's input destroyed by one
  schedule. Measured, `behind_fresh_refused`: the entry behind is counted **once** and stays
  `queued`.
- An **early return** (queue empty, hop budget, token budget, no conversation, conversation
  unavailable) has nothing to try.

**Rejected alternatives.**
- **Fall through to the next conversation inside the same attempt.** That is a second copy of the
  selection rules: the hop filter, the kind filter (F66), the cap, and the token budget. A fresh
  attempt reuses them verbatim.
- **Call `redrain_queued_agents` after giving up.** It calls `schedule_agent` for this same agent
  while that agent's `asyncio.Lock` (`_lock_for`, `turn_scheduler.py:63-64`) is held. That lock is
  not reentrant, so the call would deadlock. This is inferred from the lock type, not run.
- **Schedule a deferred re-drain as a background task.** It runs outside the lock, a test cannot
  observe that it finished, and it is the start of the tick that `:2433` says does not exist.
  Introducing one is a different decision.

**Termination.** A repetition begins only after an entry was set `withdrawn` and committed, and
`queued_entries` selects `state == "queued"` only. An entry is given up on when its count reaches
`DELIVERY_ATTEMPT_LIMIT` (3, `inbound_queue.py:178`), so it had at least 2 attempts before that
pass. Could anything reach 2 attempts during the pass?
- An entry that arrives during the pass has 0 attempts (`models.py:571-573`, `default=0`).
- `return_run_entries` can raise a count, but it needs a run of this agent to fail. There is none:
  every attempt starts by refusing a running agent, and the lock is held.

So every entry the pass gives up on was already queued when the pass began. The number of
repetitions is at most the number of entries queued at the start. The implementation states that
bound as a loop limit, `len(initial queued) + 1` attempts. The argument above says the limit is
never reached, and a test pins that it is not (tasks §1.8, *every entry refuses*). Measured,
`all_refuse`: three entries at attempts 2, each refused, take three calls. All three are
`withdrawn`, and the pass ends.

**An entry can be counted twice in one pass**, and R1 leaves it that way. The case is an entry that
rode in the turn whose head was given up on, in the same conversation, and is then refused again
as a turn of its own. Each count is a real refused dispatch. The alternative is to skip entries
already counted in this pass. That would hold a rider that would have started on its own, which is
the starvation F320 is about. **R2 should attack this.**

## D5 — What the pass reports

`schedule_agent` returns **the last attempt's result, except where that attempt found the queue
empty. In that case it returns the result of the attempt that gave up on the last entry.**

`"queue is empty"` takes `terminal_failure=True` by default, as do all six early returns
(`TurnRefusal`'s docstring, `turn_scheduler.py:38-42`). Reported after a give-up, it would mark a
job's `JobRun` failed with *"queue is empty"* instead of the refusal that emptied the queue
(`scheduler.py:2919-2925`). The other early returns describe what the remaining input is waiting
on, which is the true answer. The last attempt's result is therefore reported.

**What this means for each consumer.** R1 read each one and ran none.
- **The route (`agent_trigger.py:1520-1581`).**
  - A request's input arrives with 0 attempts, so it is never given up on in the pass the
    request triggered.
  - If the pass gives up on an older head and then starts the request's turn, the answer is
    *started*. Today it is *"queued behind other input"*, and the input is never delivered (F320).
  - If the pass then refuses the request's own turn for what it asked, the answer is that refusal,
    and the input is withdrawn. Today it is *queued*. F108 and *"A refusal is reported only to the
    input it is about"* both hold, because the `TurnRefusal` names the entries of the attempt that
    produced it.
- **The firing (`scheduler.py:2918-2925`).** Its entry is fresh, so the reasoning is the same:
  its `JobRun` is failed only by a refusal of a turn its own entry was in. Today a head the firing
  never queued can fail it.
- **`continue` and cutover** read `response.conversation_id` and `waiting_reason`, unchanged in
  shape.

## D6 — The one existing test whose expectation changes

`hub/tests/test_a_blocked_workspace_counts_where_input_could_run.py:227`,
`test_a_blocked_task_checkout_still_counts_with_nothing_waiting`, asserts
`[("withdrawn", LIMIT), ("queued", 0)]`. Its helper `_schedule_to_the_limit` (`:144-147`) patches the
trigger to refuse **every** call with a flagless task-checkout refusal, then schedules three
times. After this change the third schedule gives up on the head and goes on to the second entry,
in another conversation. The mock refuses that entry too, so it is counted once and the pass ends.
The expectation becomes `[("withdrawn", LIMIT), ("queued", 1)]`.

The test's subject is the head: it counts, and it is given up on. That subject is unchanged. The
second number records that the entry behind was attempted, which is F320's verdict. The
implementation says so in the test's docstring, and names this change.

Measured: this is the only failure among 748 tests in the 57 files that touch the path
(`files.txt`), run against the prototype. Chunk results are in `proto_00.log` to `proto_02.log`.
**No existing test encodes F319.** No test asserts that a refused dispatch leaves the task staged,
and none fails when it stops doing so. So the new tests are the whole of this change's coverage
of the rollback, and tasks §4 mutates them.

## D7 — The flow's staging, and a divergence's, are not the dispatch's

A flow firing records its reviewer in the same commit that queues the turn (`scheduler.py:2794`,
`:2891`), and it does so on purpose: it is what takes the task out of the reviewable pool, so the
next tick does not offer it again (F45, `scheduler.py:542-547`). A divergence restaff does the same
(`run_divergence.py:453-470`). When the dispatch of that turn is then refused, D1's rollback
discards nothing, because the dispatch staged nothing new. `enter_selected_task`'s `under_review`
branch is a no-op, and D9's holder check passes on equality. The task is left as the firing left
it, which is *"as it was before the dispatch"*.

**Why not also undo the firing's staging.**
- It was committed, as a decision of the flow, into an append-only history, and no edge reverses
  it (D2(c)).
- The flow already reports this state. Once the refused entry is given up on, no turn is pending
  or running on the task (`run_task_binding.py:267-309`). The next firing then names it under
  `agent-flows`' *"A review nobody is doing is named, whatever its history"*, through
  `_wedged_review_reason` (`scheduler.py:1732-1748`), which names the task, the agent, and three
  exits.

That surfacing is read, and not driven by R1.

**This reading of the verdict's *"whichever path (the route, or the scheduler)"* is the
proposal's most arguable choice.** R1 reads *"the scheduler"* as `turn_scheduler`, as F319's own
title does (*"refused on the scheduler path"*), and as the decision's third bullet does (*"Both live
in `turn_scheduler.py`'s refusal branch"*). If the operator meant the flow's scheduler as well, that
is a larger change, and a different one: it is a question about undoing a committed firing.

## D8 — What a rollback cannot take back

- **An SSE broadcast.** `resolve_divergences_for_task` broadcasts `run_divergence_resolved` at
  staging time (`run_divergence.py:103`). The row it closes and the event it stages are rolled
  back, but the broadcast has already gone. The UI invalidates and refetches, so it re-reads a
  divergence that is still open. This is inferred from the code and not reproduced. It needs a
  task with an open divergence to be refused a review from `completed`. Left.
- **The review checkout on disk.** A refusal raised **after** `prepare_review_turn` provisions it
  (`:1049`, `:1105`, `:1146`) leaves `.agentweave/reviews/<reviewer>` registered. Measured for
  `:1146` (`_ckout.py`). That breaches the main scenario *"A refused review leaves no checkout
  behind … refused for any reason"*. For the transient case, the checkout is the one the retry
  will re-point (`worktrees.py:599-605`). For the other two, it waits for the next review by that
  reviewer. It is out of this verdict, which is about the task, so it is **filed as F326 (D)** and
  not fixed here.
- **`seed_repo_excludes`** (`review_turn.py:210`) writes `.git/info/exclude`. It is idempotent and
  harmless.

## D9 — The delta is ADDED, not MODIFIED

The main requirement *"Dispatching a review staffs the task, whichever path dispatched it"*
(`task-lifecycle-governance:1796`) already says a refused review leaves the task *"exactly as the
refusal found it"*, and its scenario *"A refused review leaves no checkout behind"* says the same of
status and holder. F319 is a breach of that text, not a gap in it.

A MODIFIED block would have to reproduce that requirement and keep every scenario, including one
R1 has measured false for post-provisioning refusals (D8, F326). Re-asserting it knowingly in a
change's own delta would make the delta wrong on arrival. So the delta **adds** a requirement
stated where the existing one is silent:
- refusals raised **when queued input is delivered**, not only when a request is answered;
- refusals raised **during** the staging (A) and **after** it (B, T);
- **deferrals** that clear on its own;
- and where the refusal's words are recorded.

The existing requirement is left as it stands. F326's fix owns its checkout scenario.

## D10 — What the operator is told, before and after

| leg | answer to the request | what the queue records | event | the task, after |
|---|---|---|---|---|
| B0/B1/B2, route | `409` + the refusal's sentence (F108, `agent_trigger.py:1524-1554`) | entry `withdrawn` (`withdraw_refused_entry`) | `queue_entry_withdrawn` | **today** `Under Review`, held by the refused reviewer; **after** as before the dispatch |
| A | `200 queued`: the route's check passes at queue time (the timing gap) | `waiting_reason` = the guard's sentence, every attempt; `withdrawn` at 3 | `queue_entry_abandoned` at 3 | **today** `Completed`, held by the refused author; **after** as before |
| T | `200 queued` | `waiting_reason` = the address sentence; attempts unchanged | none, by design (`turn_scheduler.py:493-497`) | **today** `Under Review`, held; **after** as before |
| flow firing, any | none: no request | same as A or T | same | as the firing left it (D7) |

The fix changes the last column only. What the operator is told stays the same, and it is recorded
**after** the rollback, so it survives it.

## D11 — Open, for R2, R3 and the operator

1. **D7's reading of *"whichever path"*.** The flow and divergence staging is excluded. Attack
   this first.
2. **The rider double-count** (D4). Is one pass counting an entry twice acceptable when it rode in
   the given-up turn?
3. **D5's exception is keyed on the `"queue is empty"` string.** The implementation should key it
   on the attempt reporting "nothing was tried", not on the words. The prototype compares the
   string.
4. **D2(d) rests partly on an inference.** The review block does not read the task's status. R1
   did not read whether the session data the renderer includes does. If nothing depends on it,
   (d)'s first reason falls, and its other two stand.
5. **D8's SSE broadcast is not reproduced.**
6. **Leg A's live timing.** The live harness reached attempt 3 in 30 s through other agents' runs
   ending (F319). The drive in tasks §5 makes those passes deterministic with `continue`, which
   counts an attempt (`test_continue_does_not_consume_the_work_it_offers_to_start` covers only the
   agent-wide case). That is read, not run.
