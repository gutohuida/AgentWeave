# Tasks — a failed run does not eat its input

Read `hub/hub/run_reconciliation.py:29-99` first. It is the template for the whole of phase 1, and
its comment at `:53-60` is the reason phase 2 exists.

**No migration.** Every column this change uses (`delivery_attempts`, `abandoned_reason`,
`withdrawn_at`) landed in `0072` with `2026-08-14-the-seams-loop7-found`.

## 1. A failed run hands its input back — both transports

- [ ] 1.1 In `hub/hub/api/v1/agent_trigger.py`, exec path (~`:1415-1451`): inside the session block,
      **outside** the `if run:` guard and before the block's `await db.commit()`, add
      `returned = await return_run_entries(db, run_id) if final_status == "failed" else []`.
      Outside the guard because a run row that has vanished still has entries to hand back — the
      pre-spawn branch at `:1239` already reads this way.
- [ ] 1.2 Same site, after the commit: `await _report_abandoned_entries(db, project_id, agent, run_id)`.
      The existing helper, unchanged.
- [ ] 1.3 Same site: persist + broadcast `queue_entry_queued` per returned id, copying the loop at
      `:1250-1253` exactly — same payload keys, same order.
- [ ] 1.4 Codex app-server path (~`:1855-1890`): 1.1–1.3 again, structurally identical. `final_status`
      comes from `outcome.status` at `:1842-1849`; `stopped` arrives as `"interrupted"` and must not
      requeue.
- [ ] 1.5 Confirm both paths still reach `schedule_agent(project_id, agent)` at their end (`:1504`,
      `:1934`) — the retry is driven by that call and it must run after the commit (D3).

## 2. Divergence is not evaluated for a run whose work is being re-handed

- [ ] 2.1 Guard `await evaluate_run_end(run_id)` at `:1451` and `:1890` with `if not returned:`,
      matching `run_reconciliation.py:59` and citing its comment (D4).
- [ ] 2.2 Confirm the condition is on the **returned** set, not on `final_status`: a failed run whose
      entries were all abandoned this attempt has genuinely dropped its work and must still be
      evaluated (D4).

## 3. The re-delivered turn says the earlier attempt was cut off

- [ ] 3.1 `format_turn_prompt` (`hub/hub/inbound_queue.py:94-104`): where `entry.delivery_attempts`
      is truthy, extend that entry's block head with one clause naming the attempt number and saying
      the earlier attempt did not finish (D5).
- [ ] 3.2 Say nothing about what to do about it — no instruction to inspect the checkout or to redo
      work (D5).
- [ ] 3.3 A first delivery (`delivery_attempts` 0 or `None`) renders exactly as it does today.

## 4. A pre-spawn failure schedules the agent

- [ ] 4.1 Exec pre-spawn branch (`:1221-1254`): add `schedule_agent(project_id, agent)` after the
      entries are committed back and the events broadcast, before the `return` (D6).
- [ ] 4.2 Codex pre-spawn branch (`:1787-1822`): the same.
- [ ] 4.3 Import `schedule_agent` the way the normal paths do — a function-local
      `from ...turn_scheduler import schedule_agent`, to keep the existing import cycle intact.

## 5. Tests

New file `hub/tests/test_failed_run_returns_input.py`, shaped after
`hub/tests/test_run_reconciliation.py`.

- [ ] 5.1 A failed run on the **exec** path returns its delivered entries and increments
      `delivery_attempts`.
- [ ] 5.2 A failed run on the **app-server** path does the same.
- [ ] 5.3 A **completed** run returns nothing; a **stopped** run returns nothing.
- [ ] 5.4 Three consecutive failures abandon the entry with a reason, and `queue_entry_abandoned` is
      persisted and broadcast.
- [ ] 5.5 Divergence is **not** evaluated when entries were returned, and **is** when they were not.
- [ ] 5.6 A re-delivered entry's prompt names the earlier attempt; a first delivery's does not; a
      mixed turn annotates only the retried entry.
- [ ] 5.7 Both pre-spawn branches call `schedule_agent`.
- [ ] 5.8 **Mutation checks.** Deleting the `return_run_entries` call from **either** site must fail a
      named test; so must deleting **either** new `schedule_agent` call; so must removing the
      `if not returned:` guard.

## 6. Verification — agent-verifiable

- [ ] 6.1 `pytest hub/tests/ -q` and `pytest tests/ -q` **separately**, with
      `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`. Running them together
      fails collection.
- [ ] 6.2 `ruff check hub/ src/`; `black --target-version py311` on every file touched.
- [ ] 6.3 `npx tsc --noEmit` and `npx vitest run` from `hub/ui`. No UI source change is expected here;
      if any lands, `python scripts/refresh_ui_bundle.py` and commit `hub/hub/static/ui` with it.
- [ ] 6.4 `npx openspec validate --changes --strict`.
- [ ] 6.5 State which existing tests needed updating and why, rather than discovering it silently.
      Candidates: anything asserting `evaluate_run_end` is called unconditionally, and any test
      pinning `format_turn_prompt`'s exact output.

## 7. Verification — human-only

Against a Hub restarted onto this code. `aw-loop8` (`proj-94f3f169`) is kept as the reproduction and
needs no rebuild; its `victim` agent exists for exactly this.

- [ ] 7.1 Trigger a Codex agent on a long turn and kill the `codex` process mid-turn. *Expect:* the
      entry returns to `queued` with `delivery_attempts = 1`, and a new run starts **on its own** —
      no settings save, no project reopen.
- [ ] 7.2 Kill it twice more. *Expect:* the second clears the conversation's provider session, and
      the third abandons the entry with a stated reason that reaches the operator. The agent accepts
      new input throughout.
- [ ] 7.3 Read the third run's prompt. *Expect:* it says the earlier attempt was cut off, and names
      the attempt.
- [ ] 7.4 Does the abandoned entry read as "the Hub gave up" clearly enough to act on? Carried
      forward from `2026-08-14-the-seams-loop7-found` §9.4, which could not be reached to judge.
- [ ] 7.5 Judgement call: is two extra re-runs before abandonment the right cost for a run that fails
      for a permanent reason? The narrow alternative was rejected deliberately (D2) — this is the
      check that the choice still reads correctly once it is live.

## 8. User test guide

**Setup.** A project with a Codex-backed agent and a conversation already running.

1. **Send the agent a message that starts a long turn, then kill the `codex` process it spawned.**
   - *Expect:* the run is marked failed, and within moments a **new run starts by itself** carrying
     the same message. Previously the message vanished: the run failed, the agent went idle, and
     nothing was queued, retried, or reported.
2. **Kill it a second time.**
   - *Expect:* another retry, and this one starts a fresh provider session rather than resuming the
     old thread.
3. **Kill it a third time.**
   - *Expect:* the Hub stops retrying and tells you it gave up, naming the message and the run that
     was carrying it. The agent accepts a new message immediately afterwards.
4. **Read what the agent was sent on the second or third attempt.**
   - *Expect:* the turn states that an earlier attempt did not finish, and which attempt this is.
5. **Stop a run deliberately from the UI.**
   - *Expect:* nothing is requeued and no retry starts. A stop is not a failure.
6. **Point an agent at a runner whose binary does not exist and trigger it.**
   - *Expect:* the run fails and is retried on its own. Previously this sat queued until you happened
     to save a project setting.

**Where it would go wrong:** a run that fails three times and is never abandoned means the input is
not reaching the queue at all; an agent that retries forever means the attempt is not being counted.
Both are readable from `inbound_queue_entries.delivery_attempts` — it should climb 1, 2, 3 and stop.
