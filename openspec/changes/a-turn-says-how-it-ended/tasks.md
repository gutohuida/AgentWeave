## 0. Observed before anything is built — a gate, not a preamble

**Operator condition of approval, 2026-09-01: this change is approved on the condition that the
defect is observed live before a line is implemented.** Every behavioural claim in `proposal.md` and
`design.md` is read from code and none has been watched happen. Four sittings of review each found
the defect nearest the code that sitting happened to read; three of them read the gate expression
and none checked where its inputs come from. A drive is what checks the product.

**If phase 0 has not been completed and recorded, do phase 0 and stop.** Do not begin phase 1.
An unattended window that reaches this change with no observation record performs the observations,
commits the write-up, and then **moves on to the next item in its queue** — it does not end the
window, and it does not proceed to phase 1 on the strength of having just done phase 0. The
observations are meant to be read by a person, or at minimum by a later sitting, before anything is
built on them.

- [x] 0.1 Trial Hub on **8011** — the night window's drive Hub (`.claude/loops/night-window.md`;
      this line said 8010 until 2026-09-01, which was stale, and 8010 is the operator's trial
      instance) — started from `hub/` with uvicorn from source, against a **fresh
      fixture project** — never `proj-5e960453` or `proj-18e5d4e0`. Bind every real agent turn to
      `claude-haiku-4-5`. Port 8000 is the operator's real usage: never touch it.
- [x] 0.2 **The headline.** DONE 2026-09-01, **confirmed** — `run-2ee37e1352f3` stopped,
      database says `stopped`, route says `started`, no label, and the conversation holds
      the operator's message and nothing else. The `interrupted` case was measured too and
      behaves identically. Start a turn, stop it mid-run. Confirm the conversation presents **no
      terminal label** — the turn simply ends. This is F190 as filed, and it is the one claim four
      rounds agree on.
- [x] 0.3 **DONE 2026-09-01 — FALSIFIED. Round 2 was right; round 3b is wrong.** The
      indicator released on the same snapshot the answer landed, 0.7 s before the roster
      poll, gated by signal 1. `isSuccessCompletionEntry` **does** match: the completed
      run's persisted `status` row comes from the stream parser, not from the broadcast at
      `agent_trigger.py:2135` that round 3b traced. **Phase 1 onwards is blocked until a
      round re-argues D6 from the true premise** — signal 1 has never worked *for a run
      that did not complete*, which is narrower than the proposal claims and still real.
      Superseded, kept for the record: **The single-run indicator — the claim no round has observed and two rounds got wrong.**
      In a conversation with exactly **one** run, watch the working indicator as the answer lands.
      Round 2 concluded this case was unaffected; round 3's supplementary pass concluded it is
      broken via `lastRunSettled`'s never-firing first signal. Confirm which is true: does the
      indicator disappear when the response text arrives, or does it linger until the roster poll
      catches up? **If it disappears cleanly, the R3b finding is wrong and the change must go back
      for another round before implementation.**
- [x] 0.4 **The multi-run indicator.** DONE 2026-09-01, **confirmed**, and caught live: the
      same agent released cleanly with one run in the window and lingered under a finished
      answer with two. Same observation with **two or more** ended runs in the
      window. Round 2's correction 1 predicts the indicator is governed by `isRunning` alone.
- [x] 0.5 **The reload.** DONE 2026-09-01, **confirmed** — label still absent, and zero
      `kind="status"` rows for the stopped run out of nine output rows. Reload the conversation. Confirm the terminal label is still absent and
      that `GET /agents/{name}/output` holds **no** `kind="status"` row for the stopped run —
      round 1 measured this; confirm it still holds.
- [x] 0.6 **The recency skew that reversed D3.** DONE 2026-09-01, **confirmed** —
      `run_interrupted` at 22:24:01 against `Run.started_at` 22:22:13, a gap equal to the
      outage and to nothing about the run. The *miss* was not reproduced (see the write-up). Leave a `Run` row at `running` whose process is
      gone, restart the Hub, and read the database directly: confirm the `run_interrupted` `EventLog`
      row carries a **restart-time** timestamp while that run's `Run.started_at` is old. This is the
      fact that makes a `started_at`-ordered run query miss runs the events name. A direct DB read
      is sufficient; no UI observation is needed.
- [x] 0.7 DONE 2026-09-01 — `scripts/drive/FINDINGS.md`, *F190 phase 0 — the observation
      gate, driven 2026-09-01*. Fixture deleted, project count back to its prior value, no
      job or loop created. Superseded, kept for the record: Record what was actually seen — including anything that contradicts the design — in
      `scripts/drive/FINDINGS.md` beside F190. **An observation that falsifies a claim stops the
      change and returns it to a round.** Then delete the fixture project, confirm the project count
      returns to its prior value, and sweep for enabled jobs.

**UNBLOCKED 2026-09-02 by round RA.** Phase 0 falsified round 3b's premise for D6 (task 0.3) and
task 0.7 returned the change to a round. That round ran on 2026-09-02, re-derived D6 against
`AgentTimeline.tsx`, `agentTimelineModel.ts`, `runner_parsing.py`, `runner_events.py`,
`output_recording.py`, `agent_chat.py`, `run_reconciliation.py` and both terminal paths in
`agent_trigger.py`, and rewrote D6 from what was measured: **signal 1 fires, for a run that
finished, written by the stream parser at `runner_parsing.py:356`; D6 extends it to runs that did
not.** The change is not narrowed — every phase below still follows — but three tasks change and
three are added (2.1a, 4.5a, and the interrupted exclusion in 2.1).

**Verified and corrected 2026-09-02 by round RB.** RB re-derived RA's argument against the code
independently. Every fact RA stated is right; the **scope** it drew around one of them is not.
`parse_claude_line` runs only for the three Claude-family runner values (`agent_trigger.py:1867`)
and `status_event("completed")` occurs exactly once in the whole Hub, so signal 1 has **never**
fired for a Codex run of either transport — for any outcome, including a clean completion. RA
generalised a Claude-only producer to the product. Four tasks are corrected for it (2.1's stated
reason, 2.1a, 4.7's completed-run guard, 7.1's baseline) and one is added (2.1b). Separately,
**task 4.5a offered two fixes as equivalents and one of them does not work** — RB implemented and
ran both; 4.5a now names the one that passes and says why the other fails. Read design D6 and the
*Round RA* and *Round RB* sections before implementing phase 2 or phase 4.

Phases 1 and 3 were not touched by either correction and need no re-reading beyond their own text.

## 1. The route carries the run's facts

- [x] 1.1 Write a Hub test asserting the timeline response is an envelope carrying `events` and a
      `runs` map keyed by `run_id`, with `status`, `exit_code`, `started_at` and `ended_at` — and
      that a run whose status was corrected after its events were written reports the **corrected**
      status. Both scenarios come from *The timeline carries each run's own facts*.
- [x] 1.2 Write a Hub test asserting an event naming a `run_id` with no row leaves that key absent
      rather than erroring, and a test asserting the map contains **no** entries for runs the
      returned events do not name — *The map is scoped to the events*. Round 2 asked for the
      opposite assertion here; round 3's D3 narrowed the query, so the over-coverage it blessed no
      longer occurs.
- [x] 1.3 Add the envelope schema beside `AgentTimelineEvent` in `hub/hub/schemas/agents.py`, with
      `runs: Dict[str, RunFacts]`. Follow the `queue: Dict[str, int]` precedent in
      `hub/hub/schemas/jobs.py:125`.
- [x] 1.4 In `agent_timeline` (`hub/hub/api/v1/agents.py:729`), after the existing `asyncio.gather`
      and after the `events[:50]` truncation, collect the
      distinct `data["run_id"]` values the returned events carry, then read those rows with
      `select(Run).where(Run.project_id == project_id, Run.id.in_(run_ids))` (design D3, rewritten
      in round 3). No `ORDER BY` and no `LIMIT` — the ids are the bound. **Keep the `project_id`
      predicate**: round 3's first draft of this task dropped it, reasoning that the ids already
      came from rows the route had filtered. That is true and it is inference, not enforcement —
      the `runs` map is a new cross-project leak surface and `ix_runs_project_agent` makes the
      predicate free. Skip the query entirely when the id set is empty. Leave the three existing
      queries in the `gather` untouched.
- [x] 1.4a **Do not restore a concurrent, ordered, limited run query** — round 2 specified one
      ordered by `started_at` desc and round 3 reversed it, because a limit governs how many rows
      return and not which. `run_reconciliation.reconcile_interrupted_runs`
      (`run_reconciliation.py:59-66`) sweeps every still-`running` row in the database at Hub start
      and writes its `run_interrupted` event *then*, so an agent's newest events routinely name its
      oldest runs and a start-time ranking misses exactly those. If the round trip ever has to come
      back, read D3's rejected alternatives first.
- [x] 1.4b Write the test from *An old run named by a recent event keeps its outcome*: give an agent
      a run that started well before its most recent ones, write that run's terminal `EventLog` row
      with a **current** timestamp (the shape reconciliation produces), fill the window with newer
      runs, and assert the old run is present in the map and renders its terminal outcome. Confirm
      it fails against a `Run` query ordered by `started_at` desc and limited, rather than assuming
      it does — that is the implementation this test exists to reject.
- [x] 1.5 Map `Run.status` `running` → `started` at the boundary (design D5) and change the route's
      `response_model`. Leave the `reverse=True` / `[:50]` event sort untouched.
- [x] 1.6 Fix what the shape change breaks in the Hub suite. Only `hub/tests/test_bola.py` actually
      requests `/agents/{name}/timeline`; `test_agent_actions_coordination`, `test_agent_chat`,
      `test_codex_appserver_run_turn`, `test_failure_reporting`, `test_permission_approver` and
      `test_title_generation` match a grep for "timeline" but exercise the *chat* timeline, a
      different route. Check them, but expect the work to be in one file.
      **What breaks there, precisely:** `test_cross_project_list_reads_return_empty_data`
      (`test_bola.py:193`) puts the timeline in a `list_endpoints` loop that asserts
      `isinstance(data, list)` and that no project-A id appears in any item (`:212-220`). Move it
      out of that loop into its own block — the same treatment the agent-sessions dict wrapper
      already gets at `:222-225` — and assert **both** halves are clean: no project-A id among
      `events`, and `runs == {}`. Do **not** simply drop the path from the list: this is the only
      cross-project isolation coverage this route has, and the `runs` map is a new leak surface that
      needs it more than the events did.

## 2. The terminal status line is persisted

- [x] 2.1 Write a Hub test asserting that after a run ends, `/agents/{name}/output` contains a
      `kind="status"` row carrying the exit code — asserted for **both** the process path and the
      app-server path, per *A run's terminal status line is persisted*. Assert it for a **stopped**
      and a **failed** run specifically, not only a completed one: on a **Claude** runner a completed
      run already has such a row from the stream parser (`runner_parsing.py:356`), so a
      completed-only test on that runner passes without task 2.2 being implemented at all and proves
      nothing. Round RB's correction to the reason, not to the instruction: this is **runner-scoped**
      — a completed *Codex* run has no such row today, so a completed-only test there would fail
      honestly. Assert stopped and failed anyway; they are the cases no runner covers. **Do not
      assert it for an
      `interrupted` run** — `reconcile_interrupted_runs` writes an `EventLog` row and no
      `AgentOutput` (grep `record_agent_output` in `run_reconciliation.py`: no hits), and there was
      no Hub process alive to write one. The spec now states that bound explicitly.
- [x] 2.1a Assert what a **completed run on a Claude runner** now carries: two entries satisfying
      `isSuccessCompletionEntry` — the parser's (`content="Completed"`, `payload` with `version`,
      `phase`, `summary`) and the finalize block's (`content="Run … (exit N)."`, `payload` with
      `phase` and `exit_code`) — and that the conversation still draws neither, because
      `AgentTimeline.tsx:430` returns `null` for both. This test exists so a later reader does not
      "de-duplicate" the pair: removing the parser's row deletes the only signal that works today,
      and removing the finalize block's for a completed run makes the durable exit code
      outcome-dependent. Design D6, *Two consequences of persisting an invisible row*. **Bind the
      fixture to a Claude runner explicitly** (round RB): the pair exists only where
      `parse_claude_line` runs, so a fixture that happens to be built on a `codex` runner would fail
      this assertion for a correct reason and send the next reader hunting a defect that is not
      there.
- [x] 2.1b **Assert the Codex case, which is the one 2.2 changes most and which no round before RB
      named.** `parse_claude_line` is selected only for `runner in ("claude", "claude_proxy",
      "native")` (`agent_trigger.py:1867`); `parse_codex_line`'s only `status_event` is `"plan"`
      (`runner_parsing.py:574`) and the app-server transport's only `status_event` is `"plan"`
      (`codex_appserver.py:544`). `status_event("completed")` occurs exactly once in the whole Hub.
      So a Codex run has **never** had a persisted `phase="completed"` row for any outcome,
      including a clean completion, and after 2.2 it gains its first — not a second. Assert exactly
      one such entry for a completed Codex run, and assert that codex's own `phase="plan"` status
      row does **not** satisfy `isSuccessCompletionEntry` (RB measured that it does not). Design D6's
      runner column, and F270.
- [x] 2.2 Replace the bare broadcast at `hub/hub/api/v1/agent_trigger.py:2129-2142` (process path)
      with `output_recording.record_agent_output` (`hub/hub/output_recording.py:22`), which persists
      **and** broadcasts one row. Round 2's correction to D6: "persist in addition to broadcasting"
      invites a second insert beside the existing `sse_manager.broadcast` call and two sources of
      the same row. Two corrections from round 3's supplementary pass:
      - **The broadcast cannot be field-for-field identical, and does not need to be.** The key set
        matches exactly, but `record_agent_output` hardcodes `id=f"out-{short_id()}"`
        (`output_recording.py:81`) with no override, so the deterministic `status-{run_id}` id is
        lost. Nothing in `hub/ui/src` keys on that id — verified by grep — so this is safe. Do not
        add an id parameter to the helper for it.
      - **The justification previously given here is stale.** The `AgentOutputPanel` Handoff effect
        that scanned the output stream for this line was **deleted** (`AgentOutputPanel.tsx:148-151`
        "`lines` is no longer read here", `:252-259` "deleted, not replaced"), though
        `agent_trigger.py:2121-2126` still claims removing the broadcast "would silently break that
        feature". The consumer that actually matters is `lastRunSettled`
        (`AgentTimeline.tsx:115`), and it reads the **persisted** row through
        `isSuccessCompletionEntry` — `kind='agent_output'`, `output_kind='status'`,
        `payload.phase='completed'` — not the broadcast payload. Preserve *that* shape.
      - **What this task is worth, corrected by round RA, 2026-09-02.** Rounds 1-3 said 2.2 is
        load-bearing for the working indicator. It is not: the indicator is repaired by phases 1
        and 4, which make signal 2 correct. What 2.2 uniquely does is give a **stopped, failed or
        binding-conflicted** run a signal-1 entry, which it has never had — a completed run already
        gets one from `runner_parsing.py:356` — plus a durable exit code for every one of them.
        Without 2.2 those runs' indicators still linger for one `useAgentTimeline` round trip after
        phases 1 and 4 land. Implement it for that, and do not expect it to change anything about a
        run that completed. Design D6.
      Also check `record_agent_output`'s own `await db.commit()` against what the call site has
      pending in its session at that point.
- [x] 2.3 Do the same at `:2723-2736` (app-server path).
- [x] 2.4 **Decide whether this row should be visible at all — the premise stated here in rounds 1
      and 2 was false.** It said a completed run gains no visible line "while a stopped or failed
      run does". It does not: both spawn paths hardcode `payload={"phase": "completed"}` regardless
      of outcome, deliberately (`agent_trigger.py:2125-2126`, "`phase` stays 'completed' even for a
      stopped/failed run — it means 'the run has ended', not 'it succeeded'"), and
      `AgentTimeline.tsx:430` returns `null` for any entry `isSuccessCompletionEntry` matches. So
      persisting the row adds **no visible line for any outcome**. That is acceptable — the visible
      outcome is the terminal label from the `runs` map, and this row's job is `lastRunSettled` plus
      a durable exit code. Confirm that is the intent rather than shipping a row nobody can see by
      accident, and do **not** "fix" it by making `phase` outcome-dependent without checking every
      other reader of `phase`. **Round RA adds the consequence 2.4 stopped short of:** an invisible
      row is not inert. It is still a block, and `firstAgentBlockId` can select it and take the
      turn's stat line down with it — see task 4.5a. "Nobody can see it" and "it changes nothing on
      screen" are different claims, and only the first is true.

## 3. The client consumes the envelope

- [x] 3.1 **DONE, and the count was 10 files, not 11 — plus a twelfth this task did not
      anticipate.** Landed alone as instructed; that commit is red on its own (69 failed / 69
      across the nine, every one of them `runStatusByRunId` iterating the envelope object where
      `AgentTimeline.tsx:84` expected an array) and green at the next. Three corrections for later
      phases: (a) **`agentTimelineModel.test.ts` needed nothing here** — it exercises model
      functions over plain arrays and never touches the hook, so its only stake in this change is
      task 5.1; the substantive file at 3.1 was `workingIndicator` alone. (b) **A twelfth file,
      `agentTimeline.test.tsx`, had to move**, because `runs` was made a **required** prop of
      `AgentTimeline` rather than an optional one defaulting to `{}` — an optional map reads as
      "no run ended" at every consumer, which is the exact failure this change deletes, so the
      compiler is made to ask. That is 45 render sites, mechanically. (c) **`workingIndicator`'s
      `runDurationsByRunId` describe block was KEPT**, against this task's wording: the function
      still ships until task 4.4 deletes it, and that block holds the negative-duration guard 4.4
      is required to carry across. Delete it there, with the function, not here.
      Move the 11 UI test fixtures to the envelope shape in one commit, before touching any
      component. Landing these first makes any later failure attributable to the change rather than
      to a fixture. **Round 3's supplementary pass measured the shape of this work, and it is not
      what rounds 1 and 2 assumed:**
      - **Nine of the eleven carry the identical one-liner** `useAgentTimeline: () => ({ data: [] })`
        — `agentHandoff`, `agentRunningComposer`, `batchedQuestionComposer`,
        `composerPermissionDefault`, `continueStartsWhatItNames`, `conversationControls`,
        `conversationDestination`, `handoffPlacement`, `specChatSurface`. One line each; a single
        find-and-replace to `({ data: { events: [], runs: {} } })`.
      - **They will keep passing if you forget them**, which is the real hazard. `AgentOutputPanel`
        destructures with `= []` (`:330`) and the new code reads `data?.events ?? []`, so a mock
        still returning a bare `[]` yields an empty event list and a green test on a shape the route
        no longer produces. That is this change's own new testing requirement, violated by its own
        fixtures. Update all nine even though nothing forces you to.
      - **The substantive two are `workingIndicator` and `agentTimelineModel`.**
        `workingIndicator.test.tsx` never mocks the hook: it renders `AgentTimeline` with
        `timelineEvents` as a prop (`:57-65`), imports `runDurationsByRunId` directly (`:7`) and has
        its own describe block for it (`:84`ff), so it needs the new `runs` prop and loses that
        block. Budget the effort there, not across eleven files.
- [x] 3.2 **DONE.** `AgentTimelineResponse` and `AgentRunFacts` added beside `AgentTimelineEvent`;
      the hook is typed and fetched as the envelope. **`RunLifecycleStatus` moved** from
      `lib/agentTimelineModel.ts` to `api/agents.ts`: the route now *states* a run's status (D5's
      one rename at the boundary), so it is a wire value rather than something the client reduces
      its way to, and `AgentRunFacts.status` can be typed without duplicating the union or making
      `api/` depend on `lib/` — the reverse of this codebase's existing direction. Two importers
      updated. **SSE predicate checked and unchanged:** the invalidation at `:416` and the query at
      `:421` name the identical key literal, and `getJson` for this route has exactly one call
      site.
      Update `useAgentTimeline` (`hub/ui/src/api/agents.ts:387-392`) and the
      `AgentTimelineEvent` types to the envelope, and check the SSE invalidation predicate at
      `:354-383` still names the right query key.
- [x] 3.3 **DONE**, with one shape note: the unwrap had to move *inside* the `useMemo` rather than
      sit above it, because `timeline?.events ?? []` as a dependency is a logical expression and
      `react-hooks/exhaustive-deps` is an error here (`--max-warnings 0`). The memo depends on
      `timeline` now.
      Update `AgentActivityTab.tsx` for the unwrap only — it maps events into activity items
      (`:24`, `:39`) and needs no run facts.
- [x] 3.3a **DONE.** New file `timelineEnvelopeUnwrap.test.tsx` is the guard the nine fixtures
      structurally cannot be — the only test in the suite that puts a **non-empty** envelope through
      the hook. Two assertions, both mutation-checked: `AgentActivityTab` lists an event out of
      `data.events` (fails when the unwrap is replaced with `[]`), and `AgentOutputPanel` hands
      `AgentTimeline` both `timelineEvents` and `runs` from the envelope (both fail when the panel
      passes empties). The second stubs `AgentTimeline` and reads the props, since at phase 3
      nothing reads `runs` and the carry is therefore not observable in the DOM.
      **`AgentOutputPanel` is not symmetric with it** (round 2's correction to the design's risk
      list). It holds the hook (`:330`) and its only other use of the value is passing it to
      `AgentTimeline` (`:1033`), where all three consumers live — and `AgentTimeline` takes
      `timelineEvents` as a prop (`AgentTimeline.tsx:31`) rather than calling the hook. So
      `AgentOutputPanel` must gain the `runs` map and thread it through as a new prop. It never
      reads the run facts; it is the only thing that can carry them.

## 4. The reducers are deleted

- [x] 4.1 **DONE.** New file `src/__tests__/timelineRunFacts.test.tsx` — every test in it passes
      `timelineEvents={[]}`, which *is* the reload. Red before 4.3 and green after, measured:
      **5 failed / 3 passed** on unmodified code, the 3 being the negative assertions, which were
      vacuously true then and are mutation-checked now.
- [x] 4.2 **DONE**, with one wording correction: a run whose `Run.status` is `running` reaches the
      client as **`started`** — the route renames it at the boundary (D5) — so the test asserts the
      wire value, which is the only one the component can ever see. Both negative assertions were
      strengthened from *"none of these three labels"* to `queryByText(/Turn /)`: an assertion that
      only rules out the labels it names passes against a fourth one leaking in, which is precisely
      what mutation M3/M4 below add.
- [x] 4.3 **DONE.** All three point at `runs`; `runStatusByRunId` deleted, and with it
      `agentTimelineModel.test.ts`'s `runStatusByRunId` describe block — **which is task 5.1's
      line range**. Deleting the reducer forces its only test to go in the same commit or the tree
      does not compile, so 5.1 keeps its obligation (a replacement guarantee that the route's
      ordering is what the client depends on) but has lost its deletion half, already done here.
- [ ] 4.4 **Its tests are still where task 3.1 said they would not be:** the
      `runDurationsByRunId` describe block in `workingIndicator.test.tsx` was deliberately kept at
      phase 3 so the function did not ship untested. Delete it here, and read its
      negative-duration case before you do — it is the guard this task must carry across.
      **DONE.** Read first, as instructed: its four cases were *a measured run*, *a failed run —
      duration is not a success signal*, *an unended run is absent rather than 0*, and *a backwards
      clock is absent rather than negative*. All four are carried into
      `timelineRunFacts.test.tsx`, now against the run row rather than the events. The display
      points at `runDurationSeconds(runs[runId])`, a module-local helper in `AgentTimeline.tsx`
      rather than a new export in `agentTimelineModel.ts` — 4.5 requires the assertion to live in
      the component test, and a second exported reducer would invite exactly the model-level test
      this phase exists to stop writing.
- [ ] 4.5 Assert duration rendering in the component test, not only in a model test, since the model
      function it used to live in is gone. **Re-baseline it rather than reconciling it** (design D4,
      round 3): `Run.started_at` is stamped at row construction (`agent_trigger.py:1073`) and the
      `run_started` event only once the pty exists (`:1857-1864`), so every duration now includes the
      spawn and reads longer than the event-derived figure. A run whose spawn failed (`:1798-1804`)
      also gains a duration it does not have today — confirm that renders acceptably rather than
      treating it as a regression.
      **DONE, and the spawn-failure half was measured rather than reasoned about.** A throwaway
      probe rendered a turn holding one operator message and one `phase="failed"` status row
      against a run row of `started_at` 00:00:00 / `ended_at` 00:00:01: it renders
      **"Worked for 1s"**, on the status row's own `ResultCard`. So a failed spawn is *not* an
      instance of F269 — `isSuccessCompletionEntry` is what returns `null` at `:430`, and a
      `failed` phase does not satisfy it. **F269 is narrower than task 4.5a's prose suggests**: it
      needs a status row whose phase is `completed`, i.e. a run that ended *successfully* having
      produced nothing else. 4.5a's fix is unchanged; its scope note is.
- [x] 4.5a **The stat line must not vanish with the row it hangs on** — found by round RA,
      2026-09-02, filed as **F269 (C)** in `scripts/drive/FINDINGS.md`, and it is where phase 2 and
      phase 4 meet. `firstAgentBlockId`
      (`AgentTimeline.tsx:384-389`) picks the first block that is a work block or carries an
      `agent_output` entry; a `status` entry is its own `entry` block, because `RESULT_OUTPUT_KINDS`
      holds `status` (`agentTimelineModel.ts:9`); `durationLine` is rendered **inside** that block's
      fragment (`:406-418`); and that fragment is `return null` for a success-completion entry
      (`:430`). So once task 2.2 persists the row, a turn whose only agent output is that row —
      a run stopped before it produced anything, or a spawn that failed (`agent_trigger.py:1798`) —
      renders no "Worked for Xs · N tokens" at all. Task 4.5 hands exactly those runs a duration for
      the first time, so the gap opens at the same moment the value appears. Write the component
      test first, from *A turn that produced nothing still reports what it cost*: a turn holding
      one operator message and one persisted terminal status row must present its stat line.
      Confirm it fails before the fix — round RA already did, with a throwaway vitest probe against
      today's unmodified code: a turn holding a text row and the status row renders
      `turn-worked-for` "Worked for 5s", and the same turn holding only the status row renders no
      `turn-worked-for` at all. The defect is latent today and task 2.2 is what makes it reachable.
      The fix is a placement change, not a change to what `:430` renders; do not make the row
      visible to solve this. **Round RB implemented both fixes RA offered and ran them, and they are
      not equivalent — one does not work.** Use this one: have the success-completion branch return
      `<Fragment key={entry.id}>{durationLine}</Fragment>` instead of `null`, so the stat line
      survives the card it hung on. Measured: 6 of 6 assertions pass, the status row itself stays
      unrendered, exactly one stat line is emitted when a text row precedes it, and the 86 existing
      assertions in `workingIndicator`, `agentTimeline`, `agentTimelineModel` and `agentHandoff`
      stay green. **Do not use the other one.** Excluding success-completion entries from
      `firstAgentBlockId` leaves it `undefined` in exactly the case F269 describes — the status row
      is the turn's *only* `agent_output` block, so there is no later block to inherit the slot —
      and `blockId === firstAgentBlockId` is then false for every block. Measured: 2 of 6 fail, both
      of them the ones this task exists to make pass.
      **DONE, iteration 6.** The named fix, and no other: the success-completion branch returns
      `<Fragment key={entry.id}>{durationLine}</Fragment>`. Three assertions in
      `timelineRunFacts.test.tsx`, written from the F269 shape iteration 5 measured — an
      `operator_input` row and a `phase: "completed"` status row, nothing between — and **red
      first**: 1 failed / 10 passed on the file before the fix, the failure being the stat line
      itself. All three are mutation-checked: drawing the `ResultCard` from that branch kills
      *still draws no card*, emitting the stat line without the `firstAgentBlockId` gate kills
      *exactly one stat line*, and `return null` kills the first. **RB's rejection re-measured
      against this test set and confirmed:** the `firstAgentBlockId` exclusion was implemented and
      run here too — 1 of 3 fails, and it is the one this task exists to make pass. Same verdict,
      independently reached.
- [x] 4.6 **DONE, and done here rather than in phase 4b, because the compiler forced it.** Its
      only two consumers were the two reducers 4.3 and 4.4 delete, so the moment they went
      `tsc --noEmit` failed with `TS6133: 'LIFECYCLE_EVENT_STATUS' is declared but its value is
      never read` — not a judgement call, a build break. Deleted, and with it
      `agentTimelineModel.ts`'s now-unused `RunLifecycleStatus` import, exactly as iteration 4
      predicted when it moved that type to `api/agents.ts`.
- [x] 4.6a **`AgentTimeline`'s `timelineEvents` prop now has no reader at all** — discovered at
      4.3, not predicted by any round. All three former readers were the reducers; the only other
      mentions in the file are comments. It is left in place for now, still required, with a
      comment on the prop saying so, because deleting it touches `AgentOutputPanel` and ~45 render
      sites across the UI suite and would have made this iteration's diff unattributable. Decide
      it here: either delete the prop and thread `runs` alone, or state why the component should
      keep receiving events it does not read. Note that `AgentActivityTab` genuinely does read the
      events, so the *route* keeps returning them either way — this is about one prop, not the
      envelope.
      **DECIDED, iteration 6: deleted.** The operator's standing preference is the cleanest design
      over the least work, and the case here is stronger than tidiness — a required prop with no
      reader is a standing invitation to add one, and *the* reader anyone would add is the one
      F190 was: run state reduced out of a list the route truncates. Keeping it keeps the loaded
      gun. Gone from `AgentTimeline`'s props and its `AgentTimelineEvent` import, from
      `AgentOutputPanel` (the `timeline?.events ?? []` local and the pass-through), and from every
      render site in the suite. `AgentActivityTab` is untouched and still lists the events, so the
      route's envelope is unchanged. The deletion is **asserted, not merely done**:
      `timelineEnvelopeUnwrap.test.tsx` now checks the panel hands the timeline `runs` and
      `not.toHaveProperty('timelineEvents')`, so re-threading it is a failing test rather than a
      silent regression.
- [x] 4.7 Verify the third consequence is repaired **in both states, not just on reload**
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
      - **Single-run, completed on a Claude runner: assert it does NOT change.** Round 3's supplementary pass said
        this case was broken too; phase 0 task 0.3 watched it work, and round RA re-derived why —
        the parser's `status_event("completed", …)` (`runner_parsing.py:356`) is persisted, so
        signal 1 already fires for a run that finished, and the indicator already releases on the
        answer's own snapshot rather than on the roster poll. Assert the behaviour phase 0 measured
        still holds after the change, including with the second `phase="completed"` row task 2.2
        adds. This is a regression guard, not a repair.
      - **Single-run, completed on a Codex runner: assert it DOES change** (round RB). The guard
        above is Claude-scoped and asserting it against a Codex fixture would assert the wrong
        thing. Codex has no completion sentinel of its own, so signal 1 has never fired for it and a
        cleanly completed Codex turn's indicator lingers for one `useAgentTimeline` round trip
        today — the 2026-08-18 tail complaint, fixed for Claude and still live here (F270). RB
        measured the UI half on unmodified code: with only `run_started` in `timelineEvents`, the
        indicator is absent when the Claude parser's status row is present among the entries and
        present when it is not. Assert that after task 2.2 the Codex case behaves like the Claude
        one.
      - **Single-run, stopped or failed: assert it DOES change.** This is the case signal 1 has
        never covered, because no `result` line is ever emitted, so no `phase="completed"` row is
        written. Today `lastRunSettled` stays false for the life of that conversation and the
        indicator lingers until the roster poll. After task 2.2 it must go out when the persisted
        status row lands. Bind this assertion to a stopped run specifically — a completed-run
        version of it passes today and proves nothing.
      **DONE, iteration 6 — six tests appended to `workingIndicator.test.tsx`.** This is a
      verification task, not a repair, so red-first does not apply and **mutation-checking is the
      proof they are not vacuous.** Three mutations, and every one of the six is killed by at
      least one: *`anotherRunIsUnderway` always true* kills LIVE, RELOADED and all three
      per-runner guards (7 of the file's 20 tests); *always false* kills STILL-UNDERWAY;
      *`lastRunSettled` loses signal 1* kills LIVE and all three guards. The live/reloaded split is
      real and the mutations show it: RELOADED survives the signal-1 mutation because it rests on
      the run row, LIVE does not. LIVE is rendered in the true live shape — the status row streamed
      in, the newest run's ROW still reading `started` because the refetch has not landed, the
      older run long since terminal. The CODEX and STOPPED guards each assert **both** halves of
      the change (without the persisted row the indicator is present; with it, absent), so each
      states what changed rather than only where it landed.

## 5. The testing rule is enforceable

- [x] 5.1 Replace `agentTimelineModel.test.ts:223-235` — the fixture that feeds ascending events to
      a route that returns descending — with whatever survives step 4, and assert the *shuffled
      input* scenario from *Payload-shaped model functions are tested against real route ordering*.
      **DONE — and the shape moved, which this line now records rather than forces.** The deletion
      half happened in iteration 5, because removing `runStatusByRunId` left the describe
      uncompilable. The replacement is three tests at the end of `timelineRunFacts.test.tsx`.
      **There is no model function left to feed events to**, so the guarantee could not be restated
      about one: what replaced the reducer is a keyed map the route builds by id lookup, read as
      `runs[turn.runId]`. The shuffled-input scenario therefore lands on *the component's read of
      `runs`* — render twice with the map's keys in opposite orders and the rendered text is
      identical. Two further tests assert each turn gets **its own** run's outcome in each order,
      because order-independence alone is satisfied by a read that is uniformly wrong. Both
      mutations — first-wins `Object.values(runs)[0]` and last-wins (the deleted reducer's own
      shape) — kill all three. No mutation was found that separates test 1 from tests 2-3, so they
      are redundant for *detection* and differ only in what they state; recorded rather than
      trimmed, since the requirement's scenario is the thing test 1 exists to satisfy.
- [x] 5.2 Add a test that fails if the timeline route's ordering is reversed, so the coupling between
      route order and client expectation is asserted somewhere rather than assumed.
      **DONE — two tests, and the coupling turned out not to be the presentational one.** MEASURED:
      the only surviving reader of `timeline.events` is `AgentActivityTab`, and it **re-sorts**
      ascending after merging the output lines (`AgentActivityTab.tsx:52`). Reversing the route's
      sort would reorder nothing on screen. What it changes is *which events come back at all* —
      the three per-source queries are merged and only then cut to 50, so descending is what makes
      those 50 the newest 50, and because `runs` is looked up from the ids the returned events name,
      the newest runs' outcomes drop out of the facts map with them. That is F190 again by a
      different route, and it is why the second test asserts the map and not only the list.
      `test_the_route_returns_its_events_newest_first` states the contract; forty events plus twenty
      older heartbeats make `test_the_truncation_keeps_the_newest_events_and_the_runs_they_name`
      sensitive to it. **Mutation-checked, not assumed**: `reverse=True` → `reverse=False` at
      `agents.py:802` fails both, twice, reproducibly. Task 1.4b also dies under that mutation —
      incidentally, since it neither names nor asserts an ordering, and would pass against a route
      that returned every event unordered.
- [x] 5.3 Record the rule where a reviewer will meet it, and note in `spec-queue/DECISIONS.md` (D-4)
      that the rule is now stated and only its sweep remains open.
      **DONE, with a pointer correction.** The rule is a line in `CLAUDE.md`'s Critical Rules —
      the place this repo puts standing rules and the one a reviewer meets without going looking —
      naming the requirement rather than a path, so archiving the change does not stale it. It
      states in its own text that only the instance it was learned from is checked.
      **`D-4` no longer exists**: the 2026-09-01 evening re-triage dissolved it into `R-1`, and its
      F190 sweep row is now the measured table inside R-1. The note was written there instead, and
      it is deliberately an entry on the *cost* side of R-1's open question — a spec requirement, a
      `CLAUDE.md` line and two mutation-checked test sites is what one convention cost, with no
      sweep and no automated check, so R-1 is not answered by it.

## 6. Verified by the implementer against a running Hub

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
- [ ] 6.7 Do **not** mark F190 retired here. Phase 7 closes it — the operator's approval condition
      is that a round which did not build the change verifies it.

## 7. Verified by a round that did not build it

**Operator condition of approval, 2026-09-01: after implementation, a new round tests it.** Phase 6
is the implementer checking its own work, which is necessary and is not this. This phase is a fresh
sitting that did not write the code.

- [ ] 7.1 Re-run the phase 0 observations against the implemented change and confirm each one moved
      the way it was supposed to — the stopped turn names its stop, the multi-run indicator releases
      on the newest run's terminal signal rather than on the roster poll, a **stopped** single-run
      conversation now releases on its persisted status row, and all of them survive a reload.
      Phase 0's record is the baseline; this is the comparison. **One of them must be unchanged:**
      a *completed* single-run conversation already released cleanly at 0.3, so if that case now
      behaves differently, something regressed. Round RA, 2026-09-02. **That baseline was taken on a
      Claude runner and only binds there** (round RB): the same case on a Codex runner has no
      signal-1 row today, so it is expected to *change*. Phase 0 has no Codex baseline, so do not
      read one into it — say so rather than inferring.
- [ ] 7.1a Confirm *A turn that produced nothing still reports what it cost* holds against the built
      code, by stopping a run before it emits anything and reading the turn: it must carry both the
      terminal label and the "Worked for Xs" line. Task 4.5a exists because persisting the status
      row can take that line with it, and this is the check that the placement fix actually fired
      rather than the test being written around it.
- [ ] 7.2 Read the implemented route against *The run facts cover every run the events name*
      specifically: confirm the run lookup is keyed by the ids the returned events carry, carries
      the `project_id` predicate, and has no `ORDER BY` or `LIMIT` that could reintroduce the
      coverage gap. This requirement was breached by two consecutive rounds' own design; it is the
      one most likely to be breached again by the implementation.
- [ ] 7.3 Confirm `test_bola.py`'s cross-project coverage for this route still exists and asserts
      both halves of the envelope — that it was moved out of the `isinstance(data, list)` loop
      rather than deleted from it.
- [ ] 7.4 Re-read the four artifacts against the built code and correct whatever the implementation
      taught. Only then mark F190 retired.
