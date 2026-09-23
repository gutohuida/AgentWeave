# Test guide — a live view that fell behind is told, and catches up

## Agent-verifiable

1. **The Hub counts what it drops.** 1.1 fails before, passes after.
2. **The stream says so, once, even after a burst followed by silence.** 1.2 and 1.3.
3. **The gap is not a project's event.** 1.2 asserts no `project_id` on it.
4. **The app catches up.** 1.6 and 1.7: every query invalidated and the reconnect hook fired, in
   both orders the Hub can emit.
5. **The feed says it.** 1.8.
6. **Numbers add up on the wire.** 3.1 on a trial Hub: events received plus `dropped` = 3,000.

## Human-only

1. On a trial Hub, open the app on a project's Activity tab, then background the tab (or throttle
   it in DevTools to "Offline" for a few seconds without closing the connection) while an agent
   streams a long answer. Bring it back. The feed shows *"The live connection fell behind and N
   events were not delivered…"*, and the task board and agent panel show current state without a
   reload. Judge whether the sentence reads as a calm notice rather than an error.
