# Design — a refused capability reaches the operator

**R1, 2026-09-18.** Every file:line below was read in this round. F376's *diagnosis* is not
re-derived here — DIRECTION.md 2026-09-18 forbids that and the measurements stand
(`scripts/drive/FINDINGS.md`, F376 and the D-1 addendum after F380). What is derived here is the
**repair**.

## Round 1 — the code as it is

- `hub/hub/api/v1/jobs.py:32-51` — `_require_agent_job_allowance`. Order matters and does not
  change: `agent is None and run_id is None` returns (an **operator** call carries neither header,
  so nothing below touches the operator's own path); incomplete attribution → 403; stale attribution
  → 403; then `project.allow_agent_jobs` false → 403 *"Scheduled work from agents requires operator
  approval or an enabled allowance"*. **Only that last branch is in scope.**
- Callers of the gate: `:568`, `:847`, `:1163`, `:1294` — `create_loop`/`create_flow` (POST /jobs),
  `update_job`, `archive_job`, `toggle_job`/`run_job`. One branch repairs all of them.
- `hub/hub/db/models.py:79` — `allow_agent_jobs`, `default=False, server_default="0"`.
- Its **only** writer anywhere in `hub/hub` is `PATCH /queue/settings`
  (`hub/hub/api/v1/inbound_queue.py:98`), operator-authenticated. **No agent-facing route or MCP
  tool can set it** — checked by grepping every `allow_agent_jobs` occurrence outside migrations.
  This is the fact that decides D4.
- `hub/ui/src/components/environment/ProjectSettingsPanel.tsx:146` — the only control.

## D1 — the record is a question of record, not a permission request

**Decision.** The refusal opens a row in `questions` through `ask_question_for_actor`
(`hub/hub/api/v1/questions.py:234`), not a `PermissionRequest`.

`permission_requests` looks like the obvious home — the sentence says *"approval"*, and
`hub/hub/operator_direction.py` already turns a route's refusal into a card, an SSE event and a
409 the caller polls. It is the wrong home, and the reason is in that module's own design notes and
in the sweep code:

| | `permission_requests` | `questions` |
|---|---|---|
| Lifetime | **expires**: the adapter waits `AW_DECISION_TIMEOUT` (120s, `mcp_server.py:927`) then `POST`s `/expire` (`:1512`); the run's end sweeps anything still pending (`permission_requests.py:22`, joined to the run-end transaction) | never expired; `answered` is a boolean nobody sweeps |
| Where the operator sees it | inside one agent's output panel (`AgentOutputPanel.tsx:1026`) | a top-level destination (`App.tsx:382` → `QuestionsPanel`) |
| A late answer | cannot exist — the row is gone | **queued and the agent woken** (`questions.py:121` `deliver_batch_if_complete`, `:179` the wake tail, `turn_scheduler.schedule_agent`) — the whole point of the archived change `a-late-answer-is-delivered` |

F376's harm was *the operator came back to nothing*. A record that cannot outlive the turn cannot
repair that, so the decisive property is lifetime, and only one of the two rows has it.

**Read and confirmed in this round, because the whole design rests on it.** `answer_question`
(`questions.py:433-441`) queues the answer whenever the asker is not still waiting, and
`_asker_still_waiting` (`:48`) is true only for a **blocking** question whose wait has not ended and
whose run still lives. So a **non-blocking** question — which is what this change opens — always
takes the queued-and-woken path; the code says so in as many words: *"A non-blocking question still
needs this, and so does a blocking one nobody is waiting on any more: nothing is there to receive
it."* `deliver_batch_if_complete` itself has no waiting check at all (`:121-169`), and
`announce_queued_answer` (`:173`) ends in `schedule_agent`, whose wake is explicitly documented as
safe for an agent whose run is still live.

**And the delivered entry enters at `hop_depth=0`** (`questions.py:154`). That is not incidental to
F376: the finding measured the whole build running as one chain off the operator's 17:36 message,
hand-driven messages inheriting `+1`, and the chain dying at hop 7 against a budget of 6. An answer
that resumes the agent at depth zero is the same reset a flow firing gets
(`scheduler.py:3111`, `:3443`) and the opposite of what a relayed message would get.

**This is not a criticism of `operator_direction.py`.** Turn-scoped is right for *"may this agent
run this command now"*: an answer that arrives after the turn has nothing to authorise. It is wrong
for *"may agents schedule work in this project"*, which is true or false independently of any turn.

## D2 — the agent does not wait, and that is the design

DIRECTION.md said the answer to *what happens to the agent's turn while it waits* decides whether
raising a request is worth doing at all. The answer here: **there is no wait.**

- The route returns **403** with a typed body — `code: "project_setting_blocks_capability"`, the
  setting's name, its current value, the `question_id`, and one sentence saying the operator has
  been asked and will answer into the agent's queue.
- **403, not 409.** 409 + `operator_direction_required` is the *poll-and-retry* protocol
  (`operator_direction.py`, `mcp_server.py:845`), and it presumes an answer inside the turn. Using
  it here would tell an agent to poll a decision that may arrive after its run has ended, i.e. to
  block until a timeout that changes nothing. The refusal is a genuine refusal *now*.
- The agent is told what to do instead: do other work, or end the turn; the answer arrives as input.
  Nothing requires it to ask its own question about the same setting — and if it does, the operator
  gets two cards, which D5 bounds for the Hub's own copy but cannot prevent for the agent's.
- **No new adapter wait.** `archive_job` wraps its call in `_await_decision`
  (`mcp_server.py:840-861`); nothing analogous is added to the five job tools here. This keeps the
  adapter thin, which is a requirement rather than a preference
  (`openspec/specs/agent-capability-plane/spec.md:107`, *"MUST NOT hold a governance or waiting rule
  that the contract does not itself impose on every caller"*), and it means an HTTP-only agent gets
  the identical behaviour with no protocol of its own.

## D3 — what the operator is actually being asked

`openspec/specs/agent-capability-plane/spec.md:915-926` already states the plane's two-class theory:
scheduled jobs need a standing allowance **because a job invokes a model repeatedly, so an agent
creating one commits spend the operator did not authorise per occurrence**; tasks, messages,
questions and evidence need none.

So per-call approval of a `create_flow` is not a smaller version of the allowance — it is a
*different and larger* grant, and the shipped permission card (`tool_name`, `tool_input`) says
nothing about recurring spend. The question the Hub must put is the one the setting represents:
**may agents schedule work in this project?** That is also the question the operator can answer
without reading the call's arguments, which matters because they were leaving.

## D4 — the answer does not flip the setting, deliberately

`allow_agent_jobs` has exactly one writer and it is operator-authenticated (D1's list). Answering
the question therefore does **not** enable the allowance; the question names where the operator
does that (Environment › Settings, `ProjectSettingsPanel.tsx:146`) and its options are
*"Enabled it — go ahead"* / *"Leave it off"*.

Rejected: making the answer apply the setting. It needs either a new column on `questions` carrying
an effect (a migration, and a general effect-hook on an inbox that deliberately has none) or a new
`capability_requests` table with its own decide route and its own card — a second pending-decision
surface for the operator to learn, which `operator_direction.py` explicitly refused to build for the
same reason. Worse, a toggle inside the card would be **a second control for one setting**, and
`the-controls-that-gate-collaboration-are-visible` (F379, DIRECTION.md's item 2) is the change that
owns that surface. Two controls for one setting is how they diverge.

**Follow-up, recorded not built:** one-click enable belongs in F379's change. This change is what
makes the refusal reach a person; that one is what makes answering it one click.

## D5 — one card per project, and a no is a no

- **Dedupe.** Before opening, look for a question for this project, with this change's stable
  question text, where `answered` is false. If one exists, open nothing and return its id. F376's
  run made 21 runs and 20 fallback messages; without this the inbox gets one card per attempt.
- The text therefore **must not name the requesting agent** (the row's `from_agent` already does) or
  the call's arguments, or the dedupe key varies and the cards multiply.
- **A negative answer stops the asking.** Re-asking after a no is the failure
  `operator_direction.py`'s denied branch already names — *"this is an answer rather than a timeout:
  do not ask again for the same thing."* **How that is detected is superseded by D13 (R3):** R1
  keyed it on `answer_labels` containing the *"Leave it off"* label, and that column is empty for
  every typed answer, so the rule as written re-asked after an operator typed *"no, leave it off"*.
  D13 replaces it with a rule that never reads the answer's polarity.
- **Known limit, stated not hidden:** the answer wakes `from_agent`, the agent that was refused
  first. A second agent refused while the card was open is not woken by the answer; its next call
  simply succeeds, because by then the gate passes. Recorded in the spec delta as a scenario so a
  later round cannot mistake it for an oversight.

## D6 — the refusal's own wording

Today: *"Scheduled work from agents requires operator approval or an enabled allowance."* It is
false in both halves — no approval is requested, and *"an enabled allowance"* names nothing the
agent can find. Replaced by a sentence that names the setting, its value, that the operator has been
asked, and that an answer will arrive as a message. `mcp_server._readable_detail`
(`mcp_server.py:124`) surfaces `message` out of a dict detail, so an agent that only ever sees the
sentence still sees the whole protocol — the same reason `operator_direction._direction_required`
carries both the sentence and the id.

**R3 — what the agent actually reads, end to end, and one consequence.** `_hub_request` builds
`HubAPIError(exc.code, _readable_detail(body), method, path, structured)` (`mcp_server.py:186-196`)
and `HubAPIError.__str__` is `f"Hub rejected {method} {path} ({status}): {detail}"` (`:103-105`);
FastMCP reports that as the tool error, which is how F376's sentence reached the transcript
verbatim (*"Error calling tool 'request_agent': Hub rejected POST /agents/request (400): …"*, the
F378 measurement). So the sentence is prefixed, never truncated, and must read correctly after
`Hub rejected POST /jobs (403):`.

Executed rather than reasoned about — constructing the refusal this change will raise:

```
str(HubAPIError(403, _readable_detail(detail), "POST", "/jobs", detail))
  -> Hub rejected POST /jobs (403): Agents cannot create or change scheduled work in this
     project: the project setting `allow_agent_jobs` is off. ... (q-abc123)
e.data["question_id"] -> q-abc123
```

The consequence: **the `question_id` in `HubAPIError.data` does not reach the model.** `.data` is
read by exactly one place on this surface — `archive_job`, and only for
`code == "operator_direction_required"` (`mcp_server.py:843-848`); the other five job tools return
`_job_effect(...)` and let the error propagate untouched. Anything the *agent* must know therefore
has to be in `message`, so the record's id goes into the sentence as well as into the body. Task
4.8's `.data` assertion stands — it is what a future adapter would read — but nothing in this
change may depend on it reaching a turn.

## D7 — the rule is the contract's

The record is opened by the **route**, inside the session the gate already holds. The MCP adapter
changes only its prose: the job tools' docstrings, and each `_Operation`'s `http_note` in
`hub/hub/api/v1/agents.py` (the same place `archive_job`'s protocol is described, `:1276-1289`).
Behaviour is identical on both access paths because only one of them holds any of it.

**R3 — which tools those actually are, because R1 and R2 both named one that does not exist.** The
gate has four **route** call sites (`create_job` POST `/jobs`, `update_job` PATCH
`/jobs/{job_id}`, `archive_job`, `run_job` — `jobs.py:568`, `:847`, `:1163`, `:1294`), and **six**
MCP tools reach them:

| tool | `mcp_server.py` | route it reaches |
|---|---|---|
| `create_job` | `:602` | POST `/jobs` |
| `create_loop` | `:638` | POST `/jobs` |
| `create_flow` | `:718` | POST `/jobs` |
| `toggle_job` | `:865` | PATCH `/jobs/{job_id}` (the `update_job` route) |
| `run_job` | `:871` | POST `/jobs/{job_id}/run` |
| `archive_job` | `:818` | POST `/jobs/{job_id}/archive` |

**There is no `update_job` MCP tool** — it is a route name, reached by `toggle_job` — and
`create_job`, which R1's and R2's task 3.1 never named, is the oldest and plainest of the six.
Confirmed independently of `mcp_server.py` by the contract surface, whose `_Operation` table lists
exactly these six and no `update_job` (`agents.py:1239`, `:1251`, `:1260`, `:1269`, `:1293`,
`:1328`). Five of the six propagate the refusal untouched through `_job_effect` → `_hub_request`;
`archive_job` catches `HubAPIError` and re-raises everything that is not
`operator_direction_required` with a `permission_request_id`, its own comment naming *"the allowance
is off"* among them (`:843-848`). So task 3.1's assumption that the error paths do not differ holds
— but its list of tools did not.

## D8 — generality, without widening the blast radius

`hub/hub/refused_capability.py` takes what the sentence and the card both need: the setting's name,
its current value, what enabling it would allow, where the operator changes it, and the attribution
(`project_id`, `agent`, `run_id`). F378 — `request_agent` refused because `project_sessions` holds
zero rows on every project on the Hub — is the same shape and is the intended second caller, but
**it is not called from here in this change**; DIRECTION.md defers that repair (and *retire* is a
live option for it). The requirement is written for the shape; the scenarios pin the one caller.

**R3 narrows the reuse claim, which was untested.** F378's refusal fires where
`templates.get(body.template)` is not a dict, with `templates` read from
`_get_session_data(project_id, session)` — the `project_sessions` table (`agents.py:2053-2059`).
That is **not a setting with a value the operator changes**, and three of this signature's
parameters have no truthful value there: `setting` (the state is the absence of rows in a table),
`current_value` (nothing to print), and above all `where_changed` — *no surface writes that table*
is the finding itself. Calling this helper there would produce a refusal that points the agent and
the operator at a control that does not exist, which is the same class of lie F376 is about.

So what F378 can reuse is the **shape** — a durable record, an honest refusal, dedupe on stable text
— and not necessarily this signature. Its repair needs a writer for approved templates, or the
decision to retire the tool, *before* any refusal copy helps. This change must not be read as having
pre-built F378's helper; it has built one caller's, in a shape the second can be measured against
when its own round comes.

## D9 — two traps a later round must not fall into

1. **Do not reuse the "unasked question" surface.** `openspec/specs/agent-capability-plane/spec.md:281`
   still requires that a turn ending on an unasked question be surfaced to the operator. That
   detector was **dropped in migration `0082` (2026-08-20)** and `CLAUDE.md` forbids reintroducing
   it. The spec text is stale; this change neither uses nor repairs it. Flagged here so a round does
   not propose building on a mechanism that no longer exists.
2. **Do not assume the gate fires for the operator.** It returns early when both headers are absent
   (`jobs.py:39`), which is why D-1's reproduction needed a real bound agent turn rather than a
   plain API call. A test that calls the route without agent attribution proves nothing about this
   change (the F190 shape: green for a month while the behaviour could not fire).

## D10 - the record carries no conversation, and that is a decision R1 did not make (R2)

`ask_question_for_actor` stamps `conversation_id` from the asking run
(`questions.py:255` -> `conversations.conversation_id_for_run:354`, which returns `None` for a null
run). R1's task 1.4 said to pass the refused agent's `run_id`. **R2 reverses that: pass
`created_by_run_id=None`, so the row carries no run and no conversation.**

Three readers join a question to work through `conversation_id`, none of them mentioned in R1, and
two of them would then report something untrue about a run that is not waiting:

1. **The conversation attention rail** (`conversations.py:433-441`). Its query is
   `answered IS FALSE AND wait_ended_at IS NULL` - **no `blocking` filter and no `declined`
   filter** - and `"waiting"` deliberately outranks `"running"`. Nothing would ever clear ours: the
   only writer of `wait_ended_at` besides the tool's own report is the run-end sweep, whose
   candidate query filters `blocking IS TRUE` (`run_task_binding.py:718-722`). So a loop
   conversation would read *"waiting on the operator"* for its whole life while its run kept
   working. That file's own comment names this as the defect to avoid - *"the rail would say
   'waiting on the operator' ... about a run that is running and waiting for nothing. That is F14's
   own defect, inverted"*.
2. **The loop's pending-request report** (`scheduler._pending_loop_request:400-452`). When a loop's
   queue drains, the most recent unanswered `Question` on the **prior firing's conversation** is
   reported as `kind: "question"` - what the loop was waiting on. Again unfiltered by `blocking`.
   An agent refused `create_flow` inside a loop that has plenty of other work would make that loop
   report our record as the thing it is waiting for.
3. **The per-job open-question count** (`jobs.py:399-410`), which the operator reads as *"these
   still need me"*. This one our record would answer honestly, and losing it is the cost of the
   decision - stated, not hidden.

The trade is one-sided because of what D1 already argued: the record's value is that it is
**independent of the turn**. Stamping the turn's conversation onto it re-couples it to the turn
through three readers, two of which then lie. `from_agent` is the only attribution delivery needs -
`deliver_batch_if_complete` resolves the conversation from `latest_open_conversation(project,
from_agent)` and opens one if there is none (`questions.py:145-151`), and `announce_queued_answer`
wakes by agent name (`:203`). And a question with a null run and conversation is **the shipped
shape** of one asked through the operator route (`POST /questions` passes `created_by_run_id=None`,
`questions.py:293`), not a new one.

Checked for None-safety along the whole answer path, because this is the round that changed it:
`_asking_run_has_ended` returns `False` on a null run (`:42`) and is never reached anyway -
`_asker_still_waiting` short-circuits on `blocking` (`:70`); `release_block_for_question` returns
`None` on a null `blocked_task_id` (`run_task_binding.py:833`); nothing in
`PATCH /questions/{id}` reads `question.conversation_id`.

## D11 - what `blocking=False` actually costs, measured in the panel (R2)

R1 chose `blocking=False` for its delivery behaviour and left the operator-side cost as an open
question for this round. Read: `QuestionsPanel.tsx:150-151` partitions on
`question.blocking && stillWaiting(question)`. Ours therefore renders in the ordinary **Unanswered**
section (`:184-194`) rather than the red *"Blocking - agents are waiting for your answer"* banner,
with no urgency timer (`:43-48`, which is computed only for a blocking row) and the agent name in
the default colour rather than red. It is a full row: same `QuestionRow`, same answer form, same
options.

**That is the correct rendering, not a concession.** No agent is waiting; a red banner asserting one
is would be false, and the banner's own comment says partitioning on both facts is what keeps it
true of every row inside it. `wait_expires_at` is also NULL for a non-blocking question by
construction (the Hub stamps it for blocking questions only, `db/models.py:998-1000`), so nothing
renders a deadline that does not exist.

## D12 - the schema the record must satisfy (R2)

`QuestionCreate` (`hub/hub/schemas/questions.py:22-34`) is stricter than R1 assumed, and an
implementer passing R1's task 1.4 literally would fail validation:

- `options: List[QuestionOption] = Field(min_length=2, max_length=8)` - **required, at least two.**
  D4's *"Enabled it - go ahead"* / *"Leave it off"* satisfies it exactly; there is no optionless
  form of this question.
- `header: str = Field(min_length=1, max_length=64)` - **required**, and no longer than 64
  characters.
- `multi_select: bool` - **required**, no default. `False` here.
- `question: str` at most 10000; option `label` at most 200, `description` at most 500.

The dedupe key is the question text (D5), so those bounds are bounds on the key: the text must stay
under 10000 characters with the setting's value interpolated, which it trivially does, and must not
interpolate anything that varies.

## D13 - the dedupe does not read the answer's polarity, because it cannot (R3)

R1's negative branch, kept by R2, asked whether the resolved question's `answer_labels` contained
the *"Leave it off"* label. **Measured in both surfaces that answer a question, `answer_labels` is
empty for every typed answer:**

- `AnswerForm.tsx:33-38` (the Questions destination) sends `labels` **only** when the textarea is
  empty — `writtenAnswer ? {id, answer} : {id, answer, labels}` — and typing clears any selection
  (`:84-87`).
- `AgentOutputPanel.tsx:934-942` (the conversation composer) does the same thing in its own words:
  `const labels = typed ? [] : (chosenLabels ?? questionSelection)`.
- `answer_question` stores exactly what arrived: `question.answer_labels = list(body.labels or [])`
  (`questions.py:405`).

So the column is non-empty **only** on the click path, and on that path `answer` is already the
labels joined — the labels carry nothing the text does not. An operator who types *"no, leave it
off, it's too expensive"* lands on `answered=True, answer_labels=[]`, which R1's rule reads as
**affirmative** and re-asks on the next refusal. The failure mode of the rule meant to stop the
nagging was to nag, and free text is not an edge case: the model's own comment calls it the
product's guarantee — *"The operator is never **confined** to these — a typed answer is always
allowed"* (`db/models.py:940-941`).

**Run, not read** (`py -3.11`, against the installed schemas):

```
QuestionAnswer(answer="no, leave it off, too expensive")   -> labels = []
QuestionAnswer(answer="Leave it off", labels=["Leave it off"]) -> labels = ['Leave it off']
```

The first is the exact payload both surfaces send for a typed answer, and
`answer_labels = list(body.labels or [])` makes it `[]` in the row. R1's rule tested that list for a
label it can never contain on that path.

**Decision. Do not classify the answer at all.** The gate runs only when the setting is false
(`jobs.py:47`, `not project.allow_agent_jobs`), so a **resolved** identical question plus a firing
gate is already the whole fact: the operator has seen these exact words and the setting is still
off. Two branches, no prose read:

1. the most recent identical question is **neither answered nor declined** → open nothing, raise
   carrying its id and saying the operator has been asked and has not answered yet;
2. it is **answered or declined** → open nothing, raise quoting what the operator actually said (or
   that they declined it), and that the setting is still off.

"Resolved means answered **or** declined" is the definition `_completed_batch` already uses
(`questions.py:93-95`), not a new one.

**Why this is better rather than merely simpler.** The Hub's guess at an answer's polarity is
strictly less informative than the answer, and a wrong guess is invisible — it produces a card the
operator has to dismiss again. Quoting the operator's own sentence back to the agent tells it more
than *"the operator said no"* ever could, and it cannot be wrong.

**The cost, stated.** An operator who answers *"Enabled it — go ahead"* and then does not flip the
toggle is never re-asked. The refusal then tells the agent exactly that, in their words, and the
agent can raise it in a message; D4's follow-up (one-click enable, F379's change) removes the case
entirely. The alternative — re-asking on an answer the Hub judged affirmative — buys one nudge and
pays for it with a rule that re-asks after every typed no.

**Two more things this round measured about the dedupe query.**

- **It has no index and does not need one.** `Question` has no `__table_args__` at all
  (`db/models.py:927-1010`); the table's indexes are on `answered`, `batch_id`,
  `created_by_run_id`, `conversation_id` and `blocked_task_id` — **none on `project_id` and none on
  `question`** (read from `sqlite_master` on the trial profile database, which holds 32 questions,
  all on one project). The dedupe is a scan bounded by a project's questions, and the panel's own
  list route already reads that table per project on every SSE tick. No migration, no index.
- **Two simultaneous refusals open two records, and that is tolerated.** Two runs refused in the
  same instant both find nothing and both insert. Bounded: the next refusal dedupes onto the most
  recent, so it is two rows rather than a stream, and the second is cosmetic. Closing it needs a
  unique index on `(project_id, question)` — a migration this change has decided not to make (D4) —
  so it is stated here and the test asserts sequential dedupe only.

## D14 - a fourth reader D10 cannot fix, and why it is still acceptable (R3)

D10 unbound the record from the refused run's **conversation**. One reader keys on `from_agent`
instead, so it is untouched by that: `activeQuestionFor` (`hub/ui/src/lib/pendingQuestions.ts:24-46`)
picks the question shown in an agent's conversation tray by `from_agent === agent && !answered &&
!declined` — **no `blocking` filter** — and sorts `asker_waiting !== false` first (`:38`), then
`batch_index`, then oldest `created_at`.

Our record's `asker_waiting` is computed as `wait_ended_at is None and created_by_run_id not in
ended` (`questions.py:333-344`). With a NULL run that is **always `True`** — the module's own
documented rule, *"Unknown asker → presumed waiting"*. So the record sorts with the genuine waiters,
and being older it can be the one the tray shows while that agent is really blocked on a later
question.

**Not repaired here, and the reason is what makes it acceptable:** this is the behaviour of *every*
question with no run, including every one posted through the operator route
(`questions.py:293` passes `created_by_run_id=None`). The record is not a new shape, so it inherits
an existing quirk rather than introducing one. Narrowing `asker_waiting` to read `blocking` would
change that whole shipped class from inside one refusal's change, and `_with_asker_state`'s comment
says in as many words that it deliberately does not read `blocking` — *"that is
`_asker_still_waiting`'s concern, not this field's"*.

Pinned rather than left implicit: task 4.10 asserts `asker_waiting` is `true` on the record, so a
later reader sees it was decided, and task 5.2's drive looks at the refused agent's conversation
tray as well as the Questions destination — so the round after the drive argues with a measurement
instead of this prediction.

## Rounds

- **R1, 2026-09-18** - proposal and design. Rejected (a) on lifetime and on what the operator would
  be approving; adopted (b)'s honest sentence as half; chose the question of record.
- **R2, 2026-09-18** - an independent re-derivation against `jobs.py`, `questions.py`,
  `permission_requests.py`, `run_task_binding.py`, `scheduler.py`, `conversations.py`,
  `mcp_server.py`, `db/models.py`, `schemas/questions.py` and `QuestionsPanel.tsx`. **The core
  decision survives; one of its details does not.**
  - **Confirmed, by re-reading rather than by quoting R1.** *Nothing sweeps a non-blocking
    question*: the only run-end sweep's candidate query filters `created_by_run_id == run.id AND
    blocking IS TRUE` (`run_task_binding.py:715-722`), there is no `DELETE` against `questions`
    anywhere in `hub/hub`, and `record_wait_ended` is an `UPDATE` of a timestamp, not a removal.
    *(a)'s row really is turn-scoped*: `expire_pending_for_run` is an `UPDATE ... SET status =
    'expired'` whose caller commits it into the run-end transaction
    (`permission_requests.py:22-38`), and `OPERATOR_DECISION_TIMEOUT` is 120s
    (`mcp_server.py:927`) with `_report_wait_ended` posting `/expire` (`:1512`). *A dict detail
    reaches an MCP agent as a sentence*: `_readable_detail` returns `detail["message"]` when it is
    a non-empty string (`mcp_server.py:124-140`) and `_hub_request` uses it for
    `HubAPIError.detail` at `:195`, while `HubAPIError` also keeps the structured body in `.data`
    (`:92-101`) - so the `question_id` survives for an adapter without prose-parsing. *Committing
    inside the gate is safe*: at all four call sites (`jobs.py:568`, `:847`, `:1163`, `:1294`) the
    gate is the **first statement** after `project_id, _ = project`, so nothing of the route's own
    is pending in the session when `ask_question_for_actor` commits.
  - **Answered, where R1 left a question.** Task 2.3's interaction is settled by ordering: in
    `archive_job` the allowance gate runs at `:1163` and `require_operator_direction` only at
    `:1182`, inside the `agent_identity is not None` branch - so an agent with the allowance off
    raises out of the gate and never reaches the 409 path, and no permission request is opened.
    That ordering is load-bearing and must not be reversed.
  - **Changed.** The record must carry **no run and no conversation** (new **D10**) - R1's task 1.4
    had it carry both, which would pin the refused run's conversation to `"waiting"` for the rest
    of its life and make a loop report the record as what it is waiting on. `blocking=False`'s cost
    is now measured rather than deferred (**D11**), and `QuestionCreate`'s mandatory `options`
    (at least 2), `header` and `multi_select` are recorded (**D12**) - R1's task 1.4 as written
    would not have validated.
- **R3, 2026-09-18** - a second independent re-derivation, against `mcp_server.py`,
  `api/v1/jobs.py`, `api/v1/questions.py`, `api/v1/agents.py`, `schemas/questions.py`,
  `db/models.py`, `conversations.py`, `AnswerForm.tsx`, `AgentOutputPanel.tsx`,
  `lib/pendingQuestions.ts` and the trial profile database. **It did not change the decision, and it
  changed four things inside it** - none of them reachable by re-reading R1 or R2, and two of them
  defects an implementer would have shipped.
  - **Changed - the dedupe's negative branch could not fire** (new **D13**). Both surfaces that
    answer a question send `labels` only when nothing was typed (`AnswerForm.tsx:33-38`,
    `AgentOutputPanel.tsx:934-942`), so `answer_labels` is empty for every typed answer and R1's
    rule read a typed *"no, leave it off"* as affirmative and re-asked. The rule meant to stop the
    nagging nagged. Replaced by one that never reads the answer's polarity: a **resolved** record
    (answered *or* declined) stops the asking and the refusal quotes what the operator actually
    said. The gate only runs while the setting is false, so nothing is lost by not interpreting.
  - **Changed - the tool set was wrong in both directions** (**D7**, R3 table). There is no
    `update_job` MCP tool; there are six job tools and `create_job` (`mcp_server.py:602`) is one
    R1 and R2 both omitted. Cross-checked against `agents.py`'s `_Operation` table. Tasks 3.1 and
    3.2 corrected.
  - **Changed - D8's reuse claim narrowed.** F378's blocking state is an empty table with no
    writer, so `setting`, `current_value` and `where_changed` have no truthful value there; the
    reusable part is the shape, not this signature.
  - **Changed - what reaches the model** (**D6**, R3 paragraph). `.data` is read by exactly one
    place on this surface (`archive_job`, and only for `operator_direction_required`), so the
    record's id must be in the sentence; and the sentence is always prefixed with
    `Hub rejected POST /jobs (403):`, which is how F376's own sentence reached its transcript.
  - **Added, as measured costs rather than repairs.** A fourth reader keys on `from_agent` and so
    survives D10 (new **D14**): the conversation tray's `activeQuestionFor` is unfiltered by
    `blocking` and sorts presumed-waiting first, and `asker_waiting` is a constant `true` for any
    question with no run - the shipped behaviour of every operator-posted question, pinned by task
    4.10 and looked at in task 5.2's drive rather than changed from inside this change. The dedupe
    query has no index and needs none (measured: 32 questions, no index on `project_id` or
    `question`), and two simultaneous refusals open two records - bounded, cosmetic, and closable
    only by a migration this change has decided not to make (**D13**).
  - **Confirmed, by reading rather than by quoting R2.** D10 is safe at delivery for a reason R2
    did not state: `deliver_batch_if_complete` never reads `question.conversation_id` at all - it
    resolves `latest_open_conversation(project, from_agent)` and opens an operator-origin
    conversation when there is none (`questions.py:145-151`), naming it from the question's first
    120 characters (`conversations.py:139-149`, `title_from_message:23-40`,
    `CONVERSATION_TITLE_MAX_LENGTH = 120`), a no-op on a thread that already has a title. So the
    answer reaches the same thread whether or not the run was stamped, and the fresh-thread case is
    the shipped behaviour of any late answer with no open thread. Also confirmed: the gate is the
    first statement after `project_id, _ = project` at all four call sites, and the question text's
    interpolated *current value* is stable because the gate's own branch is
    `not project.allow_agent_jobs` (`jobs.py:47`) - the value is false at every call, so it cannot
    vary the dedupe key.
