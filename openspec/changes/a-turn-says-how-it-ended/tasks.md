## 1. The route carries the run's facts

- [ ] 1.1 Write a Hub test asserting the timeline response is an envelope carrying `events` and a
      `runs` map keyed by `run_id`, with `status`, `exit_code`, `started_at` and `ended_at` — and
      that a run whose status was corrected after its events were written reports the **corrected**
      status. Both scenarios come from *The timeline carries each run's own facts*.
- [ ] 1.2 Write a Hub test asserting an event naming a `run_id` with no row leaves that key absent
      rather than erroring, and a test asserting the map MAY contain runs no returned event names.
- [ ] 1.3 Add the envelope schema beside `AgentTimelineEvent` in `hub/hub/schemas/agents.py`, with
      `runs: Dict[str, RunFacts]`. Follow the `queue: Dict[str, int]` precedent in
      `hub/hub/schemas/jobs.py:125`.
- [ ] 1.4 Add the fourth query to `agent_timeline` (`hub/hub/api/v1/agents.py:729`) inside the
      existing `asyncio.gather`, scoped by `project_id` and `agent`, ordered by `started_at` desc
      with its own limit. Confirm by `EXPLAIN QUERY PLAN` that it uses `ix_runs_project_agent`.
- [ ] 1.5 Map `Run.status` `running` → `started` at the boundary (design D5) and change the route's
      `response_model`. Leave the `reverse=True` / `[:50]` event sort untouched.
- [ ] 1.6 Run the Hub tests that touch this route — `test_agent_actions_coordination`,
      `test_agent_chat`, `test_bola`, `test_codex_appserver_run_turn`, `test_failure_reporting`,
      `test_permission_approver`, `test_title_generation` — and fix what the shape change breaks.

## 2. The terminal status line is persisted

- [ ] 2.1 Write a Hub test asserting that after a run ends, `/agents/{name}/output` contains a
      `kind="status"` row carrying the exit code — asserted for **both** the process path and the
      app-server path, per *A run's terminal status line is persisted*.
- [ ] 2.2 Persist the status row at `hub/hub/api/v1/agent_trigger.py:2129-2142` (process path) in
      addition to broadcasting it, keeping the broadcast payload byte-identical so the live path is
      unchanged.
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
- [ ] 3.3 Read `AgentActivityTab.tsx` and `AgentOutputPanel.tsx` and update them for the unwrap.
      Neither is expected to need run facts; confirm that rather than assume it.

## 4. The reducers are deleted

- [ ] 4.1 Write a component test asserting the terminal label renders for a stopped run **from
      persisted state alone**, with no live stream — the reload scenario from *A run's terminal
      outcome is visible*. This must fail before 4.3 and pass after.
- [ ] 4.2 Write a component test asserting a `running` run presents no terminal label, and that a
      `failed` run and a silent `completed` run present different terminal states.
- [ ] 4.3 Point `AgentTimeline.tsx`'s three consumers at the map: the terminal label (`:202`),
      `lastRunSettled` (`:116`) and `anotherRunIsUnderway` (`:133`). Delete `runStatusByRunId`
      (`agentTimelineModel.ts:187-199`).
- [ ] 4.4 Point the duration display at `started_at`/`ended_at` and delete `runDurationsByRunId`
      (`:138-168`). **Carry its negative-duration guard across** — a clock that went backwards must
      still not render "Worked for -3s" (design D4).
- [ ] 4.5 Assert duration rendering in the component test, not only in a model test, since the model
      function it used to live in is gone.
- [ ] 4.6 Confirm `LIFECYCLE_EVENT_STATUS` has no remaining consumer; delete it if not, and keep it
      only if something still legitimately reads it.
- [ ] 4.7 Verify the third consequence is repaired: with a reloaded conversation containing several
      ended runs, the working indicator does not linger under a finished answer
      (`AgentTimeline.tsx:118-136`).

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
