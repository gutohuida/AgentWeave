# Test guide — an agent can be paused, and keeps its input

## Agent-verifiable

1. **A pause holds against every sender.** Tasks 1.1–1.3 fail today and pass after.
2. **Nothing is lost or counted.** Task 1.2's `delivery_attempts == 0` and 1.4's order.
3. **The race F15 measured is closed.** Task 1.5 — the stub that reads `paused_at` at stop time is what
   proves the order; a test that only checks the end state would pass with the order reversed.
4. **Flows and loops agree with the queue.** Tasks 1.6, 1.7.
5. **The agent plane cannot pause anything.** Task 1.9.

## Human-only

1. On a trial Hub, pause an agent from its header while a peer is chatting with it: the header,
   the roster and the composer's queue line all say "Paused", and Resume delivers what waited.
2. Decide whether an operator's own message to a paused agent should wait (this design) or deliver
   (design D2 point 1).
