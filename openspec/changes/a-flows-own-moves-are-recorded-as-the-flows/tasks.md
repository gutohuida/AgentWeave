## 0. Rounds and decision

- [x] 0.1 R2: independent re-derivation against `task_transition_service.py:555-720`, `scheduler.py:846-908,3336,3709`, `agent_trigger.py:860-905`, `run_divergence.py`, `tasks.py:_transition_view`, `TaskTransitionHistory.tsx`, `test_flow_chain_end_to_end.py:330-352`. Re-derive design's claim that `agent_trigger.py:898` only transitions on an operator dispatch
- [ ] 0.2 R3: second independent re-derivation; `openspec validate a-flows-own-moves-are-recorded-as-the-flows --strict` passes
- [ ] 0.3 The operator answers D8 (recorded cause vs third actor kind); recorded in `spec-queue/DECISIONS.md`

## 1. Tests first

- [ ] 1.1 `hub/tests/test_flow_chain_end_to_end.py:342-352`: replace the pin. Assert the set of `(task_id, to_status)` with `origin == "job"` is `{("task-chain-b","assigned"), ("task-chain-a","under_review")}`, each with `job_id` equal to the flow's job id, and that **no** row has `actor_kind == "operator"` with `origin == "actor"`. FAILS today (both rows are `origin="actor"`, no `job_id` attribute)
- [ ] 1.2 New `hub/tests/test_a_flows_moves_are_the_flows.py`: fire a loop (reuse `_make_loop_job` from `test_loop_busy_guard.py`) whose queue holds one pending task; the resulting `pending → assigned` row has `actor_kind == "operator"`, `origin == "job"`, `job_id == job.id`. FAILS today
- [ ] 1.3 Same file, control: `POST /agent/trigger` with `review_task_id` for a `completed` task (operator dispatch) records `origin == "actor"`, `job_id is None`. PASSES today and must keep passing
- [ ] 1.3a Same file (R2): a loop-queued review entry for task T (T staged `under_review` by the firing) is left queued while the reviewer is busy; the operator then moves T `under_review → revision_needed → in_progress → completed`; the entry is delivered. The `completed → under_review` row recorded at delivery has `origin == "job"` and `job_id == job.id`. FAILS today (`origin == "actor"`) — and would still fail under a fix that only touched the two scheduler callers
- [ ] 1.3b Same file (R2), control: the same delivery where the operator's own review trigger for T is among the delivered entries records `origin == "actor"`
- [ ] 1.4 Same file, unit: `apply_transition(..., origin="job")` without `job_id` raises `ValueError`; with a run actor raises `ValueError`; `origin="actor"` with a `job_id` raises `ValueError`. FAILS today (unknown origin raises for a different reason — assert on the message)
- [ ] 1.5 `hub/tests/test_task_transitions.py`: a source scan beside `test_only_the_binding_module_may_record_a_runtime_transition` — only `scheduler.py`, `api/v1/agent_trigger.py` and `task_transition_service.py` contain `ORIGIN_JOB`/`origin="job"`; every `enter_selected_task(` call in `scheduler.py` passes `job_id=`, and every `new_entry(` call in `scheduler.py` passes `job_id=`. FAILS today (no such constant)
- [ ] 1.6 `GET /tasks/{id}/transitions` after 1.2's firing: rows in the route's own order (oldest first by `sequence`), the job row carries `job_id`, `job_name` equal to the job's name and `job_kind == "loop"`; the same for a flow gives `"flow"`. FAILS today
- [ ] 1.7 UI (`hub/ui/src/__tests__/`): `TaskTransitionHistory` fed the route's real order renders `Flow <name> moved` for an `origin: 'job'`, `job_kind: 'flow'` row, `Loop <name> moved` for `job_kind: 'loop'`, and `You moved` for an `actor` operator row; a test reversing the two rows' order must still attribute each correctly (F190: the component must not rely on position). FAILS today

## 2. The fix

- [ ] 2.1 `ORIGIN_JOB`, `ORIGINS`, the `job_id` parameter and its checks in `apply_transition`; `job_id` written to the row; divergence resolution on `origin != ORIGIN_RUNTIME`
- [ ] 2.2 Model columns + one migration: `task_transitions.job_id` and `inbound_queue_entries.job_id` (both nullable `String(64)`, no FK; head bumps per `.claude/rules/db-migrations.md`). `new_entry(..., job_id=None)`; `scheduler.py:3404` and `:3736` pass `job.id`
- [ ] 2.3 `enter_selected_task(..., job_id: Optional[str] = None)`: pass `origin=ORIGIN_JOB, job_id=job_id` to both `apply_transition` calls when set; `scheduler.py:3336` and `:3709` pass `job.id`; at `agent_trigger.py:898` read the cause from the delivered entries naming the review task (design Context: operator entry present → actor; else a `job_id` → job), extending `_review_task_from_entries` to return it
- [ ] 2.4 `_transition_view` adds `job_id`, `job_name`, `job_kind`; MCP `task_history` docstring names the origin
- [ ] 2.5 UI type + `TaskTransitionHistory.tsx`; `npm run lint`, vitest, `make ui`; commit `hub/ui/src` and `hub/hub/static/ui` together

## 3. Verify

- [ ] 3.1 Group 1 passes; full `hub/tests/` with `claude` stripped from PATH; CLAUDE.md lint block
- [ ] 3.2 Drive a two-task flow on a trial Hub with Haiku agents; open a task's history drawer and record the lines verbatim
- [ ] 3.3 Sync the delta and archive
