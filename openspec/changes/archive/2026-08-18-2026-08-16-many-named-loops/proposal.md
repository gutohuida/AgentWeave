# Many named loops

## Why

**The loop that runs this very session is not in the product.** Operator, this session: "Improving
the job system with more visibility, traceability and the ability to do better then what we're doing
now with the loop that we do." Everything that makes tonight's overnight run legible — an ordered
queue of work, a current item, why it stopped, a narrative of what each firing did — lives in
`.claude/autonomous/STATE.json` on disk, outside the Hub entirely.

The gap is narrower than it looks. `AIJob` (`hub/hub/db/models.py:1123`) already schedules a cron,
already fires an agent through the Hub's own execution path — no synthetic message, no watchdog
round trip (`hub/hub/scheduler.py:_do_fire_job`) — and already records each firing as a `JobRun`
(`:1160`). What is missing is not execution; it is the semantics layered on top of execution that
`STATE.json` proves matter: a named purpose, a stop condition, a queue of work items with their own
status, and a way to see, after the fact, what a firing actually produced. Verified this session:
`JobRun` records `fired_at`/`status`/`trigger`/`session_id`/`error_summary` but never the
conversation a firing created (`scheduler.py:284-304` builds a `Conversation` object and never
attaches its id to the `JobRun` it writes two lines later) — today, tracing "what did firing #12 of
this job actually do" means guessing at a conversation from timestamps.

**Two operator notes, both binding, both already recorded in `STATE.json`'s
`decisions_for_user`.** First: compose with what the Hub already has rather than reinvent it under
new names — an iteration is already a `Run` with a conversation, output logs and cost accounting
attached; a queue item is close to a `Task`, which already has status, assignee, transitions and
(as of `2026-08-16-the-corpus-keeps-what-shipped`/`-the-board-scoped-by-document`, both shipped
earlier tonight) a precedent for being scoped to something other than itself; a loop's "decisions for
the operator" are already the `Question` table and `ask_user`. Second: **many named loops**, never a
singleton — a tight development loop iterating every few minutes alongside a nightly security scan
alongside a weekly dependency audit, each with its own cadence (already expressible: `AIJob.cron` is
already per-job), its own purpose, its own queue, its own stop condition.

## What Changes

- **A `Loop` wraps exactly one `AIJob`, adding the four things `STATE.json` proves an unattended run
  needs and `AIJob` does not have**: a stated purpose, a stop condition (`stop_at`, a wall-clock
  deadline; `stop_when_queue_empties`, a work-based one), and a recorded reason once it stops. A job
  with no `Loop` row behaves exactly as it does today — this is additive, opt-in per job, not a
  replacement for the plain recurring-message job `AIJob` already is.
- **A loop's queue is its `Task`s.** `Task` gains `loop_id` (nullable, indexed, no foreign key —
  mirroring `spec_document_id`'s own reasoning: a table-level constraint naming a column makes that
  column undroppable in SQLite). `GET /tasks` gains `loop_id` as a third, independent scope
  parameter, alongside the `spec_document_id`/`exclude_archived_completed` pair
  `2026-08-16-the-board-scoped-by-document` shipped earlier tonight — same mechanism, second caller,
  not new machinery. The board can already show "this loop's work" with no new UI concept: it is the
  same scoped-board affordance that change already built.
- **`JobRun` gains `conversation_id`**, set at creation from the `Conversation` object the scheduler
  already builds two lines above where it writes the row. This is the one column that turns "a job
  fired" into "a job fired, and here is everything that happened" — the conversation's output log,
  its questions, its bound tasks are all already keyed off `conversation_id` elsewhere in the Hub;
  this is the missing join key, not new storage for something the Hub does not already record.
- **A loop's stop condition is enforced as one more skip-check the scheduler already has**, alongside
  the existing self-registered-poll-agent guard (`scheduler.py:_job_agent_skip_reason`). Before a
  scheduled or manual fire proceeds, if the firing job's loop has a `stop_at` in the past, or
  `stop_when_queue_empties` is set and the loop's queue has held at least one task and now holds no
  open (non-terminal) one — "empty" meaning drained rather than never-filled, so a loop created
  before its work exists is not killed on its first tick (design D4a) — the fire
  is skipped exactly the way an existing skip already is — a `JobRun` with `status="skipped"` and a
  stated reason — and the loop is marked stopped with that reason, the job disabled, and removed from
  the scheduler. **This is the entire boundary of what "the Hub reacts to a stop condition" means
  here**: it can only ever prevent a fire the scheduler was already about to make on its own cron; it
  never creates a firing, never decides what an agent does next, never writes a queue item, and never
  re-enters a conversation on its own initiative. Choosing the next queue item, updating the job's
  message, and deciding when work is done all remain something the operator or the running agent does
  — exactly as `divergence_policy`'s `surface`/`retry`/`escalate` already stop short of choosing an
  agent's next move for it.
- **Visibility is the existing Jobs surface, extended, not a second page.** `JobResponse` gains an
  optional `loop` object (purpose, stop condition, stop reason, a queue summary by status, the
  current item, and a count of open questions across the loop's own conversations) when the job has
  one; a plain job's response is unchanged. `JobCard.tsx` renders the loop block when present. This
  keeps "many loops" answered by the page that already lists many jobs, rather than a parallel
  surface the operator has to learn.

## Capabilities

### Added Capabilities

- `agent-loops`: a project MAY name a recurring job as a loop, with a stated purpose, a stop
  condition, and a queue of tasks it owns; the Hub SHALL surface, for any such loop, its current
  queue item, its firing history with a durable link to what each firing produced, and why it
  stopped when it has.

### Modified Capabilities

- `task-lifecycle-governance`: a task list SHALL be scopeable to one loop's queue, mirroring the
  existing document-scope mechanism.

## Impact

**Behaviour** — a job created without loop fields behaves exactly as `AIJob` does today; nothing
about an existing job's firing, message, or history changes. A job created *as* a loop gains a stop
condition the scheduler now checks before each fire, and its firings become traceable to the
conversation each one produced.

**API** — `POST /jobs` gains three optional fields (`purpose`, `stop_at`, `stop_when_queue_empties`)
that, together, opt a job into having a `Loop` row; omitting all three creates a plain job exactly as
before. `PATCH /jobs/{id}` gains the same three as optional updates, plus `stop_reason` (write path
for an operator recording their own reason when pausing by hand) — all four apply only to a job that
already has a loop; supplying any of them for a job that does not is a 400, not a silent no-op.
`GET /jobs`, `GET /jobs/{id}` embed the derived `loop` object described above. `GET /tasks` gains
`loop_id`. No new router, no new top-level endpoint.

**Migration** — one new table (`loops`), two additive nullable columns on existing tables
(`tasks.loop_id`, `job_runs.conversation_id`). No existing column, index, or constraint changes; no
`batch_alter_table` recreate is needed anywhere in this migration, unlike `0074`'s CHECK-constraint
widening — every change here is a plain `ADD COLUMN`/`CREATE TABLE`, guarded the way `0071` guards
its own additive columns for an upgrade starting from an early revision.

**UI** — `JobForm.tsx` gains an optional, collapsed-by-default "Make this a loop" section (purpose,
stop conditions). `JobCard.tsx` renders a loop's queue summary, current item, and open-questions
count when present, linking into the already-scoped task board (`?loop_id=`) and the existing
conversation view for a firing's own output.

## Non-Goals

- **Not building the thing that would drive a loop.** No code here decides to fire a loop's job when
  its cron would not already have; no code chooses what an agent does next, writes the next queue
  item, or resumes a conversation on the Hub's own initiative. The `stop_at`/`stop_when_queue_empties`
  checks only ever *prevent* an already-scheduled fire — they add no new occasion for one. Composing
  a loop out of this change and actually letting it run itself end to end (choosing its own next
  queue item, retrying a stalled iteration, restarting itself) is future work, not tonight's.
- **Not a second execution path.** A loop's firing goes through the exact same
  `scheduler._do_fire_job` every `AIJob` already uses — direct spawn, no synthetic message, no
  watchdog. Nothing here adds a second way to start a run.
- **Not replacing `AIJob`/`JobRun` with new tables**, per the operator's own pre-authorised default —
  `Loop` wraps an `AIJob` by foreign key; a job's cron, message, agent, and firing history stay
  exactly where they are.
- **Not a queue-ordering field.** A loop's queue is whatever `Task`s carry its `loop_id`; "current
  item" is derived (the queue's own `in_progress`/`blocked` task if one exists, else its oldest
  `pending` one) from the same `status`/`created_at` every task already has, not a new position
  column to keep in sync.
- **Not extending the archived-document task exclusion to loops.** `exclude_archived_completed`
  (`2026-08-16-the-board-scoped-by-document`) is about a task's *declaring document*; a loop-scoped
  task list shows every task the loop owns regardless of status, the same "an explicit scope hides
  nothing" rule that change already established for `spec_document_id`.
