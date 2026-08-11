## Why

Found by the operator on 2026-08-11, testing `2026-08-10-blocked-and-conversation-binding` in the
running app:

> *"We need a way to close the answer box without answering. Why? Because for example it asked me a
> question once, I didn't respond, and then it tried again — I responded. But once I sent an answer
> the first question was still there... In some cases we might want this behavior, in others we
> don't. We need a way to not answer and free the screen."*

Three separate things produce that experience, and only the first is the one being asked for.

**A question has no exit but an answer.** `AgentQuestionCard` renders options and routes the
composer's send to them; nothing closes a question the operator does not intend to answer. The only
other terminal state is `ask_user`'s deadline expiring inside the *agent's* process, which the Hub
never learns about — so the row stays outstanding forever
(`2026-08-10-blocked-and-conversation-binding`, R2, which deliberately left it that way).

**The queue is strictly oldest-first**, so a dead question sits in front of a live one.
`activeQuestionFor` sorts by `batch_index` then `created_at` and takes the head. When an agent asks,
times out, and asks again, the operator is shown the *first* question and their answer is routed to
it — correctly, and confusingly, because the question they are actually being waited on for is the
one behind it.

**Nothing distinguishes a question someone is waiting on from one nobody is.** A blocking `ask_user`
holds its run open only while that run lives. Once it has ended, the question is inert: no tool call
is waiting, and answering it now merely queues a message. The Hub knows the asking run and its
status, and shows neither.

This also has a consequence the previous change created. An unanswered blocking question is what
parks a task as `blocked` — so a question the operator has decided not to answer would otherwise
hold a task waiting on an answer that is never coming, which is the "blocked with no reason" state
R5 exists to prevent.

## What Changes

- **A question can be declined.** The operator closes it without answering, and it stops being
  outstanding.
- **A declining reaches an agent still waiting.** `ask_user` returns as soon as its questions are
  answered *or declined*, rather than waiting out a deadline for an answer that will not come. The
  agent is told which happened, so it can proceed on its own judgement instead of on silence.
- **Declining releases a task the question had parked.** The task returns to the in-progress status
  and re-enters the ordinary run-boundary check.
- **A question nobody is waiting on says so, and moves out of the way.** Questions whose asking run
  has ended are marked, and sort behind live ones, so a dead question never stands in front of one
  an agent is blocked on.

### Non-Goals

- **Declining on the agent's behalf, automatically.** A question left alone stays outstanding
  (R2 stands). Declining is an act the operator takes.
- **Deleting the question.** A declined question is a record that the operator was asked and chose
  not to answer, which is exactly the kind of thing the transition history exists to keep.
- **A reason for declining.** Unlike a block, which someone has to act on, a decline ends the
  matter; requiring an explanation would tax the cheap escape this exists to provide.
- **Reopening a declined question.** The agent has already been told. If it still matters, it asks
  again — which is the path that already works.
- **Changing what a timeout does.** The Hub still never learns about `ask_user`'s deadline.

## Capabilities

### New Capabilities

*(none — both land in capabilities that already exist)*

### Modified Capabilities

- `agent-capability-plane`: what `ask_user` returns when the operator declines, and the rule that
  declining is the operator's alone.
- `task-lifecycle-governance`: declining a question releases the task it parked.

## Impact

**Schema** — `questions.declined` and `questions.declined_at`. Migration `0061`, guarded, no
backfill: nothing before it could be declined.

**Backend** — `hub/hub/api/v1/questions.py` (the decline route, and the asker's state on the
response); `hub/hub/run_task_binding.py` (a declined question no longer parks a task, and declining
releases one); `hub/hub/schemas/questions.py`.

**Agent surface** — `hub/hub/mcp_server.py`: the `ask_user` wait ends on declined as well as
answered, and `get_answer` reports it. This is a change to what an agent is told, so the docstring
is part of the change rather than a note about it.

**Frontend** — `AgentQuestionCard` gains a dismiss control; `activeQuestionFor` skips declined
questions and orders live ones first; the card marks a question nobody is waiting on.

**Risk.** The ordering change is the one with reach: `activeQuestionFor` is the single selector both
the card and the composer's submission use, and its docstring already warns what happens if the two
disagree. The sort key keeps batches contiguous — every question in a batch shares an asking run, so
they sort together — but that is a property to test rather than to assume.
