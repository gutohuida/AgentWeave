# Design — A batch of answers arrives as one turn

## Context

Two delivery paths exist and only one of them knows about batches.

`ask_user` polls every question id it created and returns when all have resolved
(`mcp_server.py:329-333`). It is batch-aware and correct.

`POST /questions/{id}/answer` decides per question whether to queue
(`questions.py:213-240`). It has never read `batch_id`. Where the asker is gone, it produces one
queue entry — one turn — per answer.

The two are not redundant. They cover different states: the tool covers "the asker is alive and
holding the call open", the endpoint covers "nobody is waiting, so this has to reach the agent as
new input". The endpoint is where the defect is.

## Decisions

### D1 — Delivery is per batch; recording stays per answer

An answer is persisted, broadcast, and releases its parked task immediately, unchanged. What moves
is the queue entry: it is created on the answer or decline that **completes** the batch, and carries
all of it.

Splitting the two is what keeps the existing guarantees intact. *"An answer survives an
interruption"* is a spec scenario, and it holds because persistence never waited on anything.
Deferring the *write* as well as the delivery would have broken it and put the operator's answers in
browser memory.

**Rejected:** batching in the UI, holding answers until the operator finishes and submitting once.
It loses answers on reload, and it makes the browser responsible for a guarantee the database was
already providing.

**Rejected:** keeping per-answer entries and having the *scheduler* coalesce them. The queue would
then hold entries that must not be delivered individually, and every reader of the queue would need
to know that. The entry that exists should be the entry that is meant.

### D2 — A batch completes when every question is answered or declined

Not "every question is answered": a decline is the operator resolving it, and
`2026-08-11-declining-a-question` D2 already establishes that a decline is a decision handed back
rather than an absence. A batch whose remaining questions are declined is finished.

Consequence, stated because it is the risk this design takes on: **a batch nobody finishes is never
delivered.** Today its answers would trickle out one turn at a time. Under D1 they sit recorded and
undelivered until the operator answers or declines the rest.

That is the correct trade — an answer arriving as its own turn is the defect being fixed, so
delivering *some* answers early is not a fallback worth preserving — but it is only acceptable if
the state is visible, which is D5. A part-answered batch must not look like answers that vanished.

**Rejected:** delivering a partial batch after a timeout. It reintroduces the split delivery on a
delay, and picks a number that would be wrong for both the operator who stepped away for a minute
and the one who closed the laptop.

### D3 — The delivered entry carries every answer in the batch, including ones no run received

Scope the entry by `batch_id`, not by "answers given since the run ended".

This rescues an answer that is currently lost outright. If the asking run dies partway through the
operator's stepping, the answers given *before* it died were recorded with `asker_still_waiting`
true — so nothing queued — and the tool call never returned, so nothing consumed them. They reach
nobody. Reading the batch from the database rather than tracking what happened since means they are
included by construction, without needing to detect the case.

Order is `batch_index`, which is the order the agent asked in. `ask_user`'s own return is documented
as "one entry per question, in the order you asked them"; the queued form should not disagree with
the tool form about something as cheap as ordering.

### D4 — A decline is delivered as a decline, not as an omission

The delivered text names every question in the batch, each with its answer or with the fact that the
operator declined it.

Omitting declined questions would leave the agent unable to distinguish "the operator passed on
this" from "this was never asked" — and those call for opposite behaviour. The tool return already
makes this distinction explicitly (`answered=True` / `declined=True` / neither), for reasons its
docstring spells out. The queued path is the same information reaching the same agent by a different
route, and it should not quietly lose a distinction the other route treats as load-bearing.

### D5 — A batch that is not delivered yet says so

Because nothing reaches the agent until the batch completes, the panel states how many of the batch
are answered and that they are sent together.

Without it the change trades a visible annoyance for an invisible one: today the operator sees the
agent react too early, which is wrong but legible. Under D1 they would answer two of three, see
nothing happen, and have no way to know the agent is waiting on the third rather than ignoring them.

The existing step counter ("2 of 3") is *position*, which the current spec is explicit about — it is
not the same statement and does not replace this one.

### D6 — Nothing is queued when a batch produced no answers

A batch resolved entirely by declines queues nothing, matching what a single declined question does
today: *"unlike an answer, a decline carries no content for the agent to act on beyond the fact
itself"* (`questions.py:300-301`).

The alternative — delivering "you asked three things and the operator declined all of them" — is a
turn spent telling an agent that nothing was decided. Where an agent is alive it already learns this
through the tool return, which is the path that can act on it.

### D7 — A batch of one is unchanged

A single question has `batch_size` 1 and completes on its only answer or decline, so it produces
exactly the entry it produces today. This is why the model's *"a question asked on its own is simply
a batch of one"* is worth keeping: the new path needs no special case, and the old behaviour is a
consequence rather than a branch.

## Risks / Trade-offs

- **An abandoned batch strands its answers** (D2). Mitigated by D5, not eliminated. The operator's
  route out is declining the rest, which the panel already offers.
- **The delivered turn is longer** — several questions and answers in one entry rather than one. That
  is the point, and it matches what a live asker already receives.
- **A batch is delivered later than its first answer was given.** Deliberate: the agent should act on
  the operator's decisions once, having seen all of them, rather than starting on the first while the
  rest are still being made.
- **Two answers completing concurrently could both see the batch as complete** and queue twice. The
  completion check and the entry creation happen in one transaction; the test for it is 4.6.

## Migration Plan

None. `batch_id`, `batch_index` and `batch_size` already exist and are already populated by
`POST /questions/batch`. Questions predating them have `batch_size` 1 by server default, so they are
batches of one and behave as they always did (D7).

In-flight state at deploy: a partly-answered batch whose earlier answers already queued keeps those
entries — they are real operator input and deleting them would discard it. Its remaining answers
deliver as a batch. The seam is one turn's worth of duplication in the worst case, against silently
dropping something the operator said.

## Open Questions

- **Should an abandoned batch eventually deliver?** D2 says no, on the grounds that no defensible
  deadline exists. If part-answered batches turn out to be common in practice rather than a corner,
  the answer may be an explicit operator action ("send what I have") rather than a timer.
