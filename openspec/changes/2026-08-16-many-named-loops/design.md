# Design — Many named loops

## D1. `Loop` wraps an `AIJob` by foreign key, one row per loop-job

```python
class Loop(Base):
    __tablename__ = "loops"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    job_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ai_jobs.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    purpose: Mapped[str] = mapped_column(Text, default="", nullable=False)
    stop_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    stop_when_queue_empties: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    stop_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    created_by_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    updated_by_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (Index("ix_loops_project", "project_id"),)
```

**Why a foreign key here, unlike `Task.spec_document_id` or the new `Task.loop_id`/`JobRun.
conversation_id` below.** The undroppable-column trap is about a **table-level CHECK constraint**
naming a column (`hub/hub/db/models.py`'s own comment on `Task.spec_document_id`, and `0074`'s
comment on `ck_spec_documents_phase`) — SQLite cannot drop a column a CHECK references without
rebuilding the table. A plain `ForeignKey` is not that trap: SQLite does not enforce foreign keys at
all in this codebase (no `PRAGMA foreign_keys=ON` anywhere, confirmed by `0073`'s own design note),
so it is metadata for the ORM and for whoever reads the schema, not a constraint the database
enforces or a column an `ADD COLUMN` migration would ever need to touch again. `loops` is also a
brand-new table — there is no existing-column-drop hazard to create in the first place. `ondelete=
"CASCADE"` matches `JobRun.job_id`'s own declaration one table up: deleting an `AIJob` through the
existing, unchanged `DELETE /jobs/{id}` path removes its `Loop` row for free, with no new code in
that handler.

**Why no `status` enum.** A candidate design gave `Loop` its own `active`/`stopped` status,
duplicating `AIJob.enabled`. Two booleans that must always agree are worse than one: "is this loop
firing" is already answered by `job.enabled`, and adding a second field that means almost the same
thing creates exactly the drift hazard this proposal's own `Why` calls out about `JobRun.session_id`
already conflating two meanings. A loop reads as stopped when `job.enabled is False`; `stop_reason`
(nullable) is populated only when *this proposal's own code* — the stop-condition check in D4, or an
operator-supplied reason via `PATCH` — is what disabled it, and stays `NULL` when an operator pauses
a loop's job the same way they pause any other job today (the existing `toggle_job` path, untouched).
A loop the operator paused with no stated reason and a loop that stopped itself both read as "not
firing"; only the latter also carries why.

**Why `purpose` is `Text` with a plain string default, not nullable.** Every other free-text
"why" field on a row somebody is expected to have written — `Agent.description`,
`SpecDocumentEvent`-style commentary — defaults to nullable *optional* commentary. `purpose` is
different: it is the one field the UI is meant to always have something to show next to a loop's
name (`STATE.json`'s own `purpose` field is never blank in three overnight runs' worth of state
files), and a loop created via a minimal API call with the field omitted should read as "purpose not
yet stated" (`""`) rather than force every reader to null-check it. Same reasoning `Charter.content`
already uses for the identical shape.

## D2. `Task.loop_id` and `GET /tasks?loop_id=`, the same shape `spec_document_id` already proved

```python
loop_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
```

No foreign key, matching `spec_document_id` beside it on the same model — the identical SQLite
undroppable-column reasoning applies here without modification; this column sits on an *existing*
table (`tasks`), so an `ADD COLUMN` migration is the only thing this proposal ever gets to do to it.

`hub/hub/api/v1/tasks.py`'s `list_tasks` gains a third parameter:

```python
loop_id: Optional[str] = Query(None)
```

applied as a third `elif` arm alongside `spec_document_id`'s exact-match filter and
`exclude_archived_completed`'s exclusion (`2026-08-16-the-board-scoped-by-document`, design D1) —
`list_tasks` today has exactly two branches (`if spec_document_id: ... elif exclude_archived_
completed: ...`, confirmed by reading `hub/hub/api/v1/tasks.py:421-439` in this round's cold review),
so this is the second `elif` added to that chain, making three branches total:

```python
if spec_document_id:
    q = q.where(Task.spec_document_id == spec_document_id)
elif loop_id:
    q = q.where(Task.loop_id == loop_id)
elif exclude_archived_completed:
    ...
```

**Why `elif`, matching D1's own reasoning exactly.** A caller scoping to a loop wants every task that
loop owns, unfiltered — the identical "an explicit scope is never allowed to hide anything" rule
`-the-board-scoped-by-document` already established for `spec_document_id`. Combining `loop_id` with
`exclude_archived_completed` would risk the same category of surprise that proposal already ruled
out: a scope naming something explicitly should never come back thinner than what was asked for.
`spec_document_id` and `loop_id` are mutually exclusive scopes by construction — a task declared by a
specification document and a task queued by a loop are different origins — so which one wins if
both were somehow supplied is undefined only in the sense that no real caller will ever supply both;
`spec_document_id` is checked first purely because it is the parameter that already existed.

**Why this is not a fifth `TasksBoard.tsx` fetch mode.** `useTasks()` already accepts an options
object (`{ excludeArchivedCompleted }`, from the prior change); this proposal adds `{ loopId }`
beside it, read the same way `useDocumentTasks` already reads `spec_document_id` — a query-string
parameter keyed into the React Query cache key so the loop-scoped and default views cache
independently. No new hook shape, no new component: a loop's "open its queue" affordance in
`JobCard.tsx` (D5) calls the same `setActiveTaskIds` mechanism `SpecDocumentTasksLink` already
proved live.

## D3. `JobRun.conversation_id` — the missing join key, not new storage

```python
conversation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
```

No foreign key — loose reference, matching `AgentOutput.run_id`'s own precedent and comment ("no FK
constraint... existing rows may carry ad hoc values from before the referenced concept existed"):
every `JobRun` written before this migration has `NULL` here, honestly, because nothing recorded it.

Set in exactly one place, `scheduler.py::_do_fire_job`, one line after the existing
`run = JobRun(...)` construction:

```python
run = JobRun(
    id=run_id,
    job_id=job.id,
    project_id=job.project_id,
    fired_at=fired_at,
    status="fired",
    trigger=trigger,
    session_id=resume_session_id,
    conversation_id=conversation.id,
)
```

`conversation` is already a local variable at this point in the existing function — built two blocks
above, either resolved from `job.last_session_id` or freshly created — so this is a one-line change
to a value the function was always computing, not a new lookup.

**Why this is worth a whole design entry.** It is the single fact this proposal exists to make
recoverable: today, "what did firing #12 of job X actually do" requires guessing which conversation
belongs to which `JobRun` from `fired_at` timestamps, because nothing links them. With
`conversation_id` recorded, a loop's firing history (D5) can deep-link each entry straight to that
conversation's own output log and questions — both already keyed on `conversation_id` elsewhere in
the Hub (`AgentOutput.conversation_id`, `Question.conversation_id`) — with no new rendering surface,
only a join.

## D4. The stop-condition check is a second skip-reason function, composed exactly like the first

`scheduler.py` already has one skip-reason check, run inside `_do_fire_job` before the queue entry is
created: `_job_agent_skip_reason` (self-registered poll agents manage their own execution). This
proposal adds a second, checked immediately beside it:

```python
async def _loop_stop_reason(session: AsyncSession, job: AIJob) -> Optional[str]:
    """Return why *job*'s loop should stop firing, or `None` if it should proceed.

    Only ever prevents a fire the scheduler was already about to make on its own cron or a manual
    trigger — see design D4. Never creates a firing, never decides what happens next.
    """
    result = await session.execute(select(Loop).where(Loop.job_id == job.id))
    loop = result.scalars().first()
    if loop is None:
        return None
    now = datetime.now(timezone.utc)
    if loop.stop_at is not None and now >= loop.stop_at:
        return f"loop stop time reached ({loop.stop_at.isoformat()})"
    if loop.stop_when_queue_empties:
        open_count = await session.scalar(
            select(func.count(Task.id)).where(
                Task.loop_id == loop.id, Task.status.not_in(TERMINAL_FOR_BINDING)
            )
        )
        if not open_count:
            return "loop queue is empty"
    return None
```

reusing `TERMINAL_FOR_BINDING` (`hub/hub/run_task_binding.py:272`, already imported for the identical
"no further work expected" idea by `-the-board-scoped-by-document`, design D1) rather than a second
open/closed vocabulary.

`_do_fire_job` calls it exactly where it already calls `_job_agent_skip_reason`, and a positive
result is handled **identically to that existing skip path** — a `JobRun` with `status="skipped"`,
`error_summary=reason`, the existing `job_run_skipped` event persisted and broadcast — with three
additions specific to a loop stopping (not merely one fire being skipped): the loop's own
`stop_reason`/`stopped_at` are stamped, `job.enabled` is set `False`, and the job is removed from the
live scheduler (`self.scheduler.remove_job(job_id)`, the same call `remove_job` already makes) so it
does not fire again next cron tick only to be skipped again. A new `loop_stopped` SSE event is
broadcast alongside the existing `job_run_skipped` one — `JobCard.tsx`'s loop block needs to know to
re-fetch even for an operator who is not watching the jobs list at the exact moment a scheduled fire
silently stops itself.

**Why this belongs in `_do_fire_job` and not a separate poller.** `AIJob`'s own cron already causes
`_do_fire_job` to run on schedule; a loop's stop condition only ever needs to be checked at the
moment a fire was about to happen, because a fire is the only occasion anything about the loop's
state would change. A separate background poller checking `stop_at` continuously would be new
scheduled infrastructure this proposal's own non-goals rule out ("no new occasion for a fire") —
worse, it would be exactly the kind of second execution driver `STATE.json`'s scope ceiling forbids,
even though its job here is only to *stop* things. The one gap this leaves, accepted deliberately: a
loop whose `stop_at` passes between firings is not marked stopped until the next cron tick notices —
for a `stop_at` set in whole minutes against a cron no finer than per-minute, that gap is bounded by
one cron period, not an unbounded wait.

## D5. Visibility — `loop` embedded on the existing `JobResponse`, not a new endpoint

```python
class LoopSummary(BaseModel):
    purpose: str
    stop_at: Optional[datetime] = None
    stop_when_queue_empties: bool
    stop_reason: Optional[str] = None
    stopped_at: Optional[datetime] = None
    queue: Dict[str, int]  # status -> count, over Tasks where loop_id == this loop's id
    current_task: Optional[Dict[str, str]] = None  # {"id": ..., "title": ..., "status": ...}
    open_questions: int

class JobResponse(BaseModel):
    ...  # unchanged fields
    loop: Optional[LoopSummary] = None
```

`get_job`/`list_jobs` compute `loop` only when a `Loop` row exists for that job — a plain `AIJob`'s
response carries `loop: null`, the same shape every optional relationship in this codebase already
takes (compare `SpecDocumentTasksLink` returning `null` when a document has no tasks).

**`current_task` derivation** — no stored pointer, per proposal.md's own non-goal: among `Task`s with
this loop's `loop_id`, prefer one whose `status` is `in_progress` or `blocked` (there is normally at
most one, by the same reasoning `divergence_policy` already relies on — a task a run is bound to
stays bound until it moves), ordered by `updated` descending; if none, the oldest `pending` task by
`created_at`; if none, `null` (queue empty or every item terminal).

**`open_questions` derivation** — `SELECT COUNT(*) FROM questions WHERE conversation_id IN (SELECT
DISTINCT conversation_id FROM job_runs WHERE job_id = :job_id AND conversation_id IS NOT NULL) AND
answered = false AND declined = false`. This is D3's entire payoff: without `JobRun.conversation_id`
this query has no `IN` list to build.

**Why extending `JobResponse` rather than a `GET /loops/{id}` endpoint.** A `Loop` has no existence a
caller would ever fetch independent of its job — it has no cron, no message, no agent of its own;
every field that makes a loop's card readable (`name`, `agent`, `cron`, `enabled`, `next_run`,
`history`) already lives on the job. A separate endpoint would mean every caller of "show me this
loop" makes two requests and stitches them together, for a relationship that is 1:1 and never
optional-on-the-job-side in the other direction. `JobCard.tsx` already renders one card per job
(`JobsPage.tsx`); rendering "many loops" is rendering that same list with a loop block inside the
cards that have one — the multiplicity the operator asked for ("we can have loops for multiple
things") is already the shape of a list of jobs, not a new one.

## D6. Creating and updating a loop reuses `POST /jobs` and `PATCH /jobs/{id}`

`JobCreate` gains three optional fields:

```python
purpose: Optional[str] = Field(default=None, max_length=4000)
stop_at: Optional[datetime] = None
stop_when_queue_empties: bool = False
```

`create_job` creates a `Loop` row **iff at least one of `purpose`, `stop_at`, or
`stop_when_queue_empties` was supplied** (`purpose` non-`None`, or `stop_at` not `None`, or
`stop_when_queue_empties is True` — a bare `False` default supplied by every ordinary caller that
never mentions loops at all does not, by itself, opt a job in). `JobUpdate` gains the same three plus
`stop_reason: Optional[str]`, applied to the existing `Loop` row when the job has one; supplying any
of the four for a job with no `Loop` row is a `400` (`"this job is not a loop; create it with a
purpose or stop condition to make it one"`), not a silent no-op — the same "explicit input, explicit
outcome" instinct `-the-board-scoped-by-document` applied to `spec_document_id`/`exclude_archived_
completed` never silently combining.

**Why no "convert an existing plain job into a loop" path beyond `PATCH` with a stop field.** `PATCH`
already lets an operator add `purpose`/`stop_at`/`stop_when_queue_empties` to a job that has none of
them yet — that path both creates the missing `Loop` row (mirroring `create_job`'s own "at least one
field" rule) and updates one that already exists, so there does not need to be a separate "upgrade
this job" affordance. A job can also never be *downgraded* back to plain — once a `Loop` row exists it
stays, with an operator able to clear `stop_at` (set it back to `null`) and leave `stop_when_queue_
empties` `false`, which is functionally "not stopping itself" without deleting the row. Deleting the
row entirely was considered and rejected: it would discard `purpose` and `stop_reason`'s history for
no operational benefit, since an inert `Loop` row with no stop condition costs nothing to keep.

## D7. `list_jobs` computes every job's `loop` block in four batch queries, never one query per job

**Added in round 2's cold review**, elevated from tasks.md 4.4's task-level warning because a cold
read of `hub/hub/api/v1/jobs.py:178-191` shows the starting point is worse than "watch the N+1
shape" implies: today's `list_jobs` runs **exactly one query, full stop** — it does not even fetch
history the way `get_job` does. Computing `queue`/`current_task`/`open_questions` per job the naive
way — one query each, per job, inside a loop over the `list_jobs` result — would turn a single-query
endpoint into `1 + 4×L` queries where `L` is the number of jobs that are loops, on the exact endpoint
this whole change's operator motivation ("many named loops... at different cadences") expects to
carry a growing `L`. That is precisely the "pile-up" shape this session has spent N1/N2b avoiding
elsewhere on the task board; `list_jobs` should not reintroduce it on the jobs page.

`list_jobs` (and `get_job`, which already does one extra query and gains three more per job's `loop`
computation, so the same batching applies there too, just over a result set of size one) SHALL
compute `loop` in a fixed number of queries independent of job count:

1. One query: `SELECT * FROM loops WHERE job_id IN (:job_ids)` — builds `job_id -> Loop` for every
   job in the page being returned.
2. One query: `SELECT loop_id, status, COUNT(*) FROM tasks WHERE loop_id IN (:loop_ids) GROUP BY
   loop_id, status` — builds `loop_id -> {status: count}` for every loop found in step 1.
3. One query: `SELECT * FROM tasks WHERE loop_id IN (:loop_ids) AND status IN ('in_progress',
   'blocked', 'pending') ORDER BY loop_id, (status != 'pending') DESC, updated_at DESC,
   created_at ASC` — fetched once, then `current_task` is picked per loop in Python by taking the
   first row for each `loop_id` (the ordering puts an in-progress/blocked row before any pending row
   within the same `loop_id`, matching D5's derivation rule), rather than a second round trip per
   loop.
4. One query: the `open_questions` count from D5, but grouped —
   `SELECT job_runs.job_id, COUNT(*) FROM questions JOIN job_runs ON job_runs.conversation_id =
   questions.conversation_id WHERE job_runs.job_id IN (:job_ids) AND questions.answered = false AND
   questions.declined = false GROUP BY job_runs.job_id`.

Four queries total for a page of jobs, not four queries per loop-job. `get_job`'s existing single-job
call reuses the same four functions with a one-element `job_ids`/`loop_ids` list — no special-cased
single-job path to keep in sync with the batch one.

## D8. What this leaves for a future change, named rather than assumed away

No code anywhere lets an agent or the Hub choose a loop's next queue item, mark one done and start
the next, or update `job.message` between firings — an operator or the running agent does all of
that today by hand (editing the job, or, for a `resume`-mode job, simply continuing the conversation
with full context of what it already did, the same way tonight's own overnight session works from a
freshly-read `STATE.json` each iteration but without the Hub ever choosing to re-read it). Composing
`Loop`/`Task.loop_id`/`JobRun.conversation_id` into something that actually drives itself — the Hub
deciding when an iteration is "done" and starting the next one, an agent marking its own queue item
complete through a new MCP tool — is explicitly future work; this change gives that future work a
data model and a visibility surface to build on, and stops there.
