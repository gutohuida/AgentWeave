# Tasks — a refused capability reaches the operator

Findings: **F376 (A)** — closes it; **F378 (B)** — *not* closed here (its repair is deferred by
DIRECTION.md 2026-09-18; this change only makes the helper it will reuse).

**R1, 2026-09-18; amended by R2 and R3, 2026-09-18. Nothing below is built; the three rounds
`CLAUDE.md` requires are now done.** Tasks carrying **(R2)** or **(R3)** were changed or answered by
that round; see design.md's Rounds section for what moved and why. R3 changed two tasks that would
have shipped defects: 1.3's dedupe could not detect a typed *"leave it off"* (design **D13**), and
3.1 named an MCP tool that does not exist while omitting one that does (**D7**, R3 table).

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
  **(R3)** Interpolating the *current value* is safe: the gate's own branch is
  `not project.allow_agent_jobs` (`jobs.py:47`), so the value is false at every call that can reach
  this, and the key cannot vary with it. The text to use, as the round wrote it out:

  > May agents schedule work in this project? The project setting `allow_agent_jobs` is **off**, so
  > the Hub refuses every attempt by an agent to create or change scheduled work — loops, flows and
  > jobs. Enabling it lets agents create and run recurring work, which commits repeated model spend
  > without asking again. You change it yourself at Environment › Settings.
- [ ] 1.3 **(R3 — rewritten; design D13.)** Dedupe: select the most recent `Question` for this
  `project_id` with that exact text, and **never read the answer's polarity**.
  - **none** → open a new one (1.4);
  - **neither answered nor declined** → open nothing, raise carrying its id and saying the operator
    has been asked and has not answered yet;
  - **answered or declined** → open nothing, raise quoting what the operator said verbatim (or that
    they declined it) and that the setting is still off. Do **not** claim they have been asked again.

  The rule R1 wrote — *"`answer_labels` contains the `Leave it off` label"* — **cannot fire on a
  typed answer**: both answering surfaces send `labels` only when the textarea is empty
  (`AnswerForm.tsx:33-38`, `AgentOutputPanel.tsx:934-942`), so a typed *"no, leave it off"* stores
  `answer_labels = []` (`questions.py:405`) and R1's rule would have re-asked. Nothing is lost by
  not interpreting: the gate runs only while the setting is false, so a resolved record plus a
  firing gate already means *the operator saw these exact words and it is still off*. "Resolved
  means answered **or** declined" is `_completed_batch`'s own definition (`questions.py:93-95`).
  Two simultaneous refusals will still open two records; that is tolerated and stated (D13), not
  fixed with an index.
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
  question. **(R3)** The descriptions must be honest about D4 and D13 — answering does not flip the
  setting, and the question is not asked again either way: *"Turn the setting on yourself at
  Environment › Settings; agents may then schedule recurring work here."* / *"Agents keep being
  refused. Nothing is asked again for this project."* `header`: `"Scheduled work"`.
- [ ] 1.6 Raise `HTTPException(403, detail={...})` carrying `code:
  "project_setting_blocks_capability"`, `message` (the sentence), `setting`, `current_value`,
  `question_id`, and one clause saying the answer arrives as input and the call should not be
  polled or repeated (design D2, D6). **(R3)** The `question_id` must also appear **inside
  `message`**: `.data` is read by exactly one place on this surface (`archive_job`, and only for
  `operator_direction_required`, `mcp_server.py:843-848`), so the body's structure does not reach
  the model — only the sentence does, prefixed with `Hub rejected POST /jobs (403):`
  (`mcp_server.py:103-105`). The sentence, written out and checked against that prefix:

  > Agents cannot create or change scheduled work in this project: the project setting
  > `allow_agent_jobs` is off. The operator has been asked whether to enable it — question
  > `q-abc123`, on their Questions destination; the setting itself is at Environment › Settings.
  > This is a refusal, not a wait: do not poll, and do not repeat this call. If they enable it,
  > their answer will reach you as a message and you can create the job then; until then, do the
  > work directly or say in a message that you are blocked on it.

  The two dedupe variants (1.3) replace the second sentence only: *"The operator was asked and has
  not answered yet (`q-abc123`)."* and *"The operator was asked and answered: “Leave it off”. The
  setting is still off and nothing further has been opened for it — raise it with them in a message
  rather than repeating this call."*

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

- [ ] 3.1 **(R3 — the list was wrong in both directions; design D7's table.)**
  `hub/hub/mcp_server.py` — the docstrings of the five job tools that propagate this refusal
  untouched: `create_job` (`:602`), `create_loop` (`:638`), `create_flow` (`:718`), `toggle_job`
  (`:865`), `run_job` (`:871`). They state the new refusal: the setting, that the operator is asked
  once, that the answer arrives as a message, and that polling is not the protocol here. **Add no
  wait** (design D2, D7). **There is no `update_job` MCP tool** — that is the PATCH route, reached
  by `toggle_job` — and `create_job` is the one R1 and R2 both missed; it is the plainest of the six
  and the likeliest for an agent to reach for.
- [ ] 3.2 `hub/hub/api/v1/agents.py` — the same for each affected `_Operation`'s `text`/`http_note`,
  beside `archive_job`'s existing protocol note (`:1276-1289`). The two must not contradict: one
  action on that surface polls, five do not. **(R3)** The six operations are `create_job` (`:1239`),
  `toggle_job` (`:1251`), `run_job` (`:1260`), `archive_job` (`:1269`), `create_loop` (`:1293`) and
  `create_flow` (`:1328`) — this table is the independent confirmation that no `update_job` tool
  exists. `toggle_job` and `run_job` currently say only *"same allowance."*, which is exactly the
  sentence this change makes false; they need the new refusal named, not a cross-reference.
  `archive_job`'s own note keeps its 409 poll protocol untouched: the allowance refusal precedes it
  (task 2.3) and the two cannot both fire.

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
- [ ] 4.5 **(R3 — rewritten with the case that breaks R1's rule.)** A resolved record stops the
  asking, three ways, each refusing again afterwards and asserting **no second question** and a
  sentence that does not claim a fresh ask: (a) answered by **clicking** *"Leave it off"* (labels
  present); (b) answered as **typed free text** — `PATCH` with `answer="no, leave it off"` and
  **no** `labels`, which is what both UI surfaces send for a typed answer and is the case R1's
  `answer_labels` rule read as affirmative; (c) **declined** (`POST /questions/{id}/decline`).
  Case (b) is the regression test for design D13 — it fails against R1's rule and passes against
  this one.
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

- [ ] 4.10 **(R3 — pins design D14.)** Assert the record's `asker_waiting` is `true` in
  `GET /questions`, with the reason in the test's own words: `_with_asker_state` presumes an
  unknown asker is waiting (`questions.py:333-344`), so any question with no run reports `true`,
  and the conversation tray's `activeQuestionFor` sorts on that unfiltered by `blocking`
  (`lib/pendingQuestions.ts:24-46`). This is the shipped behaviour of every operator-posted
  question and is **not** changed here; the test exists so a later reader sees it was decided
  rather than missed.

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
  conversation must still read as running, not waiting. **(R3)** Open the refused agent's own
  conversation as well and look at the question tray (design D14): record what it shows and whether
  a record nobody is waiting on sitting there is acceptable to look at. That observation, not this
  prediction, is what a later round should argue with.
- [ ] 5.3 Set F376's `Status:` line to `fixed <sha>` only after 5.2. Never on the strength of 4.x.
