# Tasks — A refused request says so

Round discipline: this file is written in round 1. **Rounds 2 and 3 revise it**, and implementation
starts only after round 3. Nothing here is closed by a plan existing.

## 1. Review rounds

- [ ] 1.1 **Round 2** — compare the proposal and design against the code independently. Do not
      re-read round 1's reasoning; re-derive from `turn_scheduler.py`, `agent_trigger.py:1195-1302`,
      and `scheduler.py:2440-2590`. Fix the proposal.
- [ ] 1.2 **Round 2** — enumerate every hub test that asserts `200` for a condition this change
      makes a refusal (D9: 35 `waiting_reason` references across 13 files; start with
      `test_archived_send_refusal.py`, `test_a_decided_task_takes_no_new_work.py`,
      `test_project_workspace_unavailable.py`). Write the list into this file as explicit tasks. A
      behaviour change discovered as a test failure is a behaviour change nobody decided.
- [ ] 1.3 **Round 2** — verify D2's central claim by reading, not by recall: that no early return in
      `schedule_agent` can produce a `refusal`, and that `"queue is empty"` is genuinely reachable
      after this route's own commit.
- [ ] 1.4 **Round 3** — independent second comparison against the code, including whatever round 2
      changed. Check specifically that the new requirements do not contradict *Repeated delivery
      failure does not wedge an agent* (`agent-conversation-workspace`, line 1213), which requires
      returned input to be retried to a limit — D5 withdraws an entry before that limit.
- [ ] 1.5 **Round 3** — confirm the delta's four requirements are each falsifiable by a test that
      does not restate the implementation.

## 2. The refusal is carried out of the scheduler

- [ ] 2.1 Add the refusal carrier to `ScheduleResult` — the refused condition's status, its
      sentence, and the ids of the entries the refused turn would have carried.
- [ ] 2.2 Populate it in `schedule_agent`'s `except TriggerAgentError` branch, only when the error
      is non-transient. No early return may set it.
- [ ] 2.3 Test: every early return leaves the carrier absent, including `"queue is empty"` with its
      defaulted `terminal_failure=True`.
- [ ] 2.4 Test: a non-transient `TriggerAgentError` populates it with the error's own status and
      the ids of exactly the selected entries.
- [ ] 2.5 Test: a transient refusal (D8 checkout collision) leaves it absent.
- [ ] 2.6 Confirm `scheduler.py`'s two flow consumers are unchanged in behaviour — a test that
      fires a job into a non-transient refusal still marks the job run `failed` with its reason.

## 3. The route answers with the refusal

- [ ] 3.1 Refuse with the carried status and sentence when the carrier is present **and** names this
      request's own entry.
- [ ] 3.2 Every other outcome keeps today's `200 … "queued"`.
- [ ] 3.3 A refusal naming other entries yields the queued-behind-other-input answer, not the
      foreign sentence (D6).
- [ ] 3.4 Test: the F108 reproduction — a review dispatch refused by a condition F76's pre-queue
      guards do not cover — answers with a non-2xx carrying the refusal's sentence.
- [ ] 3.5 Test: an archived agent, a task that does not exist, and an unimplemented runner each
      answer with their own status.
- [ ] 3.6 Test: a refusal raised while building a turn for another conversation answers `200`, does
      not carry the foreign sentence, and says the input is waiting behind other input.
- [ ] 3.7 Test: a concurrent drain that empties the queue answers `200 … "queued"` (D2's race).
- [ ] 3.8 Update the tests enumerated in 1.2, each as its own deliberate change.

## 4. The queue agrees with the answer

- [ ] 4.1 Withdraw the request's own entry when answering with a refusal, recording the refusal as
      the reason.
- [ ] 4.2 Tolerate an entry `schedule_agent` already withdrew at the attempt limit (D5).
- [ ] 4.3 Test: after a refused request, the entry is not queued and its recorded reason names the
      refusal.
- [ ] 4.4 Test: no `queue_entry_abandoned` event arrives later for an entry this path withdrew.

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
      live request did. Reproduce F108's exact call and read what the operator gets.
- [ ] 6.6 Sync the delta into `openspec/specs/agent-conversation-workspace/spec.md` by hand, then
      archive with `--skip-specs` and fix the doubled date prefix.
- [ ] 6.7 Update `scripts/drive/FINDINGS.md`: F108 closed as a class; file the two items from the
      design's *Filed, not fixed here*.
