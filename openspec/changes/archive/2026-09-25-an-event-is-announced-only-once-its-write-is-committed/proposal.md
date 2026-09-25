# Proposal — an event is announced only once its write is committed

**Round 1, 2026-09-24** (bundle B9, spec track S4). Finding: **F335 (D)**. Re-verified on the
worktree's HEAD `ce086b6` (code identical to `404c7d5` for every file cited). **Nothing here is
implemented yet.** This change must land **with or before** `every-event-the-hub-sends-reaches-the-app`
(F251): that change admits `run_divergence_resolved` to the app, and without this one the app would
then render F335's false line.

## Why

`resolve_divergences_for_task` (`hub/hub/run_divergence.py:66-107`) closes a task's open
divergences when the task enters review. It is reached from `apply_transition`
(`hub/hub/task_transition_service.py:709-711`), whose caller commits. So it stages its writes —
`resolved_at` on each row (`:93-94`) and an event row through `persist_event(..., commit=False)`
(`:97-103`) — and then **broadcasts at once** (`:104`), before anything is committed. Its own
docstring argues this is safe (`:82-83`: *"`sse_manager.broadcast` needs no such care: its payload
is exactly what is already in memory"*). That argument is the defect: what is in memory may be
rolled back.

It is. When a review is refused at delivery (`prepare_review_turn` after `enter_selected_task`),
F319's fix rolls the scheduler's transaction back. The divergence stays open and no event row is
written, but the live stream has already carried `run_divergence_resolved` — measured on the wire
by the 2026-09-13 day drive (`curl -N /api/v1/events`: `event: run_divergence_resolved`,
`data: {"task_id":"task-1275228c05dd","count":1,...}`, 0 rows written). Today the app drops that
kind (F251), so no screen shows it. Once F251 is fixed, the Activity feed renders
*"1 open divergence on T resolved"* (`hub/ui/src/lib/eventSummary.ts:149`) for a divergence that
is still open.

Re-verified: the broadcast is still at `run_divergence.py:104`, after `persist_event(commit=False)`
at `:97-103`; `apply_transition` is still its only caller (`task_transition_service.py:711`). A scan
of every `persist_event(..., commit=False)` site (`run_divergence.py:102`,
`task_transition_service.py:776`, `:797`) finds this the **only** one followed by a broadcast.

## What changes

- The Hub gains one way to announce a staged write: an announcement **deferred to the commit of the
  session that staged it**, published when that session's root transaction commits and discarded
  when it rolls back or ends uncommitted.
- `resolve_divergences_for_task` uses it. A refused review announces nothing; a real one announces
  `run_divergence_resolved` exactly once, after its commit.
- `SSEManager` gets one synchronous funnel (`publish`) that both the existing `async broadcast` and
  the deferred path go through, so a test can observe every frame at one point.
- A test forbids the shape from coming back: a function that stages an event row with
  `commit=False` may not call `sse_manager.broadcast` directly, even after its own commit, and a
  function that commits itself may not defer an announcement after its last commit (where it would
  be silently discarded). Each failure message says what to do instead, because B10's
  `a-loop-is-stopped-archived-and-delegated-from-its-own-tab` adds four functions of that shape and
  whichever change lands second converts them (design D4).

## What does not change

- Every other broadcast site. They run after their own commit (routes commit, then broadcast;
  `persist_event`'s default `commit=True` commits before the broadcast that follows it). The
  ordering of `run_divergence_resolved` before the PATCH route's `task_updated` is kept (design D3).
- The event row, the divergence rows, and F319's rollback.

## Impact

- `hub/hub/sse.py` (a `publish` funnel, a `defer_broadcast` helper and two session listeners),
  `hub/hub/run_divergence.py` (one call), tests. No migration, no UI change.
- Spec: `local-project-workspace` gains *"An event is announced only once the write it reports is
  committed"*.
