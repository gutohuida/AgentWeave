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
      makes a refusal. **Answered, and the answer is "none, by construction."** D10 makes the
      classification an explicit flag on `TriggerAgentError` defaulting to `False`, so a raise site
      keeps today's behaviour until this change marks it. The enumeration therefore becomes the
      list of sites to mark (group 2) plus the three tests that prove the *unmarked* population
      must not move:
  - [ ] 1.2a `test_agent_trigger.py::test_unbound_agent_accumulates_queue_with_visible_reason`
        must still pass unchanged — `200 … "runner … bound"`.
  - [ ] 1.2b `test_runner_binding_redrain.py` must still pass unchanged — F96's bind-then-deliver.
  - [ ] 1.2c `test_runtime_diagnostics.py::test_agent_trigger_reports_missing_cli_directly` must
        still pass unchanged — `200 … "not found in PATH"`.
  - [ ] 1.2d `test_agent_trigger.py::test_writing_agent_is_not_spawned_when_a_real_repository_cannot_be_prepared`
        must still pass unchanged — `200 … "wrong ref"` (worktree preparation is environment-level).
  - [ ] 1.2e `test_project_workspace_unavailable.py` must still pass unchanged — the workspace
        refusal is `workspace_unavailable`, hence transient, hence never request-level.
- [x] 1.3 **Round 2** — verify D2's central claim by reading, not by recall.
      **Both halves checked.** No early return can produce a `refusal`: the carrier is written in
      one place, the `except TriggerAgentError` branch. `"queue is empty"` after this route's own
      commit is reachable *only* as a race — `schedule_agent` serialises on `_lock_for` (`:59`), so
      a concurrent re-drain must complete first, and its `Run` must also have left `running` or the
      route's call returns `"agent is already running"` at `:65`. D2 rewritten to rest on
      construction instead.
- [ ] 1.4 **Round 3** — independent second comparison against the code, including whatever round 2
      changed. Check specifically that the new requirements do not contradict *Repeated delivery
      failure does not wedge an agent* (`agent-conversation-workspace`, line 1213), which requires
      returned input to be retried to a limit — D5 withdraws an entry before that limit.
- [ ] 1.5 **Round 3** — confirm the delta's four requirements are each falsifiable by a test that
      does not restate the implementation.
- [ ] 1.6 **Round 3** — audit round 2's own new claim, the one nothing has yet re-derived: that
      each site marked in 2.0 is genuinely request-level and each site left unmarked is genuinely
      environment-level. `:452` ("is not an agent in this project") is the one round 2 flagged as
      arguable; `:817` (canonical context could not be written) is the one it left unmarked with
      the least evidence.

## 2. The refusal is carried out of the scheduler

- [ ] 2.0 **New in round 2 (D10).** Add the request-level classification to `TriggerAgentError`,
      defaulting to `False`, documented the way `transient` is — the question it answers, and why
      it is not the negation of `transient`. Mark exactly these sites in `agent_trigger.py`:
  - [ ] 2.0a `:337` a turn batching more than one review target
  - [ ] 2.0b `:351` a turn batching a review together with work
  - [ ] 2.0c `:432` invalid agent name
  - [ ] 2.0d `:452` the agent is not in this project
  - [ ] 2.0e `:474` the agent is archived
  - [ ] 2.0f `:499` the runner has no execution adapter
  - [ ] 2.0g `:591` `work_dir` combined with a review turn
  - [ ] 2.0h `:613` the review target cannot be bound to this project
  - [ ] 2.0i `:626` the review target is not in a status a review starts from
  - [ ] 2.0j `:643` the review target is already under review by someone else
  - [ ] 2.0k `:657` the reviewer is the task's own author
  - [ ] 2.0l `:670` there is nothing to review
  - [ ] 2.0m `:673` `work_dir` overriding isolation for a writing agent
  - [ ] 2.0n `:684` invalid `work_dir`
  - [ ] 2.0o `:874` unsupported runner at command build time
      **Left unmarked, deliberately:** `:441` (conversation unavailable — the scheduler's own
      `:85` early return covers the queue path and no `refusal` should exist for it), `:461`,
      `:480`, `:507`, `:535`, `:737`, `:756`, `:817`, `:912`, `:517`.
- [ ] 2.1 Add the refusal carrier to `ScheduleResult` — the refused condition's status, its
      sentence, and the ids of the entries the refused turn would have carried.
- [ ] 2.2 Populate it in `schedule_agent`'s `except TriggerAgentError` branch, only when the error
      is request-level. No early return may set it.
- [ ] 2.3 Test: every early return leaves the carrier absent, including `"queue is empty"` with its
      defaulted `terminal_failure=True`.
- [ ] 2.4 Test: a request-level `TriggerAgentError` populates it with the error's own status and
      the ids of exactly the selected entries.
- [ ] 2.5 Test: a transient refusal (D8 checkout collision) leaves it absent, **and** an
      environment-level non-transient refusal (no runner bound) leaves it absent too.
- [ ] 2.6 Confirm `scheduler.py`'s two flow consumers are unchanged in behaviour — a test that
      fires a job into a non-transient refusal still marks the job run `failed` with its reason,
      for an environment-level refusal as well as a request-level one.

## 3. The route answers with the refusal

- [ ] 3.1 Refuse with the carried status and sentence when the carrier is present **and** names this
      request's own entry.
- [ ] 3.2 Every other outcome keeps today's `200 … "queued"`.
- [ ] 3.3 A refusal naming other entries yields the queued-behind-other-input answer, not the
      foreign sentence (D6).
- [ ] 3.4 Test: the F108 reproduction, chosen from what round 2 showed is *actually* reachable —
      a review dispatch that passed the route's pre-queue guards and meets `:643` at dispatch
      because another reviewer took the task while the entry waited (the TOCTOU population).
      It answers with a non-2xx carrying the refusal's sentence.
- [ ] 3.5 Test: a mistyped agent name (`:452`) answers with its own status, since the route has no
      pre-queue mirror for it.
- [ ] 3.6 Test: a refusal raised while building a turn for another conversation answers `200`, does
      not carry the foreign sentence, and says the input is waiting behind other input.
- [ ] 3.7 Test: a concurrent drain that empties the queue answers `200 … "queued"` (D2's race).
- [ ] 3.8 No existing test is edited by this group. If one turns red, stop: it means a site was
      marked in 2.0 that should not have been, or the gate is not the one D10 specifies.

## 4. The queue agrees with the answer

- [ ] 4.1 Withdraw the request's own entry when answering with a refusal, recording the refusal as
      the reason.
- [ ] 4.2 Tolerate an entry `schedule_agent` already withdrew at the attempt limit (D5) — **and
      read it correctly**: `expire_on_commit=False` plus a separate scheduler session means the
      route's `entry` is stale, so refresh the row before deciding (D11).
- [ ] 4.3 Test: after a refused request, the entry is not queued and its recorded reason names the
      refusal.
- [ ] 4.4 Test: no `queue_entry_abandoned` event arrives later for an entry this path withdrew.
- [ ] 4.5 Test (D11): with `schedule_agent` withdrawing through its own session, the route still
      sees the withdrawal. Mutation-check it by removing the refresh — the test must fail.
- [ ] 4.6 Test: an environment-level refusal leaves the entry queued, so F96's repair still
      delivers it.

## 5. The operator reads the reason

- [ ] 5.1 `AgentOutputPanel.tsx` — render the server's sentence instead of
      `Trigger failed with status <n>`.
- [ ] 5.2 `NewConversationSurface.tsx` — render the server's sentence instead of
      `Could not start the conversation`.
- [ ] 5.3 UI tests for both, asserting the sentence reaches the operator.
- [ ] 5.4 Confirm `api/tasks.ts`'s path already surfaces `ApiError`'s detail where
      `useStartWorkOnTask` is rendered; fix it if it does not.
- [ ] 5.5 Rebuild the bundle: `py -3.11 scripts/refresh_ui_bundle.py`, commit source and bundle
      together.

## 6. Verification

- [ ] 6.1 Mutation-check every new test: break the thing it names, confirm that test fails.
- [ ] 6.2 Full hub suite **with `claude` stripped from PATH** — the sweep that caught two cells this
      branch would have failed CI on.
- [ ] 6.3 CLI suite, UI suite, `ruff` / `black` / `mypy` / `npm run lint` / `tsc --noEmit`.
- [ ] 6.4 `npx openspec validate --specs --strict`.
- [ ] 6.5 **Drive it live** against the trial Hub. Three review rounds did not find F108; the first
      live request did. Reproduce a reachable case and read what the operator gets.
- [ ] 6.6 Sync the delta into `openspec/specs/agent-conversation-workspace/spec.md` by hand, then
      archive with `--skip-specs` and fix the doubled date prefix.
- [ ] 6.7 Update `scripts/drive/FINDINGS.md`: F108 closed as a class, **and corrected** — its own
      four examples were already answered, which is worth recording where the next reader of the
      finding will meet it. File the two items from the design's *Filed, not fixed here*.
