# Proposal — a flow's own moves are recorded as the flow's

**Round 1, 2026-09-24** (bundle B3, decision D8). Findings **F47 (C)** and **F120 (C)**, the same
defect seen twice, re-verified on HEAD `404c7d5`. **Nothing here is implemented yet.**

## Why

When a loop or flow fires, it stages its selection through `enter_selected_task`
(`hub/hub/scheduler.py:846-908`): `pending → assigned` for ordinary work and `completed →
under_review` for a review. Both moves pass `operator()` (`:906`, `:908`) with the default
`origin="actor"`. The task history therefore says **the operator asked for** a move that a
scheduled firing made while nobody was awake:

- `TaskTransitionHistory.tsx:40-44` renders such a row as **"You moved `pending` → `assigned`"**.
- On the operator's real database, read `mode=ro` 2026-09-24: **38 `operator`/`actor` rows**; F47
  (2026-09-14) attributed ~26 of 32 on `LoopEngine` to cron ticks.
- `test_flow_chain_end_to_end.py:342-352` pins exactly these two rows as operator-attributed, and says
  it does so *"so that fixing it … fails here"*.

This is not only untidy. `task-lifecycle-governance`, *"Every accepted transition is recorded append-only"*, already
requires: *"The recorded cause SHALL distinguish a transition an actor asked for from one the system
made on that actor's behalf."* A flow's staging is the system acting on the operator's behalf, and it
is recorded as the operator asking. The shipped requirement is violated today.

D8 asked whether the fix is a **third actor kind**. The same spec forbids one in so many words
(*"There SHALL NOT be a third actor kind for the system"*, requirement *"The system may cause a
transition without becoming an actor"*), for a reason that still holds: the transition map
(`task_transitions.py:TRANSITIONS`) and author/reviewer separation are keyed on actor kind, so a
third kind would need every edge to declare whether the system may take it. The recorded **cause**
is the axis the spec already provides for exactly this distinction.

## What Changes

- A third **origin** value, `job`, meaning *"a scheduled firing made this move, with the operator's
  authority"*, plus a nullable `task_transitions.job_id` naming the job. The actor stays `operator`
  — the authority the gate needs is unchanged, so no legality or separation rule moves.
- `enter_selected_task` takes the firing's `job_id`; its two scheduler callers (`scheduler.py:3336`,
  `:3709`) pass `job.id`; its hand-dispatched-review caller (`agent_trigger.py:898`) passes none and
  stays the operator's own act.
- `apply_transition` accepts `origin="job"` only with a `job_id` and an operator actor; divergence
  resolution keeps firing for it (`origin != "runtime"` instead of `== "actor"`).
- `GET /tasks/{id}/transitions` and the MCP `task_history` carry `job_id` and the job's name; the
  history drawer reads **"Flow *<name>* moved …"** instead of "You moved …".
- A source scan (beside `test_only_the_binding_module_may_record_a_runtime_transition`) holds that
  only `scheduler.py` records `origin="job"`.

## Capabilities

### Modified Capabilities

- `task-lifecycle-governance` — adds a requirement for how a scheduled firing's moves are recorded.

## Impact

- **Migration** (next free number at IMPL time): one nullable `String(64)` column, **not** a foreign
  key (the SQLite drop trap recorded at `db/models.py:708-712`). Existing rows are not rewritten —
  history is append-only (`TaskTransition` docstring) and a backfill would invent a cause nobody
  observed; the 38 existing operator rows keep saying what they say.
- **UI:** `TaskTransitionHistory.tsx` and the `TaskTransition` type; one bundle refresh.
- No change to any guard, the transition map, or `ACTOR_KINDS`.
