# Test guide — a task is attended only by a turn that will reach it

## Agent-verifiable

1. **The held assignee is not re-briefed when a peer's name sorts first** (F370). Task 1.1 fails
   before and passes after, in both insertion orders. 1.2 is its control. The assertion is a count
   of `job` entries, so it cannot pass vacuously.
2. **An idle assignee whose turn cannot start is not re-briefed** (F368). Task 1.3 fails before and
   passes after. 1.4 proves a refused head is still retried by the briefing, as today.
3. **A review nobody is doing is named although someone else has input about it** (F371). Tasks
   1.5 and 1.6 fail before and pass after. 1.8 and 1.9 are the controls that stop the fix from
   over-reaching: a staffed review still queued, and a running review, stay in flight.
4. **A refused review delivery is named with its refusal** (D3, D4). Task 1.7.
5. **Nobody's availability moved** (D5). Task 1.12 over every existing staging.
6. **One helper.** `grep -rn "tasks_with_a_turn_pending_or_running\|task_agent_pairs_with_a_turn_queued" hub/`
   finds nothing after the change.

## Human-only

1. On a trial Hub (`:8010`), a flow with a completed task and a reviewer that is busy: the flow card
   says the review is in flight, naming the reviewer. Send a message naming that task to a third
   agent. The card still says in flight (the reviewer's own input is queued).
2. Withdraw the reviewer's queued review input from its conversation (Discard). On the next firing
   the card names the reviewer and says nobody is reviewing it, and offers the three exits. It does
   not say "none is queued" although the third agent's message still is.
