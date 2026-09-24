# Design — a firing is counted once, however many agents it starts

## Operator review, 2026-09-24

Opus adversarial review, recorded in `spec-queue/tracks/reviews/B2-2026-09-24.md` §2: APPROVE, with
one LOW note applied here. `scripts/drive/t_row11_loop.py:231` and `:312` assert
`run_count == len(history)`. That holds for a single-agent loop, so the script keeps passing, but it
reads the counter the way F121 did (one per row). New task 2.7 re-points both verdicts at the number
of distinct `fired_at` values in the history (the script already reads `fired_at`, `:224`, `:304`),
so the drive states this change's meaning and would catch a multi-agent regression.

**Built on the recommended answer to D1** (a `JobRun` row is a *dispatch*: one agent's share of one
firing; a *firing* is the rows sharing `(job_id, fired_at)`; a *run* is one attempt, a `Run` row).
If the operator answers D1 otherwise:

- *a row is a firing*: this change is unnecessary in its counter half (the rows would already count
  firings), but that answer needs a new child table for the per-agent conversation correlation, and
  a different change entirely;
- *a row is an attempt*: the counter must count distinct `fired_at` values instead, and this change
  is rewritten around that.

**Round 1, 2026-09-24.** Nothing here is implemented yet.

## Context

Where the counter moves, read at HEAD:

| Site | Line | When | Moves `run_count`? |
|---|---|---|---|
| Busy guard refusal | `scheduler.py:3044-3060` | loop refused, nothing written | no |
| `_job_agent_skip_reason` | `:3079-3097` | `skipped` row | no |
| Plain job coalesced | `:3107-3143` | `skipped` row or `tick_count` | no |
| Loop stop reached | `:3153-3190` | `skipped` row | no |
| Stall (first / continuing) | `:3290-3325` | `skipped` row or `tick_count` | no |
| Primary selection queued | `:3437-3444` | row → `in_progress` | **+1** (F11 comment `:3438-3442`) |
| Each extra selection | `_stage_selection`, `:3753-3756` | its own row, `in_progress` | **+1 each** |
| Firing raises | `:3515-3538` | row → `failed` | no |

`job.last_run` is stamped once per firing at `:3442` and deliberately **not** per selection
(`:3754-3755`: *"moving it per selection would make it mean 'the last agent started'"*). The same
argument applies to the counter, and the comment beside it draws the opposite conclusion only
because it had no settled meaning for a row. D1 supplies one.

Readers of `run_count`:

- `JobCard.tsx:435` — the badge. `:362-363` and `:436-442` (F25) define it as *"firings that
  actually ran"*.
- `api/v1/tasks.py:704` — `if job.run_count > 0` gates an agent adding to a loop's queue after the
  loop has fired. A boolean; unaffected.
- `api/v1/jobs.py:880` and `JobResponse.run_count` (`schemas/jobs.py:213`) — served as is.
- `src/agentweave/jobs.py:114,348` — the CLI's own local `Job` dataclass, not the Hub's column.

## Decisions

### D1 — The counter counts firings that queued work for at least one agent

Delete the increment in `_stage_selection`. The primary path's increment already happens at the
boundary F11 chose, before any extra selection is staged (`:3444` commits before
`_stage_additional_selections` runs at `:3452`), so every firing that stages extras has been counted
exactly once.

*Rejected:* **count distinct `fired_at` values at read time.** Correct, but `_prune_job_history`
keeps 100 rows (`scheduler.py` `_prune_job_history`), so the lifetime count is not recoverable from
rows, and the card would need a query per job.

*Rejected:* **a second counter, `dispatch_count`.** Nothing reads a per-dispatch total. The history
already lists the dispatches.

### D2 — The card names firings

`{job.run_count} runs` becomes `{job.run_count} fired`. The `refused` badge (`:447-451`) is
unchanged. Together they read *"3 fired · 1 refused"*, which is the F25 reconciliation stated in the
right unit: both halves count firings.

The word *run* is kept for `Run` rows everywhere else in the app (the conversation's *Turn failed*,
*Worked for*…). Using it for firings as well is the overload F121 names.

### D3 — No backfill

Existing inflated counters stay. The history is pruned, so a recount is not possible; a guess would
be a new lie. The migration plan says so, and the test guide tells the operator what to expect on a
flow that fired wide before this change.

## Risks / Trade-offs

- **An operator who read the badge as "agents started" loses that number.** It was never labelled
  that, and the history lists each dispatch.
- **History rows of one firing share `fired_at`** and `GET /jobs/{id}/history` orders by
  `fired_at.desc()` only (`api/v1/jobs.py:1313`), so their relative order is unspecified. This change
  does not rely on that order and adds no test that does.

## Migration Plan

None. No column changes. Counters in existing databases are left as they are (D3).

## Open Questions

1. **Should each history row name its agent?** A wide firing's rows are identical in the card's
   history except for their conversation, and `JobRunResponse` (`schemas/jobs.py:82-94`) carries no
   agent. The row's conversation knows it (`Conversation.agent`). *Recommended:* yes, as a follow-up
   change, not here. It is presentation, it needs a join in two routes, and F121 does not ask for it.
