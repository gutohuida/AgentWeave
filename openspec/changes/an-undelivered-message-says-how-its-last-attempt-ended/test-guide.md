# Test guide — an undelivered message says how its last attempt ended

## Agent-verifiable

1. **The run's error reaches the conversation's response.** Tasks 1.1-1.4 fail before (no `error` in
   `RunFacts`) and pass after, on all three routes, with an over-long error fitted rather than a 500.
2. **It is rendered on the right block.** Task 1.5, in the route's real order, and it fails when the
   order is reversed.
3. **A give-up without a run is unchanged, and now refreshes the conversation.** Tasks 1.6 and 1.7.
4. **F273's settled state is pinned.** Task 1.8: a status line that cannot be written leaves the run's
   outcome and exit code intact, logged, not relabelled.
5. **Live.** Task 3.1.

## Human-only

1. On a trial Hub, bind an agent to a runner that cannot start (F291's fixture), open its
   conversation, and send a message. Within a few seconds the message reads **not delivered**, with
   *"delivery failed 3 times; the Hub stopped retrying"*, and beneath it *"Last attempt failed: …"*
   naming why. Nothing needs a reload.
2. A normal conversation looks exactly as before: no new line on delivered messages or completed
   turns.
