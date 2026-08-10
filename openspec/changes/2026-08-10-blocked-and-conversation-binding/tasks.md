# Tasks

**Unblocked 2026-08-10.** All five of `design.md`'s open questions were settled with the operator
before any code was written (R1–R5), along with D4's column-vs-join-table and D5's choice of how a
blocked task escapes the divergence check. `TRANSITIONS` is what B3 and B4 will be written against,
so its shape was cheap to settle now and expensive to revise later.

The status name is **`blocked`**, and per R3 it renders as a treatment inside the `in_progress`
column rather than as a ninth column.

Ordered by dependency. 1–3 are the waiting status; 4–5 the conversation binding; 6 the operator's
surface; 7 specs; 8 verification.

## 1. The status

- [x] 1.1 Add the ninth status and its four edges to `hub/hub/task_transitions.py` per design D2,
      with the docstring stating why `blocked → completed` is absent. Also `STATUS_BLOCKED`, named
      because four modules must ask "is this waiting on a person?" and a bare literal in each is how
      one ends up spelled differently
- [x] 1.2 Add it to the two pinned declarations — `src/agentweave/constants.py` and
      `hub/hub/schemas/tasks.py` — which `hub/tests/test_task_transitions.py` already asserts agree
- [x] 1.3 Tests for each edge, and for the two refusals: from `pending`, and straight to `completed`
- [x] 1.4 **Found by the pinning, not by inspection:** a *third* declaration exists —
      `mcp_server.TaskStatus`, the agent-facing `update_task` parameter. `blocked` is deliberately
      **withheld** from it, so an agent cannot express the request at all (D3); the omission is
      asserted in `test_task_transitions.py` and `test_mcp_tool_schemas.py` so nobody "completes the
      list" later
- [x] 1.5 **Hazard closed at the same time:** `blocked → in_progress` is a legal run edge, so
      `bind_run_to_task` would have silently unparked a blocked task merely by a run starting — and
      that run's end would then have recorded a divergence. Guarded explicitly in
      `run_task_binding.py`

## 2. Blocking is observed, not asserted

- [x] 2.1 Link a blocking `Question` to the task it blocked — a nullable column, not a join table
      (design D4); migration `0059`, guarded. Also `tasks.blocked_reason` in the same migration
- [x] 2.2 At the run boundary, move a bound task to the waiting status when the run ends with an
      unanswered blocking question, `origin='runtime'`, attributed to the run
- [x] 2.3 Answering that question returns the task to `in_progress`, in
      `hub/hub/api/v1/questions.py` where the answer lands
- [x] 2.4 Refuse the waiting status from any agent actor, in `update_task_for_actor` beside the
      divergence-policy guard
- [x] 2.5 Tests: an agent cannot reach it; the operator can; a timed-out question leaves the task
      waiting and nothing unparks it (R2); a **non-blocking** question does not block it (R1)
- [x] 2.6 A block carries a reason (R5) — required on an operator-set block, filled from the
      question text on a runtime-set one
- [x] 2.7 **Found while wiring 2.3:** `ask_user` only holds the tool call open while the run lives,
      so a blocking question that outlived its run (timed out, or the run crashed) had nobody awake
      to receive the answer — and the existing "a blocking asker is already awake" shortcut dropped
      it silently. That is exactly the question that parked a task. Now queued when the asking run
      is *known* to have ended; the presumption is otherwise left alone

## 3. A waiting task is not divergent

- [x] 3.1 Implement D5 option (1): the divergence check excludes a task **whose status at the run
      boundary is `blocked`** — not merely one blocked by this run — leaving `origin` meaning "who
      caused this" rather than bending it to make the check simpler
- [x] 3.2 Tests: no divergence and no response run while waiting; the check applies again once
      released
- [x] 3.3 **A `blocked` edge obligates the status control.** Because a hand-set block must name what
      it is waiting for (R5), a menu offering "Blocked" must collect a reason before it sends, or it
      offers a move that then fails. `test_every_move_the_endpoint_offers_is_actually_accepted`
      encodes this; **task 6.3 must honour it**

## 4. The binding moves to the conversation

- [x] 4.1 `conversations.task_id`; migration `0060`, guarded, no backfill
- [x] 4.2 At spawn, inherit the conversation's binding when delivered entries name no task; an entry
      that names one wins and rebinds the conversation
- [x] 4.3 Keep `Run.task_id` as the per-run record (D6) and assert in test that it is still what
      transitions and divergences are attributed to
- [x] 4.4 Tests: a follow-up composer turn is bound and checked; naming a different task rebinds;
      an unbound conversation stays unbound; a deleted or foreign task unbinds rather than failing
      the turn

## 5. Releasing

- [x] 5.1 Release on a terminal transition of the bound task — `approved`/`rejected` only.
      `completed` and `under_review` deliberately excluded: work under review comes back often, and
      releasing there would unbind precisely the thread about to do the revisions
- [x] 5.2 An explicit operator release — `DELETE /agent/{agent}/conversations/{id}/task`, idempotent
- [x] 5.3 Test that nothing infers a release from conversation content (D7) — a source scan, since
      the failure it guards against is a *new* caller quietly clearing a binding

## 6. The operator's surface

- [ ] 6.1 The board shows a blocked task as a **treatment inside the `in_progress` column** (R3) —
      the card does not move when it blocks or unblocks
- [ ] 6.2 The card says what it is waiting for (R5's reason), linking the question
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
