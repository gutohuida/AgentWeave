# Design — an undelivered message says how its last attempt ended

**Built on the recommended answers to D11 for F291 and F273**, and consistent with D1: a `Run` row is
the record of one attempt, and the conversation reads an attempt's outcome from it (the run facts
map), never from the output stream alone. If the operator answers otherwise:

- *F291: render an abandoned message's failed runs as turns of their own*: `groupIntoTurns` would
  need to make a turn for a run with no entries, which it cannot (it groups entries). A larger change
  to the model; rejected below;
- *F291: leave it*: F291 is closed as *the banner is the surface*; the error stays off-screen;
- *F273: give a failed status-line write its own error row, or retry it*: a second write to report
  the failure of a write, on the path where writes are failing. Rejected below.

**Round 1, 2026-09-24.** Nothing here is implemented yet.

## Context

The chat response for a conversation (`api/v1/agent_chat.py:690-721`), in the order the route
returns it:

1. output rows, delivered entries and outbound messages, then **abandoned** entries, **sorted
   together by timestamp** (an abandoned entry's timestamp is its `arrived_at`, `:207-210`);
2. then the still-waiting entries, appended unsorted;
3. `runs`: facts for every `run_id` the final list names (`_run_facts_for`, `:311-345`), including an
   abandoned entry's (`run_id=entry.delivered_in_run_id`, `:212`).

The client groups that list (`agentTimelineModel.ts:50-73`): an abandoned entry becomes a one-entry
turn `{ runId: null, abandoned: true }` in place (`:57-60`); `AgentTimeline` renders it with
`MessageEntry … queued` (`AgentTimeline.tsx:261-272`), which shows the *not delivered* chip and
`abandoned_reason` (`:873-899`). Nothing on that path reads `runs`.

A pre-spawn failure: three runs, each `failed`, each with `Run.error` set (`agent_trigger.py:2178`),
no output rows. The entry keeps the **last** run's id (`inbound_queue.py:286-288`). So the one run
the conversation can name is the attempt that finally made the Hub give up. That is the one the
operator needs.

## Decisions

### D1 — `RunFacts.error`

`error: Optional[str] = Field(default=None, max_length=RUN_FACTS_ERROR_CHARS)`, filled from
`Run.error` through a fitter (as `JobRun.error_summary` is fitted, `db/models.py:1413-1419`, to stop
an over-long value from turning the route into a response-validation 500). `RUN_FACTS_ERROR_CHARS`
is 500, the same bound `_safe_error_summary` uses (`api/v1/jobs.py:56-63`). Fitted, not redacted:
the same text is already broadcast unredacted (below), and redacting only here would make the two
disagree.

`Run.error` is not new exposure: the same `str(exc)` is already broadcast as `run_failed.error`
(`_transport_failure_fields`, `agent_trigger.py:1836-1837`) and persisted into the event log.

Both constructions change: `agent_chat.py:341` and `agents.py:894`. `AgentRunFacts` in
`hub/ui/src/api/agents.ts:134-139` gains `error?: string | null`.

### D2 — The abandoned turn reads its run

In `AgentTimeline`'s abandoned branch, look up `runs[entry.run_id]` and pass it to `MessageEntry` as
`lastAttempt`. Where present, render beneath the reason, in the same muted style:

| Last attempt's facts | Line |
|---|---|
| `failed`, error | *Last attempt failed: {error}* |
| `failed`, no error | *Last attempt failed (exit {exit_code})* where there is one, else *Last attempt failed* |
| `interrupted` | *Last attempt was interrupted by a Hub restart* |
| any other status | nothing |

*No "before it started".* R1 considered saying so and dropped it: the only server-side signal would
be `Run.pid is None`, and a Codex app-server run never sets `pid` (the only write is
`agent_trigger.py:2240`, on the PTY path), so it would call every Codex failure a failure to start.
The error text says what happened (*"%1 is not a valid Win32 application"*); the line does not need
to classify it.

*Rejected:* **turn the failed runs into turns.** They have no entries; `groupIntoTurns` would need a
new kind of turn built from `runs` rather than from entries, and the three runs are the same failure
three times. One line under the message says it once.

### D3 — `queue_entry_abandoned` refreshes the conversation

Add it to `QUEUE_EVENT_TYPES` (`agentChat.ts:284-290`). R2 checked that the frame reaches the hooks
at all: `queue_entry_abandoned` is already in `useSSE`'s dispatch allowlist (`useSSE.ts:21-68`), so
the one-line addition fires in production without B9's change. Its payload carries `agent`
(`turn_scheduler.py:641-647`, and `_report_abandoned_entries` on the run path), which is what
`eventTargetsAgent` matches (`:334-335`).

### D4 — F273 needs no product change

The requirement is amended (the delta) to say what the code already does and why that is enough.
The test plan pins it, so a later change that drops the run facts' exit code, or that relabels a run
because its status line failed, fails a test.

*Rejected:* **an error row for a failed status-line write.** It is a second write on the path where a
write just failed, and the fact it would report is already recorded twice (the run row; the log).
*Rejected:* **retrying non-lock errors.** `_record_observation`'s docstring gives the reason it does
not (`agent_trigger.py:1932-1934`): an unexpected error is a defect, and swallowing it would hide
every output of every run.

## Risks / Trade-offs

- **An error message can be long or ugly** (a Windows `WinError` string, a stack-free exception
  repr). Fitted to 500 characters; shown as-is otherwise, because it is the only diagnosis there is.
- **A UI bundle reaches `:8000` on the operator's next reload.** Covered by the human check.

## Migration Plan

None.

## Open Questions

None.
