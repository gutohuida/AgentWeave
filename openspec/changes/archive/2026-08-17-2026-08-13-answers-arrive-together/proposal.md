# A batch of answers arrives as one turn, not one turn per answer

## Why

**The operator answers the first question of a batch and the agent starts work on it while they are
still deciding the second.** Reported from real use: *"in multiple answers each answer is
individually sent. Which makes the agent works on the first one right away while I'm deciding on the
others."*

The tool half is already right. `ask_user` holds its turn until every question in the batch resolves
(`mcp_server.py:330-333`), so an agent whose run is still alive receives the whole batch at once.
That is the path the existing spec describes and it works.

The defect is the other path. When the asking run is no longer waiting — it timed out, it was
interrupted, it crashed, or the question was non-blocking — `POST /questions/{id}/answer` creates a
queue entry per answer (`questions.py:228-240`). Each entry is a turn. So a three-question batch
becomes three turns, delivered as the operator picks each option, and the agent acts on answer one
against a batch it was told would arrive together.

This is visible in the live database: an `inbound_queue_entries` row reading
`"Question: What should the app primarily help people do?\n\nAnswer: …"` — one answer, one entry, its
own turn.

**A second defect sits behind the first, and is worse.** An answer recorded while the asking run was
still alive but which the run never received — because it died mid-wait — is delivered to nobody at
all. `asker_still_waiting` was true when it was recorded, so nothing queued; the tool call never
returned, so nothing consumed it. The operator answered and the answer went nowhere. Today the
batch's *later* answers queue individually and the earlier one is silently dropped.

Nothing in `agent-capability-plane` covers delivery when the asker is gone. The requirement *"An
agent can ask several questions in one turn"* describes the tool's wait; *"The operator answers a
batch one question at a time"* describes the panel. Neither says what reaches the agent when nobody
is waiting, so the per-answer behaviour was never a decision — it is what the single-question path
did, applied to a batch.

## What Changes

- **Delivery becomes per batch.** When the asker is no longer waiting, an answer does not queue on
  its own. The batch queues **once**, when every question in it has been answered or declined.
- **Recording stays immediate.** Each answer is still persisted, broadcast, and still releases a task
  it had parked, the moment the operator gives it. Only *delivery* waits, so a reload still resumes
  a part-answered batch exactly as the current spec requires.
- **The delivered turn carries the whole batch**, in the order asked — including any answer recorded
  while the run was still alive and which it never received. That answer reaches the agent for the
  first time.
- **A declined question is delivered as declined**, not omitted. The agent must be able to tell
  "they passed on this" from "this was never asked", because those call for different behaviour.
- **An unfinished batch is visibly unfinished.** Since nothing is delivered until the batch resolves,
  the panel says how many are answered and that they go together, so a part-answered batch does not
  read as answers that vanished.

## Capabilities

### Modified Capabilities

- `agent-capability-plane`: the requirement that an agent can ask several questions in one turn gains
  what happens when the asking run is gone before the answers are — delivery is per batch, carries
  every answer including ones the dead run never received, and distinguishes a decline from silence.

## Impact

**Behaviour** — `POST /questions/{id}/answer` stops creating a queue entry per answer for a batched
question. It creates one entry for the batch, on the answer or decline that completes it.

**Recovered** — answers recorded against a run that died mid-wait, currently delivered to nobody.

**Unchanged** — the tool's own wait; the panel's one-at-a-time stepping; declining; task release;
the `question_answered` broadcast; and a batch of one, which behaves exactly as a single question
does today because it completes on its only answer.

**No migration.** `batch_id`, `batch_index` and `batch_size` already exist on `questions`
(`models.py:765-769`); this change reads them where it previously ignored them.

## Non-Goals

- **Not changing how the operator answers.** One question at a time, advancing as they go, is
  specified behaviour and stays. This changes when the *agent* hears about it, not how the operator
  works.
- **Not batching the operator's answers client-side.** Holding them in the browser until the batch
  finishes would lose them on reload and contradicts *"An answer survives an interruption"*. Answers
  are persisted as given; delivery is what is deferred.
- **Not delivering a partly-answered batch on a timer.** A batch completes when its questions are
  resolved, not when a clock says so. What an abandoned batch should do is a real question and it is
  handled by making the state visible, not by guessing at a deadline.
- **Not changing the decline contract.** A decline still queues nothing on its own and still releases
  a parked task. It now also counts toward completing its batch, and is named in the delivered text.
- **Not touching the still-waiting path.** An agent that is alive already receives the batch
  together, and this change must not alter that — including the measured behaviour that a waiting
  asker is not *also* sent a queue entry.
