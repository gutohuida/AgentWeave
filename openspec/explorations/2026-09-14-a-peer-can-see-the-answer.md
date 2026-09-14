# A peer can see the answer

**2026-09-14, day window, I-1 brief 7 of 11.** This is an improvement brief, not a proposal: there
is no change directory and no tasks. Source: `spec-queue/observations/2026-09-14-LoopEngine.md`,
`## Improvements` item 7, `#### tester` item 4 and `### Architect` item 5.

## What we saw

**A reviewer was told to wait on an answer it could not read.**
- **The question was the Architect's.** Overnight the Architect asked the operator whether FR-70's
  "missing" state should pause a loop on its first iteration (`q-dc3b14272b96`). It then told
  `tester` not to decide the evidence that hinged on it.
- **The waiting was `tester`'s.** At 03:51 `tester` called `get_answer` on that id to see whether it
  could now decide. It got *"Question not found"*. The route answers 404 for a question another
  agent asked (`hub/hub/api/v1/agent_actions.py:722-727`). That scoping is deliberate.
- **So the waiting agent kept its own record.** `tester`'s saved note on the task names the open
  question and records that `get_answer` returns 404 for it (brief 8,
  `project-notes-inside-the-product`). The Architect polled `get_answer` itself four times between
  03:54 and 04:39, each inside a turn woken for something else, each *"pending": true*.
- **Nobody answered overnight, so here nothing was lost.** But the shape is the one F356 describes
  from the other side: when an answer does arrive, the agent whose work it unblocks has no way to
  learn it. The only route is the asker noticing and relaying, and the asker is often mid-thread with
  someone else or has hit the hop budget (21 suspensions).

## What would change

An agent that is waiting on the operator's answer to a peer's question can read that answer, and is
told when it arrives. The cleanest form uses a link the Hub already half-has: a question can name the
task it concerns (`Question.blocked_task_id` exists, but only for the task its asker parked). Then:
1. `get_answer` admits a question asked by a peer **on a task the caller holds or reviews**, not only
   one the caller asked. Every other question stays a 404, as today.
2. When such a question is answered, the Hub queues a short notice for the agents on that task,
   carrying the answer, the same way an answer reaches an asker whose run has ended.

Part 2 is what actually helps. Part 1 alone would still leave `tester` polling.

## Why it matters

It helps the agent whose work is unblocked by a decision, which on a team with a coordinator is
usually not the one who asked. On LoopEngine the reviewer held evidence undecided on an open question
and had no way to learn the answer except the asker relaying it. With this, the operator's answer
would have reached `tester` directly. The polling (four calls by the Architect, one by `tester`) and
the saved note recording the 404 would not have been needed.

## Rough cost — a code-read estimate

- **The read:** `get_own_question` (`hub/hub/api/v1/agent_actions.py:715-728`) compares
  `question.from_agent` with the calling agent, by name. It would also admit the case above.
- **The link:** `Question.blocked_task_id` (`hub/hub/db/models.py:970`) records only a task the
  question *parked*. A question about a task nobody parked needs its own column, say `task_id`, and
  `ask_user` a way to set it. That is **a migration**, and an argument on `ask_user` in
  `hub/hub/mcp_server.py`, **which F354 keeps out today**. Without that argument, the task could be
  inferred from the asking run's bound task, which needs no tool change.
- **The notice:** `answer_question` (`hub/hub/api/v1/questions.py:304-400`) queues an answer only for
  `from_agent` (`_deliver_batch_if_complete`, `:83-120`). A second recipient is a second entry. It
  must share F356's repair, because both decide who receives an answer and when.
- **Capabilities:** `openspec/specs/agent-capability-plane` (questions), `run-task-binding` (*"An
  answer reaches an asker whose run has ended"*, `:639`), and `conversation-checkpoint`.
- **API shape:** `get_answer` admits more ids. The response shape is unchanged. No UI.

## Risks and open questions

- **The scoping is unspecified.** No requirement says a question is readable only by its asker. The
  `from_agent` check is code, not spec. A spec loop would write the rule down for the first time, so
  it must choose it on purpose.
- **An operator's answer can be private to the asker.** An operator who answers the Architect may not
  expect `tester` to read it. Is a task-scoped question shared with the task's agents by default?
  That is the operator's call.
- **"Holds or reviews" must be read at answer time**, not at ask time, because reviewers change.
- **Order.** After F356. Both change who an answer reaches, and F356 is the loss of the asker's own
  answer, which matters more.

## The decision, in one line

Approve a spec loop, after f356 is built, for *an answer to a question about a task reaches the
agents on that task*, with the operator choosing whether such answers are shared by default.
