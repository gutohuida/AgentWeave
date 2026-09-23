# Design — Stop clears a run an earlier Hub left running

**Built on the recommended answer to D11 for F168** (the stale-run sweep's second trigger is the
operator's Stop, applied to a run this process did not start). If the operator answers otherwise:

- *a periodic sweep*: replace D2 with an interval job in the scheduler that runs D1's single-run
  reconciliation over every such run. Rejected below; the 2026-08-21 operator decision against a
  periodic reaper (`2026-08-21-diagnose-and-clear-a-broken-loop` design D2) argues the same way;
- *startup also clears pid-alive runs*: change `reconcile_interrupted_runs`'s `pid_alive` skip
  (`run_reconciliation.py:79-80`) to terminate and reconcile. Reverses a pinned behaviour
  (`test_run_reconciliation.py:132`) and kills a process at boot on a pid-only identity check with
  nobody asking. Rejected below;
- *leave it*: F168 stays open as a restart-only state.

**Round 1, 2026-09-24.** Nothing here is implemented yet.

## Context

### The route today (`agent_trigger.py:1681-1739`)

1. Select the newest `running` run for the agent (`:1697-1703`). None → 404 (after `require_known_agent`).
2. A PTY handle in `run_liveness.active_ptys` → mark stop requested, terminate, answer 200 `stopping`.
3. An app-server run in `active_app_server_runs` → mark stop requested, answer 200 `stopping`.
4. Otherwise → **409** *"not in a stoppable state right now"*. The comment names two windows:
   *spawned but not yet registered* (between the commit at `:1311-1313` and `run_liveness.active_ptys
   [run_id] = pty` at `:2225`), and *already past its read/wait loop* (after the `finally` pops the
   handle at `:2707`, before the terminal status is committed). Both are windows in the life of a run
   **this process** started.

### Who can start a run

Only `trigger_agent_directly` creates `Run` rows (`agent_trigger.py:608`, the commit at
`:1293-1313`), called by the trigger route and by `turn_scheduler._attempt_turn`. Both run in this
process. So a `running` run with `started_at` before this process's start was created by an earlier
process, which is gone.

### Why the row survived startup

`reconcile_interrupted_runs` leaves a run whose `pid` is alive (`:79-80`). `pid_alive`'s own docstring
records its limit: a pid-existence check, not identity (`pty_runner.py:142-147`). The skip is the
conservative choice at boot: nobody asked for anything to be killed.

## Decisions

### D1 — One definition of *reconciled*

Extract the loop body of `reconcile_interrupted_runs` (`run_reconciliation.py:82-126`: mark
`interrupted`, `ended_at`, `expire_pending_for_run`, `record_turn_usage(sample=None)`,
`return_run_entries`, divergence deferral, `abandoned_for_run`, `run_interrupted` persisted and
broadcast) into `reconcile_run(db, run) -> ReconciledRun`, returning what the caller needs to
schedule and evaluate after its commit. Startup calls it in its loop, unchanged in effect. Stop calls
it for one run. The dispatch conclusion added by `a-retried-firing-records-how-its-work-ended` (if
that change lands first) belongs inside it too, so both callers conclude a firing the same way.

### D2 — Stop clears a run this process did not start

`run_liveness.PROCESS_STARTED_AT = datetime.now(timezone.utc)`, set at import. In the route's
fallthrough (step 4), before refusing:

- if `run.started_at < PROCESS_STARTED_AT`:
  - if `run.pid` is set and `pid_alive(run.pid)`: `terminate_process_tree(run.pid, force=True)` in the
    executor (`pty_runner.py:184`);
  - `reconcile_run(db, run)`, commit, then the post-commit steps (divergence evaluation, schedule the
    agent and every agent with queued input in the project, as `reconcile_interrupted_runs` does at
    `:128-150`);
  - answer 200: `status: "interrupted"`, message *"{agent}'s run {id} was left running by an earlier
    Hub process. It has been stopped and recorded as interrupted."*
- otherwise: today's 409, unchanged.

*A boot instant, not a set of started ids.* Both are exact for this question; the instant needs no
write at every start site and cannot be forgotten by a new one. The clock is the same clock that
wrote `started_at` (`db/models.py:1156`, `default=_now`).

*Terminate, then reconcile.* The operator pressed Stop, and the process is the agent's by the same
pid check startup already trusts to keep it running. Left alive, it would go on writing into the
checkout that the re-drained next turn is about to use (the reason F359 terminates on failure,
`agent_trigger.py:2683-2694`).

*Rejected:* **a periodic sweep.** Needs a timer, and it would have to decide on its own to kill a
process on a pid-only check.
*Rejected:* **startup kills pid-alive runs.** Same, at boot, with nobody asking.
*Rejected:* **`GET /runs` + a per-run cancel route.** F168's own bound: the state is one run per agent,
and a cancel hitting the same empty registries has the same 409.

### D3 — The busy refusals name the way out

Where the running run is an earlier process's (the same test as D2):

- `trigger_agent_directly`'s 409 (`:747-754`) reads *"{agent} has a run left running by an earlier Hub
  process ({run_id}). Stop it to clear it."*
- `turn_scheduler._attempt_turn`'s waiting reason (`:328-331`) reads the same, still
  `terminal_failure=False`: the input keeps waiting, and Stop's re-drain delivers it.

Otherwise both keep today's text.

### D4 — What the route returns when what it calls raises

| Raises | Answer | State left |
|---|---|---|
| `terminate_process_tree` | **409** *"Could not stop the process {pid} left by an earlier Hub: {error}. The run is unchanged."* | run `running`; nothing reconciled. Reconciling while the process may still write would free the checkout under it |
| `reconcile_run` or its commit | **500** *"Could not record run {id} as interrupted: {error}"*, error fitted and redacted as `_safe_error_summary` does | the transaction rolls back; the run stays `running` (process already terminated, so a second press reaches `reconcile_run` again with the pid dead) |
| post-commit scheduling | **200** as D2; the failure is logged | run `interrupted`; the queue is re-drained by the next run end or project open, as after any startup reconciliation that could not schedule |

## Risks / Trade-offs

- **Pid reuse.** If the orphan exited and its pid was reused, Stop terminates an unrelated process
  tree. `pid_alive`'s docstring accepts the same risk at startup in the opposite direction (keeping a
  row alive). The window is narrow (pid reuse takes many spawns) and the act is the operator's
  explicit request. Open Question 1.
- **Clock steps.** A wall-clock step backwards after boot could make a run this process started read
  as earlier. It would then be terminated by handle-less Stop, which for a run of this process is
  the *spawned-but-not-registered* window only, milliseconds wide. Accepted.

## Migration Plan

None.

## Open Questions

1. **Kill by pid on Stop, or only record?** *Recommended: kill* (D2). The alternative records the run
   `interrupted` and leaves any orphan running unobserved, saying so in the answer; it is safe against
   pid reuse and unsafe for the checkout.
