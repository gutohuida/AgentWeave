# Tasks

Settled with the operator on 2026-08-11 before implementation: declining tells a waiting agent (D2),
it releases a task the question parked (D3), and a question nobody is waiting on is marked and sorts
out of the way (D5, D6).

Ordered by dependency. 1 is the state; 2 the agent surface; 3 the task interaction; 4 the operator's
surface; 5 specs; 6 verification.

## 1. The state

- [x] 1.1 `questions.declined` and `questions.declined_at` in `hub/hub/db/models.py`, beside
      `answered` rather than replacing it (D1)
- [x] 1.2 Migration `0061`, guarded, no backfill; bump **both** head assertions
- [x] 1.3 `POST /questions/{id}/decline`, refusing a question that is already answered
- [x] 1.4 `declined` on `QuestionResponse`; the decline is broadcast and persisted as an event
- [x] 1.5 Tests: declining closes it; an answered question cannot be declined; declining twice is
      idempotent

## 2. The agent is told

- [x] 2.1 `ask_user`'s wait ends on answered **or** declined, and reports which (D2)
- [x] 2.2 `get_answer` reports a declined question as declined rather than as still pending
- [x] 2.3 The `ask_user` docstring says the operator may decline, and what that means — this is a
      change to what the agent is told, not a note about one
- [x] 2.4 Tests: the poll ends on a decline; the returned entry says `answered: False` and names the
      decline

## 3. A declined question does not hold a task

- [x] 3.1 `unanswered_blocking_question` excludes declined rows (D4) — without this the run-boundary
      check re-parks the task on a question the operator already closed
- [x] 3.2 Declining releases a task the question parked, through the **same** function answering
      uses (D3)
- [x] 3.3 Tests: a declined question parks nothing at the run boundary; declining releases a parked
      task to `in_progress` and clears its reason; the check applies again afterwards

## 4. The operator's surface

- [x] 4.1 `QuestionResponse.asker_waiting`, computed from the asking run and defaulting to `True`
      when unknown (D5)
- [x] 4.2 `activeQuestionFor` skips declined questions and sorts live ones first (D6)
- [x] 4.3 A dismiss control on `AgentQuestionCard`
- [x] 4.4 The card marks a question nobody is waiting on
- [x] 4.5 Tests: a declined question is never the active one; a live question outranks a stale one;
      **a batch stays contiguous under the new sort** — the property D6 depends on
- [x] 4.6 `npm run build`, `rm -rf hub/hub/static/ui`, copy, confirm with `diff -rq`

## 5. Specs

- [x] 5.1 Apply the two delta specs
- [x] 5.2 `npx openspec validate --specs --strict` and `--changes --strict`

## 6. Verification

### 6a. Agent-verifiable

- [x] 6.1 `pytest hub/tests/ -q` — **1500 passed, 10 skipped** (1481 at this change's start).
      `pytest tests/ -q` — **372 passed, 3 skipped**
- [x] 6.2 `npx vitest run` — **751 passed across 79 files** (739 at start); `npx tsc --noEmit` clean
- [x] 6.3 `ruff check hub/ src/` clean; `black` applied — 287 files unchanged
- [x] 6.4 Unit: declining ends the poll rather than running to the deadline
- [x] 6.5 Unit: a declined question neither parks a task nor keeps one parked
- [x] 6.6 Unit: a batch does not fragment under the live-first sort
- [x] 6.7 Live: Hub restarted by exact PID (12492 stopped, port confirmed free, new process
      **21272** bound). Serving process proved new **behaviourally** — `/openapi.json` publishes
      `declined` and `asker_waiting` on `QuestionResponse` and the `POST .../questions/{id}/decline`
      route. Migration `0061` applied to the real database, **no backfill**: 0 declined rows.

      Behavioural probe against a **copy** of the operator's real database (`proj-cddb0827`, agent
      `claude-1`), all three steps as designed: an unanswered blocking question parked the task with
      its text as the reason; declining released it to `in_progress` and cleared the reason; and a
      later run's boundary check did **not** re-park it on the question just closed, while still
      recording a divergence (`div-92e9e7ef`) — so the decline holds and the check resumes rather
      than being permanently disarmed. The copy was deleted; **the operator's live board was not
      written to** (0 probe rows).

### 6b. Human-only — the operator runs these

- [ ] 6.8 Does dismissing feel like it *ended* the question, or like it merely hid it?
- [ ] 6.9 With a stale question and a live one outstanding, is it obvious which one is being asked
      of you?
- [x] 6.10 Is "nobody is waiting on this" the right thing to say about a question whose agent has
      moved on — or does it read as an error?
- [x] 6.11 Does declining ever lose something you wanted back? (D1 keeps the record; nothing surfaces
      it yet — this is the check on whether that matters.)
      **Settled 2026-08-11 by the operator: neither a reason nor a reopen.** Both were offered
      explicitly and both declined. A decline ends the matter; requiring an explanation would tax
      the cheap escape the feature exists to provide, and if the question still matters the agent
      asks again — which the `asker_waiting` sort now keeps out of the way of. **D7 records this.**
      This closes the open question carried since the change was proposed; the shipped behaviour is
      confirmed as intended, not as a deferral.

### 6c. User test guide

**Setup.** The Testbed project, `claude-test-1`, and the Hub serving the new code.

1. **A question can be closed without answering.** Get the agent to ask you something, then dismiss
   it instead of answering.
   *Expect:* the card clears and the composer is free.
   *Failure looks like:* no way to close it, or the same question returning on the next render.

2. **The agent is told.** Do the same while the agent's run is still going.
   *Expect:* the agent continues promptly rather than sitting until its question timeout, and its
   next output shows it knows you declined.
   *Failure looks like:* a long pause, then the agent behaving as though nobody was there.

3. **Dismissing frees a parked task.** Let a question park a task (blocked), then dismiss it.
   *Expect:* the task returns to In Progress and the purple "Waiting on you" banner clears.
   *Failure looks like:* a card still saying it is waiting, with no question behind it.

4. **A dead question does not stand in front of a live one.** Let a question go unanswered until the
   agent gives up and asks again.
   *Expect:* the newer question is the one you are asked; the older is marked as no longer waiting.
   *Failure looks like:* being asked the stale one first — the case that started this.

5. **Answering still lands where you are looking.** With two questions outstanding, answer the one on
   screen.
   *Expect:* your answer resolves the question you were shown.
   *Failure looks like:* the answer landing on the other one.
