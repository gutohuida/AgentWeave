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

**(Round 2) The third row is narrower than the table says.** The sweep (`run_divergence.py:713-736`)
stamps at most **one** question, the earliest from `unanswered_blocking_question` (`.limit(1)`,
`run_task_binding.py:667-677`). It is also reached only on the task-bound branch of
`evaluate_run_end`: an unbound run returns before it (`:706`). So a batch of three whose report was
lost gets one `wait_ended_at` at the run's end, not three. That changes nothing this change
decides. By then the run has ended, and the run-ended arm answers "nobody is waiting" for every
question in the batch without reading `wait_ended_at`. It is recorded because the row read as
covering the batch, and D1's argument cites the sweep.

**(Round 2) The two clocks can also disagree by configuration, and that favours D1.** The Hub
computes `wait_expires_at` from `effective_question_wait(agent_row)` at the **ask**
(`agent_actions.py:519-523`). The tool reads `AW_QUESTION_TIMEOUT` once, when its process starts at
the **spawn** (`mcp_server.py:935`). An operator who changes `question_timeout_seconds` while a run
is live splits the two. Read, not measured. If the timeout is shortened, the Hub's deadline passes
first and the tool keeps polling, which is the grace window made longer. `wait_ended_at` handles
that correctly, and `wait_expires_at` would duplicate every answer inside it. If the timeout is
lengthened, the tool gives up first and its report is refused by `wait_has_expired`. That is a
second route into D5's residual.

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
  would otherwise queue the batch twice. **(Round 2)** The keys are no longer collected during the
  loop from the row as loaded. They come from the rows this request stamped, re-read after its
  commit. See D4, *The report half*.

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

### (Round 2) The report half, as round 1 wrote it, still decides before it commits

D4 claims that "whichever commits second sees the first one's write". That holds for the answer
route. It does not hold for the report as D3 specifies it, because the report picks its branch from
the row **as loaded**, and loading comes before its commit. Walk the interleaving:

1. The report loads question Q: unanswered, `wait_ended_at` NULL, deadline passed.
2. The operator's answer commits `answered = True`. The answer route refreshes and reads
   `wait_ended_at` NULL. The run is live, so it decides the asker is still waiting and queues
   nothing.
3. The report takes the **expired** branch from its stale row, writes `wait_ended_at`, and commits.
   Only the changed column is flushed, so the answer survives in the database. But Q entered no
   delivery key, because at load time it was not answered.

Both writers declined to deliver. The requirement forbids exactly that (*"SHALL NOT both decline to
deliver"*). No database snapshot prevents this. `engine.py` sets no isolation level and emits no
`BEGIN` before a `SELECT` (only `check_same_thread`, `:39`), so the driver's default applies. The
load reads committed state and holds no transaction open until the `UPDATE`. This is read, not
measured. The window is the milliseconds between load and commit: rare, but D4's whole claim is
*never a lost one*.

**The fix is to decide delivery from the report's own committed writes, not from its load:**

- Take the batch key from **every question this request stamped**, on either branch. After the loop,
  re-read those rows with `populate_existing`, and key each one that is `answered` in committed
  state. Then whichever of the two writers commits second sees the other's write, and D4 becomes
  true for both.
- A row accepted through the *already recorded* branch (`:683`) is not re-keyed. That is what keeps
  task 2.6, a second report delivering nothing, true.

### (Round 2) The invariant D3 leans on is not enforced at the write

D3 narrows the late decline on the ground that a declined question never carries `wait_ended_at`.
**That can already be broken today.** Run the same interleaving with a decline in place of the
answer: the report loads Q unresolved, the decline commits, and the report stamps `wait_ended_at`
on its stale row. The result is a declined question carrying `wait_ended_at`, and
`proceeded_without_answer_reason` (which reads `wait_ended_at` alone, `tasks.py:456-462`) then says
*"Proceeded without your answer"* about a question the operator declined. The race predates this
change. This change should not rest an argument on the invariant while leaving it unguarded.

**The fix is to make the stamp a guarded `UPDATE`:** `UPDATE question SET wait_ended_at = :now
WHERE id = :id AND wait_ended_at IS NULL AND declined IS FALSE`. Replace the ORM attribute write
with it, and read the `rowcount`. SQLite serialises writers, so the `WHERE` is judged against
committed state at the moment of the write.

- A `rowcount` of 1 means this request stamped the row. It enters the post-commit re-read above.
  For the expired branch only, `release_block_for_expired_wait` runs, as it does today.
- A `rowcount` of 0 means the row was declined, or its end was already recorded by a concurrent
  report or sweep. Either way the caller's assertion is true, so the row is accepted, with no key
  and no release.

The same one statement serves both D3 branches. The answered branch keeps skipping
`wait_has_expired`.

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

### (Round 2) The challenge: one of D5's costs is wrong, and there is a third option

**The write cost is overstated.** The tool stops polling a question once it has read it resolved
(`if question_id in answers: continue`, `mcp_server.py:387-389`). So a receipt stamp costs one write
per resolved question, not one per poll. The migration cost stands. So does today's day rule
against one.

**The residual has two routes, not one.** The first is the one D5 names: the report is lost, the
answer arrives after the tool's last poll, and the run lives on. The second is D1's configuration
split: the timeout is lengthened mid-run, so the tool's report is refused. Both leave a question
that is answered, has `wait_ended_at` NULL, and was answered after its deadline. A receipt closes
both, but only **at the run's end**. While the run lives, no design can tell whether the tool will
poll again.

**A third option needs no migration.** At the run's end, deliver any blocking question from this
run that is answered, has `wait_ended_at` NULL, and has `answered_at > wait_expires_at`. Both
timestamps are the Hub's own, so this is the same-clock comparison `wait_has_expired` already makes.
It fires in three cases:

- the report was lost, which is a true delivery;
- the report was refused under the configuration split, which is a true delivery;
- an answer landed in the grace window and the tool returned it, which is a **duplicate**. The
  window is about 2 s per wait.

That is D4's own trade: at worst a duplicate, never a loss. It turns both routes of the residual
from *lost* into *delivered at the run's end*. It would live in `evaluate_run_end` beside the sweep.
It would need its own stamp for idempotency, since `wait_ended_at` would then mark the task
*"Proceeded without your answer"*, and that is false in the grace-window case. And it has to reach
unbound runs, which the sweep does not (`:706`).

**Round 2's position.** D5 stands for **this** change, for scope. The third option adds a new
delivery path at the run's end, with its own idempotency question, and deserves its own three
rounds. It is not a clause to bolt on here. But D5's stated reasons are corrected above, and the
proposal's *Residual* now names both routes and the third option. That way the follow-on starts from
the right costs. **Round 3 should re-derive this position rather than inherit it.** In particular,
R3 should check whether the idempotency stamp can be avoided, for instance by deriving it from a
queue entry's existence. If it can, the option may be small enough to take here after all.

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
