# Tasks — a loop is stopped, archived and delegated from its own tab

## 0. Rounds

- [ ] 0.1 R2: re-derive, against `hub/hub/api/v1/jobs.py` (`update_job`, `archive_job`),
  `hub/hub/api/v1/loops.py`, `hub/hub/loop_ending.py`, `hub/ui/src/components/spec/LoopTab.tsx`,
  `hub/ui/src/hooks/useSSE.ts` and `openspec/specs/agent-loops/spec.md`, and without reading design
  D1-D4 first: (a) whether an operator stop really writes no `loop_stopped` event today; (b) whether
  D1's three reasons hold; (c) the state/visibility table in D4. Decide D2's open point (pin
  `stopped` for an operator stop) and D3's (move `archive_loop`/`set_loop_control` events into the
  transaction).
  **Done 2026-09-24.** D2: pin `stopped`. D3: yes, and extended to `archive_job` (D3a/D3b).
  See the B10 record.
- [ ] 0.2 R3: the same, fresh. Also confirm the B9 `ast` guard's wording (design D3).
  **Done 2026-09-24.** B9 is final, and its guard has a second rule: a deferred announcement must
  come before the function's own last commit. So design D3 now moves every event row of the four
  functions into the transaction, and it fixes the frame order in a table. 2.1, 2.2 and 2.2c were
  rewritten to match. The human-only steps read loop history through the API, because `LoopTab`
  renders no events.

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
- [ ] 1.4 Same file: make `persist_event` raise inside the stop PATCH. Monkeypatch
  `hub.api.v1.jobs.persist_event`, the name the route imported, not `hub.utils`. The conftest
  client is `ASGITransport` with the default `raise_app_exceptions=True` (`conftest.py:864`), so the
  exception reaches the test rather than a 500. Wrap the call in `pytest.raises`, or build a local
  client with `raise_app_exceptions=False` and assert 500. Then a fresh read shows
  `ending_state is None` with the job still `enabled`. **Fails on a version that persists after
  commit.** That version would leave the loop ended with no event.
- [ ] 1.11 Same file: `PATCH {"stop_reason": "loop queue is empty"}` on a running loop →
  `GET /loops/{id}` `ending_state == "stopped"`. **Fails today**: it reads `completed`. It
  guards design D2.
- [ ] 1.12 Same file: archive a **running** loop's job (`POST /jobs/{id}/archive`, operator).
  `GET /loops/{loop_id}` `events`, looked up by `event_type`, holds one `loop_stopped` with
  `data.reason == "archived with its job"` and one `loop_archived`. **Fails today**: neither is
  written against the loop. A second case archives an already-ended loop's job: `loop_archived`
  is present and no `loop_stopped` is added.
- [ ] 1.13 Same file: monkeypatch `hub.api.v1.loops.persist_event` to raise on
  `POST /loops/{id}/control {"control": "creator"}`. A fresh read shows `control is None`. **Fails
  today**: the control commits before the event write. Do the same for `/archive` on an ended loop:
  `archived_at` stays `None`.
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
  loop_id=loop.id, commit=False)` before the commit (design D3). Also move the existing
  `loop_edit_staged` row (`:1152`) above the commit with `commit=False`. The frames go in design
  D3's table order: `loop_edit_staged`, `loop_stopped`, `job_updated`.
- [ ] 2.2 `archive_job` docstring: replace *"Revisit only if a stop control ships"* with the D1
  outcome. Also in `archive_job` (design D3a): capture `ended_now` before `end_loop`. Before the
  commit, persist `loop_stopped` (when `ended_now`) and `loop_archived` `{"id": loop.id}` with
  `loop_id=loop.id, commit=False`. Also move the existing `job_archived` row (`:1291`) above the
  commit with `commit=False`. The frames go `job_archived`, `loop_stopped`, `loop_archived`.
- [ ] 2.2a `hub/hub/loop_ending.py`: `end_loop(..., completed: bool)`, required and keyword-only.
  The `QUEUE_DRAINED_REASON` comparison moves to `scheduler.py:3156`. Both routes pass
  `completed=False`. Update the module docstring (design D2).
- [ ] 2.2b `hub/hub/api/v1/loops.py` `archive_loop` / `set_loop_control`: `persist_event(...,
  commit=False)` before `session.commit()`, then the broadcast (design D3b).
- [ ] 2.2c Check whether B9's `an-event-is-announced-only-once-its-write-is-committed` has landed
  (`grep -n "def defer_broadcast" hub/hub/sse.py`).
  - **Landed:** every frame in design D3's table is a `defer_broadcast(...)` placed **above** its
    function's own `session.commit()` (`update_job`, `archive_job`, `archive_loop`,
    `set_loop_control`), in the table's order. None is left where today's post-commit broadcast
    sits, because rule 2 fails that and nothing would publish it. Test 1.2's spy moves to
    `SSEManager.publish`. Run `test_no_staged_event_is_broadcast_before_commit` and
    `test_no_announcement_is_deferred_after_the_last_commit`.
  - **Not landed:** the frames are `await sse_manager.broadcast(...)` after each commit, in the
    same order. Record in the commit message that B9's task 2.4b now applies to these four
    functions.
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
