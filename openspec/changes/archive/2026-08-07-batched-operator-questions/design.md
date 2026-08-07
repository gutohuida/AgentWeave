# Design

## Decision 1 — one row per sub-question, sharing a batch identity

Rejected: one `Question` row carrying a JSON list of sub-questions. Every existing reader — the
answer endpoint, the options storage, the questions list, the unasked-question backstop's
`created_by_run_id` check, the operator's questions panel — is written against one row meaning one
question. Folding a list inside would fork all of them.

With one row each, `batch_id` is the only new concept, and everything that works today keeps working.
A question asked outside a batch is a batch of one.

## Decision 2 — each answer is saved as it is given

T3 holds every draft in memory and submits the whole set at the end
(`buildPendingUserInputAnswers` returns `null` until all are answered). That is right for T3, where
the questions arrive as one in-memory pending input.

Here the agent is blocked for up to `QUESTION_ANSWER_TIMEOUT` (240s) while the operator works through
three questions. A refresh, a navigation, or a closed tab in that window would discard every answer
already given and leave the agent waiting on a batch that now has no one answering it. Rows are
durable; drafts are not.

**Consequence, accepted:** the operator cannot go back and change an earlier answer within a batch.
Once answered, a sub-question is answered. This is the honest cost of durability, and the smaller
loss — three questions is a short walk, and a wrong answer is recoverable by telling the agent,
which is a conversation the operator was already having.

## Decision 3 — `batch_size` is denormalized onto the row

The step counter needs to say `2/3` while only the *unanswered* rows are on hand: the panel fetches
unanswered questions, and answered ones drop out of that list by design.

Storing `batch_size` on each row makes the counter derivable from what is already fetched —
`answered = batch_size - remaining_in_batch` — with no second request and no endpoint that returns
answered rows just to count them. It is denormalized and immutable: a batch's size is fixed when it
is created.

## Decision 4 — one selector, used by both the card and the composer

Today `AgentQuestionCard` picks `pending[0]` and `AgentOutputPanel` separately picks its own
`pendingQuestion`. With one question outstanding those always agree. With a batch they can diverge on
ordering, and the failure is silent and bad: the operator reads question 2 and their answer is
recorded against question 1.

So `activeQuestionFor(questions, agent)` lives in `hub/ui/src/lib/` and returns the active question
plus its step position. Both call it. Ordering is `batch_index`, then `created_at` — a total order,
not whatever the API happened to return.

## Decision 5 — 1 to 4 questions

Claude Code's `AskUserQuestion` caps at 4, and the cap is doing real work: past a handful, a
step-through stops feeling like answering and starts feeling like a form. The lower bound is 1 rather
than 2 because a single question is the common case and must not need special handling.

## Decision 6 — the tool always takes a list

Rejected: accepting either a single question or a list. That is the tolerant reader the previous
change already decided against — a shape an agent can get wrong in two ways instead of one. Claude
Code's own tool always takes a list, and agents demonstrably handle it.

## Risks

- **A partially-answered batch whose agent has already timed out.** The remaining rows stay pending
  and the operator answers into nothing. Same exposure as a single unanswered question today, and the
  same mitigation: the tool tells the agent plainly that nobody answered.
- **Ordering by `batch_index` assumes it is set correctly at creation.** It is assigned by position in
  the submitted list, in one place.
