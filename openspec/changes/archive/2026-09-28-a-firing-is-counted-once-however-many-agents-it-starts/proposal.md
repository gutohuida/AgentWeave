# Proposal — a firing is counted once, however many agents it starts

**Round 1, 2026-09-24** (bundle B2, spec track S7 after decision D1). Finding: **F121 (C)**,
re-verified against HEAD `ce086b6` (the bundle worktree; product code identical to `404c7d5`).
**Nothing here is implemented yet.**

## Why

A job's card shows `{job.run_count} runs` (`hub/ui/src/components/jobs/JobCard.tsx:435`). The
comment four lines below it (`:436-442`, F25) defines that number as *"firings that actually ran"*.
The counter does not count that.

- `_do_fire_job` increments `job.run_count` once, where the firing's primary selection reaches a
  queued entry (`hub/hub/scheduler.py:3443`).
- `_stage_selection`, which writes each *extra* selection of a wide flow firing, increments it
  again for every extra agent (`scheduler.py:3753-3756`, whose comment says so: *"One per row, so
  `run_count` keeps counting `JobRun`s"*).

So a flow firing that starts two agents adds 2, and one that starts three adds 3. F121 measured
`run_count == 4` after two presses of Run, and 5 after three. The test that pins today's behaviour
says it outright: `hub/tests/test_flow_width.py:423-424`, *"`run_count` keeps counting `JobRun`s"*,
`assert run_count == 2` for one firing.

The loop measurement in *"F121, strengthened"* (FINDINGS.md) is the other direction: a skipped
firing adds nothing. That half is **consistent with the F25 definition** and stays. What is wrong is
only the per-agent increment, and the card's word for the number.

Decision D1 (recommended answer, see the bundle record `spec-queue/tracks/B2.md`) settles what the
rows are: a `JobRun` row is a **dispatch**, one agent's share of one firing, correlated to its
agent's run through its own conversation. A firing is the set of rows sharing `(job_id, fired_at)`.
The counter on the job is therefore a count of **firings**, and it must not move per dispatch.

## What Changes

- `_stage_selection` stops incrementing `job.run_count` (`scheduler.py:3753-3756`). The comment is
  rewritten to state the D1 meaning: rows count dispatches, the counter counts firings that started
  work.
- `JobCard`'s badge names what it counts: `{n} fired` instead of `{n} runs`. The F25 comment is
  rewritten to match. The `refused` badge beside it is unchanged, and still reconciles with it: a
  refused firing is a firing that started no agent.
- `run_count` keeps its name on the wire (`JobResponse.run_count`, `hub/hub/schemas/jobs.py:213`;
  the CLI's `src/agentweave/jobs.py:114` carries an unrelated local counter of the same name). Its
  schema gains a description stating the meaning.
- Existing counters are **not backfilled**. A flow's counter in an existing database stays inflated
  by its past wide firings. It cannot be recomputed: `_prune_job_history` keeps 100 rows per job.

## Capabilities

### Modified Capabilities

- `loop-firing-accountability`: adds one requirement stating what a firing's count means when a
  firing starts several agents.

## Impact

- `hub/hub/scheduler.py` (`_stage_selection`), `hub/hub/schemas/jobs.py` (field description),
  `hub/ui/src/components/jobs/JobCard.tsx` (badge), a UI bundle refresh (`make ui`; commit
  `hub/ui/src` and `hub/hub/static/ui` together).
- `hub/hub/api/v1/tasks.py:704` reads `run_count > 0` as "has fired at least once". Both meanings
  give the same boolean, because every firing that reaches `_stage_selection` has already
  incremented once at `:3443`. Unaffected.
- Tests that move on purpose: `test_flow_width.py:424` (2 → 1); `jobCard.test.tsx:391-412`
  (`'0 runs'` → `'0 fired'`) and `:433-435` (`'1 runs'` → `'1 fired'`; R2 found this second one).
- **What counts (R2).** The increment sits where the firing's input is queued (`scheduler.py:3437-3444`),
  before `schedule_agent` runs (`:3471`), and its comment says a turn that then fails to begin still
  counts. R1's wording *"firings that started at least one agent"* was therefore not what the code
  counts; the spec delta and the field description now say *queued work for at least one agent*.
- Neighbours (R2): `a-flow-stages-its-review-in-the-dispatch` and
  `a-flows-own-moves-are-recorded-as-the-flows` (both open) edit `_stage_selection` too, in other
  lines; whichever lands second rebases.
- No migration, no route shape change.
