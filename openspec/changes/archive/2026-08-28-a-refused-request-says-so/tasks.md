# Tasks — A refused request says so

Round discipline: this file is written in round 1. **Rounds 2 and 3 revise it**, and implementation
starts only after round 3. Nothing here is closed by a plan existing.

## 1. Review rounds

- [x] 1.1 **Round 2** — compare the proposal and design against the code independently. Do not
      re-read round 1's reasoning; re-derive from `turn_scheduler.py`, `agent_trigger.py:1195-1302`,
      and `scheduler.py:2440-2590`. Fix the proposal.
      **Found three things**, all written into the proposal and design:
      (a) three of F108's four named examples are already refused *pre-queue* by the route
      (`:1108` archived, `:1173`/`:1199` task missing, `:1134` invalid `work_dir`) and the fourth
      (unimplemented runner) is unreachable through the API — so round 1's mechanism would have
      shipped with none of its named cases able to fire;
      (b) the gate `not transient` is too wide and would reverse F96 (D10);
      (c) round 1's D2 evidence (`"queue is empty"` reachable) is a narrow race, and the design does
      not need it (D2, revised).
- [x] 1.2 **Round 2** — enumerate every hub test that asserts `200` for a condition this change
      makes a refusal. Round 2 answered **"none, by construction"** — D10 makes the classification
      an explicit flag defaulting to `False`, so an *unmarked* raise site keeps today's behaviour.
      **That answer was wrong, and the full suite found it.** The reasoning covered the unmarked
      population and never asked the other half of its own question: which existing tests reach a
      site this change *does* mark. Exactly one does:
  - [x] 1.2f `test_a_decided_task_takes_no_new_work.py::test_triggering_a_run_on_a_task_under_review_is_not_refused`
        asserted `200` while never registering `builder`, so it met `:452` and turned red. The test
        was green for a reason unrelated to what it claims: the route answered `200` to *every*
        refusal, so its assertion could not tell the task-band guard it names from a typo'd agent
        name. Fixed by registering the agent, which makes the `200` mean what the docstring says.
        **Recorded rather than quietly edited** — a test that changes without anyone deciding it is
        the thing group 3.8 exists to prevent, and this one did change.
      The three tests that prove the *unmarked* population must not move, all still passing
      untouched:
  - [x] 1.2a `test_agent_trigger.py::test_unbound_agent_accumulates_queue_with_visible_reason`
        must still pass unchanged — `200 … "runner … bound"`.
  - [x] 1.2b `test_runner_binding_redrain.py` must still pass unchanged — F96's bind-then-deliver.
  - [x] 1.2c `test_runtime_diagnostics.py::test_agent_trigger_reports_missing_cli_directly` must
        still pass unchanged — `200 … "not found in PATH"`.
  - [x] 1.2d `test_agent_trigger.py::test_writing_agent_is_not_spawned_when_a_real_repository_cannot_be_prepared`
        must still pass unchanged — `200 … "wrong ref"` (worktree preparation is environment-level).
  - [x] 1.2e `test_project_workspace_unavailable.py` must still pass unchanged — the workspace
        refusal is `workspace_unavailable`, hence transient, hence never request-level.
- [x] 1.3 **Round 2** — verify D2's central claim by reading, not by recall.
      **Both halves checked.** No early return can produce a `refusal`: the carrier is written in
      one place, the `except TriggerAgentError` branch. `"queue is empty"` after this route's own
      commit is reachable *only* as a race — `schedule_agent` serialises on `_lock_for` (`:59`), so
      a concurrent re-drain must complete first, and its `Run` must also have left `running` or the
      route's call returns `"agent is already running"` at `:65`. D2 rewritten to rest on
      construction instead.
- [x] 1.4 **Round 3** — independent second comparison against the code, including whatever round 2
      changed. **No contradiction with *Repeated delivery failure does not wedge an agent*** — that
      requirement governs input a run *returned*, and its attempt limit is a ceiling ("stop retrying
      it before it can block an agent indefinitely"), not a floor. The one clause that reads as a
      floor is scoped to returned input, and this input was never delivered to return. **One real
      gap found and closed in the delta:** that requirement also says given-up input must name the
      run that carried it, and nothing carried this input — recorded rather than left to be
      reconciled by a reader (D14).
- [x] 1.5 **Round 3** — confirm the delta's requirements are each falsifiable by a test that does
      not restate the implementation. They are: each names an observable the caller or the operator
      can read — the answer's status and sentence, whether the queue still holds the input, which
      event arrives, what the UI displays — and none names `ScheduleResult`, `TriggerAgentError` or
      a flag. Two scenarios were added because round 3's own findings introduced new observables.
- [x] 1.6 **Round 3** — audit round 2's marking list. **Three corrections, all in D13:**
      `:474` (archived agent) is unreachable through the queue — `agent_lifecycle.archivable`
      refuses to archive an agent holding queued entries — so it is marked but **must not get a
      test claiming to exercise it**; `:499`/`:874` are likewise unreachable through the API;
      and `:452` is confirmed request-level but **does** reverse F96-shaped behaviour, deliberately,
      because input addressed to a name that is on no roster has no addressee. `:817` reviewed and
      left unmarked: an `OSError` writing the context file is the environment, not the request.

## 2. The refusal is carried out of the scheduler

- [x] 2.0 **New in round 2 (D10).** Add the request-level classification to `TriggerAgentError`,
      defaulting to `False`, documented the way `transient` is — the question it answers, and why
      it is not the negation of `transient`. Mark exactly these sites in `agent_trigger.py`:
  - [x] 2.0a `:337` a turn batching more than one review target
  - [x] 2.0b `:351` a turn batching a review together with work
  - [x] 2.0c `:432` invalid agent name
  - [x] 2.0d `:452` the agent is not in this project
  - [x] 2.0e `:474` the agent is archived
  - [x] 2.0f `:499` the runner has no execution adapter
  - [x] 2.0g `:591` `work_dir` combined with a review turn
  - [x] 2.0h `:613` the review target cannot be bound to this project
  - [x] 2.0i `:626` the review target is not in a status a review starts from
  - [x] 2.0j `:643` the review target is already under review by someone else
  - [x] 2.0k `:657` the reviewer is the task's own author
  - [x] 2.0l `:670` there is nothing to review
  - [x] 2.0m `:673` `work_dir` overriding isolation for a writing agent
  - [x] 2.0n `:684` invalid `work_dir`
  - [x] 2.0o `:874` unsupported runner at command build time
      **Left unmarked, deliberately:** `:441` (conversation unavailable — the scheduler's own
      `:85` early return covers the queue path and no `refusal` should exist for it), `:461`,
      `:480`, `:507`, `:535`, `:737`, `:756`, `:817`, `:912`, `:517`.
- [x] 2.1 Add the refusal carrier to `ScheduleResult` — the refused condition's status, its
      sentence, and the ids of the entries the refused turn would have carried.
- [x] 2.2 Populate it in `schedule_agent`'s `except TriggerAgentError` branch, only when the error
      is request-level. No early return may set it.
- [x] 2.3 Test: every early return leaves the carrier absent, including `"queue is empty"` with its
      defaulted `terminal_failure=True`.
- [x] 2.4 Test: a request-level `TriggerAgentError` populates it with the error's own status and
      the ids of exactly the selected entries.
- [x] 2.5 Test: a transient refusal (D8 checkout collision) leaves it absent, **and** an
      environment-level non-transient refusal (no runner bound) leaves it absent too.
- [x] 2.6 Confirm `scheduler.py`'s two flow consumers are unchanged in behaviour — a test that
      fires a job into a non-transient refusal still marks the job run `failed` with its reason,
      for an environment-level refusal as well as a request-level one.
      `test_scheduler.py::test_job_that_cannot_start_records_the_queue_reason_as_failed` already
      covered the environment-level half and passes untouched;
      `test_a_request_level_refusal_still_fails_the_job_run` adds the half this change creates.
      The consumers read `terminal_failure`, which this change never touched — the refusal rides
      alongside in a field only the route reads.

## 3. The route answers with the refusal

- [x] 3.1 Refuse with the carried status and sentence when the carrier is present **and** names this
      request's own entry.
- [x] 3.2 Every other outcome keeps today's `200 … "queued"`.
- [x] 3.3 A refusal naming other entries yields the queued-behind-other-input answer, not the
      foreign sentence (D6).
- [x] 3.4 Test: the F108 reproduction, chosen from what round 2 showed is *actually* reachable —
      a review dispatch that passed the route's pre-queue guards and meets `:643` at dispatch
      because another reviewer took the task while the entry waited (the TOCTOU population).
      It answers with a non-2xx carrying the refusal's sentence.
- [x] 3.5 Test: a mistyped agent name (`:452`) answers with its own status, since the route has no
      pre-queue mirror for it. **Round 3:** this is the one marked site with a reachable,
      route-driven test. `:474`, `:499` and `:874` are marked but unreachable (D13) — do not write
      tests that construct states the product forbids in order to reach them.
- [x] 3.6 Test: a refusal raised while building a turn for another conversation answers `200`, does
      not carry the foreign sentence, and says the input is waiting behind other input.
- [x] 3.7 Test: a concurrent drain that empties the queue answers `200 … "queued"` (D2's race).
- [x] 3.8 No existing test is edited by this group. If one turns red, stop: it means a site was
      marked in 2.0 that should not have been, or the gate is not the one D10 specifies.
      **One turned red, and stopping was right.** It was
      not a wrongly-marked site — `:452` was re-derived in round 3 (D13) and confirmed — it was a
      test whose `200` never meant what it claimed. See 1.2f. The edit is deliberate and recorded;
      no other existing test moved across 3,499.

## 4. The queue agrees with the answer

- [x] 4.1 Withdraw the request's own entry when answering with a refusal, recording the refusal as
      the reason.
- [x] 4.2 Tolerate an entry `schedule_agent` already withdrew at the attempt limit (D5) — **and
      read it correctly**: `expire_on_commit=False` plus a separate scheduler session means the
      route's `entry` is stale, so refresh the row before deciding (D11).
- [x] 4.3 Test: after a refused request, the entry is not queued and its recorded reason names the
      refusal.
- [x] 4.4 Test: no `queue_entry_abandoned` event arrives later for an entry this path withdrew.
- [x] 4.4a **New in round 3 (D12).** Broadcast and persist `queue_entry_withdrawn` for the entry
      this path withdraws — the same kind and payload shape `api/v1/inbound_queue.py:271-272`
      already emits, which `useSSE.ts:491` already handles. Without it the operator holds an error
      and a queue card still counting the input, because `queue_entry_queued` was already broadcast
      at `:1268` before the refusal was known.
- [x] 4.4b Test: the refused request emits `queue_entry_withdrawn` and does **not** emit
      `queue_entry_abandoned`.
- [x] 4.5 Test (D11): with `schedule_agent` withdrawing through its own session, the route still
      sees the withdrawal. Mutation-check it by removing the refresh — the test must fail.
- [x] 4.6 Test: an environment-level refusal leaves the entry queued, so F96's repair still
      delivers it.

## 5. The operator reads the reason

- [x] 5.1 `AgentOutputPanel.tsx` — render the server's sentence instead of
      `Trigger failed with status <n>`.
- [x] 5.2 `NewConversationSurface.tsx` — render the server's sentence instead of
      `Could not start the conversation`.
- [x] 5.3 UI tests for both, asserting the sentence reaches the operator.
- [x] 5.4 Confirm `api/tasks.ts`'s path already surfaces `ApiError`'s detail where
      `useStartWorkOnTask` is rendered; fix it if it does not.
- [x] 5.5 Rebuild the bundle: `py -3.11 scripts/refresh_ui_bundle.py`, commit source and bundle
      together.

## 6. Verification

- [x] 6.1 Mutation-check every new test: break the thing it names, confirm that test fails.
- [x] 6.2 Full hub suite **with `claude` stripped from PATH** — the sweep that caught two cells this
      branch would have failed CI on. **3,499 passed, 84 skipped, 1 xpassed, 1 failed** — the one
      failure being 1.2f, now fixed. Re-run after the fix.
- [x] 6.3 CLI suite (440 passed, 3 skipped), UI suite (1,446 passed, 139 files), `ruff` clean,
      `black` clean over 517 files, `mypy src/` clean, `npm run lint` clean, `tsc --noEmit` clean.
- [x] 6.4 `npx openspec validate --specs --strict`.
- [x] 6.5 **Drive it live** against the trial Hub. Reproduced `:452` — a mistyped agent name — on
      the trial Hub at 8010: `POST /agent/trigger` answered **409** with the refusal's own sentence
      where it used to answer `200 {"success": true, "status": "queued"}`, and
      `GET /queue/<agent>/status` reported `waiting_count: 0`, so the answer and the queue agree.
      The population that must not move was driven in the same pass: an agent with no runner bound
      still answers `200 … queued` and its entry stays at `waiting_count: 1`, so F96's repair still
      has something to deliver.
- [x] 6.6 Sync the delta into `openspec/specs/agent-conversation-workspace/spec.md` by hand, then
      archive with `--skip-specs` and fix the doubled date prefix. Synced: 4 requirements, 9
      scenarios, taking the capability to 61 requirements;
      `npx openspec validate --specs --strict` passes 42/42. Archived, and the doubled prefix
      renamed as the dead-end note predicted.
- [x] 6.7 Update `scripts/drive/FINDINGS.md`: F108 closed as a class, **and corrected** — its own
      four examples were already answered, recorded in the finding itself where the next reader
      meets it rather than only in this change's design. The design's two filed items are placed:
      the delivery-attempt one became **F114 (severity A)** with a live measurement, and
      `terminal_failure`'s dishonest defaults are named in F108's closing paragraph as filed and
      unfixed. Four further findings came out of the same drive — F109, F110, F111, F112, F113.
