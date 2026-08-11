# Design — declining a question

## Context

From the operator testing the blocked status in the running app on 2026-08-11. The full observation
is in `proposal.md`; the short version is that a question has no exit but an answer, and a dead one
queues in front of a live one.

All three decisions below were settled with the operator before implementation.

## Goals / Non-Goals

**Goals.** The operator can end a question without answering it, an agent waiting on one is told
rather than left to time out, and the screen orders questions by whether anyone is actually waiting.

**Non-Goals.** As stated in `proposal.md`.

## Decisions

### D1 — Declining is a terminal state of its own, not an empty answer

`questions.declined`, beside `answered`, rather than `answered=True` with a null answer.

An empty answer is a claim the operator said nothing *in response*; declining is the claim they
chose not to respond at all. Collapsing them would make every existing reader of `answered` treat a
decline as an answer — including `unanswered_blocking_question`, which would then stop parking tasks
for the right reason and start failing to park them for the wrong one.

It also keeps `answer`/`answer_labels` meaning what they say. A declined question has no answer, and
a reader that finds `answered=True` with nothing in `answer` has to guess which case it is in.

*Rejected: a `status` enum replacing `answered`.* Cleaner on paper, and it would touch every query,
schema and UI path that reads `answered` today, for a distinction two booleans express exactly.

### D2 — A declining ends the agent's wait

`ask_user` polls each question until it is answered; it now stops on answered **or** declined, and
reports which. The entry comes back `answered: False, declined: True`.

The alternative — let the agent wait out `AW_QUESTION_TIMEOUT` — spends real wall-clock and real
tokens waiting for something that has already been decided, and arrives at exactly the same state
the agent would reach anyway. Worse, it makes declining feel like it did nothing: the operator
clears their screen and the agent sits there.

Told, rather than told nothing, because the two mean different things to the agent. A timeout means
"nobody was there"; a decline means "someone was there and chose not to say". The second is
information: it says the decision is the agent's to make.

**The distinction is deliberately not enforced beyond that.** What an agent does with a decline is
its own judgement — this change tells the truth and stops there.

### D3 — Declining releases a task the question parked

The operator has said the answer is not coming, so the task is no longer waiting on them. Leaving it
`blocked` would be a card claiming to wait for something that will never arrive, with no question
behind it — the state R5 (a block names what it is waiting for) exists to prevent.

It returns to `in_progress`, the same edge and the same actor as answering: the operator caused it,
so `origin='actor'`. From there the ordinary run-boundary check applies again, which is right — work
that is no longer waiting on a person is work that can be dropped in the ordinary way.

Same shape as `release_block_for_answer`, so it is the *same function*, taking the question rather
than the answer. Two functions differing only in what they are called would be two things to keep in
step, and a block released one way but not the other is precisely the bug this is guarding.

### D4 — A declined question does not park a task

`unanswered_blocking_question` excludes declined rows.

Without it the previous change's mechanism would immediately undo this one: the operator declines,
the task is released, the run ends, the boundary check finds the same still-unanswered blocking
question and parks the task again — on a question the operator has already closed.

### D5 — "Is anyone waiting?" is derived from the asking run, and defaults to yes

`QuestionResponse.asker_waiting`, computed from the asking run's status, not stored.

Stored, it would be a second copy of a fact the `runs` table already holds, and it would go stale the
moment a run ended — which is the exact transition it exists to describe.

**It defaults to `True` when unknown**, matching `_asking_run_has_ended` in the answer path: a
question with no recorded asking run is presumed to have someone waiting. Presuming the opposite
would sort a live question behind dead ones and mark it as inert, which is worse than the reverse.

### D6 — Live questions sort first; batches stay contiguous by construction

The sort key becomes `(not asker_waiting, batch_index, created_at)` — previously
`(batch_index, created_at)`.

Every question in a batch is created by one `ask_user` call from one run, so every question in a
batch shares an `asker_waiting` value and they sort together. That is what makes it safe to put a
whole-queue predicate ahead of the within-batch order, and it is asserted rather than assumed.

`activeQuestionFor` is the single selector both the card and the composer's submission read — its
own docstring warns that if the two disagree, the operator reads one question and answers another.
Changing the order here is therefore changing it in one place, which is the whole reason that
selector exists.

### D7 — A decline carries no reason and cannot be reopened

Both were built as questions rather than assumptions, put to the operator on 2026-08-11, and both
were declined. Recorded here because "we never got round to it" and "we decided against it" are
different states, and only the second one is safe for a later session to build on.

A reason field would tax the thing the feature exists to provide. Declining is the *cheap* escape
from a question you do not want to answer; making it demand a sentence first turns a dismissal back
into a reply, which is the friction that produced the original complaint — a question sitting on
screen that the operator had already mentally moved past.

Reopening is worse than merely unnecessary. It reintroduces the loop D4 exists to prevent: a
reopened question is once again an unanswered blocking question, so the boundary check re-parks the
task the decline just released, and the operator's decision is undone by the mechanism meant to
honour it. Guarding that would mean a third state — declined-but-reopenable — for a case the agent
already covers by asking again.

What makes both safe to omit is D5's sorting. The reason a decline felt irreversible was that a
stale question could get back in front of a live one; now that it cannot, "the agent will ask
again" is a real answer rather than a hope. The record is kept either way — `declined` and
`declined_at` are stored, nothing deletes the row — so surfacing declined questions later remains
possible without a migration if the need ever appears.

## Risks / Trade-offs

- **An agent that treats a decline as an answer** → it is told `answered: False`, and the payload
  names the decline explicitly. Beyond that this change does not police what agents conclude.
- **The operator declines something the agent genuinely needed** → the agent proceeds on its own
  judgement, which is the same position it is in after a timeout, and it can ask again.
- **A released task with no run attached** → it sits `in_progress` with nothing running, exactly as
  it does after a late answer releases it. Not new, and not made worse here; the staleness surface
  deferred in R2 is where it belongs.
- **Ordering changes what the composer's send targets** → the risk is real and is why the batch
  contiguity property is tested rather than reasoned about.

## Migration Plan

`0061` — `questions.declined` (NOT NULL, server default false) and `questions.declined_at`
(nullable). Guarded, no backfill: nothing before this migration could be declined, and marking
historical unanswered questions as declined would claim the operator made a decision they never made.
Head assertions bumped in `hub/tests/test_migrations.py` **and**
`hub/tests/test_project_persistence.py`.
