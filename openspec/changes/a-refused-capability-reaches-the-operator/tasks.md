# Tasks — a refused capability reaches the operator

Findings: **F376 (A)** — closes it; **F378 (B)** — *not* closed here (its repair is deferred by
DIRECTION.md 2026-09-18; this change only makes the helper it will reuse).

**R1, 2026-09-18; amended by R2, 2026-09-18. Nothing below is built. One more independent
re-derivation round (R3) is owed before any task is started** — `CLAUDE.md`'s round discipline, and
this repository's dominant failure mode is a fix that passes its tests and cannot fire in
production. Tasks carrying **(R2)** were changed or answered by that round; see design.md's Rounds
section for what moved and why.

Tests run under `py -3.11`, never bare `python`. `black` needs `--target-version py311` on this
machine. No migration, no schema change, no UI change (design D4).

## 1. The record

- [ ] 1.1 New `hub/hub/refused_capability.py`. One coroutine, e.g.
  `refuse_for_project_state(session, *, project_id, agent, run_id, setting, current_value,
  what_enabling_allows, where_changed, capability)`. It returns nothing and always raises; the
  caller's `raise` is not optional (design D8).
- [ ] 1.2 It composes the **stable** question text: names the setting, its current value, what
  enabling it allows, and where the operator changes it (Environment › Settings). It **must not**
  contain the requesting agent's name, the run id, or the call's arguments — the dedupe key is the
  text (design D5).
- [ ] 1.3 Dedupe: select the most recent `Question` for this `project_id` with that exact text.
  - unanswered → open nothing, raise carrying its id;
  - answered, and `answer_labels` contains the *"Leave it off"* label, or declined → open nothing,
    raise **without** claiming the operator has been asked;
  - answered affirmatively, or none → open a new one.
- [ ] 1.4 **(R2)** Open through `ask_question_for_actor` (`hub/hub/api/v1/questions.py:234`) — not a
  hand-built `Question` — so the id scheme, the `question_asked` broadcast and the batch fields are
  the shipped ones. `from_agent` is the refused agent; **`created_by_run_id=None`**, so the row
  carries no run and therefore no `conversation_id` (design **D10** — passing the run would pin the
  refused run's conversation to `"waiting"` for the rest of its life, `conversations.py:433-441`,
  and make a drained loop report this record as what it is waiting on,
  `scheduler._pending_loop_request:400-452`). `blocking=False` (design D11).
- [ ] 1.5 **(R2)** Satisfy `QuestionCreate` (`hub/hub/schemas/questions.py:22-34`), which is
  stricter than it looks (design **D12**): `options` is **required with at least two entries** —
  *"Enabled it — go ahead"* / *"Leave it off"*, each with a `description`; `header` is **required**
  and at most 64 characters, naming the capability; `multi_select` is **required** and is `False`.
  A call omitting any of the three fails validation, so there is no optionless form of this
  question.
- [ ] 1.6 Raise `HTTPException(403, detail={...})` carrying `code:
  "project_setting_blocks_capability"`, `message` (the sentence), `setting`, `current_value`,
  `question_id`, and one clause saying the answer arrives as input and the call should not be
  polled or repeated (design D2, D6).

## 2. The gate

- [ ] 2.1 `hub/hub/api/v1/jobs.py:44-51` — replace **only** the `allow_agent_jobs` branch with a call
  to 1.1. Leave the early return for operator calls (`:39`) and both attribution refusals exactly as
  they are; their order is load-bearing (design D9.2).
- [ ] 2.2 **(R2 — read and answered; re-confirm only if the routes have moved.)** At all four call
  sites (`:568`, `:847`, `:1163`, `:1294`) the gate is the **first statement** after
  `project_id, _ = project`, so nothing of the route's own is pending in the session when
  `ask_question_for_actor` commits — no half-written job, no partial update is made durable by the
  refusal's commit. The precedent for committing and *then* raising is
  `operator_direction._open_request`. **Keep it that way:** any future route that does work before
  calling the gate breaks this, so the gate stays the first statement.
- [ ] 2.3 **(R2 — read and answered.)** `archive_job` calls the allowance gate at `:1163` and
  `require_operator_direction` only at `:1182`, inside the `agent_identity is not None` branch. An
  agent with the allowance off therefore raises out of the gate and never reaches the 409 path: the
  new refusal, no permission request, no two records. **That ordering is load-bearing** — reversing
  it would open a turn-scoped card for a decision that is not turn-scoped. Assert it (task 4.7)
  rather than re-deriving it.

## 3. What the agent is told

- [ ] 3.1 `hub/hub/mcp_server.py` — the five job tools' docstrings (`create_loop`, `create_flow`,
  `update_job`, `toggle_job`, `run_job`) state the new refusal: the setting, that the operator is
  asked once, that the answer arrives as a message, and that polling is not the protocol here.
  **Add no wait** (design D2, D7).
- [ ] 3.2 `hub/hub/api/v1/agents.py` — the same for each affected `_Operation`'s `text`/`http_note`,
  beside `archive_job`'s existing protocol note (`:1276-1289`). The two must not contradict: one
  action on that surface polls, five do not.

## 4. Tests

- [ ] 4.1 New `hub/tests/test_refused_capability.py`, **driven through the route with real agent
  attribution** (a live run, the `X-AgentWeave-Agent` header): first refusal opens exactly one
  question, broadcasts `question_asked`, and the 403 body carries the code and the `question_id`.
- [ ] 4.2 The record survives the run's end: end the run (the path that calls
  `expire_pending_for_run`) and assert the question is still unanswered, and that a
  `PermissionRequest` was never created.
- [ ] 4.3 A late answer reaches the agent: answer after the run has ended and assert an inbound queue
  entry for that agent carries the answer — the property D1 chose this row for.
- [ ] 4.4 Dedupe: two refusals, one question, same id in both bodies.
- [ ] 4.5 A negative answer: answer with *"Leave it off"*, refuse again, assert no second question and
  that the sentence does not claim the operator has been asked.
- [ ] 4.6 An operator call (no attribution headers) is refused by nothing and opens no question.
- [ ] 4.7 `hub/tests/test_agent_actions_governed.py` — `archive_job` with the allowance off returns
  the new refusal and opens no permission request (task 2.3's behaviour).
- [ ] 4.8 A test that asserts the refusal **sentence** an MCP caller sees, through
  `_readable_detail` (`mcp_server.py:124`), not just the dict — and that `HubAPIError.data` still
  carries the `question_id`, which is how an adapter learns it without parsing prose.
- [ ] 4.9 **(R2)** The record does not claim anybody is waiting. Assert the opened question has
  `created_by_run_id` and `conversation_id` NULL, and that the refused run's conversation's
  attention state is **not** `"waiting"` (`conversations.py:433-441`) — the defect design D10
  exists to avoid. A test that only checks the question exists would pass with the run stamped on
  it.

## 5. Drive it

- [ ] 5.1 Reproduce D-1's harness against the fix on the trial Hub `:8010`, from source — a fresh
  project, one `claude-haiku-4-5-20251001` agent, one real turn calling `create_flow`. Assert: one
  question visible on the operator's Questions destination, the agent's transcript carrying the new
  sentence, `permission_requests` still empty.
- [ ] 5.2 Then answer it as the operator, with the setting enabled by hand, and assert the agent wakes
  and its retry succeeds. **This is the task that proves the change**; a green suite without it proves
  only that the code runs. **(R2)** While the record is open and before answering, look at the
  Questions destination and at the conversation list: the question must render in the **Unanswered**
  section rather than under the red *"Blocking"* banner (design D11), and the refused run's
  conversation must still read as running, not waiting.
- [ ] 5.3 Set F376's `Status:` line to `fixed <sha>` only after 5.2. Never on the strength of 4.x.
