# Design — a refusal names a remedy that works

Split from `an-unstaffed-review-names-its-holders`'s design.md on 2026-09-15 (proposal.md,
*Provenance*). The decisions below are carried **verbatim** from that file's D2 (the remedy and
length-bound passages only), D4 and D5 — renumbered D1–D4 here, with each heading noting its
parent label for traceability. Nothing in this text has been reworded; only regrouped. Every R2/R3/
REV marker is original and describes rounds that ran against the parent change on 2026-09-14,
before the split. The full provenance, including everything that stayed with the sibling
directory (D1, D2's availability/clause logic, D3, D6), is in the parent's own design.md.

## Context

Three refusals told the operator's own project to take an action that did not exist: *"clear the
assignee"*, when no control clears it; a dispatch-time sentence claiming an assignment that a
refusal's own rollback had already discarded; and a stall reason that, once fitted for length,
turned out to already exceed the run history's own bound in at least one shape
(`_wedged_review_reason`). None of these depend on who is free to be handed a review — they are
about what the Hub says once an attempt has already failed, and about the length of what it stores.

## Decisions

### D1 — the remedy depends on the task's status (parent's D2, remedy passage)

**The remedy depends on the task's status.** Rung 3 is reached for `completed` tasks, and for
`under_review` rows the F70 recovery and the divergence restaff carry to the ladder. **One helper,
`own_review_remedy(task)`, writes it**, and D4 below's dispatch refusal calls the same helper (R2).
It is public, without a leading underscore, because `agent_trigger` imports it from `scheduler`.
That is the rule `enter_selected_task`'s docstring states for the same situation.
- **`completed`:** *Land it, on the task, to review it yourself*. This is F163's action, in the
  drawer for exactly this status (`TaskDetailDrawer.tsx:345`).
- **`under_review`:** *decide it yourself: approve, reject, or send it back with revision_needed*.
  `land` refuses `under_review` with a 409 (`tasks.py:1519-1530`), so naming Land it there would
  name an action that refuses.

**R3: the helper writes the status half only; the sibling directory's rung 3 appends the freeing
clause.** R2 left open whether *"rejecting a held task … frees its agent"* was part of what
`own_review_remedy` returns. This D5-shaped refusal (D4 below) answers an operator who named one
reviewer, and whether anyone else is free has no bearing on it, so the clause there would be noise.
The helper returns the `completed` or `under_review` sentence and nothing else. The rung-3 sentence
in the sibling directory appends its own clause on top — whatever that clause ends up saying once
re-derived against option (f), reachability (`F352-free`, decided 2026-09-15).

**R2: the `completed` remedy does not promise an approval.** R1 wrote *"Land it, on the task,
approves it"*. That is false in the common case.
- `land_task` evaluates the approval gate before it moves anything (`tasks.py:1543-1545`).
- `_check_unaccepted` (`requirement_gate.py:493-541`) refuses when evidence naming a commit is
  still waiting to be judged and nothing else would merge. It is rigor-independent.
- A task reaching this refusal has evidence naming a commit **by construction** in the flow case
  (the arm refuses anything else first, `scheduler.py:1538-1548`).
- A flow's review is usually what would judge that evidence. So on a repository project with a
  main branch, Land it **usually** refuses with *accept or grant* until someone decides the
  evidence.
- LoopEngine's two landings at 22:33 worked only because every piece of their evidence had already
  been decided. Read mode=ro: `task-611ae46fe0fb` had 1 accepted and 2 rejected, and
  `task-c8d4a3d70c19` had 3 accepted, all decided by `tester` at 21:21 and 21:41 without moving
  either task.

**R3: "usually", not "until".** R2 wrote that Land it refuses *until someone decides the evidence*.
The code says it refuses only where all three of these hold. Each is read from code, and none was
driven:
- **Evidence governs the merge.** A flow created through the operator's `POST /jobs` with both
  `spec_document_id` and `work_needs_evidence: false` is accepted (`api/v1/jobs.py:672-681`). Only
  the agents' `create_flow` refuses the declaration. For such a flow, `evidence_governs` answers
  from the declaration before it looks at the document (`task_integration.py:378-381`), so
  `merge_targets` returns the task's branch tip. Awaiting evidence then reaches `_check_unaccepted`
  as an advisory, not a refusal (`requirement_gate.py:538-540`), and Land it approves.
- **Nothing already accepted would merge.** Work sent back through `revision_needed` and completed
  again can carry earlier accepted evidence. That is the mixed case, also an advisory.
- **The project has a main branch, and its workspace resolves as a repository.** Otherwise
  `_merge_situation` returns `None` and the check does not run (`requirement_gate.py:393-418`).

*"To review it yourself"* is true either way. The drawer renders a gate refusal where the button
is (`TaskDetailDrawer.tsx:335-369`), naming what approval still needs.

### D2 — the stall reason fits within its column (parent's D2, length passage)

**The sentence is bounded, because one route would fail on it.** `JobRun.error_summary` is
declared `String(500)` (`models.py:1349`), and SQLite does not enforce that. **The response does:**
`JobRunResponse.error_summary` is `Field(max_length=500)` (`schemas/jobs.py:88`), and
`GET /jobs/{job_id}/history` answers `List[JobRunResponse]` (`api/v1/jobs.py:1197`). A stall reason
longer than 500 characters would be stored without complaint, and it would turn the job's history
route into a response-validation 500 for as long as that row is among the rows it returns.

- **Every `JobRun.error_summary` write is fitted to the column (at the model, not at two call
  sites).** The column is `String(500)` (`models.py:1349`), SQLite does not enforce it, and
  `JobRunResponse` does (`schemas/jobs.py:88`). Confirmed with the real schema class: a
  `response_model=List[JobRunResponse]` route answers 200 at 500 characters and **500 at 501**.
  - One constant, `JOB_RUN_ERROR_SUMMARY_CHARS = 500`, beside `JobRun`, is read by the column, by
    the schema's `max_length`, and by `fit_error_summary(text)`. The helper leaves text that fits
    unchanged, and cuts longer text to 499 characters plus `…`.
  - `JobRun` gets `@validates("error_summary")`, which applies the helper — the column enforcing
    its own declared length, which SQLite will not. It is the first `@validates` in `hub/hub`.
    Chosen over wrapping each call site because there are eight writes today
    (`scheduler.py:2580, 2609, 2762, 2923, 2966, 3062`, `api/v1/jobs.py:81` and
    `run_reconciliation.py:222`), and the next one would be written without the wrapper.
  - **R3: it fires on every write this column receives, measured.** A `DeclarativeBase` model
    with `@validates` fitted both a constructor keyword and an assignment. The real `JobRun` did
    the same through the attribute `set` event with `retval=True`, which is the hook `@validates`
    installs. That covers `api/v1/jobs.py:81`'s `JobRun(error_summary=...)`, and all seven
    assignments. The validator runs in Python when the attribute is set, so an async session
    changes nothing. Its only blind spot is a Core `update()`/`insert()`, and a grep finds none
    against `job_runs` in `hub/hub`. The column is nullable, so the helper passes `None` through.
  - *Rejected (R3):* a `TypeDecorator` fitting at bind time. It would also catch a Core statement.
    But it leaves the attribute unfitted in memory until the row is expired, so the object and the
    row would hold two values, and a response built from the object would still carry 600
    characters. `@validates` fits the value the object holds, which is what the route reads.
  - `_stall_run_to_increment` (`:923`) compares `latest.error_summary` with
    `fit_error_summary(stall_reason)`. The stored value is fitted, so comparing the raw reason
    would never match its successor, and `agent-loops`'s once-per-fact rule would record one row
    per tick.
- **R2 answered R1's open check: an existing reason already passes 500 today.** Computed, not
  observed:
  - **`_wedged_review_reason`** (`scheduler.py:1744-1748`) reaches `error_summary` through the
    stall write (`:2762`). It measures 551 characters with a 32-character reviewer and a
    256-character title, and passes 500 once the title reaches 206 characters. The title is quoted
    with `!r`, so escapes grow it: 256 backslashes make the sentence 807 characters long.
    The model-level fit would cut its remedy off the end, so **the function shortens the quoted
    title to what fits** (with `…`), and the sentence keeps its remedy.
  - **`schedule_result.waiting_reason`** (`:2923`, `:3062`) is the `detail` of any non-transient
    `TriggerAgentError`. Several embed exception text: git's stderr and two absolute paths
    (`agent_trigger.py:966, 970`), and `str(exc)` (`:607, 806, 853, 867, 1116`). These are
    unbounded by construction. The fit covers them, and cutting them loses only the tail of a git
    message. **REV: not only a git message.** A non-transient refusal becomes a terminal failure
    (`turn_scheduler.py:658-672`), and D4 below's guard sentence reaches `waiting_reason` this way
    through `agent_trigger.py:852`. The evidence-branch sentence, unfitted, measured **534**
    characters at a 64-character id and a 32-character name, and an earlier shape measured
    **583**. The fit would have cut the remedy off the end, so D4's sentence is worded to fit.
  - `_job_agent_skip_reason` (`:2580`), the stop reasons (`:2609`), both `_safe_error_summary`
    copies (`scheduler.py:2966` and `api/v1/jobs.py:81`, each already `[:500]`) and the
    reconciliation constant are bounded.
  - **Observed:** the `:8000` database's longest `error_summary` is 276 characters over 43 rows,
    and the trial Hub's 3 rows are empty (mode=ro). Nothing has failed yet. Filed as **F367 (C)**
    and retired by this change.

**Measured budget** (a 64-character task id, a 32-character agent name, D4's guard sentence):

| branch | worst | typical |
|---|---|---|
| author, operator | 395 | 302 |
| author, agent | 454 | 361 |
| evidence, operator | 449 | 356 |
| evidence, agent | 508 | 415 |

The agent branch never reaches `error_summary`, because only the flow's and the dispatch's staging
reach the queue entry, and both arrive as `operator()`. It is trimmed anyway, so no sentence
depends on that.

### D3 — once per fact means once per task (parent's D4)

`_review_unstaffed_already_stands` (`scheduler.py:1913-1941`) adds the task to its query:
`EventLog.data["task_id"].as_string() == task_id`, newest first, `limit(1)`. That makes it the
newest record **for this task** in this loop, which its own docstring already claims to read.

*Measured:* 347 of LoopEngine's 357 `review_unstaffed` events repeat their own task's previous
reason word for word. The one stretch with a single unstaffed task (22:35–22:55 UTC) recorded once.
The rule works for one task and fails for two.

*Why SQLAlchemy's JSON path and not a Python scan:* the scan is unbounded over a loop's history
(357 rows here and growing), and the JSON path compiles to SQLite's `JSON_EXTRACT`, which is built
into the SQLite that Python 3.11 ships. No runtime code uses a JSON path yet. The note in
migration `0083` avoids `json_extract` *in a migration*, for data-shape reasons that do not apply
to a column written only by `persist_event`.

**R2: it works.** `EventLog.data` is a SQLAlchemy `JSON` column (`models.py:1018`), and
`persist_event` writes the payload dict into it (`utils.py`, `data=data or {}`). Run against the
Hub's own models on `sqlite+aiosqlite:///:memory:` under `py -3.11`, with four `review_unstaffed`
rows alternating between two tasks, the way LoopEngine's did. The statement compiles to
`JSON_EXTRACT(event_logs.data, '$."task_id"') = :task_id` and returns the right newest row for each
task, and no row for a task with none. A grep finds no other `.as_string()` in `hub/hub`, so R1's
*"no runtime code uses a JSON path yet"* holds. The fallback is not needed.

*Interaction:* the reason now changes whenever the named holdings change — a fact of the sibling
directory's rung-3 logic, once re-derived. That is a changed fact, and `agent-loops` requires it
recorded again. The sibling's D2 (parent numbering) is what keeps the reason from changing on every
turn boundary; this change does not depend on that logic existing yet.

### D4 — the refusals name what the refused actor can do (parent's D5)

The guard's **decision** does not change: same edges, same actors bound, same exceptions. Only the
sentences change.

**`_guard_reviewer_is_not_the_author`** (`task_transition_service.py:443-464`, both branches) is
reached by three audiences:

| audience | how | the assignee it judges |
|---|---|---|
| the operator | `PATCH …/tasks/{id}`, including the drawer's status menu | committed, or set by the same request |
| an agent | `update_task` over MCP; `PATCH /agent-actions/tasks/{id}` over HTTP | committed over MCP; over HTTP also set by the same request (F366) |
| a flow or a dispatch | `enter_selected_task` writes the reviewer, then transitions as `operator()` (`scheduler.py:816-828`) | staged by this call, then discarded by the rollback (F334) |

**The sentence must be true in all three**, and the guard cannot tell a staged value from a
committed one. SQLAlchemy's attribute history is cleared by any autoflush between the assignment
and the guard. So the sentence describes the move, not the row. It follows this shape: *"Cannot
move task T to 'under_review' with 'dev' as its holder: 'dev' is the agent recorded as completing
it, and a task under review is held by its reviewer, so the move would make its author its
reviewer."* That is true whether `dev` was already there or was being written in. It does not say
*"is assigned to"*.

**Then the remedy, chosen by `actor.is_operator`.** The flow's staging arrives as `operator()`
(F47), and its sentence lands in the queue entry's `waiting_reason` and `abandoned_reason`, which
the operator reads. So the operator wording serves both. The guard only ever judges a `completed`
task, because `under_review` is entered from `completed` alone (`task_transitions.py:134-137`). So
Land it is always the right remedy **here**.

**Both remedies (REV wording):**
- **The operator's second half produced a wedge, and was replaced.** The PATCH that writes the
  assignee and the transition together (`tasks.py:1266-1339`) queues no turn. Review turns are
  queued only by the dispatch (`agent_trigger.py:1502`), the divergence (`run_divergence.py:266,
  467`) and the flow (`scheduler.py:2863, 3193`). In a flow, the next firing finds the task
  `under_review` held by a non-author with no turn and surfaces F154's *"Nothing will move it on
  its own"* (`scheduler.py:1370-1393`) — the 63 named-reviewer-idle events LoopEngine recorded.
  The request that gets another agent to review is the dispatch. The operator's remedy is now:
  *Land it, on the task, to review it yourself, or dispatch another agent's review turn (POST
  /agent/trigger with review_task_id).* The dispatch refuses a task with no evidence naming a
  commit (`agent_trigger.py:1446-1448`), but the guard judges only `completed` tasks, and a flow
  puts those under review only after its arm required that evidence, so the remedy is never a
  silent dead end.
- **The agent's claim about its tools was false, and was replaced.** MCP `create_task` takes an
  `assignee` (`mcp_server.py:248-251`). `send_message` with a `task_id` binds a run, and binding
  sets the assignee of an unassigned task (`run_task_binding.py:475-476`). An HTTP agent reaches
  this refusal through the route that accepts `assignee` (`agent_actions.py:276-289`). What is
  true is narrower: no task tool the agent is offered **reassigns** a task that already has a
  holder. The agent's remedy is now: *None of the task tools you are offered reassigns a task.
  Leave it completed; the operator can land it or dispatch a reviewer who is not its author.*

**Neither sentence names the HTTP hole.** *"None of your tools changes who holds a task"* is a
claim about the surface, not the route. Whether the route should take `assignee` at all is F366's
own loop.

The trailing *"Left as is, the task is claimable by nobody and 'dev' counts as busy…"* is dropped.
It describes the state the refused move *would* have produced, and read after a refusal it
describes a state that does not exist.

`actor` becomes read, **for wording only**. Its docstring's *"`actor` is deliberately unread"*
paragraph is amended to say so. The rule still binds every actor.

**`review_dispatch_refusal`** (`agent_trigger.py:497-514`) is reached only by the operator's
`POST /agent/trigger` with `review_task_id`, an API-only route (F336).
- The author branch drops *"or clear the assignee to review it yourself"* — unrelated to a refusal
  about the *reviewer* being the completer — and gains `own_review_remedy(task)` (D1 above).
- The evidence-author branch gains the same helper, for consistency.
- The remedy depends on the status, as D1's helper does. `review_dispatch_refusal` admits
  `WITH_REVIEWER_LOOP_TASK_STATUSES` as well as the reviewable ones (`agent_trigger.py:480`), and
  its D9 check refuses only a *different* holder (`:487-491`), so the author branch is reached for
  an `under_review` task that nobody holds, or that is held by the very reviewer being dispatched.
  `land` refuses `under_review` with a 409 (`tasks.py:1519-1530`). One helper for both surfaces is
  also what keeps them from drifting into two accounts of the same remedy.

**Two more sentences carry F353's defect, and two comments become false and are amended:**
- The D9 refusal, *"Reassign the task if 'x' should take it over"*, appears twice:
  `review_dispatch_refusal` (`agent_trigger.py:494`) and the dispatch path (`:840`). Its reader is
  the operator, who has no reassign control — `under_review`'s only edges are `approved`,
  `revision_needed` and `rejected` (`task_transitions.py:138-142`), so no move hands a review to
  another agent, and a PATCH of the assignee alone queues no turn (the wedge above). The sentence
  becomes *"… Let the review in flight finish, or decide it yourself"*, followed by
  `own_review_remedy`'s `under_review` sentence.
- `agent_trigger.py:847-849` says the guard's sentence *"already names both remedies and the cost
  of doing nothing"*, and `task_transition_service.py:405-406` says the operator *"clear[s] or
  reassign[s] `assignee` first, which is what the refusal asks for"*. Both are amended — after this
  change each would be a false statement about the guard.

**Both remedies fit 500 at the worst ids** — see D2's budget table above. `@validates` on `JobRun`
fits every write this column receives; the guard's own sentence is worded to fit rather than rely
on the fit alone, because the model-level fit would otherwise cut its remedy off the end.

## What this change does not do

- **It does not change who is free.** That is `F352-free`, decided 2026-09-15 in favour of option
  (f) (`4b59ee0`, already shipped) — a decision this change's tasks never touch.
- **It does not add an assignee control or a review-dispatch control to the app** (F336 names the
  second as a product decision). The sentences stop naming controls that do not exist, and name
  the one that does.
- **It does not edit `hub/hub/mcp_server.py`.** Nothing here needs it.
- **It does not close F366.** `PATCH /agent-actions/tasks/{id}` (`agent_actions.py:276-289`) takes
  the operator's `TaskUpdate`, `assignee` included, and `update_task_for_actor` writes it for any
  actor (`tasks.py:1266-1275`). MCP `update_task` carries no assignee (`mcp_server.py:307`). An
  agent over HTTP can reassign any task. `agent-capability-plane` forbids that surface difference.
  Closing the route is F366's own loop; this change describes the offered surface instead of
  relying on the route's hole.
- **It does not touch the board's stall-line hover (D6, parent numbering).** That is UI over the
  rung-3 sentence, which lives in the sibling directory.

## Risks

- **Test churn is mechanical.** The existing tests asserting sentence fragments (`could not staff
  this step`, `review it yourself`, `is the one that completed this task`, `has worked on this
  task`) are unaffected — this change's wording keeps every one of those fragments. Only the
  comments and the three refusal sentences this change actually rewords move.
- **The first `@validates` in `hub/hub`.** A validator that silently shortens a value is a pattern
  a reader may not expect. The constant's docstring says what it does and why, and the model test
  exercises it through the real route.
