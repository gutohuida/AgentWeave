# Tasks — a refused capability reaches the operator

Findings: **F376 (A)** — closes it; **F378 (B)** — *not* closed here (its repair is deferred by
DIRECTION.md 2026-09-18; this change only makes the helper it will reuse).

**R1, 2026-09-18; amended by R2 and R3, 2026-09-18; amended by R4, 2026-09-19. Nothing below is
built.** Tasks carrying **(R2)**, **(R3)** or **(R4)** were changed or answered by that round; see
design.md's Rounds section for what moved and why. R3 changed two tasks that would have shipped
defects: 1.3's dedupe could not detect a typed *"leave it off"* (design **D13**), and 3.1 named an
MCP tool that does not exist while omitting one that does (**D7**, R3 table). **R4 changed four
more**: 1.1 "always raises" and does not (**D16**), the dedupe keyed on the question's prose
(**D15**), a resolved record was permanently terminal (**D17**), and 1.1's signature carried two
dead parameters, one of them the parameter D10 forbids (**D8**, R4 paragraph).

Tests run under `py -3.11`, never bare `python`. `black` needs `--target-version py311` on this
machine.

**(R4) Scope, corrected.** One migration and one schema change — `0104`, a nullable column and a
partial unique index (design **D15**). R1-R3 declared "no migration, no schema change"; that was
true of their dedupe and is not true of this one. **Still no UI change in this change** — but
`F386` is now a **prerequisite** (design **D18**), so the UI must be repaired by its own change
first.

## 0. What must exist first (R4)

- [ ] 0.1 **`F386` is fixed and merged.** `QuestionInterruptCard` is the record's only route to a
  human (design D1's R4 paragraph), and it says `{first.from_agent} is waiting` unconditionally
  (`QuestionInterruptCard.tsx:35`, `:24`). Opening a deliberately non-blocking record onto it
  violates **this change's own ADDED requirement** — *"SHALL NOT cause any surface to report that
  the refused run, its conversation or its loop is waiting on the operator"*. Do not build §1
  before this is in. Not fixed here: it is shipped, it predates this change, its declined half
  fires today with no new code, and it lives in `hub/ui/src/components/`, which this change's
  blast-radius claim says it does not touch and which F379's change owns (design **D18**).
- [ ] 0.2 **Read `F387` and decide nothing.** The same card shows one question, oldest-first, so
  this record would sit in front of every blocking question asked after it. Not a prerequisite —
  it degrades the record's usefulness, it does not make the change state something false — but a
  round that does not know about it will rediscover it. The operator has asked (2026-09-19) that
  `R5`'s manager agent be considered for the ordering; `R5` is annotated and explicitly not
  specced, and records why a nondeterministic orderer sits **on top of** a deterministic floor.
- [x] 0.3 **Migration `0104`** (head is `0103`, `0103_allowance_refusals.py`). Add
  `questions.subject_key`, `String(200)`, **nullable**, and a **partial unique index** on
  `(project_id, subject_key)` where `answered = 0 AND declined = 0 AND subject_key IS NOT NULL`
  (design **D15**). Backfill nothing — every existing row keeps `NULL` and the partial predicate
  excludes them, so the index cannot fail on existing data. `downgrade` drops both. Follow
  `.claude/rules/` migration checklist; `0104` runs against the operator's live database on their
  next restart.
- [x] 0.4 `hub/hub/db/models.py` — the column on `Question` (the class has no `__table_args__`
  today, `:927-1010`; this adds the first one) and one comment saying what the key is for: it is a
  **structural identifier, not prose**, and it exists so the question's wording can be edited
  without re-opening every resolved record (design **D15**).
- [x] 0.5 `hub/hub/api/v1/questions.py` — `ask_question_for_actor` (`:235`) takes
  `subject_key: Optional[str] = None` and writes it onto the row. Defaulted, so all existing
  callers are untouched; assert that in a test rather than by reading.

## 1. The record

- [ ] 1.1 **(R4 — signature corrected; design D8's R4 paragraph.)** New
  `hub/hub/refused_capability.py`. One coroutine, e.g.
  `refuse_for_project_state(session, *, project_id, agent, subject_key, setting, current_value,
  what_enabling_allows, where_changed)`. It always raises; the caller's `raise` is not optional.
  **`run_id` and `capability` are struck.** Nothing consumed either: D10 requires
  `created_by_run_id=None`, 1.6's body has no field for the capability, and 1.5 hardcodes the
  header. `run_id` in particular is the parameter whose obvious use D10 forbids — leaving it in the
  signature while D8's prose still told the implementer to pass the attribution *"(`project_id`,
  `agent`, `run_id`)"* meant the only thing standing between an implementer and R2's defect was a
  parenthetical in task 1.4.
- [ ] 1.2 It composes the question text: names the setting, its current value, what enabling it
  allows, and where the operator changes it (Environment › Settings). It **must not** contain the
  requesting agent's name, the run id, or the call's arguments — this is one project-level question
  and naming one caller in it is false (design D5).
  **(R4)** The text is **no longer the dedupe key** — `subject_key` is (design **D15**) — so this
  wording may be edited later without re-opening every resolved record. That was not true in
  R1-R3 and is the reason D15 exists.
  **(R3)** Interpolating the *current value* is safe: the gate's own branch is
  `not project.allow_agent_jobs` (`jobs.py:47`), so the value is false at every call that can reach
  this. The text to use, as the round wrote it out:

  > May agents schedule work in this project? The project setting `allow_agent_jobs` is **off**, so
  > the Hub refuses every attempt by an agent to create or change scheduled work — loops, flows and
  > jobs. Enabling it lets agents create and run recurring work, which commits repeated model spend
  > without asking again. You change it yourself at Environment › Settings.
- [ ] 1.3 **(R3 — rewritten; R4 — rewritten again. Designs D13, D15, D17.)** Dedupe on
  `subject_key = "capability-refusal:allow_agent_jobs"`, **never on the question's text** and
  **never on the answer's polarity**. Select every `Question` for this `project_id` with that key,
  newest first; branch on the newest and on how many exist:
  - **none** → open a new one (1.4), `subject_key` set;
  - newest is **neither answered nor declined** → open nothing, raise carrying its id and saying the
    operator has been asked and has not answered yet;
  - newest is **resolved** (answered or declined) and it is the **only** one → open a **second**
    record (design **D17**) whose text quotes what the operator said, states the setting is still
    off, and says this is the last time the Hub will ask. Raise carrying the new id.
  - newest is **resolved** and there are **two or more** → open nothing. Raise quoting what the
    operator said (or that they declined) and that the setting is still off. Do **not** claim they
    have been asked again.

  So the Hub asks **at most twice per project, ever**, for one setting.

  **Why not R1's rule.** *"`answer_labels` contains the `Leave it off` label"* **cannot fire on a
  typed answer**: both answering surfaces send `labels` only when the textarea is empty
  (`AnswerForm.tsx:33-38`, `AgentOutputPanel.tsx:934-942`), so a typed *"no, leave it off"* stores
  `answer_labels = []` (`questions.py:405`) and R1's rule would have re-asked. "Resolved means
  answered **or** declined" is `_completed_batch`'s own definition (`questions.py:90-92`, enforced
  at `:116`).

  **(R4) Why not R3's never-again either.** R3 made any resolved record terminal forever and
  dismissed the cost because F379's one-click enable *"removes the case entirely"* — F379 is not in
  this change and is not scheduled (D4: *"recorded not built"*). The likeliest mis-click in the
  design is 1.5's past-tense *"Enabled it — go ahead"* read as *"yes, do it"* by an operator who
  enables nothing; under R3's rule that click returns the project permanently to F376 with no
  mechanism to raise it again. **The bound is a row count, not a polarity test** — derivable from
  rows already written, identical whether the operator clicked, typed or declined, so it cannot
  reintroduce D13's defect one question later.

  **(R4) Simultaneous refusals no longer open two records.** R3 tolerated that and had the test
  assert sequential dedupe only, while the spec's own scenario promised it unconditionally — the
  F190 shape, green in testing and false in the case F376 measured (21 runs). The partial unique
  index (task 0.3) makes the database refuse the second insert: catch the integrity error,
  re-select, return the existing record's id, so both callers get the **same** `question_id`.
  Handle it in this task, not by hoping it does not happen.
- [ ] 1.4 **(R2)** Open through `ask_question_for_actor` (`hub/hub/api/v1/questions.py:235`) — not a
  hand-built `Question` — so the id scheme, the `question_asked` broadcast and the batch fields are
  the shipped ones. Pass `subject_key` (task 0.5). `from_agent` is the refused agent;
  **`created_by_run_id=None`**, so the row
  carries no run and therefore no `conversation_id` (design **D10** — passing the run would pin the
  refused run's conversation to `"waiting"` for the rest of its life, `conversations.py:433-441`,
  and make a drained loop report this record as what it is waiting on,
  `scheduler._pending_loop_request:400-452`). `blocking=False` (design D11).
- [ ] 1.5 **(R2)** Satisfy `QuestionCreate` (`hub/hub/schemas/questions.py:22-34`), which is
  stricter than it looks (design **D12**): `options` is **required with at least two entries** —
  *"Enabled it — go ahead"* / *"Leave it off"*, each with a `description`; `header` is **required**
  and at most 64 characters, naming the capability; `multi_select` is **required** and is `False`.
  A call omitting any of the three fails validation, so there is no optionless form of this
  question. **(R3)** The descriptions must be honest about D4 — answering does not flip the
  setting: *"Turn the setting on yourself at Environment › Settings; agents may then schedule
  recurring work here."* / *"Agents keep being refused."* `header`: `"Scheduled work"`.
  **(R4)** R3's second description ended *"Nothing is asked again for this project"*, which D17
  makes false for the first record — the Hub asks once more. Say nothing about future asking on
  the first record; say it on the second, whose options are *"I'll enable it now"* /
  *"Leave it off — stop asking"* and whose text states outright that it is the last time.
  **(R4)** Two more fields are required and D12 missed them: `from_agent` and `question`
  (`schemas/questions.py:23-24`). `ask_question_for_actor` **discards** `body.from_agent` in favour
  of its own keyword (`questions.py:239`, `:257`) — pass the refused agent to both so they agree,
  and do not spend a cycle deciding what the discarded one should be.
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

  The dedupe variants (1.3) replace the second sentence only: *"The operator was asked and has
  not answered yet (`q-abc123`)."*; *"The operator was asked and answered: “Leave it off”. They
  have been asked once more (`q-def456`) — this is the last time."*; and, once the bound is spent,
  *"The operator was asked twice and answered: “Leave it off”. The setting is still off and nothing
  further will be opened for it — raise it with them in a message rather than repeating this call."*

- [ ] 1.7 **(R4 — new; design D16.)** **Opening the record is best-effort; the 403 is not.** Task
  1.1 says the helper "always raises" and as written it does not:
  `ask_question_for_actor` does `session.add` → `await session.commit()` → `await
  session.refresh()` (`questions.py:268-270`) and `persist_event` commits again
  (`hub/hub/utils.py:70-72`). Any of those can raise — SQLite `database is locked` is the live
  case, in exactly the concurrency F376 measured — and the route then returns **500**, so the agent
  loses the 403 *and* the honest sentence. That is worse than the defect being repaired.

  ```
  try:     question_id = await open_record(...)
  except Exception:
           log it, with the project and the key
           question_id = None
  raise HTTPException(403, detail=...)      # unconditional, either way
  ```

  With no record the body omits `question_id` and the sentence becomes: *"Agents cannot create or
  change scheduled work in this project: the project setting `allow_agent_jobs` is off. The
  operator could not be asked automatically — tell them it needs enabling at Environment ›
  Settings. This is a refusal, not a wait: do not poll, and do not repeat this call."* That is
  alternative **(b)** from the proposal, which is insufficient as the whole design and exactly
  right as the failure path. No wrapping is needed around the SSE broadcast: `sse.py:86-101`
  swallows `QueueFull` and cannot raise.

## 2. The gate

- [ ] 2.1 **(R4 — the range was wrong.)** `hub/hub/api/v1/jobs.py:46-51` — replace **only** the
  `allow_agent_jobs` branch (`:46` fetches the project, `:47-51` is the branch) with a call to 1.1.
  Leave the early return for operator calls (`:39`), the incomplete-attribution refusal (`:41-42`)
  and the **stale-attribution refusal (`:44-45`)** exactly as they are; their order is load-bearing
  (design D9.2). R1-R3 wrote this range as `:44-51`, which names the stale-attribution check — the
  one line the task tells the implementer *not* to touch — inside the range it tells them to
  replace.
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
- [ ] 4.4 Dedupe, **sequential**: two refusals one after another, one question, same id in both
  bodies.
- [ ] 4.4b **(R4 — new; design D15.)** Dedupe, **concurrent**: two refusals issued together (two
  sessions, both past the existence check before either commits), asserting **one** question row
  for the key and the **same** `question_id` in both 403 bodies. R3 tolerated two rows here and had
  the test assert the sequential case only, while the spec promised the unconditional one — green
  in testing, false in the case F376 measured. If this test cannot be made to interleave reliably,
  assert the integrity-error branch directly instead and say so in the test's own words; do not
  delete the case.
- [ ] 4.5 **(R3 — rewritten; R4 — the assertion flipped for the first resolution.)** A resolved
  record is superseded **exactly once** (design **D17**), three ways: (a) answered by **clicking**
  *"Leave it off"* (labels present); (b) answered as **typed free text** — `PATCH` with
  `answer="no, leave it off"` and **no** `labels`, which is what both UI surfaces send for a typed
  answer and is the case R1's `answer_labels` rule read as affirmative; (c) **declined**
  (`POST /questions/{id}/decline`). For each: refuse again and assert a **second** record opens,
  quoting the operator's answer and saying it is the last ask; then resolve that one, refuse a
  third time, and assert **no third record** and a sentence that does not claim a fresh ask. All
  three paths must behave identically — that is what "the bound is a count, not a polarity test"
  means, and case (b) is the regression test for design D13.
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
- [ ] 4.11 **(R4 — new; design D16.)** **The refusal survives the record failing to open.** Make
  the record's commit raise (patch `ask_question_for_actor`, or hold a write lock on the table) and
  assert the route still returns **403**, not 500; that the body carries `code`, `setting` and
  `current_value` but **no** `question_id`; and that the sentence tells the agent to raise it with
  the operator rather than claiming they were asked. This is the path `CLAUDE.md`'s *"ask what each
  route returns when the function it calls raises"* names, and no test in R1-R3 covered it.
- [x] 4.12 **(R4 — new; design D15.)** `ask_question_for_actor`'s new `subject_key` keyword
  defaults to `None` and **every existing caller is unaffected** — assert an operator-posted
  question (`POST /questions`) still writes `subject_key IS NULL`, and that the partial unique
  index does not constrain NULL-keyed rows (two open operator questions on one project coexist).

## 5. Drive it

- [ ] 5.1 Reproduce D-1's harness against the fix on the trial Hub `:8010`, from source — a fresh
  project, one `claude-haiku-4-5-20251001` agent, one real turn calling `create_flow`. Assert: one
  question visible on the operator's Questions destination, the agent's transcript carrying the new
  sentence, `permission_requests` still empty.
- [ ] 5.2 Then answer it as the operator, with the setting enabled by hand, and **record what the
  agent does** when it wakes. **This is the task that proves the change**; a green suite without it
  proves only that the code runs.
  **(R4) It no longer asserts "its retry succeeds", and the reason is a limit this change cannot
  repair.** What the woken agent receives is `_batch_delivery_text`'s rendering — the question and
  the answer, nothing else (`questions.py:217-220`) — and task 1.2 **forbids** the question from
  naming the call's arguments. So the agent wakes holding a decision with no record of what it was
  trying to schedule, which for a `session_mode="new"` job or loop firing is all the context it
  has. Nothing in what it receives tells it to retry anything. `_batch_delivery_text` is shipped
  code outside this change's blast radius, so the drive **measures** the behaviour rather than
  asserting a prediction; if the agent does not pick the work back up, that is a finding to file,
  not a failure of this task.
  **(R2)** While the record is open and before answering, look at the
  Questions destination and at the conversation list: the question must render in the **Unanswered**
  section rather than under the red *"Blocking"* banner (design D11), and the refused run's
  conversation must still read as running, not waiting. **(R3)** Open the refused agent's own
  conversation as well and look at the question tray (design D14): record what it shows and whether
  a record nobody is waiting on sitting there is acceptable to look at. That observation, not this
  prediction, is what a later round should argue with.
- [ ] 5.3 Set F376's `Status:` line to `fixed <sha>` only after 5.2. Never on the strength of 4.x.
