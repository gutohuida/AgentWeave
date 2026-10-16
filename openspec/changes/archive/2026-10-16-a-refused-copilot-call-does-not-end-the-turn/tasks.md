# Tasks — A refused Copilot call does not end the turn

## 0. Rounds and decision

- [x] 0.1 **R2**: re-derive the argument independently from the code. Do not re-read R1's reasoning
  first. *Done 2026-10-12 on the work PC; see design.md's round log.* Files:
  - `hub/hub/copilot_acp.py`: `track_call` `:369`, `answer_permission` `:2376-2425`,
    `on_notification` `:2310`, `_await_prompt` `:2742-2837`, `send_cancel` `:2226`, `run_turn`'s
    `finally` `:2739`.
  - `hub/hub/copilot_usage.py`: `:184-380`.
  - `hub/hub/api/v1/agent_trigger.py`: `:4100-4265`, `_on_refusal` `:3965`.
  - `hub/hub/run_divergence.py`: `evaluate_run_end` `:732`.

  Questions to break:
  - Is there **any** path after a `reject_once` that sends `session/cancel`, closes stdin or kills
    the process, including through `fail_turn`, `forced_failure` or a raised `on_refusal`?
  - Can a subagent's refusal be the last parent-visible event before `end_turn`? If so, would D2
    misclassify it? Check a real subagent capture, not only R1's description.
  - Does Copilot stream a subagent's text as `agent_message_chunk` on the parent session? If so,
    D2's clearing rule needs the envelope `agentId` on the chunk.
  - Under D3, what does each pinned test in 1.12 see? Is any of them a test whose *purpose* is that
    the turn ends?

  R2's answers:
  - **No path after a reject cancels, closes or kills.** `send_cancel` (`:2226`) is reached from
    Stop, the `_await_prompt` timeout and `fail_turn`. `fail_turn` is used only for autopilot
    escalation and `exit_plan_mode.requested`. `answer_permission` calls `on_decision` and then
    `on_refusal`, both suppressed. `close_forced` is set only after the prompt returns.
  - **A subagent's refusal is not the last parent-visible event** in `c5e3a780`. After it came
    `subagent.completed` and the root `task` call's completion, and the parent went on. D2 would not
    record it, given 2.B.1's subagent flag. Without that flag (`track_call` sees `data` only), a raw
    start lacking `parentToolCallId` would be misread as a root call. That is why 2.B.1 must pass
    `params`.
  - **Subagent text as `agent_message_chunk`**: not established from a capture. The mapper applies
    no subagent test to chunks. It is moot for correctness, because a chunk only *clears* the
    record. A subagent chunk clearing a root record is a missed continuation (the safe direction).
    And a subagent cannot run after a root refusal that ended the prompt.
  - **No pinned test's purpose is that the turn ends.** Each tests the answer, the card or the
    diagnostic. But see 1.12: R1 missed one test and the effect of D1 and D7 on all of them.
- [x] 0.2 **R3**: a fresh, independent comparison of the proposal against the code. Focus on what
  each changed call **returns when what it calls raises** (design D7). Also check that
  `_runtime_turn_fields` cannot change a Codex run's payload. Questions to break:
  - Does `mapper.finish()` run exactly once on every path, including a continuation that raises?
  - Can a continuation be sent after `cancel_sent`?
  - Is `_runtime_turn_fields` reached on the `run_stopped` path?

  *Done 2026-10-12 on the work PC, at `6208e9a5`; see design.md's round log.* R3's answers:
  - **`mapper.finish()`**: once on every path that **returns** an outcome, provided D3's "one tail"
    holds, a continuation that raises included. It runs **zero** times on `CancelledError` (Hub
    shutdown cancels the run's task, `main.py:487-489`), exactly as today. That path was not
    covered. D7 now says `CancelledError` is never absorbed; test 1.15.
  - **After `cancel_sent`**: no. D2's gate excludes `cancel_sent`. `check_interrupt()` at the gate
    turns a late Stop into `interrupted` + `session/cancel` before anything is sent. Note the
    behaviour change: a Stop between the last poll and the result is `completed` today and
    `interrupted` under D3 (test 1.14).
  - **`run_stopped`**: yes. One `_broadcast_run_lifecycle` call (`agent_trigger.py:4229`) serves
    all three terminal events. Codex's `TurnOutcome` has `thread_id`, `status`, `error`,
    `exit_code` and `stderr_tail`, none of the three names, so `getattr` leaves its payload
    unchanged.
  - **What each changed call returns when what it calls raises**: D7 had a contradiction. D3's
    "existing status order" would make a continuation timeout `failed`. D3 now separates what feeds
    the status from what feeds `close_forced`. The continuation's failure force-closes the session
    but keeps the first outcome; a root error and quota still fail. Whether that holds after output
    is the new `wpc1-h`.
  - **High, beyond the brief**: D5's summing of prompt results would double-count. Those results
    are process-cumulative, so 2.C.4 is dropped and 1.13 becomes a control.
  - **Also corrected**:
    - the operator wording, now "did not approve", since the card's bool cannot tell Deny from
      expiry;
    - D4/2.D.2's gate, which now reads the D4 diagnostic row, not "the last `permission_denied`";
    - an exact definition of "last" (D2).
- [ ] 0.3 The operator answers `wpc1-a` … `wpc1-f` and `wpc1-h` (added by R3) in
  `spec-queue/DECISIONS.md`.
  - If `wpc1-f` is *no*, delete the `## MODIFIED Requirements` block from
    `specs/agent-run-sandboxing/spec.md`, drop D3, D5 and task group 2.C, and rewrite the ADDED
    scenarios that continue.
  - If `wpc1-a` is (a) only, drop D4 and 2.D.
  - If `wpc1-b` is "end the turn", tests 1.3 and 2.C.1 change as `wpc1-b` says.

## 1. Tests first — each must fail on today's code unless marked as a control

All tests in the new file use the fake-ACP harness from `hub/tests/test_copilot_acp_run_turn.py`.
Import `_drive` (`:3996`), `_raw_event` (`:3912`), `_OPTIONS` (`:3944`), `_new_with` (`:3971`),
`_END_TURN` (`:3993`) and `SESSION_ID` (`:87`).

Each script replays the wire order of a refused root call. Steps 1-3 come from
`fixtures/copilot_acp/turn_write_shell_mcp.jsonl`. That fixture holds **no refusal** (R2): all nine
of its permission requests are allowed. Steps 4-6 come from Copilot's `events.jsonl` for
`run-047359204292` and `run-b1f5b4bedc18`, and their ACP-level order is uncaptured:
1. raw `tool.execution_start` `{toolCallId, toolName: "powershell", arguments: {command}}`;
2. `session/update` `tool_call` pending;
3. `server_request` `session/request_permission` with `_OPTIONS`;
4. raw `tool.execution_complete` `{success: false, error: {code: "rejected", message: "The user
   rejected this tool call."}}`;
5. `session/update` `tool_call_update` with status failed;
6. `_END_TURN`.

There is **no** `agent_message_chunk` after the reject. Continuation cases then script a second
`session/prompt` response: one or more `agent_message_chunk` updates, then `_END_TURN`.

Identify the continuation in `fake.sent_requests` by method `session/prompt` **and** by its text.
The `/mcp list` quote is also a `session/prompt`.

- [ ] 1.1 `hub/tests/test_copilot_acp_refusal_continuation.py::test_the_stop_reason_is_on_the_outcome`
  - Script: a plain turn that ends `_END_TURN` with no refusal.
  - Assert: `outcome.stop_reason == "end_turn"`, and the log (caplog) names `end_turn` and the run.
  - Record that it FAILS today: `TurnOutcome` has no `stop_reason`.
- [ ] 1.2 `test_a_judge_refusal_that_ends_the_turn_is_continued_once_with_its_reason`
  - Setup: `permission_mode="acceptEdits"`; the refused shell is `Get-ChildItem 'C:\Python*'`
    (outside the workspace), with no stub. The real judge is the one used by `run-b1f5b4bedc18`.
  - Script: the refused root call, `_END_TURN`, then the continuation's text and `_END_TURN`.
  - Assert:
    - exactly one continuation `session/prompt` is sent, in `SESSION_ID`;
    - its text names the label and the judge's reason, and says "Continue … another way, or call
      ask_user";
    - the continuation's text reaches `on_output`;
    - `outcome.status == "completed"`;
    - `refusal_continuations == 1`;
    - a `copilot.refusal_continued` diagnostic is emitted before the continuation's text;
    - `on_refusal` is called exactly once.
  - Record that it FAILS today: only the first `session/prompt` is sent.
- [ ] 1.3 `test_an_operator_deny_that_ends_the_turn_is_continued_with_the_operator_named`
  - Setup: `permission_mode="manual"`; `request_approval` returns `False` (the shape of
    `run-047359204292`, `echo hi`).
  - Assert: one continuation, whose text says "The operator did not approve" (R3: not "denied";
    the card's `False` also means expired or timed out).
  - A variant with `request_approval=None`: the refusal is recorded `decided_by="hub"`, and the
    text does not name the operator.
  - Record that it FAILS today. Under `wpc1-b` = "end the turn" this becomes a control: no
    continuation, and the diagnostic of 1.7 is emitted.
- [ ] 1.4 **Control.** `test_a_subagent_refusal_is_not_continued_by_the_hub`
  - Script: the raw start carries `data.parentToolCallId` and the envelope `agentId` (shape from
    `run-b175c9ffa621`'s `events.jsonl`, session `c5e3a780`). The subagent's refused call is
    followed by the root `task` call's `tool_call_update` completed, then root `agent_message_chunk`
    text, then `_END_TURN`.
  - Assert: no continuation; no refusal diagnostic; `ended_on_refusal` false.
  - Passes today. It must still pass after.
- [ ] 1.5 **Control.** `test_a_refusal_followed_by_agent_text_is_not_continued`
  - Script: the refused root call, then an `agent_message_chunk`, then `_END_TURN`.
  - Assert: no continuation.
  - Variants (R3):
    - the chunk's text is a question to the operator ("Should I try another way?"), with no
      `ask_user`: no continuation (the spec's "A turn that ends on a question is not continued");
    - a blank (empty or whitespace-only) chunk, which the mapper drops, is not "agent text": a
      continuation is sent. This
      variant FAILS today.
- [ ] 1.6 **Control.** `test_no_continuation_after_stop`
  - Script: the refused root call, then the interrupt set before the prompt result arrives; the
    pattern of `TestStopSendsSessionCancelAndInterrupts` (`test_copilot_acp_run_turn.py:1118`).
  - Assert: one `session/cancel`; no continuation; `outcome.status == "interrupted"`.
  - Also a variant where the result is `{"stopReason": "cancelled"}` with no interrupt: no
    continuation.
- [ ] 1.7 `test_a_turn_that_ends_on_a_refusal_without_continuing_says_so`
  - Setup: the continuation bound patched to 0, the (b)-only shape.
  - Assert:
    - a warning diagnostic `copilot.turn_ended_on_refusal` carrying `tool_call_id`, `label`,
      `reason`, `decided_by` and `continuations`;
    - `outcome.ended_on_refusal is True`;
    - `outcome.status == "completed"`.
  - Record that it FAILS today.
- [ ] 1.8 `test_the_continuation_is_bounded`
  - Script: the first prompt and the continuation **both** end on a root refusal.
  - Assert: exactly one continuation; no third `session/prompt`; `copilot.turn_ended_on_refusal`
    emitted with `continuations == 1`.
  - Record that it FAILS today.
- [ ] 1.9 `test_a_continuation_that_fails_leaves_the_first_outcome_standing`
  - Script: the continuation's response is `{"error": {...}}` whose `data` is **not** quota-shaped
    (not `errorType: "quota"` with `errorCode: "quota_exceeded"`), or it fails through the quota
    rule instead (R3). A variant uses the fake's
    `{"process_exited": True}` entry. *(R2: not script exhaustion. The fake's `AssertionError` on an
    exhausted script is a harness signal, and testing that it is absorbed would make the harness
    unable to report a missing entry.)*
  - Assert:
    - `outcome.status == "completed"`;
    - a `copilot.refusal_continuation_failed` warning diagnostic;
    - `ended_on_refusal is True`;
    - `mapper.finish()`'s review-agents report emitted exactly once;
    - `fake.closed_with_force is True` (R3: the continuation's failure feeds `close_forced`).
  - A further variant gives a quota `session.error` during the continuation. Assert it is
    `failed`, as the existing quota rule says.
  - A further variant (R3) gives a root, non-quota `session.error` during the continuation. Assert
    it is `failed` (`root_error`), not the first outcome.
  - If `wpc1-h` is (2): a variant whose continuation streams an `agent_message_chunk` and then
    `{"process_exited": True}`. Assert `failed`.
- [ ] 1.10 `test_the_continuation_uses_the_remaining_deadline`
  - Setup: `turn_timeout` small; the first prompt uses most of it; the continuation never answers.
    *(R2: `_FakeACPSession` cannot "never answer". Its `request()` returns, raises or raises on
    exhaustion. This test needs a new script entry that blocks, for example
    `{"hang": asyncio.Event()}`, added to the fake without changing the existing entries.)*
  - Assert: `session/cancel` is sent within the original deadline, the first outcome stands as
    in 1.9, and `fake.closed_with_force is True`.
- [ ] 1.11 `hub/tests/test_failure_reporting.py`: `test_a_completed_copilot_run_carries_its_stop_reason`
  - Unit-test `_runtime_turn_fields` beside `test_a_completed_run_reports_no_runtime_failure_fields`
    (`:190`):
    - `TurnOutcome(status="completed", stop_reason="end_turn", ended_on_refusal=True,
      refusal_continuations=1)` gives all three keys;
    - an outcome without the attributes (Codex) gives `{}`.
  - Extend the lifecycle broadcast test (`:135`) so that `run_completed` carries `stop_reason`.
  - Record that it FAILS today.
- [ ] 1.12 Pinned tests that script a reject followed by `_END_TURN` and nothing after. Each will
  meet a continuation `session/prompt` that the fake cannot answer (the fake raises
  `AssertionError` inside `request()`, `test_copilot_acp_run_turn.py:146-262`). **R2: that raise does
  not turn them red.** Under D7 the continuation absorbs any exception, as the first prompt already
  does (`copilot_acp.py:2791-2795`), so most stay green while silently exercising the failed-continuation
  path. Do not wait for a failure to find them. Edit each one deliberately, either to script the
  continuation's response or to assert that no continuation was sent (a control):
  - `TestOperatorCardWiring::test_manual_asks_the_operator_with_label_and_verdict[False]` (`:4096`);
  - `TestHubOwnCallIdentifiedFromRawEvents::test_without_a_load_report_it_is_judged_foreign_and_says_why_once`
    (`:4042`);
  - `TestHubOwnCallIdentifiedFromRawEvents::test_without_the_start_event_the_title_does_not_identify_it`
    (`:4063`). There is no start in `calls`, so D2 counts the call as parent;
  - `TestFullAccessWithNoAllowAllOption::test_diagnostic_and_outside_workspace_edit_rejected` (`:868`);
  - `TestEveryRequestPermissionAnsweredExactlyOnce::test_two_requests_in_one_turn_each_answered_once_and_correctly_correlated`
    (`:1302`). R2: yes, its second request (id 2, outside the workspace) is a refusal and comes
    last;
  - `TestSpecTurnRestrictsWritesAndAllowAll::test_full_access_never_sets_allow_all_and_judges_execute_as_workspace`
    (`:1666`). **Added by R2.** It refuses `Remove-Item ../../x` and then `end_turn`;
  - `TestSpecTurnRestrictsWritesAndAllowAll::test_create_edit_is_rejected_and_recorded_through_on_refusal`
    (`:1753`).

  The tests at `:868`, `:1302`, `:1666` and `:1753` also assert `outcome == TurnOutcome(session_id=…,
  status=…, error=None)` (at `:966`, `:1370`, `:1751`, `:1856`). D1 alone breaks that assertion,
  and **these do go red**. So do the 10 other such assertions in the file (14 in all: `:445`,
  `:590`, `:627`, `:741`, `:1114`, `:1244`, `:1508`, `:1560`, `:2573`, `:3006`), refusal or not.
  Update each to name the `stop_reason` that turn produces (`"end_turn"`, or none/`"cancelled"` for
  the interrupted ones at `:1244` and `:2573`) and the D2/D3 fields where they apply. Do not use
  `compare=False` (design D1). The one equality assertion in
  `test_codex_appserver_run_turn.py` compares Codex's own `TurnOutcome` and is unaffected.

  Record each one's result on today's code (green), after 2.A (the 14 equality assertions red), and
  after 2.C (the seven above changed as decided). Do not weaken an assertion to make it pass. No other
  test file drives Copilot's `run_turn` through a refusal (R2 checked every file that imports it).
  These stay green unchanged:
  - `test_copilot_acp_decide.py::TestTotality` (`:936`);
  - `test_the_answer_is_never_allow_always` (`:1029`), which pins `reject_once` as the answer;
  - `TestNoRemovedRawEventCallbackOrOutcomeFields::test_turn_outcome_has_no_prompt_usage_or_session_was_new_field`
    (`:2145`), which bans only two names.
- [ ] 1.13 **Control (R3).** `hub/tests/test_copilot_usage.py`:
  `test_a_later_prompt_result_in_one_process_is_kept_not_added`
  - Two `observe_prompt_result` calls, the second's totals at least the first's (cumulative, as
    Copilot reports within one process); no `assistant.usage`.
  - Assert: the `copilot_prompt_result` sample's tokens are the **second** result's, not the sum.
  - Passes today, and must still pass after. *(R1 had this as a summing test that failed today. R3:
    the prompt result is process-cumulative, so summing double-counts; design D5.)*
- [ ] 1.14 `test_a_stop_just_before_the_result_is_not_continued` (R3)
  - The Stop race the poll loop cannot see today: the refused root call, `_END_TURN`, with
    `should_interrupt=lambda: not fake._script` (true only once the last entry has been consumed,
    after every per-notification poll has run). No continuation is scripted.
  - Assert: one `session/cancel`; no continuation `session/prompt`; `outcome.status ==
    "interrupted"`; `fake.closed_with_force is True`.
  - Record that it FAILS today: the turn returns `completed`, because nothing polls between the
    last notification and the result.
- [ ] 1.15 `test_a_cancelled_task_during_the_continuation_propagates` (R3)
  - Script: the refused root call, `_END_TURN`, then a continuation entry that blocks (1.10's
    `hang` entry). Run `run_turn` as a task; once the continuation `session/prompt` is in
    `fake.sent_requests`, `task.cancel()` (what `_settle_background_runs` does at Hub shutdown).
  - Assert: awaiting the task raises `asyncio.CancelledError`; no
    `copilot.refusal_continuation_failed` diagnostic; the fake was closed.
  - Record that it FAILS today, only because no continuation is sent (the turn returns `completed`).
    Its purpose is to stop D7's "absorb" from swallowing cancellation.
- [ ] 1.16 `test_a_parallel_call_started_before_the_refusal_does_not_clear_it` (R3)
  - Script: root raw start A; root raw start B; the permission request for A, refused; B's
    `tool_call_update` completed; A's complete (rejected); `_END_TURN`; then the continuation.
  - Assert: one continuation, naming A.
  - A variant with B's raw start **after** A's refusal: no continuation.
  - Record that the first FAILS today and the variant passes.

## 2. Implementation

### 2.A Stop reason (D1, always)

- [ ] 2.A.1 `TurnOutcome` (`copilot_acp.py:1962`) gains `stop_reason: Optional[str] = None`,
  `ended_on_refusal: bool = False` and `refusal_continuations: int = 0`.
- [ ] 2.A.2 `_await_prompt` logs `stopReason` at info for every prompt, with the run id and the
  prompt's ordinal, and stores the last one on the outcome.
- [ ] 2.A.3 `agent_trigger.py`: add `_runtime_turn_fields(outcome)` beside `_runtime_failure_fields`
  (`:2288`). It uses `getattr` and omits empty values. Merge it into the terminal
  `_broadcast_run_lifecycle` call (`:4230`) and the closing status row's payload (`:4255`).

### 2.B Detection (D2)

- [ ] 2.B.1 `CallFacts` gains `subagent: bool = False`. `track_call` sets it from
  `data.parentToolCallId` and, from the callers that have it, the envelope `agentId`: pass `params`
  from `on_notification` (`:2310`) and from the mapper's `on_raw_event` (`:1287`).
- [ ] 2.B.2 `answer_permission` (`:2376`): on a refusal of a parent-level call, set
  `state["last_refusal"]` before calling `on_refusal` or `on_decision`. For the operator path,
  `decided_by="operator"` and the fixed reason (`wpc1-b`), worded "did not approve" (R3: the
  card's `False` is Deny, expiry or timeout alike). When `request_approval` is `None`, record
  `decided_by="hub"` with the reason "no operator channel".
- [ ] 2.B.3 Clear `state["last_refusal"]` on a root `agent_message_chunk` the mapper **keeps**
  (text not blank after `strip()`, not a `session.error` echo), or on a root raw
  `tool.execution_start` with another id that arrives **after** the refusal. Nothing after the
  prompt result counts; a later refusal overwrites an earlier one; subagent refusals are never
  recorded (design D2, "Last"; 1.5, 1.16).

### 2.C Continuation (D3, D5) — only if `wpc1-a` is (a) or (c) and `wpc1-f` is yes

- [ ] 2.C.1 Split `_await_prompt` into `_send_and_wait(blocks, deadline)` and one tail that calls
  `mapper.finish()` once.
- [ ] 2.C.2 Add `REFUSAL_CONTINUATIONS_PER_TURN = 1`. After a prompt that ended on a refusal, and
  only when no interrupt, cancel, forced failure, failure, root error or quota refusal is set:
  1. call `check_interrupt()`;
  2. emit `copilot.refusal_continued` (suppressed);
  3. clear the record;
  4. send the continuation, within the remaining deadline.
- [ ] 2.C.3 D7's raise handling: catch `Exception` only, never `BaseException`, so
  `CancelledError` propagates (1.15). A failed continuation (transport error, process exit,
  non-quota error response, its own timeout) leaves the first outcome, feeds `close_forced` but not
  the status, emits `copilot.refusal_continuation_failed`, and sets `ended_on_refusal`. A root
  `session.error` or a quota refusal during it still fails the run (design D3, "What feeds the
  tail"). Apply `wpc1-h` as decided.
- [x] 2.C.4 ~~`CopilotUsageLedger.observe_prompt_result` sums the dimensions across a turn's
  prompts~~ **Dropped by R3.** The prompt result is process-cumulative, so last-wins is already
  correct and summing would double-count; `copilot_usage.py` is unchanged (design D5; 1.13 is a
  control).

### 2.D Visibility (D4) — only if `wpc1-a` is (b) or (c)

- [ ] 2.D.1 Emit `copilot.turn_ended_on_refusal` (warning, suppressed) when D2 fires and no
  continuation is sent, or when the bound is reached. Set `ended_on_refusal`.
- [ ] 2.D.2 `run_divergence.evaluate_run_end`: when the run has a
  `copilot.turn_ended_on_refusal` or `copilot.refusal_continuation_failed` diagnostic row (R3: not
  "the last `permission_denied` event", which cannot tell which turn or whether the agent went on),
  put the refusal's label and reason from that row in the surfaced message. A DB error keeps
  today's message.

### 2.E Spec and checks

- [ ] 2.E.1 Update the pinned tests from 1.12 as decided there.
- [ ] 2.E.2 Run, with `py -3.11`:
  - `pytest hub/tests/test_copilot_acp_refusal_continuation.py hub/tests/test_copilot_acp_run_turn.py hub/tests/test_copilot_acp_decide.py hub/tests/test_failure_reporting.py hub/tests/test_copilot_usage.py -q`;
  - then `pytest hub/tests/ -q`;
  - `ruff check hub/`;
  - `black --check hub/hub/ hub/tests/`;
  - `npx openspec validate a-refused-copilot-call-does-not-end-the-turn --strict`.

## 3. Live verification

- [ ] 3.1 On the trial Hub `:8010` only, with the work-PC Copilot agent in `acceptEdits`:
  - ask it to list `C:\Python*`;
  - confirm one continuation prompt, a `copilot.refusal_continued` row, agent text after it, and
    `stop_reason: end_turn` on `run_completed`;
  - compare the premium requests for the turn against Copilot's `events.jsonl` checkpoint;
  - (R3) compare the continuation's prompt-result totals with the sum of the turn's
    `assistant.usage` calls, to confirm the prompt result is cumulative across two model prompts in
    one process (inferred, not yet measured; design D5).
- [ ] 3.2 The same in `manual`: Deny `echo hi`. Confirm the behaviour `wpc1-b` chose.
- [ ] 3.3 A refusal inside a subagent (`task` tool): no Hub continuation; the parent continues by
  itself.
- [ ] 3.4 A task run: whatever the outcome, the task is not left `in_progress` with nothing said.
  Either the agent continues, or the divergence names the refusal.
