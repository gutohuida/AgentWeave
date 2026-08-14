# Design — what a failure tells the operator

## D1. The skip text names the remedy that exists, not the one that used to be planned

`CHECKOUT_DIRTY` and `CHECKOUT_ELSEWHERE` (`hub/hub/task_integration.py:54-61`) both end *"and the
next approval will merge"*. That sentence predates
`2026-08-14-the-seams-loop7-found`'s retry route and was never true: integration fires on the
transition *into* `approved`, and restating a status is deliberately a no-op (that change's D5). By
the time the operator reads the skip the task is already `approved`, so there is no next approval to
have.

`TaskIntegrationNote.tsx` already renders a "Try again" button for both of these — it special-cases
only `NO_MAIN_BRANCH`, which links to settings instead (`:4`, `:43`). So the remedy is already on
screen and the sentence points away from it. This is a backend string change with no UI work.

`NO_MAIN_BRANCH` is left alone: "choose one in the project's settings" is both true and discharged
automatically when the operator follows it.

## D2. Two exit codes, because they answer different questions

`Run.exit_code` on the app-server path is synthetic — `0 if final_status == "completed" else 1`
(`agent_trigger.py:1853`) — because that transport has no process exit code for a turn. It is read by
`AgentOutputPanel.tsx` for handoff detection and by the `Run {status} (exit {code})` status line.
Repurposing it would silently break a working feature.

`TurnOutcome.exit_code` already carries the app-server's own exit status
(`codex_appserver.py:777`, filled from `session.returncode` at `:983`) and today reaches nothing but
`str(exc)`. So the fix is additive: broadcast it as **`runtime_exit_code`**, a distinct key that is
absent — not null-with-meaning — when no process ended.

The two names are the design, not an accident of it. `exit_code` answers "did this turn succeed";
`runtime_exit_code` answers "what did the runtime process do". Loop 8 showed both being read as
answers to the same question.

## D3. `4294967295` is rendered, not stored, as `-1`

Windows reports a forced termination as `0xFFFFFFFF`, which Python surfaces unsigned. `-1` is
actionable — it says "something killed this" — and `4294967295` reads as corruption.

Normalisation happens where the value is composed for a human: in `AppServerError.__init__`
(`codex_appserver.py:513-531`), which builds the `(exit {code})` clause every reader of `str(exc)`
sees. Values at or above `2**31` are reinterpreted as signed 32-bit; everything else passes through
untouched, so an ordinary `1` or `127` is unchanged and `None` stays absent.

Deliberately not normalised: `self.exit_code`, and `TurnOutcome.exit_code`. Those are what the OS
reported, and a diagnostic that quietly rewrites its input is a worse diagnostic. Only the rendered
clause changes. `runtime_exit_code` in the broadcast therefore carries the raw value, and the
readable form travels in the message — the same split the existing `method` and `stderr_tail` facts
already use.

## D4. The tail is delivered on both paths, because both were promised it

Two independent gaps produced one symptom.

- `_transport_failure_fields` (`agent_trigger.py:1005-1018`) enumerates the facts a pre-spawn failure
  reports and simply has no `stderr_tail` key. `AppServerError` carries one
  (`codex_appserver.py:523`); the dict never asks for it. Fixed with the same
  `getattr(exc, "stderr_tail", None)` shape the neighbouring keys use — this `except` also catches
  `FileNotFoundError`/`OSError`/`TimeoutError`, which carry none of these.
- On the normal path there is no exception at all: the turn ends with a failed `TurnOutcome`, which
  has nowhere to put a tail. `TurnOutcome` gains `stderr_tail`, filled from `session.stderr_tail()`
  where `exit_code` is already filled (`:982-984`), and the `run_failed` broadcast includes it.

`stderr_tail()` is already bounded (`STDERR_TAIL_CHARS`, `:630-635`) and already drained
continuously, so nothing new is retained and no pipe behaviour changes.

## D5. `ui_stale` names both commands, script first

`hub/hub/main.py:167` ends *"Run `make ui` to rebuild and re-record it."* `make` is absent from both
shells on this machine and `CLAUDE.md` records that, so the warning contradicts the project's own
documentation.

The instruction names `python scripts/refresh_ui_bundle.py` — which works everywhere Python does, and
is what `make ui` invokes — and keeps `make ui` as the shorthand for installations that have it. Not
the reverse order: the first command in an instruction is the one that gets pasted.

Only the stamped branch (`:161-167`) is reworded. The unstamped fallback at `:176-179` already names
`npm run build` and a copy, and rewording it belongs to whoever next touches that path.

## D6. Identifiers sort in Python, not in SQL

`hub/hub/api/v1/tasks.py:91` orders by `SpecRequirement.identifier`, a plain string sort, giving
`FR-1, FR-11, FR-2, FR-3`. A natural sort cannot be expressed portably in SQLAlchemy across SQLite
and Postgres without a dialect-specific expression, and the row count per task is small, so the sort
moves to Python after the fetch.

The key splits each identifier into digit and non-digit runs, comparing digit runs numerically. That
makes `FR-2 < FR-11`, keeps a wholly non-numeric identifier deterministic, and does not assume the
`XX-N` shape — identifiers are operator-authored and nothing constrains them to it.

Sorting the per-task list at `:110-126` fixes both `requirement_links` and the `requirement_ids`
derived from it at `:143`, so one change covers both surfaces. The `.order_by` in the query is kept:
it makes the fetch deterministic, which is what the Python sort's stability then relies on.

`hub/tests/test_task_requirement_ids_readable.py` may pin the current order. If it does, it is
updated and the reason stated in `tasks.md` rather than discovered in a diff.

## D7. What a wrong fix here looks like

Every item is a reporting change, so the failure mode is uniform: an assertion that passes against a
constant rather than against behaviour. The tests are written to go through a real skip, a real
failure broadcast and a real task read — not to import the string and compare it to itself.
