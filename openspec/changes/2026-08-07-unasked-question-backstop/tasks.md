# Tasks

## 1. Detecting a trailing question

- [x] 1.1 Add `hub/hub/unasked_question.py` with a pure `trailing_question(text) -> str | None`,
      importable without the trigger machinery.
- [x] 1.2 Rule: last non-empty line, markdown list markers and emphasis stripped, ending in `?`.
      Bounded to 400 chars.
- [x] 1.3 Text ending inside an unclosed code fence returns `None`.
- [x] 1.4 A line that is only punctuation returns `None`; empty/blank input returns `None`.
- [x] 1.5 Tests for each rule, including a mid-turn question followed by prose (⇒ `None`).

## 2. The record

- [x] 2.1 Add `UnaskedQuestion` to `hub/hub/db/models.py`: id, project_id, agent, run_id,
      conversation_id, question, status (`pending`/`asked`/`dismissed`), created_at, resolved_at.
- [x] 2.2 Migration `0032_add_unasked_questions.py`. Head becomes 0032.
- [x] 2.3 Extend `hub/tests/test_migrations.py` for the new head.

## 3. Detection at run completion

- [x] 3.1 Add `_flag_unasked_question(...)` to `hub/hub/api/v1/agent_trigger.py`.
- [x] 3.2 Suppress unless `final_status == "completed"`.
- [x] 3.3 Suppress if any `Question.created_by_run_id == run_id`.
- [x] 3.4 Suppress if `queued_entries` for the agent is non-empty, using the scheduler's own helper.
- [x] 3.5 Read the highest-`sequence` `AgentOutput` for the run with `kind="text"`.
- [x] 3.6 Persist the row, an `EventLog` row (`question_not_asked`, `severity="warn"`), and broadcast
      `question_not_asked`.
- [x] 3.7 Call it from **both** completion sites — `_execute_run` and
      `_execute_codex_appserver_run` — before `schedule_agent`.
- [x] 3.8 Never let a failure here change the run's outcome: wrap and log.
- [x] 3.9 Tests: fires once for a qualifying run; each of the four suppressions verified separately.

## 4. Operator endpoints

- [x] 4.1 `hub/hub/api/v1/unasked_questions.py` — `GET /unasked-questions` (pending by default).
- [x] 4.2 `POST /unasked-questions/{id}/dismiss`.
- [x] 4.3 `POST /unasked-questions/{id}/ask` — flip status, then trigger the agent with the canned
      re-prompt naming the question and requiring `ask_user` with structure.
- [x] 4.4 Acting on a non-pending record ⇒ 409.
- [x] 4.5 Register the router in `hub/hub/api/v1/__init__.py`.
- [x] 4.6 Tests, including project isolation (add to `hub/tests/test_bola.py`).

## 5. The card

- [x] 5.1 `hub/ui/src/api/unaskedQuestions.ts` — list hook with `refetchInterval`, ask and dismiss
      mutations.
- [x] 5.2 `hub/ui/src/components/agents/UnaskedQuestionCard.tsx` using `.conversation-interject`, so
      it reads as part of the composer like the other two cards.
- [x] 5.3 Mount in `AgentOutputPanel.tsx` beside `PermissionRequestCard`; self-filters by agent and
      pending status.
- [x] 5.4 `useSSE.ts` — subscribe `question_not_asked`.
- [x] 5.5 `api/agents.ts` — `question_not_asked` in `eventBelongsToTimeline`.
- [x] 5.6 `lib/eventSummary.ts` — a case naming the agent and the question.
- [x] 5.7 Frontend tests for the card and for the SSE/summary wiring.

## 6. The severity fix

- [x] 6.1 `agent_actions.py` and `permissions.py`: `severity="warning"` → `"warn"`.
- [x] 6.2 Test asserting a denial is stored with a severity the UI's filter list contains.

## 7. Close out

- [x] 7.1 `pytest hub/tests/ -q`, `pytest tests/ -q`, `npx vitest run`, `npx tsc --noEmit`.
- [x] 7.2 `ruff check` every touched Python file.
- [x] 7.3 `npm run build` and sync `hub/hub/static/ui`; verify with `diff -rq`.
- [x] 7.4 `npx openspec validate --specs --strict`.
- [x] 7.5 Live-verify against a real Codex run that ends in a prose question.
