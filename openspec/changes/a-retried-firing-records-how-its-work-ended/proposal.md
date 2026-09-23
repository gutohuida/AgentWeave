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
with an unordered `.first()` over every `Run` on the conversation (`run_reconciliation.py:265-268`).
After any retry there are two or more. A crash during a retried firing can read the older
`interrupted` row and write off a firing that is running.

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
  abandonment reason; a request-level refusal (`withdraw_refused_entry`, `agent_trigger.py:1625`) →
  `failed` with the refusal; the operator's withdrawal (`api/v1/inbound_queue.py:259-272`) →
  `stopped`.
- **The startup reaper uses the same rule** (design D4): it leaves a row whose conversation holds
  queued job input, and asks whether *any* run on the conversation is running (an `EXISTS`), not
  whichever `.first()` returns. `_waits_on_a_refusal` is deleted as a subset.
- A firing whose turn did not begin (`_do_fire_job`'s `terminal_failure` branch, `scheduler.py:
  3471-3477`) is **unchanged**: it is concluded `failed` at once, as `loop-firing-accountability`
  requires. Whether that verdict should wait too is Open Question 1.

## Capabilities

### Modified Capabilities

- `loop-firing-accountability`: adds a requirement stating when a firing's record for one agent
  concludes, and that a retry that completes the work is what the record says.

## Impact

- `hub/hub/scheduler.py` (`finalize_job_run_for_conversation` → `conclude_dispatches_for_conversation`),
  `hub/hub/api/v1/agent_trigger.py` (five run-end sites, the refused-request withdrawal),
  `hub/hub/turn_scheduler.py` (give-up), `hub/hub/api/v1/inbound_queue.py` (operator withdrawal),
  `hub/hub/run_reconciliation.py` (`reconcile_stale_job_runs`).
- Routes changed: `DELETE /queue/entries/{id}` gains a write. Its answer when that write raises is
  in design D3.
- No migration. No new status. No UI change: `in_progress` already renders (`JobCard.tsx:91-102`,
  neutral), and `firing_active` already requires a `running` `Run` (`api/v1/jobs.py:454-466`), so a
  row waiting for its retry never shows the loop as firing.
- No existing test is expected to move. `test_run_reconciliation.py:197`
  (`test_stale_job_run_with_a_dead_run_becomes_failed`) seeds no queue entry, so nothing is handed
  back and the row still concludes `failed`; it becomes a control (task 1.8).
