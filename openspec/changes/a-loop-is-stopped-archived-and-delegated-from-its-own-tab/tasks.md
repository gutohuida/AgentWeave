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
- [ ] 0.3 Operator review, 2026-09-24 (Opus adversarial review, then the operator's decisions).
  **Done 2026-09-24.** A stop for an ended loop is now refused with 409 and changes nothing
  (design D2a): 1.3 rewritten, 1.3a-1.3c and 2.1b added, 2.1 and 2.2a amended. Hook-level test
  1.14 added. A blank reason falls back to the default (1.6). An archived agent hides the
  delegation toggle (1.10a, 2.4a). Two residuals are noted in the design, not fixed.

## 1. Tests first — each must fail on today's code unless marked as a control

- [ ] 1.1 `hub/tests/test_loop_archival.py` (or a new `test_an_operator_stop_is_in_the_loops_history.py`):
  create a loop (`POST /jobs` with `purpose`), `PATCH /jobs/{id} {"stop_reason": "enough"}`, then
  `GET /loops/{loop_id}`: `events` holds exactly one `loop_stopped` whose `data.reason == "enough"`
  and `data.loop_id == loop_id`. **Fails today**: no such event. The test finds the event by
  `event_type`, not by position: the route returns events newest-first (`loops.py:76-80`).
- [ ] 1.2 Same file: patch `sse_manager.broadcast` and assert one `("loop_stopped", {..., "loop_id": loop_id})`
  call from the PATCH. **Fails today.**
- [ ] 1.3 Same file: stop a loop with `{"stop_reason": "enough"}`, read its `ending_state`,
  `stop_reason` and `stopped_at` from the DB, then send a second `PATCH {"stop_reason":
  "reworded"}`. It answers **409**. This is a response, not a raised exception: FastAPI handles
  `HTTPException` even under `raise_app_exceptions=True`. `detail.code == "loop_already_ended"`,
  and `detail.message` contains `"already ended"` and `"enough"`. A fresh read shows all three
  fields equal to the first read, and `GET /loops/{id}` `events` holds exactly one `loop_stopped`.
  **Fails today**: 200, and `stop_reason` becomes `"reworded"` with a new `stopped_at` (design D2a).
- [ ] 1.3a Same file: a loop that ended by its own firing. Seed `ending_state="completed"`,
  `stop_reason="loop queue is empty"` and `stopped_at` directly, as
  `test_an_operator_stop_actually_stops.py:131-134` does. `PATCH {"stop_reason": "x", "name":
  "renamed"}` answers 409, and the job's `name` is unchanged. The whole request is refused, not
  half-applied. **Fails today.**
- [ ] 1.3b Same file: stop a loop, then `POST /jobs/{id}/archive` as the operator. It answers 200.
  `loop.archived_at` is set, and `ending_state`, `stop_reason` and `stopped_at` equal their values
  before the archive. A control: it passes today and must still pass. It shows that D2a's guards
  leave `archive_job` working on an ended loop.
- [ ] 1.3c `hub/tests/test_an_operator_stop_actually_stops.py` (or a new unit file): call `end_loop`
  directly. On a `Loop` with `ending_state="completed"`, `stop_reason="loop queue is empty"` and
  `stopped_at=t0`, call `end_loop(job, loop, reason="loop stop time reached (…)", when=t1,
  completed=False)`. It returns `False`, the three fields are unchanged, and `job.enabled is
  False`. On a loop with `ending_state=None`, it returns `True` and writes all three. **Fails
  today**: the reason and time are overwritten, and it returns `None`. This covers the scheduler's
  caller (`scheduler.py:3156`), which a route test cannot reach.
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
  confirmation contains *"The firing running now finishes"*. If the operator clears the field, or
  types only spaces, and confirms, the mutation gets `reason: 'Stopped by the operator'`.
  `'  enough  '` sends `'enough'` (design D2, operator review).
- [ ] 1.7 Same file: `ending_state: 'stopped'`, `archived_at: null` → *Archive* present, *Stop* and
  the controller line absent. With `archived_at` set, neither is present.
- [ ] 1.8 Same file: `control: 'creator'` → the text names `worker`, and *Decide them yourself*
  calls the mutation with `control: 'operator'`.
- [ ] 1.9 Same file: a mutation in the error state with `detail` → a `role="alert"` line carries
  that text. A second case uses D2a's 409 body, a structured `detail` with `message` and `code:
  'loop_already_ended'`. The alert carries the `message` sentence, not the fallback.
- [ ] 1.10 Same file: `agent: ''` → the delegation button is absent.
- [ ] 1.10a Same file: mock `@/api/agents` `useAgents` so that `useAgents('archived')` returns
  `[{name: 'worker', lifecycle: 'archived'}]`. The delegation button is absent, and the controller
  line is still present. With an archived list that does not name `worker`, or one still loading,
  the button is present. **Fails today**: no controls (design D4).
- [ ] 1.14 `hub/ui/src/__tests__/loopsApi.test.tsx` (new). Follow `tasksApi.test.tsx`: a real
  `QueryClient`, `renderHook`, `globalThis.fetch` replaced with a recorder, and
  `useConfigStore.setState({selectedProjectId: 'proj-1', hubUrl: 'http://hub.test', …})`. Spy on
  `client.invalidateQueries`. For each hook, assert the recorded request:
  - `useStopLoop().mutateAsync({jobId: 'job-1', reason: 'enough'})` → `PATCH
    http://hub.test/api/v1/projects/proj-1/jobs/job-1`, JSON body exactly `{stop_reason: 'enough'}`,
    with no `enabled` key (see design *Residuals*);
  - `useArchiveLoop().mutateAsync({loopId: 'loop-1'})` → `POST …/loops/loop-1/archive`;
  - `useSetLoopControl().mutateAsync({loopId: 'loop-1', control: 'creator'})` → `POST
    …/loops/loop-1/control`, body `{control: 'creator'}`.

  Then answer each with an error (`ok: false`, `status: 409`, body the D2a detail) and await the
  rejected `mutateAsync`. `invalidateQueries` was still called with `{queryKey: ['project',
  'proj-1', 'loops']}` and with `{queryKey: ['project', 'proj-1', 'jobs']}`. That proves
  `onSettled`, not `onSuccess`. **Fails today**: the hooks do not exist.

## 2. Implementation

- [ ] 2.1 `hub/hub/api/v1/jobs.py` `update_job`: first, D2a's refusal. Place it right after the
  loop is resolved (`:998-1000`) and before any mutation: if `stop_reason` is given, the loop
  already existed, and `ending_state is not None`, raise 409 with the structured detail
  (`code: "loop_already_ended"`). Then, in the stop branch, call `persist_event(...,
  "loop_stopped", {job_id, loop_id, reason}, agent=agent_identity, loop_id=loop.id, commit=False)`
  before the commit (design D3). No `ended_now` branch is needed there, because the refusal
  guarantees the loop was running. Also move the existing
  `loop_edit_staged` row (`:1152`) above the commit with `commit=False`. The frames go in design
  D3's table order: `loop_edit_staged`, `loop_stopped`, `job_updated`.
- [ ] 2.2 `archive_job` docstring: replace *"Revisit only if a stop control ships"* with the D1
  outcome. Also in `archive_job` (design D3a): capture `ended_now` before `end_loop`. Before the
  commit, persist `loop_stopped` (when `ended_now`) and `loop_archived` `{"id": loop.id}` with
  `loop_id=loop.id, commit=False`. Also move the existing `job_archived` row (`:1291`) above the
  commit with `commit=False`. The frames go `job_archived`, `loop_stopped`, `loop_archived`.
- [ ] 2.1b Rewrite the two tests that pin the rewording (design D2a).
  `hub/tests/test_an_operator_stop_actually_stops.py::test_a_second_stop_reason_does_not_overwrite_the_recorded_ending_state`
  (`:123-143`) now expects the second PATCH to answer 409, with `stop_reason == "enough"` and
  `ending_state == "completed"` as seeded. Rename it to say that a second stop is refused.
  `hub/tests/test_loop_archival.py::test_operator_supplied_stop_reason_records_a_stopped_ending`
  (`:428-435`) now expects `edited.status_code == 409` and the first reason kept. Record both in the
  commit message as intended behaviour changes, not regressions.
- [ ] 2.2a `hub/hub/loop_ending.py`: `end_loop(..., completed: bool) -> bool`, required and
  keyword-only. The `QUEUE_DRAINED_REASON` comparison moves to `scheduler.py:3156`. Both routes pass
  `completed=False`. **Write-once (D2a):** if `loop.ending_state is not None`, clear `job.enabled`
  and return `False` without touching `stop_reason`, `stopped_at` or `ending_state`. Otherwise,
  write all three and return `True`. Replace the docstring's *"the operator editing the prose after
  the fact"* (`:48-50`) with the rule: an ending is recorded once, and a later call changes nothing
  about it. Update the module docstring (design D2). `archive_job` may use the return value instead
  of its own `ended_now` capture.
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
- [ ] 2.4 `hub/ui/src/components/spec/LoopTab.tsx`: an actions section per design D4. The stop
  sends `reason.trim() || 'Stopped by the operator'`.
- [ ] 2.4a Same component: read `useAgents('archived')` and hide the delegation toggle when that
  list names `loop.agent` (design D4).
- [ ] 2.5 Add the three hooks to the `vi.mock('@/api/loops', …)` factories in `loopTab.test.tsx`
  and `loopPendingEdit.test.tsx`. A factory without them makes `LoopTab` call `undefined`. Add
  `vi.mock('@/api/agents', () => ({ useAgents: () => ({ data: [] }) }))` to both files as well
  (2.4a). Without it, `useAgents` needs a `QueryClientProvider`, which those tests do not render.
- [ ] 2.6 `hub/tests/test_surface_ceilings.py`: `CLIENTLESS_ROUTE_CEILING` 35 → 33, after running
  `py -3.11 scripts/drive/n10_route_reachability.py` and recording the new count.
- [ ] 2.7 `make ui` (or `scripts/refresh_ui_bundle.py`). Commit `hub/ui/src` and
  `hub/hub/static/ui` together (`.claude/rules/hub-ui.md`).

## 3. Verification

- [ ] 3.1 `py -3.11 -m pytest hub/tests/test_loop_archival.py hub/tests/test_surface_ceilings.py
  hub/tests/test_jobs_crud.py hub/tests/test_an_operator_stop_actually_stops.py -q` with `claude` stripped from PATH, then the full `hub/tests/`.
- [ ] 3.2 `cd hub/ui && npm run lint && npx vitest run`.
- [ ] 3.3 The CLAUDE.md lint block.
- [ ] 3.4 Drive it on the trial Hub `:8010`, never `:8000`: see `test-guide.md` "Human-only".

## 4. Close

- [ ] 4.1 Foot F225 in `scripts/drive/FINDINGS.md` with the commit.
- [ ] 4.2 Sync the delta into `openspec/specs/agent-loops/spec.md` (run the R-2 collision script
  first; other open changes also carry `agent-loops` deltas) and archive the change.
