# A failed run does not eat its input

## Why

`2026-08-14-the-seams-loop7-found` added the machinery that stops a repeatedly-failing input from
wedging an agent: attempts are counted, a twice-failed conversation gives up its provider session, a
third failure abandons the entry and says so. Loop 8 drove that machinery on 2026-08-14
(`openspec/explorations/2026-08-14-loop8-a-dead-runtime-eats-the-message.md`) and found it wired to
the wrong half of the failure surface.

**A runtime that dies mid-turn silently eats the operator's input.** Kill the Codex app-server once
the turn is under way: the run is marked `failed`, the agent returns to `idle`, and the queue entry
stays `state='delivered'` with `delivery_attempts = 0` — never retried, never abandoned, nobody told.
Reproduced twice (`run-332ef259`, `run-68eca96d`). `return_run_entries` is called from exactly two
places, both *pre-spawn* `except` blocks (`agent_trigger.py:1239`, `:1807`). A death once `run_turn`
is under way returns a failed `TurnOutcome` through the **normal** completion path, which has no
notion of returning input at all. So `RESUME_RETRY_LIMIT` and `DELIVERY_ATTEMPT_LIMIT` are
structurally unreachable on the death mode most likely to occur, and the message the operator typed
is gone with no record that it ever existed.

**And nothing drives the retry of an entry that was returned.** Both pre-spawn branches requeue and
then `return` — `:1254` and `:1822` — before the `schedule_agent` the normal path runs at `:1504`.
`redrain_queued_agents` is reachable only from three project-lifecycle endpoints (project open,
settings save, relocate); there is no periodic drain. Observed: `entry-95f08a24` sat `queued` at
attempt 1 until an unrelated `PUT /settings` happened to drive attempt 2, and a second one drove
attempt 3. Left alone it would have sat there forever, one attempt short of the limit that was
supposed to protect it.

Neither is visible to 2358 passing tests, because both live between the failure path and the queue
rather than inside either.

## What changes

1. **Any abnormally-ended run hands its input back**, on the normal completion path, for both
   transports — not only the two pre-spawn spawn failures. The existing `return_run_entries` is
   reused unchanged, so the counting, the session reset at 2 and the abandonment at 3 all become
   reachable on the path they were written for.
2. **Divergence is not evaluated for a run whose work is being re-handed**, matching what
   `run_reconciliation.py` already does for a restart-orphaned run and for the same reason.
3. **A re-delivered turn says that the earlier attempt was cut off**, so an agent that finds work
   half-done knows why rather than inferring it from a dirty worktree.
4. **A pre-spawn failure schedules the agent**, so a returned entry is retried by the system rather
   than by an unrelated settings save.

The rule is deliberately broad: **any run that ends `failed` returns its input, capped at three
attempts.** A deliberate operator stop is `stopped`, not `failed`, and keeps its current behaviour.
A run that fails for a real reason will now re-run twice and then be abandoned with a stated reason
— that is the accepted cost, and it is why change 3 exists.

## Archive ordering

This change **modifies** the `agent-conversation-workspace` requirement *Repeated delivery failure
does not wedge an agent*, which `2026-08-14-the-seams-loop7-found` **adds** and which has not reached
the main spec yet. Applied in the other order the modification has nothing to modify. Full order for
the six now outstanding:

1. `2026-08-13-approved-means-it-is-in-the-product`
2. `2026-08-14-what-the-product-actually-built`
3. `2026-08-14-the-loop-agents-can-drive`
4. `2026-08-14-the-seams-loop7-found`
5. this change
6. `2026-08-14-what-a-failure-tells-the-operator`

## Non-goals

- **Narrowing the rule to runtime deaths only.** Returning input only where `outcome.exit_code is not
  None` would spare a genuinely-broken input two re-runs, but it also decides, from inside the Hub,
  which failures are worth retrying — a judgement the Hub is not in a position to make. The operator
  chose the broad rule.
- **A periodic queue drain.** The right fix for finding 2 is that the path which requeues also
  schedules, not a timer that sweeps up after paths that forgot to. A drain would hide the next
  instance of this bug rather than prevent it.
- **Changing what `stopped` does.** An operator who stops a run meant to stop it.
- **Reporting the failure better.** That is `2026-08-14-what-a-failure-tells-the-operator`, kept
  separate because it touches no control flow.
