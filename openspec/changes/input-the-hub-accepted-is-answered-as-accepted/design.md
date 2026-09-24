# Design — input the Hub accepted is answered as accepted

## Operator review, 2026-09-24

Adversarial Opus review: `spec-queue/tracks/reviews/B11-2026-09-24.md` §4, APPROVE WITH FIXES. The
operator's decisions (same file, head): **F349 absorbs the loop/flow/job firing path**, and
**retries are for transient errors only**. Applied here:

- **HIGH, the firing path** (`scheduler.py:3444`, `:3467`, `:3471`, `:3514`, `:3605`): folded in as
  D6. Both scheduler sites use `schedule_accepted`, every post-commit event of a firing uses
  `persist_accepted_event`, and a non-terminal `waiting_reason` leaves the `JobRun` in progress, not
  `failed`. Tasks 1.10-1.13. That is a firing that has not started *yet*, so the two requirements that
  say when a firing is failed get MODIFIED deltas that say so (`loop-firing-accountability`,
  `runtime-diagnostics`).
- **MEDIUM, the retry was not bounded**: D1 now classifies the error. Only a transient one
  (`OperationalError`, or a message naming a locked database) is retried. Anything else is logged
  once, is not retried or deferred, and leaves the entry queued. Tasks 1.14-1.15.
- **LOW, restart**: D2 now says the pending retries and the deferred set live in memory, and names what
  picks a queued entry up after a restart.
- **LOW, the requirement text**: it said "whatever fails after the input was queued". It now carries
  the exception D3's table already accepted: a withdrawal that fails after a refusal still answers 500.
  Open question 1 is closed that way.

Every line citation below was re-checked against `09127ba` (HEAD on 2026-09-24). None had drifted.

**Built on the recommended answer to B11's F349 question** (ROUNDS.md D13, *"F349 remainder"*):
**answer accepted input as accepted, and make that true by retrying the start in the Hub.** If the
operator prefers to keep a 500 (option c in D5), this change is withdrawn and F349 stays open.

## Context — measured on `ce086b6`, re-checked on `09127ba`

| Fact | Where |
|---|---|
| The entry is committed before anything else the route does after it | `hub/hub/api/v1/agent_trigger.py:1587` |
| Then, unguarded: `persist_event`, `sse_manager.broadcast`, `schedule_agent` | `:1595`, `:1596`, `:1600` |
| `schedule_agent` opens its own session under a per-agent lock | `hub/hub/turn_scheduler.py:283` |
| Its only `except` is `TriggerAgentError`; nothing catches a database error | `turn_scheduler.py:424`; `grep -n "except Exception" hub/hub/turn_scheduler.py` finds nothing |
| `ScheduleResult` can already say "not started, and why" without a refusal | `turn_scheduler.py:58-62` (`waiting_reason`, `refusal=None`) |
| Nothing retries a queued entry on a timer | F349's foot; re-drain call sites listed in the proposal |
| A deferred-schedule set exists, drained by the next request the Hub serves | `hub/hub/run_reconciliation.py:160-212`; `hub/hub/main.py:516-526` |
| The same unguarded shape at six more sites (R2 widened from four) | `messages.py:318`, `agents.py:2257`, `questions.py:212`, `inbound_queue.py:253`, `accounting.py:78`, `agents.py:2693` |
| (R3) Five of those six write an event on the route's session after the commit and before the schedule | `messages.py:285` and `:295` (and `:306` when suspended), `agents.py:2250` and `:2252`, `questions.py:207`, `inbound_queue.py:248`, `accounting.py:64`. Not `agents.py:2693` |

## D1 — `schedule_accepted` never raises

```python
async def schedule_accepted(project_id: str, agent: str) -> ScheduleResult:
    """Schedule input that is already committed. A failure here is not the request's failure."""
    try:
        return await schedule_agent(project_id, agent)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if is_transient(exc):
            logger.warning("Could not start a turn for %s/%s after accepting input: %r", project_id, agent, exc)
            retry_schedule(project_id, agent)                   # D2
            return ScheduleResult(
                waiting_reason="accepted; the Hub could not start a turn yet and will try again",
                terminal_failure=False,
            )
        logger.exception("Could not start a turn for %s/%s after accepting input", project_id, agent)
        return ScheduleResult(
            waiting_reason="accepted; the Hub could not start a turn for it, and it stays queued",
            terminal_failure=False,
        )


def is_transient(exc: BaseException) -> bool:
    """A failure that can clear on its own: a busy or locked database."""
    return isinstance(exc, (sqlalchemy.exc.OperationalError, sqlite3.OperationalError)) or (
        "database is locked" in str(exc).lower()
    )
```

**(Operator review) Transient only.** A retry is honest only for a failure that can clear without
anyone changing anything. On SQLite that is a busy or locked database, which reaches the Hub as
SQLAlchemy's `OperationalError` wrapping `sqlite3.OperationalError("database is locked")`. Anything
else (a bug, an integrity error, a missing row) fails the same way on every attempt. Retrying it
forever surfaces nothing and hides the defect, which is the review's MEDIUM. Such an error is logged
**once**, with its traceback, where `schedule_accepted` sees it. It is not retried and not deferred.
The entry stays `queued`, so the answer "accepted" is still true. The next re-drain the Hub already
runs (project open, settings save, relocate, another run's end) tries again. The answer's
`waiting_reason` does not promise a retry that will not happen. If a retry in D2 meets a
non-transient error, the same rule applies: it is logged once and the retry stops.

The exception's own text is logged, not returned: a `database is locked` or a stack of SQL is not a
sentence the operator can act on, and the message they need is that nothing is lost.

`CancelledError` is re-raised: a request cancelled by its client is not a scheduling failure.

## D2 — The Hub retries; the deferred set is the backstop

`retry_schedule(project_id, agent)` starts one background task per `(project, agent)` (a second
call while one is pending does nothing). **(R3)** The pending tasks are held in a module-level dict
keyed by the pair and removed in the task's done-callback: that dict is the "pending" test, and it
is also the strong reference asyncio needs (a bare `asyncio.create_task`, as `main.py:526` does for
the drain, may be collected before it runs). It sleeps 1 s, 5 s, then 30 s, calling `schedule_agent`
after each, and stops at the first call that does not raise. After the last failure it adds the pair
to `run_reconciliation._deferred_schedules` through a new public `defer(agents)`, so the next request
the Hub serves drains it (`main.py:516-526`). The delays are module constants so tests set them to 0.

The drain itself calls `schedule_agent` unguarded today (`run_reconciliation._schedule_now`,
`:184-187`), inside a fire-and-forget task, and it empties the set before its first `await`
(`:205`). A pair whose drain raises is therefore lost. `_schedule_now` switches to
`schedule_accepted`, so a failed drain re-enters D2's retry rather than vanishing. Under a
persistent failure that loops once per request served, which is the right amount of retrying for a
Hub that is serving requests and cannot write.

**(Operator review) Only transient errors reach this loop, and a restart forgets it.** A retry
stops at the first call that does not raise *or* raises a non-transient error (logged once, D1). The
"once per request served" loop above therefore needs a database that stays locked, and each cycle
takes 36 s. The pending-retry dict and `_deferred_schedules` are both **in memory**. A restart
drops them. The entries themselves are durable rows in `queued`, so nothing is lost, but nothing in
this change re-arms them at start. What picks them up after a restart is what picks up any queued
entry today: `redrain_queued_agents` on project open (`projects.py:316`), settings save (`:534`) and
relocate (`:603`), or another run's end. `reconcile_interrupted_runs` re-drains only agents that had
a run in flight (`run_reconciliation.py:178`). A `JobRun` left in progress by a pending retry (D6) is
marked failed by `reconcile_stale_job_runs` at start (`run_reconciliation.py:276-277`), as any
firing with no live run behind it is today.

`schedule_agent` is idempotent for an agent with nothing queued (it answers "queue is empty") and
refuses a busy agent, so a retry that races another drain does no harm. The per-agent lock at
`turn_scheduler.py:283` already serialises them.

**Why not a periodic sweep:** a timer that drains every queue is the tick the codebase has argued
against several times (`agent_trigger.py:2211-2222`, `:2640-2661`), and a failure here is an event
with a known agent. A retry keyed to it is enough.

## D3 — The trigger answers from what happened

At `agent_trigger.py:1595-1600`:

- `persist_event` and the broadcast move inside a `try` that logs and continues. The broadcast still
  runs if the persist raised, since the panel is what tells the operator their input is queued.
- **(R2) The request's session after a failed persist.** `persist_event` commits on the route's own
  `session` (`utils.py:72`). A failed commit leaves that session needing a rollback, and the refusal
  branch below reuses it (`withdraw_refused_entry(session, …)`, `:1625`): a `PendingRollbackError`,
  the very 500 this change removes. And a rollback expires every loaded row whatever
  `expire_on_commit` says (the trap `turn_scheduler.py:402-405` documents), so reading
  `conversation.id`, `conversation.provider_session_id` or `entry.id` afterwards is a lazy load in
  async code (`MissingGreenlet`). So: capture `entry_id`, `conversation_id` and
  `provider_session_id` as plain values right after the entry commit (`:1587`); in the `except`,
  `await session.rollback()`; every later line reads the captured values.
- `scheduled = await schedule_accepted(project_id, body.agent)`.

Everything after `:1600` already reads `scheduled` and answers `running` or `queued` with a reason.
With D1's result (`response=None`, `refusal=None`, a `waiting_reason`), the existing final branch
(`:1660-1670`) answers **200** `status: "queued"` with that reason and this request's
`queue_entry_id`. No new answer shape.

**What the route returns when each call raises:**

| Raises | Today | After |
|---|---|---|
| The entry commit (`:1587`) | 500, nothing queued | unchanged, and true |
| `persist_event` (`:1595`) | 500, input queued, never scheduled | 200 `queued` or `running`, per the schedule |
| `schedule_agent` (`:1600`) | 500, input queued, never retried | 200 `queued`, reason D1, retried (D2) |
| `withdraw_refused_entry` or the refusal's `persist_event` (`:1625-1643`) | 500 | unchanged: out of scope, and it raises before a refusal the caller is owed (see Open question 1) |

**A start that raised after its run began.** If `schedule_agent` raised after a run took the input,
the entry is `delivered`, and "queued" would be false. D1 cannot see that. So after D1 returns its
failure result, the route re-reads the entry in a fresh session. If it is `delivered`, the answer is
`running` with `delivered_in_run_id`. If the re-read raises too, the answer stays `queued`: the commit
succeeded, so "accepted" is the one thing known to be true.

## D3a (R3) — A post-commit event is written on its own session and never raises

R2's rollback-and-capture step fixes the trigger alone, and it has to be repeated by hand at each
route whose answer reads ORM rows (`messages.py` returns `msg`, `inbound_queue.py:254` refreshes
`entry`). The other five routes of D4 have the same hazard **before** the schedule: a failed
`persist_event` there raises out of the route, so neither `schedule_accepted` nor any retry runs,
which is F349's own defect (queued, never started) under the likeliest failure, a locked write.

One helper, beside `persist_event` in `hub/hub/utils.py`:

```python
async def persist_accepted_event(project_id, event_type, data, *, agent=None, severity="info", loop_id=None) -> None:
    """Record an event about input already committed. Its own session: a failure here cannot
    poison the caller's, and nothing the caller loaded is expired."""
    try:
        async with async_session_factory() as own:
            await persist_event(own, project_id, event_type, data, agent=agent, severity=severity, loop_id=loop_id)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Could not record %s for %s after accepting input", event_type, project_id)
```

- `async_session_factory` is imported inside the function (as `turn_scheduler` imports it at module
  top, `utils` must not import `db.engine` at module top if that would cycle; the test suite already
  runs every route and the scheduler on that same factory, `hub/tests/conftest.py:77`).
- Every **post-commit** `persist_event(session, …)` at the seven sites becomes
  `persist_accepted_event(…)`. The broadcast beside each is unchanged and still runs.
- The trigger (D3) uses the same helper, so the route's `session` never holds a failed commit. R2's
  captured-values-and-rollback step is then not needed; it stays correct if an implementer prefers
  it, but the helper is the one rule for all seven sites. Task 1.9 still pins the outcome.
- Not for a `commit=False` event (a passenger in the caller's transaction): those belong to B9's
  `an-event-is-announced-only-once-its-write-is-committed`, which does not touch these seven sites.

## D4 — The other six sites

Each calls `schedule_accepted` in place of `schedule_agent` and ignores the result, as it already
ignores `schedule_agent`'s, and writes its post-commit events through D3a's helper.

**(R2) Two more post-commit sites of the same shape**, from `grep -rn "schedule_agent(" hub/hub`:
the token-budget `PUT` (`accounting.py:78`, a loop over every agent with queued input after the
budget commit at `:62`, where one raise also skips every later agent) and the runner rebind in the
agent PATCH (`agents.py:2693`, after the commit at `:2676`). Both switch to `schedule_accepted`, so
the routes beside the trigger are **six**, not four. **Not in scope:** `checkpoints.py:334` ("run
now": nothing is committed before it and scheduling *is* its answer, so a failure there is truthfully
a failure), and the non-route callers (`scheduler.py:3471, 3605`, `run_divergence.py:874`,
`checkpoint_cutover.py:156`, `turn_scheduler.py:713`), which run in background passes with their
own handling. Their answers (the message, the answer, the released entry) describe
what they committed, and are already true once the call cannot raise.

**(Operator review)** `scheduler.py:3471` and `:3605` have moved out of that list and into D6.
`run_divergence.py:874`, `checkpoint_cutover.py:156` and `turn_scheduler.py:713` stay out.

## D6 (operator review) — The loop, flow and job firing path

`JobScheduler._do_fire_job` (`scheduler.py:2987`) has the trigger's shape, on the job's own
`session`:

| Line | What | What happens if it raises |
|---|---|---|
| `:3444` | `session.commit()` lands the entry, `run.status = "in_progress"` and the job's counters | nothing queued; the `except` records `failed`, and that is true |
| `:3457` | `_emit_loop_edit_applied(session, …)`, a `persist_event` that commits | the `except` (`:3514`) marks the `JobRun` failed, and the entry, already committed, is queued and later runs |
| `:3467` | `persist_event(session, …, "queue_entry_queued", …)` | same, and the `except`'s own `persist_event` (`:3521`) commits on the failed session: `PendingRollbackError`, which escapes `_do_fire_job` |
| `:3471` | `schedule_agent` | the `JobRun` is marked `failed` while its entry is queued and runs later. Nothing retries it |
| `:3492` | `persist_event(session, …, "job_fired", …)` | the `JobRun` is marked `failed` although its turn **did** start |
| `:3605` | `_start_additional_turns` calls `schedule_agent` for each extra selection, and its `except` (`:3606`) logs and moves on | the selection's entry stays queued with nothing to retry it; its `JobRun` stays `in_progress` until a restart fails it |
| `:3757`, `:3767`, `:3790` | `_stage_selection` commits the extra selection's rows, then two `persist_event`s on its session | `_stage_additional_selections` (`:3579`) logs and skips it, so its turn is never started though its entry is queued |

The fix is the same two helpers:

- Every post-commit event of a firing goes through `persist_accepted_event`: `:3467`, `:3492`,
  `:3767`, `:3790`, and `_emit_loop_edit_applied` (`:2374`) at `:3457`. `persist_accepted_event`
  therefore also takes `loop_id` and passes it through, since `loop_edit_applied` is recorded
  against its loop (`:2385`). The SSE broadcasts beside them are unchanged.
- `:3471` and `:3605` call `schedule_accepted`. D1's result has `terminal_failure=False`, so the
  existing test at `:3472` (`waiting_reason and terminal_failure`) already leaves the `JobRun`
  **in progress**. It is not marked `failed`. That is the operator's rule: a non-terminal
  `waiting_reason` is a firing that has not started yet, not a failed one. The same holds for an
  extra selection at `:3611`. A terminal refusal still records `failed` with its reason, as now.
- **After `:3444` the `except` no longer records the firing as failed.** A local `accepted = True`
  is set right after the commit. If anything later still raises (the terminal-refusal commit at
  `:3478` is the one database write left on `session`), the `except` rolls `session` back, logs, and
  leaves the `JobRun` as it stands, because the entry is queued and will run. Before `:3444` it
  records `failed`, as now, after a rollback so that its own `persist_event` does not meet a failed
  session.

**Why in-progress is not a lie here.** `loop-firing-accountability` says a firing SHALL NOT be
reported running once it is known that no agent was started for it. A firing whose start raised a
transient error has a retry pending (D2). It is not known that no agent will start. A non-transient
error leaves the entry queued for the next re-drain, with the same answer. The `JobRun` reaches a
terminal state when its run ends (`finalize_job_run_for_conversation`) or, if no run ever starts,
at the next start (`reconcile_stale_job_runs`), which is where any non-terminal wait already ends
up today (a busy agent is the common one). The MODIFIED deltas in `loop-firing-accountability` and
`runtime-diagnostics` say this, so neither SHALL is contradicted.

## D5 — The options

| Option | What it would break | What it releases |
|---|---|---|
| **(a) Answer accepted, retry in the Hub (this change)** | Nothing: no caller relies on a 500 here. | The false 500 at seven sites (the trigger and D4's six), and the wait on an unrelated action. |
| (b) Answer accepted, no retry | The answer is still false in effect: the input can wait indefinitely. | The status half only. |
| (c) Keep 500, add a retry | Tells the operator a queued message failed, and invites a duplicate send. | The drain half only. |
| (d) Move `schedule_agent` inside the request's transaction | The run spawn is not transactional; a rollback cannot un-spawn a process. | — |

## Open questions

None. Question 1 (`withdraw_refused_entry`'s own failure at `:1625` still answers 500 after a
refusal) was closed at the operator review. It stays: the caller is owed that refusal, and the
failure leaves the entry queued, which a retry will refuse again. The requirement now states it as
an exception.

## Round log

- R1 2026-09-24: written.
- R2 2026-09-24: line claims re-read (`agent_trigger.py:1587/1595/1600`,
  `run_reconciliation.py:184-187, 205`, `turn_scheduler.py:283, 424`). **Disagreed (2):** (1) D3
  missed that `persist_event` commits on the route's session, so a failed persist poisons the refusal
  branch and a rollback expires the rows the answer reads; D3 now captures plain values and rolls
  back; task 1.9 added. (2) Two further post-commit routes (`accounting.py:78`, `agents.py:2693`);
  D4 widened, `checkpoints.py:334` excluded with its reason. D1/D2 stand: `schedule_agent` opens its
  own session (`turn_scheduler.py:283`), so its raise cannot poison the route's.
- R3 2026-09-24: re-derived every `schedule_agent(` call (`grep`) and read each of D4's six sites.
  **Disagreed (2):** (1) five of the six also `persist_event` on the route's session between the
  commit and the schedule (the Context row R3 added), so switching only the schedule leaves a 500
  that never schedules under a locked write; D3a adds one own-session, never-raising
  `persist_accepted_event` for every post-commit event at all seven sites, and supersedes R2's
  per-route rollback (task 1.6 widened, 2.3a added). (2) Counts: proposal and tasks said "four",
  D5 "five"; now six sites plus the trigger. **Added:** D2's pending-retry dict doubles as the
  strong task reference. **Held:** D1 (own session in `schedule_agent`, `turn_scheduler.py:283`),
  the drain's loss on a raise (`run_reconciliation.py:184-187`, `:205`), `checkpoints.py:334`
  excluded. No collision with B9's `an-event-is-announced-only-once-its-write-is-committed`
  (that change is about `commit=False` events inside a caller's transaction).
- Operator review 2026-09-24 (`spec-queue/tracks/reviews/B11-2026-09-24.md` §4): D6 added (the
  firing path, `scheduler.py:3444-3605` plus `_stage_selection`'s `:3757-3790`, which the review did
  not list but has the same shape); D1 retries transient errors only; D2 states the in-memory limit
  and the restart path; the requirement names the withdrawal exception; MODIFIED deltas for
  `loop-firing-accountability` and `runtime-diagnostics`. Every citation re-checked on `09127ba`.
