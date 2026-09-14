# Design — a late answer is delivered

## Context

A blocking `ask_user` call ends in one of three ways, and the Hub records each of them:

| How the wait ended | What the tool does | What the Hub records |
|---|---|---|
| Every question answered or declined in time | returns them | `answered` / `declined`; `wait_ended_at` NULL |
| The deadline passed with some unresolved | returns the rest as expired, then `POST /questions/wait-ended` with exactly those ids (`mcp_server.py:441-460`) | `wait_ended_at = now` per id, if `wait_has_expired` (`agent_actions.py:642-712`) |
| The report never landed (swallowed failure, `mcp_server.py:449-461`) | nothing | the run-end sweep sets `wait_ended_at` (`run_divergence.py:730-735`) |

The tool's clock and the Hub's cannot cross. The Hub stamps `wait_expires_at` before it responds.
The tool computes its own deadline after the response, and sleeps `QUESTION_POLL_SECONDS = 2`
before each poll (`mcp_server.py:384-386`, `:936`). So the tool keeps polling for up to about 2 s
plus request latency **after** the Hub's deadline. That is why `wait_expires_at` cannot be the
predicate (D1).

Measured on `:8000` (`mode=ro`, 2026-09-14), the report landed on 21 of 21 expired waits, 0.06–1.2 s
after `wait_expires_at`. See `proposal.md`, *What was measured*.

## D1 — "still waiting" is: blocking, run live, wait not ended

```python
async def _asker_still_waiting(session, question) -> bool:
    return (
        question.blocking
        and question.wait_ended_at is None
        and not await _asking_run_has_ended(session, question)
    )
```

**`wait_ended_at`, not `wait_has_expired`.** `wait_ended_at` is the tool telling the Hub which
questions it did not receive. An answer in the window between the Hub's deadline and the tool's last
poll is returned by the tool. If the predicate compared against `wait_expires_at`, that answer would
also be queued, which is the duplicate the shortcut exists to prevent (`questions.py:333-338`). The
sweep also sets `wait_ended_at`, but only at the run's end, and by then the run-ended arm already
answers.

**Order kept.** `wait_ended_at` is checked before the run lookup, so a question that the report
already settled costs no query.

**One definition.** `answer_question` (`:346`) and `decline_question` (the same expression, `:453`)
both call it. So does the report path (D3), after it commits.

## D2 — the operator's view reads the same fact

`asker_waiting` is computed twice. `_with_asker_state` (`:249-270`) runs one bulk query over the
run ids. `_with_asker_state_one` (`:273-288`) goes through `_asking_run_has_ended`. Each gains the
`wait_ended_at IS NULL` arm. The bulk one needs no extra query, because the column is already on the
row it has in hand. `test_the_list_and_the_detail_route_agree` already holds the two together, and it
gains a row whose wait has ended while its run is live.

**Not** `blocking`-gated. Neither computation reads `blocking` today, and adding that is a separate
behaviour change nobody has asked for.

The UI needs no code. `AgentQuestionCard.tsx:75` and `QuestionsPanel.tsx:26` already render
`asker_waiting === false` as *nobody is waiting; an answer now arrives as a message*. That is exactly
true once the wait has ended, which is what the operator in the 14:38 batch was not told. **No
bundle.**

## D3 — the expiry report delivers what the tool never received

In `report_wait_ended`, a reported question that is already `answered` or `declined` is today
skipped as *"already answered or declined — nothing expired"* (`agent_actions.py:681`). That is
false in exactly one case, and it is the case that reaches this branch. The tool lists only the
questions it did not see resolved. So a reported question that the Hub has resolved was resolved
after the tool's last poll for it, and the run never received it.

Changed behaviour, for a question asked by the calling run that is **answered**, with
`wait_ended_at` NULL:

- record `wait_ended_at = now`. The run's wait did end without that answer. This also makes a
  second report of the same id a no-op (the existing `:683` branch), and gives
  `proceeded_without_answer_reason` the true record: the task went ahead without the answer.
- **no** `wait_has_expired` check on this branch. The refusal exists so that a report cannot create
  an expiry. It cannot create one here, because the question is already answered and nothing is
  released. The release functions are not called, because the answer already released the block
  (`release_block_for_question`).
- count it in `accepted`. The caller's assertion is true.
- after the commit, deliver once per **batch**, not once per question. Collect the batch keys
  (`batch_id`, or the question id for a batch of one) during the loop, then call
  `_deliver_batch_if_complete` once per key. Two late answers from one batch, reported together,
  would otherwise queue the batch twice.

**A question declined after the tool's last poll is accepted, and nothing else happens.** It gets no
`wait_ended_at`, no write and no delivery key. The column's stated invariant is that a declined
question never carries `wait_ended_at` (`models.py:1003-1007`, `tasks.py:447-449`), because a
decline is a decision handed back, not silence. `proceeded_without_answer_reason` reads that
column. Breaking the invariant would mark a task as having gone ahead without an answer when the
operator in fact declined.

Nothing is lost by the narrowing:
- if the batch also holds a late answer, that answer supplies the key;
- if the batch holds an unanswered question, its later answer or decline delivers through the
  answer route;
- a lone late decline delivered nothing anyway (`_batch_delivery_text`, D6 of
  `answers-arrive-together`).

What remains undelivered is the fact of a decline in a batch whose answers the tool already
returned. The agent was told that question went unanswered, when the operator had in fact declined
it. That loss is accepted, and named in the test guide.

The queue event, the SSE broadcast and `schedule_agent` that `answer_question` does after a
delivery (`:377-399`; `decline_question` repeats it at `:488-504`) move into one helper in
`questions.py`. The report route calls it too, so the report's delivery is announced and woken
exactly as the answer's is.

## D4 — decide after commit, on committed state

The two writers are the answer (`answered`) and the report (`wait_ended_at`). Each commits its own
write first, then reads the other's column from **committed** state:

- `answer_question` already commits and refreshes before it decides (`:348-349`). The predicate
  moves after that refresh. Today it is computed before the commit (`:346`), from the row as read at
  the request's start.
- `report_wait_ended` commits per question (`agent_actions.py:696`). The batch delivery runs after the loop, on
  rows re-read from the database.

Whichever commits second sees the first one's write. So a concurrent pair costs at worst one
duplicate delivery and never a lost one. That is the trade `_deliver_batch_if_complete`'s docstring
already makes and states (`:83-104`): *"losing what the operator decided is much the worse of the
two."*

**The identity-map trap, stated because it would make D3 fail silently.** The session is
`expire_on_commit=False` (`db/engine.py:163`). `report_wait_ended` loads every reported question
through `session.get` in one session. `_completed_batch`'s `select` returns those same identity-map
objects **without overwriting their loaded attributes**. So a sibling that was answered after the
route loaded it still reads `answered = False`, the batch reads incomplete, and nothing is delivered.
The re-read must use `populate_existing` (or refresh each row) before `_completed_batch` judges
completeness. Task 2.3 pins it with a sibling answered mid-request.

## D5 — no receipt stamp (considered, not taken)

The residual case is a report that never lands, an answer after the tool's last poll, and a run that
lives on. The Hub then cannot tell what the tool received. A column `answer_received_at`, stamped
when `get_own_question` (`agent_actions.py:716`) serves a resolved row to its asking run, would make
this exact, and would let the run-end sweep deliver any resolution never served.

Not taken, for three reasons:
- it costs migration `0104`, and a write on the tool's poll route;
- the measured report failure rate is 0 of 21;
- the gap it closes is the conjunction of two rare events (a report that fails, and an answer inside
  the run's remaining life), not the defect that cost the operator on 09-13.

It is named in the proposal's *Residual*, so the choice is visible and can be reversed. **R2 and R3
should challenge this choice rather than assume it.**

## D6 — the late delivery's wording is unchanged (considered, not taken)

A late answer reaches the agent in the wording a run-has-ended answer has always used. One could
argue the agent should be told *"this arrived after you went on without it"*. But the run-has-ended
case has the same property and has never said so. Changing both is a wording change with its own
tests and prompt budget, and it is not this defect. Recorded as an improvement candidate, not built.

## Risks

- **A queued answer while the asker still runs.** `schedule_agent` is called for an agent whose
  run is live. R1 read the scheduler for this, and it holds. `_attempt_turn` refuses any agent
  with a `running` run, with *"agent is already running"*, non-terminal and counting nothing
  (`turn_scheduler.py:327-334`). The run's normal end re-drains the project
  (`agent_trigger.py:2514`), which picks the entry up. Task 2.5 pins this with a test rather than
  trusting the reading.
- **A duplicate under a real race** (D4) is accepted, as it already is for two concurrent answers.
