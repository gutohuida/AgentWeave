# Test guide — a loop's outstanding mail is mail not yet delivered

## Agent-verifiable

1. **Delivered mail is not outstanding.** Tasks 1.2, 1.3 and 1.4 fail before the fix and pass after.
2. **Undelivered mail still is.** The restaged tests in 1.1 pass after. They fail after the fix
   without their restaging, which shows the join took effect.
3. **Pending means undelivered.** Task 1.5 fails before and passes after.
4. **No migration, no API change.** `git diff --stat` touches no file under `hub/hub/migrations/`
   and nothing in `hub/hub/api/v1/messages.py`.
5. **No reader of the flag is left in a product decision.**
   `grep -rn "Message.read" hub/hub --include=*.py` finds only `messages.py` (the API's own default
   filter and its `PATCH`).

## Human-only (trial Hub `:8010`, never `:8000`)

1. In a trial project, open Settings → Diagnostics. `message_counts.pending` is small, not equal
   to `total`. Send a message to an agent whose runner is unbound: `pending` goes up by one. Bind
   the runner and let it deliver: `pending` goes back down.
2. Optional, costs a real turn (Haiku): an agent creates a loop for another agent with
   `stop_when_queue_empties`. The executor messages the creator, the creator's turn receives it,
   and the queue drains. The `loop_queue_exhausted` event in Logs has `pending_request: null`.
   Before this change it named that message.
