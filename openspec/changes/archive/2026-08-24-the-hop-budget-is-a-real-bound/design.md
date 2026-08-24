# Design

Decided with the operator on 2026-08-23, after reproducing the leak deliberately against a live Hub.

## D1 — Filter the batch, do not just refuse to start

`can_start` asks whether the turn may begin; nothing then asks which entries may ride on it. Those
are different questions and the code only ever asked the first. The fix is a filter at selection,
not a stricter `can_start`: the turn should still start for the entries that are within budget, and
carry only those.

## D2 — The turn's depth is the admitting entry's depth, not `min()`

`min()` was never a decision — it is the incidental result of taking the shallowest thing in the
batch, and it is what makes the counter run backwards. With D1 in place every delivered entry is
within budget, so the admitting entry's own depth is both well-defined and the honest answer to "how
deep is this turn".

Rejected: `max()`. It would over-count a turn that legitimately batches an operator message with a
shallow agent reply, and once D1 filters the batch there is nothing left that `max()` protects
against.

## D3 — A bound needs an exit, or it is a wedge

This is the design's real content, and the operator found it by asking the right question: *if the
budget does not forgive, how does a chain ever continue?*

Without an answer, strict filtering is **worse than today**. The blocked entry sits queued forever
while the agent, prompted by the operator, starts a fresh chain around it — so a real message from
another agent is silently never read, and there is now a duplicate conversation. Today's leak at
least delivers the message.

So the entry gets three dispositions, and the operator picks:

| | |
|---|---|
| **Continue** | re-base to depth 0 and deliver — new |
| **Discard** | `DELETE /queue/entries/{entry_id}` — exists |
| **Raise the budget** | `redrain_queued_agents` already re-evaluates on settings save — exists |

Re-base to 0 rather than granting `+N`: "the operator restarted this chain" is a fact a reader can
reconstruct, where an arithmetic grant leaves a depth whose meaning depends on history nobody
recorded.

## D4 — Most of the surfacing already exists

Worth stating so the implementation is not rebuilt from scratch:

- `hop_budget_exceeded` is computed per entry (`agent_chat.py:187-188`)
- the UI already renders it (`AgentTimeline.tsx:174`, `AgentOutputPanel.tsx:629`)
- queue status already reports `"hop budget exhausted"` (`api/v1/inbound_queue.py:139`)
- withdrawal already exists

What is genuinely new is the delivery filter and the **Continue** action. The rest is connecting
things that are already built and, today, describe a state the scheduler then ignores.

## D5 — Why not "presence forgives, loudly"

The rejected alternative is in the proposal. The reason it loses in one line: the reset would be
per-conversation and unlimited, an operator does eventually say something, and a bound that any
message resets is a rate limit rather than a bound. The objection was never to forgiveness — it is
to forgiveness that happens silently, as a side effect of a `min()`, bundling a blocked message into
an unrelated turn so the operator never learns it was blocked.
