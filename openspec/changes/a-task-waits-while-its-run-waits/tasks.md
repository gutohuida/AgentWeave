## 1. Reproduce both halves as failing tests first

- [ ] 1.1 Add `hub/tests/test_a_task_waits_while_its_run_waits.py`. Build F14's shape: an agent, a run bound to a task in `in_progress`, and a blocking question asked through `POST /questions` on the agent-facing router (`agent_actions.ask_operator_question`) with the run's own credential. Assert the current behaviour — `task.status == "in_progress"`, `blocked_reason is None`, `question.blocked_task_id is None` — and run it against unmodified code to confirm it passes. A reproduction that does not pass first is not a reproduction.
- [ ] 1.2 Add F60's shape to the same file: the same setup, then the run moves the task to `completed` while the question is still unanswered. Assert what F60 measured — `tasks.status == "completed"`, `blocked_reason is None`, `questions.answered is False`, `declined is False`, `blocked_task_id is None` — and that nothing on the task response says a decision was made without the operator. Confirm it passes against unmodified code.
- [ ] 1.3 Add the batch shape: `POST /questions/batch` with two blocking questions, and assert that today neither records `blocked_task_id` and the task does not move.

## 2. Park at ask time

- [ ] 2.1 Move `_announce_block` from `hub/hub/run_divergence.py:539-568` to `hub/hub/run_task_binding.py`, beside `block_task_for_question`. Keep `severity="info"` and its docstring's reasoning. Update the `run_divergence` call site to import it.
- [ ] 2.2 In `hub/hub/api/v1/agent_actions.py`, after `ask_question_for_actor` returns, park the asking run's bound task: resolve `Run` from `actor.run_id`, take `run.task_id`, and call `block_task_for_question` with the run, task and question. Do it for the single-question route and for every question of the batch route, in batch order.
- [ ] 2.3 Only for `blocking=True`. A non-blocking ask is the agent leaving a note; parking on one would make the status mean an agent mentioned something (`unanswered_blocking_question`'s own rule).
- [ ] 2.4 Do **not** put this in `ask_question_for_actor`. That helper is shared with the operator-facing `POST /questions`, which has no run and no binding, and a park there would be a park with no asker. Add a comment saying so, because the helper is the obvious wrong place.
- [ ] 2.5 Announce it: call the moved `_announce_block` when — and only when — the transition actually happened, matching `evaluate_run_end`'s existing condition, so a batch of four announces once.
- [ ] 2.6 Correct the two comments that now state something false: `hub/hub/api/v1/tasks.py:336-343` (`_attach_awaiting_answer`'s docstring) and `hub/hub/schemas/tasks.py:317-322` (`awaiting_answer_reason`'s comment). Both say a task reaches `blocked` only when the asking run ends. Say what the field is still for instead — the two cases in design D9.
- [ ] 2.7 Flip task 1.1's assertion: the task is `blocked` with a `blocked_reason` derived from the question, `blocked_task_id` is set, and the transition is `origin='runtime'` naming the run. Add the batch assertion from 1.3 flipped: the first question transitions, the second records `blocked_task_id` without a second transition.
- [ ] 2.8 Add the case the park must refuse: a run bound to a task in `under_review` asks a blocking question. No transition, `blocked_task_id` still recorded, and `awaiting_answer_reason` reports the wait. This is the case that keeps that field alive.

## 3. Prove that blocked-while-running breaks nothing

One test per row of the proposal's table that a reviewer could reasonably doubt. These are guards,
not reproductions; they must pass before and after.

- [ ] 3.1 A run whose task was parked at ask time ends with the question still unanswered: no divergence is recorded, the task is still `blocked`, and nothing was started in response (`run-task-binding:594`).
- [ ] 3.2 A loop firing does not claim a task parked at ask time, and the loop's board still shows it as the current item (`jobs.py:354`).
- [ ] 3.3 A second run binding to a task parked at ask time leaves it parked (`run-task-binding:618`).
- [ ] 3.4 `_free_agents` still excludes the agent whose run is waiting.
- [ ] 3.5 Fix `dependency_state` in `hub/hub/api/v1/tasks.py:317`: `running_on_regressed` is derived from `response.status == "in_progress"` and must also hold for `blocked`, which is reachable only from `in_progress` and therefore has always started. Add a test for a parked task with a regressed prerequisite, and a comment recording that this was already wrong before ask-time parking and is only widened by it.

## 4. The wait's deadline, recorded

- [ ] 4.1 Add `wait_expires_at` to `Question` in `hub/hub/db/models.py`, nullable `UTCDateTime`, with a comment saying what it is for: the tool owns the timeout value, so the Hub cannot compute this and must be told.
- [ ] 4.2 New migration in `hub/hub/migrations/versions/`, guarded for a missing table the way `0033`/`0034` are. Bump the head assertions in `hub/tests/test_migrations.py` **and** `hub/tests/test_project_persistence.py`.
- [ ] 4.3 Accept `wait_seconds` on the agent-facing ask schemas (single and batch) and set `wait_expires_at = now + wait_seconds`. Optional: absent means null, and a null deadline refuses every expiry report — the safe direction, and what an older tool gets.
- [ ] 4.4 In `hub/hub/mcp_server.py`, send `wait_seconds=QUESTION_ANSWER_TIMEOUT` on the batch POST when `blocking` is true, and nothing when it is false. Check `hub/tests/test_mcp_tool_schemas.py` still passes — the module may import only stdlib and fastmcp, and `approve_tool_call` keeps no return annotation.

## 5. The end of the wait

- [ ] 5.1 Add `wait_ended_at` to `Question`, nullable, in the same migration as 4.1.
- [ ] 5.2 Add `POST /questions/wait-ended` to the agent-facing router in `hub/hub/api/v1/agent_actions.py`, taking a list of question ids. Not an `@mcp.tool()` — it is not a capability, and design D4 says why.
- [ ] 5.3 Refuse per question, silently skipping rather than erroring the batch: not asked by the calling run; no `wait_expires_at`; `wait_expires_at` not yet passed; already answered or declined. Return which ids were accepted so the tool's own behaviour is testable.
- [ ] 5.4 Set `wait_ended_at` on each accepted question, then release the task once if it is `blocked` — a new `release_block_for_expired_wait` in `run_task_binding.py` beside the other two release paths, attributed to the run with `origin='runtime'` and calling `release_reason`.
- [ ] 5.5 In `hub/hub/mcp_server.py`, call it from `ask_user` immediately after the wait loop, with the ids of the questions that expired — the `expired` list already computed at `:411`, not `unanswered`, so a decline is never reported as an expiry. Failure to reach the Hub must not raise: the tool still returns the agent its answers.
- [ ] 5.6 Test the whole path against the reproduction from 1.2: the task is `blocked`, the expiry is reported, the task is `in_progress` again with no `blocked_reason`, and `update_task(completed)` then succeeds. Assert the transition history reads `in_progress → blocked → in_progress → completed`, which is the requirement that no history states a task was completed while waiting.
- [ ] 5.7 Test each refusal in 5.3 individually, and the unreported case: the run ends without reporting, and the task is still `blocked`.

## 6. An expired wait is not an open one

- [ ] 6.1 Add `Question.wait_ended_at.is_(None)` to `unanswered_blocking_question` (`run_task_binding.py:574-602`), with the reasoning from design D6 in the docstring beside the existing `blocking`/`declined` paragraphs.
- [ ] 6.2 Add the same condition to `_attach_awaiting_answer`'s query (`hub/hub/api/v1/tasks.py:362-376`).
- [ ] 6.3 Test the case that matters: a run whose wait expired, that reported it, and that then ends **without** moving its task. It must be divergent as normal, and the task must not be re-parked. Without 6.1 this test fails by recording a wait that had already ended.

## 7. Ungate the resume

- [ ] 7.1 In `hub/hub/task_transition_service.py:371-383`, skip the dependency gate for `blocked -> in_progress`. Derive it from the task's status at the transition rather than from a flag the caller passes, so no caller can forget it and no caller can abuse it.
- [ ] 7.2 Comment it with design D5's reasoning: the gate asks whether work may *start*, `blocked` is reachable only from `in_progress`, so this work started and this edge resumes it.
- [ ] 7.3 Test all three releases — answer, decline, expiry — against a task whose prerequisite regressed while it waited. All three release; none is refused. The expiry case is the one that would otherwise leave an agent unable to complete finished work.
- [ ] 7.4 Test that the gate still refuses `pending -> in_progress` and `assigned -> in_progress` unchanged, so this does not read as a general weakening.

## 8. Say it on the task, permanently

- [ ] 8.1 Add a sibling of `reason_from_question` in `run_task_binding.py` producing the "proceeded without your answer" statement, trimmed by the same `_REASON_LIMIT`, so the two surfaces cannot spell it differently.
- [ ] 8.2 Add `proceeded_without_answer_reason` to `TaskResponse` in `hub/hub/schemas/tasks.py`, with a comment saying it is derived and why it is permanent.
- [ ] 8.3 Derive it in `hub/hub/api/v1/tasks.py` beside `_attach_awaiting_answer`: a question with `blocked_task_id == task.id` and `wait_ended_at IS NOT NULL`. **No condition on `answered`** — design D7, and the reason belongs in the code as a comment because it is the non-obvious half.
- [ ] 8.4 Render it on `TaskCard.tsx` and `TaskDetailDrawer.tsx`, distinct from the waiting treatment: waiting is a live ask, this is a decision already taken. Reuse the existing `Icon` component; do not add an icon source.
- [ ] 8.5 UI tests in `hub/ui/src/__tests__/` alongside `taskBlockedTreatment.test.tsx`: a completed task carrying the statement renders it, and a task with an answered question does not.
- [ ] 8.6 Backend tests: the statement appears on a `completed` task, survives `under_review` and `approved`, and is **still there** after the operator answers the question afterwards. That last one is F60's compounding half and is the assertion this requirement exists for.
- [ ] 8.7 If `hub/ui/src` changed: `cd hub/ui && npm run build`, then `py -3.11 scripts/refresh_ui_bundle.py`, and commit `hub/ui/src` and `hub/hub/static/ui` together.

## 9. Gates, suites and a live drive

- [ ] 9.1 `ruff check src/ hub/ tests/` · `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/` · `mypy src/` · `cd hub/ui && npm run lint`.
- [ ] 9.2 Full Hub suite. Baseline before this change is what the previous iteration measured; the difference must be exactly the tests this change adds.
- [ ] 9.3 CLI suite and UI suite.
- [ ] 9.4 A drive harness under `scripts/drive/`, against a Hub on 8011 started from current source, binding Haiku: a real agent asks a real blocking question about a real task, and the task is observed `blocked` **while the run is still `running`** — the assertion no unit test can make. Then leave it unanswered, let the timeout expire, and assert the task returns to `in_progress`, the agent completes it, and the completed task carries the statement. Restart the Hub first and confirm it serves the code under test.
- [ ] 9.5 `openspec validate a-task-waits-while-its-run-waits --strict`, sync the delta into `openspec/specs/task-lifecycle-governance/spec.md`, archive the change.
- [ ] 9.6 Update `scripts/drive/FINDINGS.md`: F14 and F60 both fixed, naming the commits and anything the implementation overturned.
