# Test guide — a review no reviewer can approve goes to the operator

## Agent-verifiable

1. **No second reviewer is spent on an operator-only refusal** (F374 point 1). Task 1.1 fails
   before and passes after. The assertion that matters is the absence of a queue entry for the
   second reviewer.
2. **A reviewer who can clear it still gets it.** Task 1.2 (granted), 1.4 (a conflict an agent can
   repair) and 1.5 (the mixed case the gate lets through) are controls that pass before and after.
3. **The operator reads the gate, not the roster** (F374 point 3). Tasks 1.1 and 1.3 check the
   divergence reason; 1.7 checks the flow card's sentence and its 500-character fit.
4. **A failed gate evaluation changes nothing, unless git is what failed.** Tasks 1.6, 1.6b and 1.8;
   a git timeout or `OSError` holds the review for the operator (1.6c, operator 2026-09-24), and the
   predicate's git never runs on the event loop or waits longer than 5 s (1.6d).

## Human-only

1. On a trial Hub, a flow over a document with a requirement; an author records evidence naming a
   commit and completes the task; do **not** accept the evidence. Let the flow staff a reviewer and
   let it end without a verdict (or stop it). Open the flow's card and the event log: the card
   names the task, says approval waits on you, and says to accept or reject the evidence. No second
   reviewer has been started. Accept the evidence, then approve the task yourself: it approves.
