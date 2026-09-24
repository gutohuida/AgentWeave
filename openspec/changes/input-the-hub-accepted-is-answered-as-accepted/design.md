# Design — input the Hub accepted is answered as accepted

**Built on the recommended answer to B11's F349 question** (ROUNDS.md D13, *"F349 remainder"*):
**answer accepted input as accepted, and make that true by retrying the start in the Hub.** If the
operator prefers to keep a 500 (option c in D5), this change is withdrawn and F349 stays open.

## Context — measured on `ce086b6`

| Fact | Where |
|---|---|
| The entry is committed before anything else the route does after it | `hub/hub/api/v1/agent_trigger.py:1587` |
| Then, unguarded: `persist_event`, `sse_manager.broadcast`, `schedule_agent` | `:1595`, `:1596`, `:1600` |
| `schedule_agent` opens its own session under a per-agent lock | `hub/hub/turn_scheduler.py:283` |
| Its only `except` is `TriggerAgentError`; nothing catches a database error | `turn_scheduler.py:424`; `grep -n "except Exception" hub/hub/turn_scheduler.py` finds nothing |
| `ScheduleResult` can already say "not started, and why" without a refusal | `turn_scheduler.py:58-62` (`waiting_reason`, `refusal=None`) |
| Nothing retries a queued entry on a timer | F349's foot; re-drain call sites listed in the proposal |
| A deferred-schedule set exists, drained by the next request the Hub serves | `hub/hub/run_reconciliation.py:160-212`; `hub/hub/main.py:516-526` |
| The same unguarded shape at four more routes | `messages.py:318`, `agents.py:2257`, `questions.py:212`, `inbound_queue.py:253` |

## D1 — `schedule_accepted` never raises

```python
async def schedule_accepted(project_id: str, agent: str) -> ScheduleResult:
    """Schedule input that is already committed. A failure here is not the request's failure."""
    try:
        return await schedule_agent(project_id, agent)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("Could not start a turn for %s/%s after accepting input: %r", project_id, agent, exc)
        retry_schedule(project_id, agent)                       # D2
        return ScheduleResult(
            waiting_reason="accepted; the Hub could not start a turn yet and will try again",
            terminal_failure=False,
        )
```

The exception's own text is logged, not returned: a `database is locked` or a stack of SQL is not a
sentence the operator can act on, and the message they need is that nothing is lost.

`CancelledError` is re-raised: a request cancelled by its client is not a scheduling failure.

## D2 — The Hub retries; the deferred set is the backstop

`retry_schedule(project_id, agent)` starts one background task per `(project, agent)` (a second
call while one is pending does nothing). It sleeps 1 s, 5 s, then 30 s, calling `schedule_agent`
after each, and stops at the first call that does not raise. After the last failure it adds the pair
to `run_reconciliation._deferred_schedules` through a new public `defer(agents)`, so the next request
the Hub serves drains it (`main.py:516-526`). The delays are module constants so tests set them to 0.

The drain itself calls `schedule_agent` unguarded today (`run_reconciliation._schedule_now`,
`:184-187`), inside a fire-and-forget task, and it empties the set before its first `await`
(`:205`). A pair whose drain raises is therefore lost. `_schedule_now` switches to
`schedule_accepted`, so a failed drain re-enters D2's retry rather than vanishing. Under a
persistent failure that loops once per request served, which is the right amount of retrying for a
Hub that is serving requests and cannot write.

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

## D4 — The other four routes

Each calls `schedule_accepted` in place of `schedule_agent` and ignores the result, as it already
ignores `schedule_agent`'s.

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

## D5 — The options

| Option | What it would break | What it releases |
|---|---|---|
| **(a) Answer accepted, retry in the Hub (this change)** | Nothing: no caller relies on a 500 here. | The false 500 at five routes, and the wait on an unrelated action. |
| (b) Answer accepted, no retry | The answer is still false in effect: the input can wait indefinitely. | The status half only. |
| (c) Keep 500, add a retry | Tells the operator a queued message failed, and invites a duplicate send. | The drain half only. |
| (d) Move `schedule_agent` inside the request's transaction | The run spawn is not transactional; a rollback cannot un-spawn a process. | — |

## Open questions

1. `withdraw_refused_entry`'s own failure (`:1625`) still answers 500 after a refusal has been
   decided. Recommended: leave it; the caller is owed that refusal, and the failure leaves the entry
   queued, which a retry will refuse again.

## Round log

- R1 2026-09-24: written.
- R2 2026-09-24: line claims re-read (`agent_trigger.py:1587/1595/1600`,
  `run_reconciliation.py:184-187, 205`, `turn_scheduler.py:283, 424`). **Disagreed (2):** (1) D3
  missed that `persist_event` commits on the route's session, so a failed persist poisons the refusal
  branch and a rollback expires the rows the answer reads; D3 now captures plain values and rolls
  back; task 1.9 added. (2) Two further post-commit routes (`accounting.py:78`, `agents.py:2693`);
  D4 widened, `checkpoints.py:334` excluded with its reason. D1/D2 stand: `schedule_agent` opens its
  own session (`turn_scheduler.py:283`), so its raise cannot poison the route's.
