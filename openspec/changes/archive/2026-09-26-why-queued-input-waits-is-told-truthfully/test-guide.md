# Test guide — why queued input waits is told truthfully

## Agent-verifiable

1. **A held send tells its sender** (F361). Tasks 1.1 and 1.4 fail before and pass after; 1.2 is the
   control that an ordinary send is unchanged.
2. **A listed message makes no claim.** Task 1.3.
3. **The entry is not written** (D2). Task 1.5.
4. **A holder that has gone is not reported as holding** (F289). Task 1.6 fails before and passes
   after; 1.7 (the F97 test) is the control that the live case still names the holder.
5. **A remembered refusal says it is remembered.** Task 1.8.
6. **The status route does not 500 on a failed check, and spawns no raw git.** Tasks 1.9 and 1.10
   (review 2026-09-24).

## Human-only

1. On a trial Hub with the hop budget set to 1, message agent A and ask it to message agent B, and
   ask B to reply to A. B's reply is at depth 2, past the budget. Read B's `send_message` tool result
   in its turn: it says the message was recorded and not delivered, names the depth and the budget,
   and does not tell B to resend. A's timeline still shows the amber *Autonomous continuation
   paused* banner with Continue.
2. With an agent's input refused once for a reason you then fix, open that agent's conversation:
   the "N waiting" line reads *"the last delivery attempt was refused: …"*, not a present-tense
   claim.
