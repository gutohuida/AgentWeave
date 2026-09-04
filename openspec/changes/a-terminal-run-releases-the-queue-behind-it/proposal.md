## Why

A run that has ended is supposed to release what was waiting behind it. Two things wait: the
agent's own input, queued while the run was busy, and any *other* agent parked behind the task
checkout this run held (design D8). Both are released by exactly one call —
`redrain_queued_agents(project_id)` — and nothing in the Hub runs on a timer to do it later:
`agent_trigger.py:1908` states the constraint in the code itself, *"Nothing does on a timer:
`redrain_queued_agents` is reachable only from project open, settings save and relocate."*

`_execute_run` places that call **last**, at `hub/hub/api/v1/agent_trigger.py:2281`, after the
whole post-turn bookkeeping block. The run's terminal status is committed far earlier, at `:2175`.
Between those two lines the function does real work that can raise: `evaluate_run_end`,
`_report_abandoned_entries`, `_broadcast_run_lifecycle`, a `persist_event` + broadcast per returned
entry, `record_agent_output` for the terminal status row, and `maybe_generate_title`.

The exception handler at `:2282` catches all of it, and computes `already_terminal` at `:2305-2313` by
re-reading the run row and asking whether it is still `running`. It then uses that one flag for two
different questions. The first use is right, and its comment argues it well: do not relabel a run
that already ended cleanly as `failed` because some later bookkeeping raised. The second use is the
redrain at `:2358`, which sits inside `if not already_terminal:` (`:2350`) — even though its own
comment says it is *"[u]nconditional, where this was gated on `returned`"*, on the grounds that *"a
run that fails releases the task checkout it held exactly as a run that succeeds does"*.

So the redrain is skipped in exactly the window where the normal path's redrain was also skipped.
An exception between `:2175` and `:2281` leaves the run correctly terminal, correctly labelled and
correctly broadcast, with the input behind it queued and nobody coming for it. `reconcile_interrupted_runs`
does not recover it either: it selects only `Run.status == "running"` (`run_reconciliation.py:60`),
and this run is not running. The entry waits for an unrelated operator action — opening the project,
saving settings, relocating the workspace — and is delivered by coincidence rather than by design.

**Observed.** `test_stop_endpoint_marks_run_stopped_and_broadcasts_run_stopped` asserts
`queued_entry.delivered_in_run_id is not None` for an entry that arrived behind a run that was then
stopped, and CI reports `None`: the stopped run's `record_agent_output` raised at `:2235`, `:2281`
was never reached, `already_terminal` was `True`, and the entry was never handed to a successor.
The operator-visible shape is a message that simply never runs.

This is **F286 (B)** in `scripts/drive/FINDINGS.md`.

### The second half, which the finding got wrong and this round corrects

F286 says `_execute_codex_appserver_run` *"has the same layout … and reaches the same handler."* The
layout is the same; **the handler is not reached.** Two code facts:

1. `_execute_run` delegates to `_execute_codex_appserver_run` at `:1824`, and the delegation is
   **above** `_execute_run`'s own `try:` (`:1846`), followed by `return`. Nothing that raises inside
   the app-server path can reach the handler at `:2287`.
2. `_execute_codex_appserver_run`'s outer construct is `try: … finally:` (`:2536` / `:2873`) with
   **no `except` clause at all**. Its only `except` is an inner one covering the spawn/connect
   (`:2692`, for `FileNotFoundError`, `AppServerError`, `asyncio.TimeoutError`, `OSError`).

So on the app-server path an exception raised after the spawn escapes the coroutine entirely, into a
task whose only done-callback is `_background_runs.discard` (`:1231`), which never retrieves it. The
consequence splits by where it lands:

- **After the terminal commit at `:2813`**, it is F286 again, with no handler even attempting a
  redrain, and no `logger.exception` — so the stranding is silent in the log as well as in the UI.
- **Before it**, the `Run` row stays `status="running"` with `error=None` and no terminal broadcast.
  `turn_scheduler.schedule_agent` refuses a new turn while one is `running`, so the agent queues
  every subsequent trigger instead of running it. That is precisely the unbounded outage
  `_execute_run`'s handler exists to prevent, documented at `:2283-2303` — the app-server path never
  got the same guard. Recovery is a Hub restart: app-server runs never set `Run.pid` (`:1937` is the
  only assignment, on the PTY path), so `reconcile_interrupted_runs`'s `run.pid is not None and
  pid_alive(run.pid)` is `False` and the row is reconciled to `interrupted` at the next start — and
  only then.

Both halves are the same defect in one sentence: **whether the queue behind a run gets released
depends on what happened after the run ended, when it should depend only on the run having ended.**

## What Changes

- A run reaching a terminal status releases the queue behind it **unconditionally** — the release
  is a consequence of the run boundary, not of the bookkeeping that follows it succeeding.
- The `already_terminal` flag keeps its first job (do not relabel a cleanly-ended run as failed) and
  loses its second (do not release the queue).
- The app-server execution path gains the same terminal-status guarantee the PTY path has: a failure
  after the spawn ends the run rather than leaving it `running` until a Hub restart, and is logged.
- No schema change, no migration, no UI change.

## Impact

- Affected specs: `agent-conversation-workspace` (ADDED: *A run that has ended releases the queue
  behind it*; ADDED: *Every started run reaches a terminal status without a restart*)
- Affected code: `hub/hub/api/v1/agent_trigger.py` (`_execute_run`'s handler; `_execute_codex_appserver_run`)
- Affected tests: `hub/tests/test_agent_trigger.py`
- **Not in scope:** F285, the in-memory `StaticPool` test-harness artefact that supplied the
  exception CI actually saw, and F287, the redundant `db.refresh` in `output_recording.py` that
  turns that artefact into a raise. Both are real and both are separate; this change is about what
  the Hub does *when* an exception lands there, which is why it outlives either fix.

### Capability placement, stated so a later round can overturn it

Both requirements go to `agent-conversation-workspace` because that capability already owns the
queue, its delivery and the wedge family — *Repeated delivery failure does not wedge an agent*
(`spec.md:1228`) is the nearest neighbour, and it states the governing principle for *returned*
input: *"an input left queued until an unrelated request happens to drain it is retried by
coincidence rather than by design."* F286's entry is never returned — it is input that arrived while
the agent was busy and was never delivered at all — so that requirement does not reach it, which is
the gap this change fills rather than a contradiction of it.

`turn-outcome-visibility` was considered and rejected: its stated purpose is a run that ends without
advancing its deliverable, not whether a run reaches an outcome at all. `run-task-binding` owns the
checkout hold but not the queue. A later round may still move the second requirement; it should say
so if it does.
