# Tasks

**Not started, and not to be started without a decision on `design.md`'s open questions** — in
particular the edge set in D2 and D5's choice about how a blocked task escapes the divergence check.
`TRANSITIONS` is what B3 and B4 will be written against, so its shape is cheap to settle now and
expensive to revise later.

Ordered by dependency. 1–3 are the waiting status; 4–5 the conversation binding; 6 the operator's
surface; 7 specs; 8 verification.

## 1. The status

- [ ] 1.1 Add the ninth status and its four edges to `hub/hub/task_transitions.py` per design D2,
      with the docstring stating why `blocked → completed` is absent
- [ ] 1.2 Add it to the two pinned declarations — `src/agentweave/constants.py` and
      `hub/hub/schemas/tasks.py` — which `hub/tests/test_task_transitions.py` already asserts agree
- [ ] 1.3 Tests for each edge, and for the two refusals: from `pending`, and straight to `completed`

## 2. Blocking is observed, not asserted

- [ ] 2.1 Link a blocking `Question` to the task it blocked (design D4); migration `0059`, guarded
- [ ] 2.2 At the run boundary, move a bound task to the waiting status when the run ends with an
      unanswered blocking question, `origin='runtime'`, attributed to the run
- [ ] 2.3 Answering that question returns the task to `in_progress`, in
      `hub/hub/api/v1/questions.py` where the answer lands
- [ ] 2.4 Refuse the waiting status from any agent actor, in `update_task_for_actor` beside the
      divergence-policy guard
- [ ] 2.5 Tests: an agent cannot reach it; the operator can; a timed-out question leaves the task
      waiting (design Open Question 2)

## 3. A waiting task is not divergent

- [ ] 3.1 Implement D5 option (1): the divergence check excludes a task in the waiting status,
      leaving `origin` meaning "who caused this" rather than bending it to make the check simpler
- [ ] 3.2 Tests: no divergence and no response run while waiting; the check applies again once
      released

## 4. The binding moves to the conversation

- [ ] 4.1 `conversations.task_id`; migration `0060`, guarded, no backfill
- [ ] 4.2 At spawn, inherit the conversation's binding when delivered entries name no task; an entry
      that names one wins and rebinds the conversation
- [ ] 4.3 Keep `Run.task_id` as the per-run record (D6) and assert in test that it is still what
      transitions and divergences are attributed to
- [ ] 4.4 Tests: a follow-up composer turn is bound and checked; naming a different task rebinds;
      an unbound conversation stays unbound

## 5. Releasing

- [ ] 5.1 Release on a terminal transition of the bound task
- [ ] 5.2 An explicit operator release
- [ ] 5.3 Test that nothing infers a release from conversation content (D7)

## 6. The operator's surface

- [ ] 6.1 The board shows a waiting task — column or treatment, per design Open Question 3
- [ ] 6.2 The card says what it is waiting for, linking the question
- [ ] 6.3 Unblock from the card
- [ ] 6.4 Show and release a conversation's binding
- [ ] 6.5 `npm run build`, `rm -rf hub/hub/static/ui`, copy, confirm with `diff -rq`

## 7. Specs

- [ ] 7.1 Apply the three delta specs
- [ ] 7.2 `npx openspec validate --specs --strict` and `--changes --strict`

## 8. Verification

### 8a. Agent-verifiable

- [ ] 8.1 `pytest hub/tests/ -q` and `pytest tests/ -q` — all pass, counts no lower than at start
- [ ] 8.2 `cd hub/ui && npx vitest run`, `npx tsc --noEmit` — pass and clean
- [ ] 8.3 `ruff check hub/hub/ hub/tests/` clean; `black` applied
- [ ] 8.4 Unit: every new edge accepted, `pending → blocked` and `blocked → completed` refused
- [ ] 8.5 Unit: a run ending with an unanswered blocking question leaves its task waiting, recorded
      `origin='runtime'` and naming the run
- [ ] 8.6 Unit: answering releases it; an agent requesting it is refused
- [ ] 8.7 Unit: a waiting task produces no divergence and no response run
- [ ] 8.8 Unit: turn 2 of a bound conversation is bound and checked — the hole this change exists
      to close
- [ ] 8.9 Live: behavioural probe against a database copy, and confirm the serving process is new by
      what it publishes rather than by a 200

### 8b. Human-only — the operator runs these

- [ ] 8.10 When an agent asks you something mid-task, does the board tell you *that* is why nothing
      is moving — without you having to work it out?
- [ ] 8.11 Does a waiting task read as "someone needs you" rather than as a failure?
- [ ] 8.12 Now that every turn of a bound conversation is checked: is the volume of stalled markers
      informative or is it noise? **This is the real answer to the previous change's Open Question 1**,
      which could not be judged while only the first turn was checked
- [ ] 8.13 Does a conversation staying bound ever surprise you — does it keep attributing work to a
      task you had moved on from?

### 8c. User test guide

**Setup.** `testbed/`, one project, one agent with a runner that can ask questions. Confirm the Hub
is serving the new code first.

1. **A question parks the task, visibly.** Start work on a task from its card. Give the agent
   something genuinely ambiguous so it uses `ask_user`, and do not answer.
   *Expect:* when the run ends, the task shows as waiting and names the question.
   *Failure looks like:* the task still says in progress, or shows as stalled — the agent asked, it
   did not drop it.

2. **Answering resumes it.** Answer the question.
   *Expect:* the task returns to in progress.
   *Failure looks like:* it stays waiting, or jumps to completed.

3. **A waiting task is not retried.** Repeat step 1 with the policy set to "Try again once".
   *Expect:* no new run. The agent is waiting on you, not stuck.
   *Failure looks like:* a run starting while the question is still unanswered — the case that made
   this change necessary.

4. **The agent cannot park it itself.** Ask the agent, in plain words, to mark the task blocked
   without asking you anything.
   *Expect:* it cannot; there is no such operation.
   *Failure looks like:* the task showing as waiting with no question behind it.

5. **A follow-up turn is still checked.** Start work from a card, then reply in the composer and let
   that turn end without the task moving.
   *Expect:* that turn is checked too — this is what the change fixes.
   *Failure looks like:* only the first turn ever being noticed.

6. **The binding lets go.** Approve the task, then talk to the agent in the same conversation.
   *Expect:* nothing further is attributed to the finished task.
   *Failure looks like:* stalled markers on work you have already approved.
