# Proposal — a retried firing records how its work ended

**Round 1, 2026-09-24** (bundle B2, spec track S7 after decision D1). Findings: **F147 (B)** and
**F123 (C)**, taken together because they are one defect reached two ways. Both re-verified against
HEAD `ce086b6` by reading; the mechanism lines are unchanged since they were filed (`git log -S` on
`"Reconciled on Hub start: no live run behind this firing"` last touches `264a299`, 2026-08-21).
Not re-driven in R1. **Nothing here is implemented yet.**

## Why

A job's history is the one view the operator reads to learn whether a job's work happened. After a
crash, and after any ordinary failed attempt that the Hub retries, it reports **failed for work that
completed**.

**The crash (F123, F147).** Startup runs two passes back to back (`hub/hub/main.py:466-467`).
`reconcile_interrupted_runs` marks the dead `Run` `interrupted` and hands its input back to the queue
(`run_reconciliation.py:104`, `return_run_entries`). One line later, `reconcile_stale_job_runs`
finds the firing's `JobRun` still `in_progress`, sees no `running` `Run` on its conversation, and
writes it `failed` with *"Reconciled on Hub start: no live run behind this firing"*
(`run_reconciliation.py:258-281`). The returned input is delivered seconds later **on the same
conversation**, and that run completes. Its end calls `finalize_job_run_for_conversation`
(`scheduler.py:2282-2303`), which selects only `status == "in_progress"` rows. The row is `failed`,
so nothing matches, and the history says `failed` forever. F147 measured it:
`run-3d282cf81379 completed exit 0` on the firing's own conversation, twelve seconds after
`job_runs … failed`.

**The same shape without any crash (found in R1).** Every run-end site in `agent_trigger.py` calls
`finalize_job_run_for_conversation(…, "failed")` **before** `return_run_entries`, and whether or not
the input goes back: the failure tail (`:2050-2051`), the pre-spawn failure (`:2193-2194`), the
Codex pre-spawn failure (`:3065-3066`), and the two finalize blocks (`:2522-2528`, `:3159-3163`).
A first attempt that fails before or after it spawns is retried up to `DELIVERY_ATTEMPT_LIMIT = 3`
(`inbound_queue.py:222`). If the retry succeeds, the history still reads `failed`.

**The precedent is already in the code, for one case.** A provider-allowance refusal returns its
input to be delivered at the reset, and the finalize block skips the conclusion for it:
*"The run that finally delivers it flips the row, whatever it ends as; flipped here, that run would
find no `in_progress` row and the history would read `failed` for an instruction that was carried
out"* (`agent_trigger.py:2515-2521`). The divergence check already skips the same way: *"Skipped
when the input went back to the queue"* (`:3166-3169`). This change makes that the rule rather than
the exception.

**A second defect in the reaper (F147).** `reconcile_stale_job_runs` correlates a row to its run
with a `.first()` over every `Run` on the conversation, with no `ORDER BY`
(`run_reconciliation.py:265-268`). After any retry there are two or more. **R2 settled that it is
not luck:** the only index leading on `runs.conversation_id` is `ix_runs_conversation_started`
(`conversation_id, started_at`; `db/models.py:1239`, migration `0017`), SQLite's plan for the query
is `SEARCH runs USING INDEX ix_runs_conversation_started`, and rows come back in `started_at` order,
so `.first()` is **always the earliest-started run** (checked with `EXPLAIN QUERY PLAN` against that
schema: a `running` row inserted first still came back second). A crash during a retried firing
therefore always reads the older `interrupted` or `failed` row and writes off a firing that is
running. Today it is latent only because every retried row is already `failed` by then; once this
change keeps the row open, it would fire every time.

Decision D1 (recommended answer, `spec-queue/tracks/B2.md`): a `JobRun` row is a **dispatch**, one
agent's share of one firing. An attempt is a `Run`. A dispatch has concluded when its input has, not
when one attempt has.

## What Changes

- **One rule for when a dispatch concludes** (design D1): its conversation holds no job input still
  queued, and no run on it is running. `finalize_job_run_for_conversation` becomes
  `conclude_dispatches_for_conversation`, which checks that rule itself and concludes **every**
  `in_progress` row on the conversation when it holds.
- **Every run-end site concludes after the input is handed back**, not before (design D2). The five
  sites above call the new function after `return_run_entries`. The allowance-refusal guard at
  `:2521` is subsumed: its input is queued, so the rule does not hold.
- **Input the Hub or the operator takes out of the queue concludes its dispatch** (design D3): the
  scheduler giving up at the delivery limit (`turn_scheduler.py:600-640`) → `failed` with the
  abandonment reason; the operator's withdrawal (`api/v1/inbound_queue.py:259-272`) → `stopped`.
  (R1 also listed `withdraw_refused_entry`, `agent_trigger.py:1625`. R2 removed it: its only caller
  withdraws the entry the trigger route itself just wrote, always `origin_type="operator"`
  (`agent_trigger.py:1567-1571`), so it can never withdraw job input.) The operator's withdrawal
  strands a row **today** as well, not only after this change: withdraw a job's input while its
  agent is busy and the row stays `in_progress` until the next Hub start.
- **The startup reaper uses the same rule** (design D4): it leaves a row whose conversation holds
  queued job input, and asks whether *any* run on the conversation is running (an `EXISTS`), not
  whichever `.first()` returns. `_waits_on_a_refusal` is deleted as a subset. **This reverses a
  pinned, decided case** (a firing queued for an agent with no runner reads `failed` at restart;
  `test_a_held_agent_is_busy.py:732-739`). Open Question 3 asks the operator.
- A firing whose turn did not begin (`scheduler.py:3471-3477` for the primary selection,
  `:3611-3616` for each extra selection of a wide flow) is **unchanged**: it is concluded `failed` at
  once, as the operator decided on 2026-08-21. Whether that verdict should wait too is Open
  Question 1.

## Capabilities

### Modified Capabilities

- `loop-firing-accountability`: adds a requirement stating when a firing's record for one agent
  concludes, and that a retry that completes the work is what the record says.

## Impact

- `hub/hub/scheduler.py` (`finalize_job_run_for_conversation` → `conclude_dispatches_for_conversation`),
  `hub/hub/api/v1/agent_trigger.py` (five run-end sites),
  `hub/hub/turn_scheduler.py` (give-up), `hub/hub/api/v1/inbound_queue.py` (operator withdrawal),
  `hub/hub/run_reconciliation.py` (`reconcile_stale_job_runs`).
- Routes changed: `DELETE /queue/entries/{id}` gains a write. Its answer when that write raises is
  in design D3.
- No migration. No new status. No UI change: `in_progress` already renders (`JobCard.tsx:91-102`,
  neutral), and `firing_active` already requires a `running` `Run` (`api/v1/jobs.py:454-466`), so a
  row waiting for its retry never shows the loop as firing.
- **Existing tests that move (R2; R1 said none would):**
  - `test_a_held_agent_is_busy.py:732-739`, `test_a_firing_for_an_agent_with_no_runner_and_no_refusal_still_fails`
    — seeds an `in_progress` row with queued job input and no refusal and asserts `failed` at
    restart. D4 leaves it `in_progress`. It inverts, or stays, according to Open Question 3;
  - `test_scheduler.py:1289-1328` (`test_loop_fire_whose_spawn_fails_leaves_the_job_run_failed_not_stuck_in_progress`) — asserts `failed` after awaiting only
    the background runs that existed before the retries were scheduled. After D2 the first failure
    requeues (attempt 1 of 3), so the row reads `in_progress` until the third attempt abandons the
    input. The test must await every retry and then assert `failed` with the abandonment reason;
  - `test_scheduler.py:46` (used at `:1333-1373`) and `test_flow_holds_the_loop_requirements.py:162` import
    `finalize_job_run_for_conversation` by name and follow the rename.
  `test_run_reconciliation.py:197` (`test_stale_job_run_with_a_dead_run_becomes_failed`) seeds no
  queue entry, so nothing is handed back and the row still concludes `failed`; it stays a control.
