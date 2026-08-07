# Tasks

## 1. The batch on the row

- [x] 1.1 `Question` gains `batch_id` (nullable, indexed), `batch_index` (default 0), `batch_size`
      (default 1) in `hub/hub/db/models.py`.
- [x] 1.2 Migration `0033_add_question_batches.py`; head becomes 0033. Existing rows read as a batch
      of one without backfill.
- [x] 1.3 Update the head assertions in `test_migrations.py` and `test_project_persistence.py`.
- [x] 1.4 `QuestionResponse` carries the three fields.

## 2. Creating a batch

- [x] 2.1 `AgentQuestionBatchCreate` in `hub/hub/schemas/questions.py`: `questions` (1–4), each the
      existing required structure; `blocking`.
- [x] 2.2 `POST /questions/batch` on `agent_actions.py` — one row per entry, sharing a generated
      `batch_id`, `batch_index` by position, `batch_size` the length. Returns the ids in order.
- [x] 2.3 Reuse `ask_question_for_actor` so a batched question is created by the same path as any
      other, including `created_by_run_id`.
- [x] 2.4 Tests: 1 and 4 accepted; 0 and 5 rejected; a malformed entry rejects the whole call and
      creates nothing.

## 3. The tool

- [x] 3.1 `ask_user(questions, blocking=True)` in `hub/hub/mcp_server.py`; the single-question
      signature is removed.
- [x] 3.2 Docstring teaches the list, the 1–4 bound, and that each entry needs the full structure.
- [x] 3.3 Poll until every id is answered or the deadline passes; return one entry per question.
- [x] 3.4 On expiry, return the answers given and say plainly which went unanswered.
- [x] 3.5 Tests: a batch of 3 round-trips; a partly-answered batch at expiry; a batch of 1 behaves as
      before; multi-select answers stay lists.
- [x] 3.6 Update `_tool_surface_lines()` in `api/v1/agents.py` to describe the new signature.

## 4. Stepping through, in the UI

- [x] 4.1 `hub/ui/src/lib/pendingQuestions.ts` — `activeQuestionFor(questions, agent)` returning the
      active question, its 1-based step, and the batch total. Ordering: `batch_index`, then
      `created_at`.
- [x] 4.2 Unit-test it directly: batch ordering, partly-answered batches, several batches
      outstanding, no questions.
- [x] 4.3 `AgentQuestionCard` uses it; the counter becomes the real step counter and shows for any
      batch larger than one.
- [x] 4.4 `AgentOutputPanel` uses the same selector for `pendingQuestion`, so the composer answers
      what is displayed.
- [x] 4.5 `Question` type in `api/questions.ts` gains the three fields.
- [x] 4.6 Frontend tests: stepping advances, the counter reads `2/3`, and the answer is recorded
      against the displayed question.

## 5. Close out

- [x] 5.1 `pytest hub/tests/ -q`, `pytest tests/ -q`, `npx vitest run`, `npx tsc --noEmit`.
- [x] 5.2 `ruff check` every touched Python file.
- [x] 5.3 `npm run build` and sync `hub/hub/static/ui`; verify with `diff -rq`.
- [x] 5.4 `npx openspec validate --specs --strict`.
- [x] 5.5 Live-verify: a real agent asks three questions in one call, and the operator steps through
      them in the browser.
