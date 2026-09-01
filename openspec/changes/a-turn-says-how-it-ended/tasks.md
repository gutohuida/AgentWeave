## 1. The route carries the run's facts

- [ ] 1.1 Write a Hub test asserting the timeline response is an envelope carrying `events` and a
      `runs` map keyed by `run_id`, with `status`, `exit_code`, `started_at` and `ended_at` — and
      that a run whose status was corrected after its events were written reports the **corrected**
      status. Both scenarios come from *The timeline carries each run's own facts*.
- [ ] 1.2 Write a Hub test asserting an event naming a `run_id` with no row leaves that key absent
      rather than erroring, and a test asserting the map contains **no** entries for runs the
      returned events do not name — *The map is scoped to the events*. Round 2 asked for the
      opposite assertion here; round 3's D3 narrowed the query, so the over-coverage it blessed no
      longer occurs.
- [ ] 1.3 Add the envelope schema beside `AgentTimelineEvent` in `hub/hub/schemas/agents.py`, with
      `runs: Dict[str, RunFacts]`. Follow the `queue: Dict[str, int]` precedent in
      `hub/hub/schemas/jobs.py:125`.
- [ ] 1.4 In `agent_timeline` (`hub/hub/api/v1/agents.py:729`), after the existing `asyncio.gather`
      and after the `events[:50]` truncation, collect the
      distinct `data["run_id"]` values the returned events carry, then read those rows with
      `select(Run).where(Run.id.in_(run_ids))` (design D3, rewritten in round 3). No `ORDER BY`, no
      `LIMIT`, and no `project_id`/`agent` scope on this query — the ids already came from rows the
      route filtered. Skip the query entirely when the set is empty. Leave the three existing
      queries in the `gather` untouched.
- [ ] 1.4a **Do not restore a concurrent, ordered, limited run query** — round 2 specified one
      ordered by `started_at` desc and round 3 reversed it, because a limit governs how many rows
      return and not which. `run_reconciliation.reconcile_interrupted_runs`
      (`run_reconciliation.py:59-66`) sweeps every still-`running` row in the database at Hub start
      and writes its `run_interrupted` event *then*, so an agent's newest events routinely name its
      oldest runs and a start-time ranking misses exactly those. If the round trip ever has to come
      back, read D3's rejected alternatives first.
- [ ] 1.4b Write the test from *An old run named by a recent event keeps its outcome*: give an agent
      a run that started well before its most recent ones, write that run's terminal `EventLog` row
      with a **current** timestamp (the shape reconciliation produces), fill the window with newer
      runs, and assert the old run is present in the map and renders its terminal outcome. Confirm
      it fails against a `Run` query ordered by `started_at` desc and limited, rather than assuming
      it does — that is the implementation this test exists to reject.
- [ ] 1.5 Map `Run.status` `running` → `started` at the boundary (design D5) and change the route's
      `response_model`. Leave the `reverse=True` / `[:50]` event sort untouched.
- [ ] 1.6 Fix what the shape change breaks in the Hub suite. Only `hub/tests/test_bola.py` actually
      requests `/agents/{name}/timeline`; `test_agent_actions_coordination`, `test_agent_chat`,
      `test_codex_appserver_run_turn`, `test_failure_reporting`, `test_permission_approver` and
      `test_title_generation` match a grep for "timeline" but exercise the *chat* timeline, a
      different route. Check them, but expect the work to be in one file.

## 2. The terminal status line is persisted

- [ ] 2.1 Write a Hub test asserting that after a run ends, `/agents/{name}/output` contains a
      `kind="status"` row carrying the exit code — asserted for **both** the process path and the
      app-server path, per *A run's terminal status line is persisted*.
- [ ] 2.2 Replace the bare broadcast at `hub/hub/api/v1/agent_trigger.py:2129-2142` (process path)
      with `output_recording.record_agent_output` (`hub/hub/output_recording.py:22`), which persists
      **and** broadcasts one row. Round 2's correction to D6: "persist in addition to broadcasting"
      invites a second insert beside the existing `sse_manager.broadcast` call and two sources of
      the same row. Confirm the broadcast payload it emits is field-for-field what the hand-rolled
      one emitted, since `AgentOutputPanel`'s Handoff flow scans for this exact shape.
- [ ] 2.3 Do the same at `:2723-2736` (app-server path).
- [ ] 2.4 Verify the row does not double-render: `isSuccessCompletionEntry` already hides the
      completed-phase status row from the transcript, so confirm a *completed* run gains no visible
      line while a stopped or failed run does.

## 3. The client consumes the envelope

- [ ] 3.1 Move the 11 UI test fixtures to the envelope shape in one commit, before touching any
      component: `agentHandoff`, `agentRunningComposer`, `batchedQuestionComposer`,
      `composerPermissionDefault`, `continueStartsWhatItNames`, `conversationControls`,
      `conversationDestination`, `handoffPlacement`, `specChatSurface`, `workingIndicator`,
      `agentTimelineModel`. Landing these first makes any later failure attributable to the change
      rather than to a fixture.
- [ ] 3.2 Update `useAgentTimeline` (`hub/ui/src/api/agents.ts:387-392`) and the
      `AgentTimelineEvent` types to the envelope, and check the SSE invalidation predicate at
      `:354-383` still names the right query key.
- [ ] 3.3 Update `AgentActivityTab.tsx` for the unwrap only — it maps events into activity items
      (`:24`, `:39`) and needs no run facts.
- [ ] 3.3a **`AgentOutputPanel` is not symmetric with it** (round 2's correction to the design's risk
      list). It holds the hook (`:330`) and its only other use of the value is passing it to
      `AgentTimeline` (`:1033`), where all three consumers live — and `AgentTimeline` takes
      `timelineEvents` as a prop (`AgentTimeline.tsx:31`) rather than calling the hook. So
      `AgentOutputPanel` must gain the `runs` map and thread it through as a new prop. It never
      reads the run facts; it is the only thing that can carry them.

## 4. The reducers are deleted

- [ ] 4.1 Write a component test asserting the terminal label renders for a stopped run **from
      persisted state alone**, with no live stream — the reload scenario from *A run's terminal
      outcome is visible*. This must fail before 4.3 and pass after.
- [ ] 4.2 Write a component test asserting a `running` run presents no terminal label, and that a
      `failed` run and a silent `completed` run present different terminal states.
- [ ] 4.3 Point `AgentTimeline.tsx`'s three consumers at the map: the terminal label (`:220`),
      `lastRunSettled` (`:114`) and `anotherRunIsUnderway` (`:131`). Delete `runStatusByRunId`
      (`agentTimelineModel.ts:187-199`).
- [ ] 4.4 Point the duration display at `started_at`/`ended_at` and delete `runDurationsByRunId`
      (`:138-168`). **Carry its negative-duration guard across** — a clock that went backwards must
      still not render "Worked for -3s" (design D4).
- [ ] 4.5 Assert duration rendering in the component test, not only in a model test, since the model
      function it used to live in is gone. **Re-baseline it rather than reconciling it** (design D4,
      round 3): `Run.started_at` is stamped at row construction (`agent_trigger.py:1073`) and the
      `run_started` event only once the pty exists (`:1857-1864`), so every duration now includes the
      spawn and reads longer than the event-derived figure. A run whose spawn failed (`:1798-1804`)
      also gains a duration it does not have today — confirm that renders acceptably rather than
      treating it as a regression.
- [ ] 4.6 Confirm `LIFECYCLE_EVENT_STATUS` has no remaining consumer; delete it if not, and keep it
      only if something still legitimately reads it.
- [ ] 4.7 Verify the third consequence is repaired **in both states, not just on reload**
      (`AgentTimeline.tsx:117-137`). Round 2's correction: `anotherRunIsUnderway` is OR'd into
      `runVisiblyActive`, so it defeats the live path too, and a reload-only check would pass while
      the live regression stood.
      - **Live:** an agent with two or more ended runs in its window, `isRunning` still true from the
        polled roster — assert the indicator is *not* shown once the newest run's status entry has
        streamed in. This is the 2026-08-18 tail complaint, and it is the case round 1 missed.
      - **Reloaded:** the same conversation loaded fresh with no live stream — assert the same.
      - **Still-underway:** stop a turn and send a new message; assert the indicator *is* shown while
        run B has no entries yet. This is the 2026-08-20 fix, which currently passes only vacuously
        (the indicator shows because it always shows) and must still pass once it means something.
      - **Single-run:** one run in the window — assert unchanged, since `anotherRunIsUnderway` was
        always correctly false here, which is why the defect survived manual review.

## 5. The testing rule is enforceable

- [ ] 5.1 Replace `agentTimelineModel.test.ts:223-235` — the fixture that feeds ascending events to
      a route that returns descending — with whatever survives step 4, and assert the *shuffled
      input* scenario from *Payload-shaped model functions are tested against real route ordering*.
- [ ] 5.2 Add a test that fails if the timeline route's ordering is reversed, so the coupling between
      route order and client expectation is asserted somewhere rather than assumed.
- [ ] 5.3 Record the rule where a reviewer will meet it, and note in `spec-queue/DECISIONS.md` (D-4)
      that the rule is now stated and only its sweep remains open.

## 6. Verified against a running Hub

- [ ] 6.1 Drive it: on the trial Hub with a fresh fixture project, start a turn, stop it mid-run,
      and confirm the conversation names the stop. Bind every real agent turn to `claude-haiku-4-5`.
- [ ] 6.2 Reload the page and confirm the label and the exit code are both still there — the
      scenario that neither carrier survived before this change.
- [ ] 6.3 Repeat for a failed run and an interrupted run (restart the Hub mid-run to produce the
      latter via `run_reconciliation.py:65`).
- [ ] 6.4 Confirm `hub/hub/static/ui` is rebuilt and stamped via
      `py -3.11 scripts/refresh_ui_bundle.py`, and that the bundle actually carries the change —
      grep the served bytes, not the source.
- [ ] 6.5 Delete the fixture project, confirm the project count returns to its prior value, and sweep
      for enabled jobs before finishing.
- [ ] 6.6 Run `ruff check src/ hub/ tests/`, `black --check --target-version py311 src/ hub/hub/
      hub/tests/ tests/`, `mypy src/`, the Hub suite and the UI suite. Record the numbers rather than
      asserting green.
- [ ] 6.7 Mark F190 retired in `scripts/drive/FINDINGS.md` only after 6.1–6.3 have actually been
      observed.
