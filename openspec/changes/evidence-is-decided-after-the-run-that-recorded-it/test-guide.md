# Test guide — evidence is decided after the run that recorded it

## Agent-verifiable

1. **A mid-run decision is refused, and clears by itself.** Tasks 1.1-1.3: 409 `recording_run_live`
   while the run is registered, 200 once it is not. 1.1 and 1.2 fail on today's code.
2. **Nothing wedges on a crashed run.** 1.4: a `running` row the registry does not hold is decidable.
3. **Refusal order is unchanged for the other refusals.** 1.5.
4. **A same-turn re-record revises instead of refusing.** 1.7 fails today; 1.8 (different runs) keeps
   refusing; 1.9 (reworded requirement) makes a new row.
5. **The agent is not told to commit.** 1.10.
5a. **A second record in a new, dirty turn revises that turn's row.** 1.7b.
5b. **A merge failure after a decision does not 500 the decision.** 1.14 — fails today (measured).
6. **The live trial** (3.1), with the 409 body recorded verbatim.

## Human-only

1. Open a document whose requirement has evidence an agent is recording right now (the agent is
   mid-turn). Once `the-coverage-bar-takes-the-evidence-decision-it-asks-for` has shipped, the row
   should read as still being recorded, with its buttons held. Before that change ships there is no
   screen; nothing to check by eye.
2. After the turn ends, the same row offers Accept and Reject, and the commit it shows is the one the
   turn produced, not the one it started from.
