# Tasks — a loop is stopped, archived and delegated from its own tab

## 0. Rounds

- [ ] 0.1 R2: re-derive, against `hub/hub/api/v1/jobs.py` (`update_job`, `archive_job`),
  `hub/hub/api/v1/loops.py`, `hub/hub/loop_ending.py`, `hub/ui/src/components/spec/LoopTab.tsx`,
  `hub/ui/src/hooks/useSSE.ts` and `openspec/specs/agent-loops/spec.md`, and without reading design
  D1-D4 first: (a) whether an operator stop really writes no `loop_stopped` event today; (b) whether
  D1's three reasons hold; (c) the state/visibility table in D4. Decide D2's open point (pin
  `stopped` for an operator stop) and D3's (move `archive_loop`/`set_loop_control` events into the
  transaction).
- [ ] 0.2 R3: the same, fresh.

## 1. Tests first — each must fail on today's code unless marked as a control

- [ ] 1.1 `hub/tests/test_loop_archival.py` (or a new `test_an_operator_stop_is_in_the_loops_history.py`):
  create a loop (`POST /jobs` with `purpose`), `PATCH /jobs/{id} {"stop_reason": "enough"}`, then
  `GET /loops/{loop_id}`: `events` holds exactly one `loop_stopped` whose `data.reason == "enough"`
  and `data.loop_id == loop_id`. **Fails today**: no such event. The test finds the event by
  `event_type`, not by position: the route returns events newest-first (`loops.py:76-80`).
- [ ] 1.2 Same file: patch `sse_manager.broadcast` and assert one `("loop_stopped", {..., "loop_id": loop_id})`
  call from the PATCH. **Fails today.**
- [ ] 1.3 Same file: a second `PATCH {"stop_reason": "reworded"}` on the ended loop adds **no**
  second `loop_stopped` event. It passes today as a control, because there are none, and must still
  pass after the fix.
- [ ] 1.4 Same file: make `persist_event` raise inside the stop PATCH (monkeypatch). The response is
  500, and a fresh read shows `ending_state is None` with the job still `enabled`. **Fails on a
  version that persists after commit.** That version would leave the loop ended with no event.
- [ ] 1.5 `hub/ui/src/__tests__/loopTabActions.test.tsx` (new). Mock `@/api/loops` with `useLoop`
  and the three new hooks. For a loop with `ending_state: null`, `archived_at: null`,
  `control: null`, `agent: 'worker'`: *Stop* is present, *Archive* absent, the text says you decide,
  and *Let worker decide* calls the control mutation with `{loopId, control: 'creator'}`. **Fails
  today**: no controls.
- [ ] 1.6 Same file: *Stop* → confirm → the stop mutation is called with `{jobId: 'job-1', reason:
  'Stopped by the operator'}` by default, or with the typed reason. With `firing_active: true` the
  confirmation contains *"The firing running now finishes"*.
- [ ] 1.7 Same file: `ending_state: 'stopped'`, `archived_at: null` → *Archive* present, *Stop* and
  the controller line absent. With `archived_at` set, neither is present.
- [ ] 1.8 Same file: `control: 'creator'` → the text names `worker`, and *Decide them yourself*
  calls the mutation with `control: 'operator'`.
- [ ] 1.9 Same file: a mutation in the error state with `detail` → a `role="alert"` line carries
  that text.
- [ ] 1.10 Same file: `agent: ''` → the delegation button is absent.

## 2. Implementation

- [ ] 2.1 `hub/hub/api/v1/jobs.py` `update_job`: `ended_now` before `end_loop`; when true,
  `persist_event(..., "loop_stopped", {job_id, loop_id, reason}, agent=agent_identity,
  loop_id=loop.id, commit=False)` before the commit, and the broadcast after it (design D3).
- [ ] 2.2 `archive_job` docstring: replace *"Revisit only if a stop control ships"* with the D1
  outcome.
- [ ] 2.3 `hub/ui/src/api/loops.ts`: `useStopLoop` (`patchJson` `/jobs/${jobId}` `{stop_reason}`),
  `useArchiveLoop` (`postJson` `/loops/${loopId}/archive`), `useSetLoopControl` (`postJson`
  `/loops/${loopId}/control` `{control}`). Each `onSettled` invalidates
  `['project', pid, 'loops']` and `['project', pid, 'jobs']`.
- [ ] 2.4 `hub/ui/src/components/spec/LoopTab.tsx`: an actions section per design D4.
- [ ] 2.5 Add the three hooks to the `vi.mock('@/api/loops', …)` factories in `loopTab.test.tsx`
  and `loopPendingEdit.test.tsx`. A factory without them makes `LoopTab` call `undefined`.
- [ ] 2.6 `hub/tests/test_surface_ceilings.py`: `CLIENTLESS_ROUTE_CEILING` 35 → 33, after running
  `py -3.11 scripts/drive/n10_route_reachability.py` and recording the new count.
- [ ] 2.7 `make ui` (or `scripts/refresh_ui_bundle.py`). Commit `hub/ui/src` and
  `hub/hub/static/ui` together (`.claude/rules/hub-ui.md`).

## 3. Verification

- [ ] 3.1 `py -3.11 -m pytest hub/tests/test_loop_archival.py hub/tests/test_surface_ceilings.py
  hub/tests/test_jobs_crud.py -q` with `claude` stripped from PATH, then the full `hub/tests/`.
- [ ] 3.2 `cd hub/ui && npm run lint && npx vitest run`.
- [ ] 3.3 The CLAUDE.md lint block.
- [ ] 3.4 Drive it on the trial Hub `:8010`, never `:8000`: see `test-guide.md` "Human-only".

## 4. Close

- [ ] 4.1 Foot F225 in `scripts/drive/FINDINGS.md` with the commit.
- [ ] 4.2 Sync the delta into `openspec/specs/agent-loops/spec.md` (run the R-2 collision script
  first; other open changes also carry `agent-loops` deltas) and archive the change.
