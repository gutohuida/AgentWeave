# Exploration — Batch the loop board's dependency gate (2026-08-21)

**Status:** OPEN. **A specification for this already exists**, written by an agent:
`spec/changes/batch-dependency-gate-evaluation-in-loop-summaries/spec.html`, phase `exploring`.
This note exists so the openspec side has a pointer; the content lives there.

## The finding

Measured 2026-08-21 while closing `diagnose-and-clear-a-broken-loop` task 3.5, which asked whether
the firing-active correlation was affordable. It was — and the measurement found something else.

At 300 loops / 3,000 `job_runs`:

| | |
|---|---|
| the correlation task 3.2 added | **+0.02–0.06 ms** (~0.9% of a listing) |
| `_batch_loop_summaries` overall | **~141–151 ms** |
| `dependency_gate.evaluate` calls per listing | **300** — one per loop |

`_batch_loop_summaries` promises in its own docstring to compute every job's loop block "in six
fixed queries, never one query per job". The `current_task` selection breaks that promise.

## The call sites

Three, established by an agent's inventory and verified against source:

1. `hub/hub/task_transition_service.py:236` — single-task. **Imported aliased**
   (`from .dependency_gate import evaluate as evaluate_dependencies`), so a literal grep for
   `dependency_gate.evaluate` misses it.
2. `hub/hub/scheduler.py:318` (`_first_startable_candidate`) — set-shaped, one query per candidate.
3. `hub/hub/api/v1/jobs.py:196` (`_batch_loop_summaries`) — set-shaped, across a whole page.

Other matches in `api/v1/tasks.py` and elsewhere are comments, not calls.

## Why this is worth keeping

Not for the milliseconds — trial projects have few loops and nobody has felt it. It is on the path
of **every** loop listing, and the cost is structural rather than incidental, so it grows with the
thing the product is trying to encourage people to create.

## Open questions

1. Does the batch entry point replace the per-task `evaluate`, or sit beside it? (The agent's
   document records this as resolved; worth re-reading before accepting.)
2. Does `scheduler.py:318` want the same batching, or does short-circuiting on the first startable
   candidate already make it cheap enough?
3. What pins the property afterwards — a query-count assertion, or a timing budget? A timing budget
   in CI is a flake; a query count is not.
