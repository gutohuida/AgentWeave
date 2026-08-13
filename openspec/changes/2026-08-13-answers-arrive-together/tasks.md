# Tasks — A batch of answers arrives as one turn

The change is one function's worth of logic in `questions.py`, plus making the wait visible. Most of
the work is in the cases around it, which is where the current behaviour was never decided.

## 1. Establish the current behaviour before changing it

- [x] 1.1 Confirm `POST /questions/{id}/answer` is the **only** producer of a queue entry from a
      question. If a second path exists, batching one of them leaves the split delivery in place.
      **Confirmed:** `questions.py:228` was the only `new_entry` call in the module. The other nine
      call sites are the scheduler, messages, triggers, checkpoints and divergence — none of them
      question-derived.
- [x] 1.2 Confirm `decline_question` queues nothing today, and that `release_block_for_question` is
      called from both the answer and decline paths. D2 makes a decline complete a batch; it must not
      change what a decline does on its own.
      **Confirmed:** `release_block_for_question` is called from exactly two places, one in each
      path. The decline path built no entry at all.
- [x] 1.3 Confirm `batch_id` is populated for **every** question created through
      `POST /questions/batch`, including a batch of one, and that `batch_size` defaults to 1 for rows
      predating the column. D7 rests on a single question being a batch of one rather than a special
      case.
      **Confirmed for the batch route, and the task's premise was wrong about the rest.**
      `agent_actions.py:377` mints a `batch_id` for every batch including one of size 1. But
      `ask_question_for_actor` defaults `batch_id=None`, and both `POST /questions` and the agent's
      single-question route take that default — so **a question asked on its own has a NULL
      `batch_id`, not a batch id of size one.** D7 therefore needs two ways of being a batch of one:
      a null id, and a complete batch. `_completed_batch` returns `[question]` immediately for a
      null id, and `test_a_question_with_no_batch_id_is_a_batch_of_one` pins it. Had this gone
      unnoticed, every operator-asked question would have queried a batch that does not exist.
- [ ] 1.4 Reproduce the defect against the running Hub: ask a batch, let the asking run end, answer
      the first question, and observe a queue entry created before the batch is finished. **Record
      the entry.** This is the before-state and the change is judged against it.
      **Not done as written, and it is now impossible from this commit** — the code no longer has
      the behaviour to reproduce. The before-state is instead evidenced by the row already in the
      live database, recorded in the proposal: a queue entry reading `"Question: What should the app
      primarily help people do?\n\nAnswer: …"`, one answer, its own turn. Reverting to reproduce it
      properly was judged not worth the round trip against evidence that already exists.

## 2. Deliver per batch (D1, D2, D3)

- [x] 2.1 In the answer path, replace the per-answer queue entry with a batch check: when the asker
      is no longer waiting, create the entry only if every question sharing this `batch_id` is now
      answered or declined.
- [x] 2.2 Build the entry from every question in the batch, ordered by `batch_index`, each with its
      answer or its decline (D3, D4). Read them from the database rather than tracking what has
      happened since the run ended — that is what includes an answer the dead run never received.
- [x] 2.3 Leave persistence, the `question_answered` broadcast, and `release_block_for_question`
      exactly where they are. Only the queue entry moves (D1).
- [x] 2.4 Make the decline path complete a batch: if declining resolves the last outstanding
      question, the batch delivers. A decline still queues nothing on its own (D2, D6).
      This gave the decline path a queue entry for the first time, so it also gained the
      `queue_entry_queued` event, the broadcast, and the `schedule_agent` call the answer path
      already had. A delivery nothing wakes the agent for is not a delivery.
- [x] 2.5 Queue nothing when the completed batch holds no answers (D6).
- [x] 2.6 The completion check and the entry creation happen in one transaction, so two answers
      landing together cannot both see the batch as complete (see 4.6).
      **This task was wrong, and wrong in the dangerous direction.** One transaction does not
      protect it: two requests each mutating their own question inside their own *uncommitted*
      transaction would each see the other's question outstanding and each decline to deliver,
      leaving a complete batch that reaches nobody. Losing the operator's decisions is far worse
      than delivering twice. **Done instead:** the answer is committed first and the completeness
      check runs against committed state, so the concurrent failure is a duplicate rather than a
      loss. The duplicate is left open — closing it needs a delivery marker with nowhere in the
      schema to live, and the panel answers strictly one question at a time. Recorded in design.md
      under Risks.
- [x] 2.7 Name the conversation from the batch rather than from one question, so a three-question
      batch does not title its thread with whichever question happened to complete it.

## 3. Say that the answers are being held (D5)

- [x] 3.1 The questions panel states, for a batch whose asker is no longer waiting and which is part
      answered, that the answers go to the agent together when the batch is finished.
      Shown for any multi-question batch whose asker has gone, rather than only once one is
      answered: the operator benefits from knowing before they start, and the message also names
      dismissing the rest as the way to send what they have.
- [x] 3.2 Distinct from the step counter, which is position and stays as it is. Do not overload it.
- [x] 3.3 Use the `Icon` component if the statement carries one. Do not introduce a second icon
      system. **No icon used**, so nothing to decide.

## 4. Tests — agent-verifiable

All in `hub/tests/test_question_batch_delivery.py` unless stated.

- [x] 4.1 A batch whose asker has ended: answering the first question queues **nothing**; resolving
      the last queues **exactly one** entry carrying every question and answer in ask order.
- [x] 4.2 The entry names a declined question as declined rather than omitting it (D4).
- [x] 4.3 An answer recorded while the run was waiting, whose run then ends, appears in the delivery
      made when the batch completes (D3). **This is the currently-lost answer** — assert it reaches
      the agent, not merely that it is recorded.
- [x] 4.4 A batch resolved entirely by declines queues nothing (D6).
- [x] 4.5 A batch of one behaves exactly as today: one answer, one entry (D7).
      Asserted byte-for-byte against the old wording, plus the null-`batch_id` case from 1.3.
- [ ] 4.6 Two answers completing a batch concurrently produce one entry, not two (D1, 2.6).
      **Not written, because 2.6 established the guarantee does not exist.** A test asserting one
      entry would fail, and one asserting two would pin a behaviour nobody wants. What is worth
      testing is that the batch is never *lost*, which is what the post-commit ordering buys — and
      exercising that needs two genuinely concurrent requests against one database, which this
      suite has no way to stage. Left open and named rather than quietly dropped.
- [x] 4.7 The still-waiting path is untouched: a live asker answering every question receives them
      through the tool and has **no** entry queued. This is the measured behaviour from
      `2026-08-11-declining-a-question`; a regression here costs a whole extra turn.
- [x] 4.8 An answer is persisted and releases its parked task before the batch completes (D1).
- [x] 4.9 UI: a part-answered held batch states that the answers travel together; a batch of one does
      not make that statement. `agentQuestionCard.test.tsx`, three cases including a live asker.
- [x] 4.10 `pytest hub/tests/ -q` and `pytest tests/ -q` **run separately** — together they fail
      collection. `npx vitest run` and `npx tsc --noEmit` from `hub/ui`.
- [x] 4.11 `ruff check hub/ src/`, `black` on every file touched.
- [x] 4.12 Rebuild `hub/ui/dist`, copy over `hub/hub/static/ui`, confirm with `diff -rq`.
- [x] 4.13 `npx openspec validate --changes --strict` and `--specs --strict`.

## 4d. Driven against the running Hub

A temporary project with an agent bound to **no runner**, so the delivered turn would queue rather
than spawn, and the queue entry could be inspected without a real run. A `Run` row was inserted to
obtain a credential, the batch asked through the agent's own route, the run then marked completed —
the exact state this change is about — and the project's rows and directory removed afterwards.
The Hub was restarted onto this commit first.

```
asked: 3   batch_id: qbatch-0618120f
asking run ended

after answer 1 (alpha): 0 queue entrie(s)
after answer 2 (beta):  0 queue entrie(s)
after answer 3 (gamma): 1 queue entrie(s)
```

The single delivery, read back from `inbound_queue_entries`:

```
You asked 3 questions. The operator has now resolved all of them.

1. First?
   Answer: alpha

2. Second?
   Answer: beta

3. Third?
   Answer: gamma
```

Before this change each of those three answers produced its own entry, and so its own turn — the
first of them starting the agent while the operator was still on the second.

## 5. Verification — human-only (the operator runs these)

Nothing below can be closed by an agent. Each needs a person looking at a running app.

- [ ] 5.1 **The reported symptom is gone.** Have an agent ask several questions, let its run end,
      then answer them one at a time. The agent must not start work until the last one is given.
- [ ] 5.2 Does the held-batch statement read as reassurance or as a warning? It exists so that
      answering two of three does not look like nothing happened.
- [ ] 5.3 Answer part of a batch and walk away. Confirm the outstanding questions are still visibly
      outstanding, and that declining them delivers what you already answered.
- [ ] 5.4 Confirm a live agent — one still waiting — is unaffected: it should still receive the batch
      through the tool, with no extra turn afterwards.
- [ ] 5.5 Answer a single question, as before. It should behave exactly as it always has.

## 6. User test guide

**Setup.** An agent that will ask you several questions at once. Asking it to plan something
underspecified is the reliable way to get one.

1. **Get a batch.** Have the agent ask three questions in one go. You should see them one at a time,
   with a step count.
2. **Let its run end** — wait out its question timeout, or interrupt it. This is the case that was
   broken; a still-running agent was always fine.
3. **Answer the first question.** The agent should do nothing. Before this change it woke up and
   started working on that answer alone.
4. **Check the panel says so.** It should tell you the answers go together when you finish, rather
   than leaving you wondering whether the first one registered.
5. **Answer the rest.** Now the agent wakes, once, with everything you said in the order it asked.
6. **Try declining one.** Answer two, decline the third. The agent should still wake once, and should
   be told you declined rather than being left to guess.
7. **Ask a single question and answer it.** Unchanged — one answer, one turn.

**What is deliberately absent:** a batch you never finish is never delivered. The answers are kept,
and the outstanding questions stay visible; declining the rest is how you send what you have. There
is no timer that eventually gives up and delivers half.
