# Proposal — input the Hub accepted is answered as accepted

**Round 1, 2026-09-24** (bundle B11, `spec-queue/tracks/B11.md`). Finding: **F349 (B)**, its open
remainder. `fef65d4` (2026-09-22) removed the measured cause, the resolver's autoflushed
`last_seen_at` write. What it left is recorded in F349's own foot: *"a failure after
`trigger_agent`'s entry commit still answers 500 for input that is queued … Answering `queued`
instead is only true if something will drain the entry, and nothing on a timer does."* Re-verified
on `ce086b6`. **Nothing here is implemented yet.**

## Why

`POST /agent/trigger` commits the operator's input as a queue entry (`agent_trigger.py:1587`), and
only then persists an event (`:1595`), broadcasts it (`:1596`) and calls `schedule_agent` (`:1600`).
None of the three is guarded. `schedule_agent` opens its own database session
(`turn_scheduler.py:283`), so a `database is locked` from any concurrent writer, or any other
exception, propagates. The route then answers **500** for a message that is in the queue, which is
F108's shape: a route whose status disagrees with its effect. The operator is told the send failed
and may send it again.

Answering "queued" alone would be a second false sentence, and F349's foot says why: nothing
retries. The re-drain is reachable only from project open, settings save, relocate, and the end or
failure of another run (`grep -rn "redrain_queued_agents(" hub/hub`: `agent_trigger.py:2077, 2222,
2661, 3087, 3224`, `projects.py:316, 534, 603`). An idle agent whose scheduling raised keeps the
entry `queued` until one of those happens, which is F90's measured wait.

Four more routes commit input and then call `schedule_agent` unguarded, in the same shape:
`messages.py:318` (a message to an agent), `agents.py:2257`, `questions.py:212` (a delivered answer),
`inbound_queue.py:253` (a released entry). **Read, not measured**; the trigger is the measured one.

## What Changes

- **One helper schedules after a commit and never raises** (design D1):
  `schedule_accepted(project_id, agent)` in `turn_scheduler.py`. On success it returns what
  `schedule_agent` returned. On an exception it logs it, arranges a retry (D2), and returns a result
  saying the turn could not be started yet.
- **A failure to schedule is retried by the Hub, not by an unrelated action** (design D2): a bounded
  background retry (1 s, 5 s, 30 s), and after the last one the agent joins the existing
  deferred-schedule set that the next request the Hub serves drains
  (`run_reconciliation.py:160-212`, `main.py:516-526`).
- **The trigger answers from what happened to the input** (design D3). After a commit, the answer is
  "accepted" in every case: `running` where a turn started with it, else `queued` with a
  `waiting_reason`. A scheduling failure's reason reads *"accepted; the Hub could not start a turn
  yet and will try again"*. An event that fails to persist is logged and does not change the answer.
- The four other routes call the helper in place of `schedule_agent`, and keep their answers.

No migration, no API shape (the trigger's `TriggerAgentResponse` already has `status` and
`waiting_reason`), no UI.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-conversation-workspace`: a new requirement, *Input the system has accepted is answered as
  accepted, and a failure to start it is retried*.

## Impact

- `hub/hub/turn_scheduler.py` (the helper), `hub/hub/run_reconciliation.py` (a public `defer` into
  the existing set), `hub/hub/api/v1/agent_trigger.py` (`:1587-1672` only), and the four call sites.
- `hub/tests/`: a new `test_accepted_input_is_answered_as_accepted.py`.
- **Interaction:** F133 (`queue status recomputes the reason`, a no-spec round in B11) reads the same
  queue. This change writes no `waiting_reason` column; it only answers the request. No collision.
