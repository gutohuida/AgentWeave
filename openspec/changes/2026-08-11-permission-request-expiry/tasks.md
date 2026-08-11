# Tasks — A permission request never outlives the run that raised it

## 1. Reproduce before fixing

- [ ] 1.1 Write a failing test at the **HTTP route level** — the seam nothing currently covers. Open a
      request through `POST /agent-actions/permission-requests`, let the wait lapse without a
      decision, then assert the row is *not* pending and that `POST .../decide` is refused. It must
      fail on today's code for the stated reason, not for a setup error.
- [ ] 1.2 Confirm the second symptom in the same test or beside it: a stale pending row keeps its
      conversation marked as waiting (`conversations.py:268-269`). Fixing 2 and 3 must clear it.

## 2. The Hub closes what the run stops waiting on

- [ ] 2.1 Add `POST /agent-actions/permission-requests/{id}/expire` in `agent_actions.py`, beside the
      existing agent-facing routes and authenticated the same way — run-bound identity, never an
      agent name from a body or header.
- [ ] 2.2 Scope it per design D6: only `pending` → `expired`, only for a request belonging to the
      calling run, idempotent on an already-terminal row (success, no change, no error). Carries no
      reason — `_report_decision` reports the decision; this reports only that nobody is listening.
- [ ] 2.3 Write `decided_at`/`decided_by` in a way that keeps a timeout distinguishable from an
      answer, which `db/models.py:1157-1159` says `decided_at` is for. State which you chose.

## 3. The run reports, and the run's end sweeps

- [ ] 3.1 `mcp_server._ask_operator` — call the expiry endpoint on the timeout path before returning
      its denial. **Best-effort exactly like `_report_decision`**: every failure swallowed, no
      exception escaping, and no change to the decision or its timing. The denial must be returned
      even if the Hub is unreachable.
- [ ] 3.2 Add one helper that expires a run's pending requests, and call it from **both** run-end
      sites (`agent_trigger.py:1270` and `:1656`), in the transaction that already sets `run.status`
      and `run.ended_at`. One helper, two call sites — per D5, writing it twice is how the two paths
      drift.
- [ ] 3.3 **Check the assumption**: search for every place a run reaches a terminal status. If there
      is a third, call the helper there too and record that the set was verified rather than assumed.
- [ ] 3.4 Confirm the Codex path is unaffected — it already expires its own row at
      `agent_trigger.py:1451`, and the sweep must be a harmless no-op after it, not a double write.

## 4. Refuse a decision nobody is waiting for

- [ ] 4.1 `permissions.py` — the 409 guard already exists and already says the right thing. Confirm it
      now fires for `expired`, and that the row's status, `decided_at`, and `decided_by` are left
      untouched when it does.
- [ ] 4.2 Surface the 409 in the UI as "the run has moved on" rather than a generic failure. An
      operator who hits the race must learn what happened, per D3.

## 5. The operator sees that the agent gave up

- [ ] 5.1 Keep an expired request visible instead of filtering it out. `list_permission_requests`
      defaults to `pending_only=True` — decide whether expired rows arrive via that endpoint or
      alongside, and say which in the task notes.
- [ ] 5.2 `PermissionRequestCard.tsx` — an expired request reads as expired and offers no allow/deny.
      Reuse the "no longer waiting" treatment from `2026-08-11-declining-a-question` rather than
      inventing a second visual language for the same idea (D4).
- [ ] 5.3 Expired and operator-answered must be visibly different, not one grey state for both.
- [ ] 5.4 Use the `Icon` component; introduce no second icon system and no raw hex.

## 6. Close the test gap

- [ ] 6.1 Make 1.1 pass.
- [ ] 6.2 Cover the full lifecycle over **real HTTP routes**, not a stubbed `_hub_request`: open →
      expire-on-timeout → decide is refused; open → run ends → row expired; open → operator allows →
      run sees `allowed`.
- [ ] 6.3 Test the race directly: decide and expire arriving together leave exactly one terminal
      status, whichever lands first.
- [ ] 6.4 Test that an unreachable Hub on the expiry call still returns the run's denial, unchanged
      and undelayed — the rule the whole reporting path is built on.
- [ ] 6.5 `test_permission_approver.py` — the timeout test currently asserts only the local denial
      against a stubbed Hub. Extend it to assert the write-back is attempted.
- [ ] 6.6 Frontend tests for the expired card: marked, not answerable, distinct from answered.
- [ ] 6.7 A test that a conversation stops reading as "waiting" once its request expires.

## 7. Verification — agent-verifiable

- [ ] 7.1 `pytest hub/tests/ -q` green; record the count against the 1500 baseline.
- [ ] 7.2 `pytest tests/ -q` green (372 baseline).
- [ ] 7.3 `npx vitest run` green (759 baseline across 80 files); `npx tsc --noEmit` clean.
- [ ] 7.4 `ruff check hub/ src/` and `black` clean.
- [ ] 7.5 `npx openspec validate --changes --strict` and `--specs --strict` pass.
- [ ] 7.6 `npm run build`, refresh `hub/hub/static/ui`, confirm with `diff -rq`.
- [ ] 7.7 Re-run the standalone probe from the exploration
      (`testbed/scratch/run_probe.sh`) at 0s and 65s and confirm both still allow — the fix must not
      regress the path that already worked.
- [ ] 7.8 Behavioural probe against a **copy** of the real database: open a request, expire it both
      ways (timeout report, and run-end sweep), confirm the decide route refuses afterwards. Delete
      the copy; write nothing to the live board.
- [ ] 7.9 Restart the Hub by exact PID and confirm `/openapi.json` publishes the new route.

## 8. Verification — human-only (the operator runs these)

- [ ] 8.1 Does an expired card tell you what happened, or just look broken?
- [ ] 8.2 Having missed one, do you know what to change so you do not miss the next?
- [ ] 8.3 Is an expired card distinguishable from one you answered, at a glance?
- [ ] 8.4 Do expired cards accumulate into clutter over a real session?

## 9. User test guide

**Setup.** Testbed, a Claude agent, the composer's Permissions pill on **"Ask me"**. For step 1, set
the agent's permission timeout low (about 30s) so you are not waiting two minutes.

1. **The card stops pretending.** Ask the agent to run a shell command. When the card appears, **do
   not answer it.** Wait out the timeout.
   *Expect:* the card turns to expired on its own, and the agent continues, having been refused.
   *Failure looks like:* the card sits there as though still live — the original bug.

2. **A late answer is not silently swallowed.** With the card expired, try to Allow it.
   *Expect:* you are told the run has moved on. Nothing is recorded as approved.
   *Failure looks like:* it accepts, says nothing, and the tool still does not run.

3. **Approving in time still works.** Ask for another shell command and answer **Allow** promptly.
   *Expect:* the tool runs. This is the path that already worked and must keep working.
   *Failure looks like:* any regression here — the fix touched the timeout path, not this one.

4. **A stopped run does not leave a card behind.** Trigger a permission card, then **Stop** the run
   while it waits.
   *Expect:* the card closes as expired rather than outliving the run.
   *Failure looks like:* a card for a run that is no longer running.

5. **The conversation stops saying it is waiting.** After steps 1 and 4, look at the conversation.
   *Expect:* it no longer reads as waiting on you.
   *Failure looks like:* a permanent "waiting" marker with nothing behind it — the second symptom.
