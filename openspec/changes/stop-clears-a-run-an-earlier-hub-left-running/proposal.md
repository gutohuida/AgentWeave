# Proposal — Stop clears a run an earlier Hub left running

**Round 1, 2026-09-24** (bundle B2, decision D11, finding **F168 (B)** in its narrowed form of
2026-08-31). Re-verified against HEAD `ce086b6`: the stop route's refusal (`"is not in a stoppable
state right now"`) is unchanged since `58fef98`; the only callers of `reconcile_interrupted_runs`
are still `main.py:466` at startup. **Nothing here is implemented yet.**

## Why

F168 was filed as *"there is no way to list a project's runs, and no way to cancel one"*. Its own
measurement of 2026-08-31 narrowed it: at most one run per agent is live (`agent_trigger.py:747-754`
refuses a second), so per-agent Stop already is per-run Stop. **What remains is one state with no way
out but a restart:** a `Run` row reading `running` that no process in this Hub owns.

How it arises. `reconcile_interrupted_runs` (`run_reconciliation.py:66-150`) runs once, at startup,
and **skips any run whose recorded `pid` is still alive** (`:79-80`, pinned by
`test_run_reconciliation.py:132`, `test_run_with_live_pid_is_left_running`). A Hub that dies while
its agent's process survives (on Windows a child is not killed with its parent) starts again, finds
the pid alive, and leaves the row `running`. No process in the new Hub reads that agent's output or
will ever see it exit (`run_liveness.py:8-13`: the registries hold only runs *this* process
executes). Then:

- the roster shows the agent busy, because it reads the same column;
- every turn is refused: `schedule_agent` answers *"agent is already running"* (`turn_scheduler.py:
  320-331`), and `POST /agent/trigger` answers 409 *"{agent} already has a run in progress."*
  (`agent_trigger.py:747-754`);
- `POST /agent/{agent}/stop` finds the row, finds no handle in either registry, and answers **409
  *"{agent}'s run is not in a stoppable state right now."*** (`agent_trigger.py:1726-1732`).

Every route says the agent is busy, and none offers a way through. The spec carves this case out
explicitly: *"A run whose Hub was killed under it is not in scope and is recovered by reconciliation
at the next start"* (`agent-conversation-workspace/spec.md:2331-2334`). For a pid-alive run, the
next start does not recover it either, until the orphan happens to have exited.

The 409's own comment gives the reason it refuses: the run may be *"spawned but not yet registered,
or already past its read/wait loop"* (`:1722-1725`). Both are windows **of this process's own
runs**. A run started by an earlier process is in neither.

Decision D11 (recommended, `spec-queue/tracks/B2.md`): the trigger for a stale-run sweep is the
**operator's own Stop**, applied to a run this process did not start. Not a timer.

## What Changes

- The Hub records when its process started (`run_liveness.PROCESS_STARTED_AT`). A `running` run
  whose `started_at` is earlier cannot be owned by this process.
- `POST /agent/{agent}/stop`, finding such a run with no handle, **clears it** instead of refusing:
  it terminates the recorded process tree if that pid is alive, then reconciles the run exactly as
  startup would (`interrupted`, usage `unavailable`, pending permission cards expired, input handed
  back, `run_interrupted` persisted and broadcast, the queue re-drained). It answers 200 with
  `status: "interrupted"`.
- A run **this** process started and has not registered keeps today's 409: that window is real and
  the run will settle itself.
- The refusals that report the agent busy name the way out when the run is an earlier process's:
  `POST /agent/trigger`'s 409 and the scheduler's waiting reason say that the run was left by an
  earlier Hub and that Stop clears it.
- The single-run body of `reconcile_interrupted_runs` is extracted so startup and Stop share one
  definition of *reconciled*.

## Capabilities

### Modified Capabilities

- `agent-conversation-workspace`: adds *A run an earlier Hub left running is cleared by Stop*.

## Impact

- `hub/hub/run_liveness.py`, `hub/hub/run_reconciliation.py`, `hub/hub/api/v1/agent_trigger.py`
  (stop route, trigger refusal), `hub/hub/turn_scheduler.py` (waiting reason).
- Routes changed: `POST /agent/{agent}/stop`, `POST /agent/trigger` (refusal text only). What they
  return when the functions they call raise is in design D4.
- No migration, no UI change: the conversation header's Stop already calls this route.
- Not in scope, and deliberately: `GET /runs` and a per-run cancel route. F168's own bound shows
  neither would clear this state (a cancel hitting the same empty registries has the same 409).
