# A late answer is delivered

Finding: **F356 (B)**, filed 2026-09-14 by the day window's O-3 from LoopEngine on `:8000`. Round 1
2026-09-14.

## Why

An operator who answers a blocking question after `ask_user` has stopped waiting, but before the
asking run has ended, has their answer recorded and delivered to nobody.

`answer_question` decides whether to queue the answer as new input from one predicate
(`hub/hub/api/v1/questions.py:346`):

```python
asker_still_waiting = question.blocking and not await _asking_run_has_ended(session, question)
```

`_asking_run_has_ended` (`:29-45`) is true only once the run's status leaves `running`. But
`ask_user` gives up at its deadline (`mcp_server.py:384`, `QUESTION_ANSWER_TIMEOUT`, 240 s by
default), returns to the model, and the run carries on working. From then until the run ends, an
answer is treated as received by a tool call that has already returned, and the queue step
(`:359-362`) is skipped. Nothing reads the answer later: no prompt carries it, and the agent was
told *"Continue as best you can"*.

The Hub **already knows** the wait is over. The tool reports its expiry to
`POST /agent-actions/questions/wait-ended` (`agent_actions.py:642`), which records
`Question.wait_ended_at`, and the run-end sweep (`run_divergence.py:730-735`) records the same fact
if the report never landed. `questions.py` reads neither.

The shipped spec already says the delivery should happen. `agent-capability-plane`'s *An agent can
ask several questions in one turn* says *"Where the asking run is no longer waiting — it expired,
ended, or the question was not blocking — the answers SHALL reach the agent"*. The code implements
only "ended". The requirement that code was written against, `run-task-binding`'s *An answer reaches
an asker whose run has ended*, has a scenario that forbids the fix as it is worded: *"answered while
its asking run is still open → not also queued"*.

### What was measured, and what F356 got wrong

On `:8000`, read with `mode=ro` on 2026-09-14, **23** questions carry a `wait_expires_at`:

- **21 of 23** waits ran out. On all 21 the tool's report landed, and `wait_ended_at` was recorded
  0.06–1.2 s after the Hub's deadline. The other two batches, 22:54 and 16:32, were answered in
  time: `wait_ended_at` is NULL and the answers came before the deadline.
- **F356 names three batches as lost. Only one was.**
  - **23:26 (09-12), not lost.** The run ended 23:31:37. The answers came 23:43:47–23:44:14, and
    `entry-7f953e7a11b4` delivered them at 23:44:14 (*"You asked 4 questions. The operator has now
    resolved all of them."*). The shipped run-has-ended path worked.
  - **16:50 (09-13), not lost.** The run ended 16:56:17. The answers came 16:56:57–16:57:26, and
    `entry-563536954359` delivered them at 16:57:26.
  - **14:38 (09-13), lost.** `q-9721e7f28a12` and `q-0cdb0c83ac60` were answered at 14:42:41 and
    14:42:49, before the deadline of 14:42:56.3, so the tool returned them. `q-cab59299c48e` and
    `q-477c3005a5b3` were reported expired at 14:42:56.37 and answered at **14:43:10** and
    **14:43:25**. The asking run ran on until **14:57:08**. No queue entry for `Architect` exists
    between 14:42 and 15:08, when the operator wrote a new message.

  So the defect is real, and it cost the operator two of the four answers on 09-13. But F356's
  mechanism is right and its instances are wrong: two of its three "lost" batches are the shipped
  fallback working. The ledger entry is corrected in the same commit as this proposal.

## What changes

1. **A wait that ended is not waited on.** Whether the asking run can still receive the answer
   becomes one predicate: blocking, **and** the run has not ended, **and** the wait has not ended
   (`wait_ended_at IS NULL`). `answer_question`, `decline_question` and both `asker_waiting`
   computations read that one predicate, so the operator's view stops saying *someone is waiting*
   at the same moment delivery starts. (D1, D2)
2. **The expiry report delivers an answer the tool never received.** The tool reports exactly the
   questions it did not see resolved (`expired`, `mcp_server.py:441`). An answer that lands after
   the tool's last poll and before its report arrives is answered by the time the report reads it.
   Today the report skips it as *"nothing expired"* (`agent_actions.py:681`). It will record the
   wait's end on it, and deliver the batch if the batch is complete. (D3)
3. **Both writers decide after they commit.** The answer commits `answered`, then reads
   `wait_ended_at`. The report commits `wait_ended_at`, then reads `answered`. Whichever commits
   second sees the other's write, so a race costs a duplicate delivery and never a lost one. This is
   the rule `_deliver_batch_if_complete` already states for two concurrent answers. (D4)

**No new column, no migration, no `mcp_server.py` edit, no UI code and no bundle.** The UI already
renders `asker_waiting === false` as nobody waiting (`AgentQuestionCard.tsx:75`,
`QuestionsPanel.tsx:26`). The field starts telling the truth, and the view follows without a change.

## What does not change

- The delivery text, and one delivery per complete batch
  (`2026-08-13-answers-arrive-together`).
- The shortcut the predicate exists for. An answer the tool is still polling for is not also queued.
- `wait_has_expired` and the Hub-stamped deadline. They still guard the report against a forged
  early expiry.
- `proceeded_without_answer_reason` stays permanent. Recording `wait_ended_at` on a question
  answered after the report makes the task say it went ahead without that answer, which is what
  happened (D3).

## Residual, named rather than closed

Suppose the report never lands, the answer comes after the tool's last poll, and the run lives on.
Nothing in the Hub can then tell an answer the tool received from one it did not, and the answer is
still lost. The sweep cannot help, because at run end the question reads answered. The measured
report success is 21 of 21. D5 sets out why a receipt stamp that would close this gap is not taken
in this change.

## Capabilities

- **`run-task-binding`**: MODIFIED *An answer reaches an asker whose run has ended*.

## Impact

- `hub/hub/api/v1/questions.py`: the predicate, `answer_question`, `decline_question`,
  `_with_asker_state` and `_with_asker_state_one`.
- `hub/hub/api/v1/agent_actions.py`: `report_wait_ended`'s answered and declined branch.
- Tests: `hub/tests/` (new file `test_a_late_answer_is_delivered.py`).
- Day rules 2026-09-14: no `hub/hub/mcp_server.py` edit (F354), none needed. No migration. No UI
  bundle.
