# Design — a flow's own moves are recorded as the flow's

**Built on the recommended answer to D8**: *no new actor kind; a new recorded cause (`origin="job"`)
naming the job, with the operator's authority unchanged.* **If the operator answers otherwise** (a
third actor kind), this change is withdrawn: that answer must first modify
`task-lifecycle-governance`'s *"The system may cause a transition without becoming an actor"*
(which forbids it) and give every edge of `TRANSITIONS` a declaration for the new kind; the tests in
group 1 that assert what the history *says* would carry over, the ones about origin would not.

## Context — re-verified on HEAD `404c7d5`

| Finding | Still open? | Evidence |
|---|---|---|
| F47 | open, moved | `scheduler.py:906` and `:908` pass `operator()` (F47 cited `:828`/`:830`; the code moved, not the defect). `ACTOR_KINDS` still two (`task_transitions.py:36`) |
| F120 | open, same defect | rows written by those two lines are the `pending→assigned` rows F120 captured |

The staging function has **three** callers, not two (`grep -n "enter_selected_task(" hub/hub`):
`scheduler.py:3336` (`_do_fire_job`), `scheduler.py:3709` (`_stage_selection`) and
`api/v1/agent_trigger.py:898` (a review dispatched by the operator by hand — F76's repair). Only the
first two are a scheduled firing.

**Can the third caller travel an edge on a flow's behalf?** The flow writes its reviewer and stages
`under_review` before the turn is scheduled (the design-D9 comment just above `agent_trigger.py:889`), so by the time a
flow-queued review entry reaches `:898` the task is already in `WITH_REVIEWER_LOOP_TASK_STATUSES`
and the function's `pass` branch runs — no transition. The divergence restaff
(`run_divergence.py:~470-485`) likewise re-queues a review for a task already under review. So a
transition at `:898` is the operator's own dispatch, and `operator()` with `origin="actor"` is true
there. **R2 should re-derive this**: if any entry origin other than the operator's reaches `:898`
with the task still `completed`, that caller needs the entry's cause too.

## D1 — Options for D8

1. **A recorded cause, not an actor** (recommended). `origin` already exists to answer *"what caused
   this transition to be requested"* (`db/models.py:829-842`); `runtime` is its only non-actor value
   today. Adding `job` records the fact F47/F120 ask for, meets the existing requirement's cause
   clause, and moves no guard: `is_allowed` reads `actor.kind`, which stays `operator`; the
   author/reviewer guards read `actor.agent`, which stays `None`, exactly as today.
2. **A third actor kind** (`flow`/`system`). Forbidden by the shipped requirement and costs an edge
   declaration per status pair, plus every `is_operator` branch (`tasks.py:676, 1319, 1335, 1418`).
   It would also make a flow's authority a separate thing the operator must reason about, when the
   operator granted it by creating the flow.
3. **Leave it, relabel in the UI.** Not possible: the row carries nothing that distinguishes a
   flow's move from the operator's.

## D2 — The column and the value

- `ORIGIN_JOB = "job"` in `task_transition_service.py:563-565`; `ORIGINS` gains it.
- `TaskTransition.job_id: Optional[str]`, `String(64)`, nullable, indexed not required, **not a
  ForeignKey** (the same SQLite drop trap `models.py:708-712` records). Jobs are never deleted
  (`jobs.py:1174-1187` refuses), so the id stays resolvable.
- `apply_transition(..., origin, job_id=None)`: raises `ValueError` unless
  `(origin == ORIGIN_JOB) == (job_id is not None)`, and unless `origin != ORIGIN_JOB or
  actor.is_operator`. Programming errors, not refusals — same class as the existing `origin` check at
  `:589-590`.
- Divergence resolution (`:701`) becomes `if origin != ORIGIN_RUNTIME:`. Today a flow's staging
  resolves divergences because it is recorded `actor`; keeping that is the no-behaviour-change path.
  `run_advanced_its_task` (`run_task_binding.py:955-975`) filters by `run_id`, which a job move never
  carries, so it is unaffected.

Why the job and not the firing (`JobRun.id`): `_prune_job_history` evicts `JobRun` rows, and an
append-only record must not name something that will disappear. The job is durable.

## D3 — What the history says

`_transition_view` (`tasks.py:1617-1637`) adds `job_id` and `job_name` (one `AIJob` lookup per
distinct id in the response; `None` if not found). `TaskTransitionHistory.tsx`:

| origin | who | verb |
|---|---|---|
| `job` | `Flow <job_name>` (or `A flow` when the name is missing) | `moved` |
| `runtime` | unchanged | `was moved for` |
| `actor` | unchanged (`You` / agent / `A run`) | `moved` |

The MCP `task_history` docstring (`mcp_server.py:322-334`) names the new origin.

## D4 — What the route returns when what it calls raises

`GET /tasks/{id}/transitions`: the job-name lookup is a read in the same session; a raise there is a
500 like any other read failure today, and the lookup is skipped entirely when no row has a `job_id`.
The scheduler's staging runs inside the firing's transaction: a `ValueError` from the new argument
check would abort the firing exactly as a refused transition does today — which is why the check is
exercised by a unit test rather than discovered in a live firing.

## Interaction

- **B1 / S1** rewrites the attending helpers the flow's selection reads, and **S13** moves where the
  flow stages `under_review` (into the dispatch). Whichever of those lands first, the staging call it
  leaves must still pass `job_id`; the source scan in task 1.5 fails if a scheduler-side staging call
  drops it.
- **S13 is the sharp one.** It moves the flow's `completed → under_review` *into the dispatch* — that
  is, into the `agent_trigger.py:898` path this design argues is the operator's alone. After S13 that
  caller would travel the edge for flow-queued entries too, and must take its cause from the entry
  (`origin_type == "job"`) and a job reference the entry does not carry today
  (`InboundQueueEntry` has no job column; `new_entry` at `scheduler.py:3404`/`:3736` passes none).
  Whichever of the two changes lands second must add that; R2/R3 of both should check it.

## Round log

- R1 (2026-09-24): written. Not yet compared by R2/R3.
