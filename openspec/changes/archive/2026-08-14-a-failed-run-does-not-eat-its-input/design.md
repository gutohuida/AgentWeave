# Design — a failed run does not eat its input

## D1. The template already exists; this change extends its reach

`hub/hub/run_reconciliation.py:29-99` handles a run orphaned by a Hub restart. For each such run it
expires pending decisions, calls `return_run_entries`, collects `abandoned_for_run`, broadcasts, and
schedules the agent — and deliberately skips divergence evaluation when entries were returned. That
is precisely the behaviour a mid-turn death wants, and the fact that one death mode already has it
while the more common one does not is the whole of finding 1.

So this change invents nothing. It applies the reconciliation shape at the two normal-completion
sites, reusing `return_run_entries` and `_report_abandoned_entries` as they stand.

## D2. The rule is `final_status == "failed"`, not a narrower predicate

`final_status` is already computed at both sites and already distinguishes the three outcomes that
matter:

- `stopped` — the operator asked for it (`run_id in _stop_requested`, or Codex's
  `outcome.status == "interrupted"`). Input is **not** returned; the operator stopped the turn
  knowing what it was carrying.
- `completed` — the input was consumed. Nothing to return.
- `failed` — everything else: a non-zero exit, an app-server death, a binding conflict.

A narrower predicate was considered and rejected by the operator: keying off
`outcome.exit_code is not None` would return input only where a process demonstrably died, sparing a
genuinely-poisoned input two extra runs. It also means the Hub decides which failures deserve a
retry, on evidence it does not have — a binding conflict and a crashed runtime are indistinguishable
from the queue's point of view, and only one of them is safe to drop. The cap at three is what bounds
the cost of being wrong, and it already exists.

Consequence, accepted: a run that fails for a real, permanent reason now re-runs twice before being
abandoned. That is worse than today for that case and better for every other, and the abandonment is
loud where the current silence is not.

## D2a. One carve-out: a binding conflict

`binding_conflict is not None` is the single failure excluded, and it was found by two existing test
files independently rather than reasoned out in advance
(`test_conversation_contract.py::test_provider_binding_conflict_leaves_conversation_untouched_and_fails_run`
and `test_inbound_queue.py::test_delivery_cap_defers_entries_to_following_turns`).

Two reasons, either of which is sufficient.

**The turn already ran.** Every other failure here means the turn did not complete: the process died,
the runtime exited non-zero, the spawn never happened. A binding conflict is different in kind — the
runtime worked, the agent did the work, the output was streamed and recorded, and the Hub then
refused the session identity it reported. The input was *processed*, not lost. Handing it back makes
the agent redo a completed turn, which is the one thing returning input is supposed to prevent the
opposite of.

**Retrying would defeat the check.** `return_run_entries` gives up the conversation's provider
session at `RESUME_RETRY_LIMIT`, because that is what breaks a resume loop. Applied to a conflict
that means: attempt 1 refuses session B, attempt 2 refuses it and clears the binding to A, attempt 3
binds B unopposed. A runtime reporting the wrong session would acquire the binding simply by being
retried — the precise outcome
`test_provider_binding_conflict_leaves_conversation_untouched_and_fails_run` exists to forbid.

This is not the narrow "only when the runtime died" rule that was considered and rejected in D2. It
is one named cause, excluded for what that cause means, and every other failure still returns its
input.

**Cost, stated:** a conflicted turn's input is not retried. It is not lost either — it was consumed
by a turn that ran — but nothing re-delivers it, and the operator sees a failed run whose error names
the conflict. That is the pre-existing behaviour for this case, unchanged by this change.

## D3. Ordering inside the session block is load-bearing

At each site the order must be:

1. `returned = await return_run_entries(db, run_id)` — **inside** the existing session block, before
   its `await db.commit()`. The entry rows and the run's terminal status must land in one
   transaction; a reader that sees `status='failed'` and a still-`delivered` entry is exactly the
   state this change exists to remove.
2. `await db.commit()` — unchanged, already there.
3. `await _report_abandoned_entries(db, project_id, agent, run_id)` — after the commit, matching both
   pre-spawn branches. It reads `withdrawn` rows written in step 1.
4. `queue_entry_queued` persisted and broadcast per returned id, copying the loop at `:1250-1253`.
5. `schedule_agent(project_id, agent)` — already at the end of both paths (`:1504`, `:1934`),
   unchanged. It runs after the commit, so its "this agent already has a run in progress" guard reads
   the terminal row rather than a stale `running` one.

The existing `if run:` guard wraps the `commit()`. `return_run_entries` must sit **outside** that
guard, as it does at `:1239` — an entry whose run row has vanished still needs handing back, and the
pre-spawn branches already establish that reading.

## D4. Divergence is skipped exactly when entries were returned

`evaluate_run_end(run_id)` is called unconditionally at `:1451` and `:1890`. `run_reconciliation.py`
skips it when `returned_entry_ids` is non-empty, and its comment at `:53-60` gives the reason: the
work is about to be handed to a new run that will bind to the same task, so nothing has been dropped
and there is no divergence to report. Firing it here would tell the operator a task was abandoned
moments before the retry picks it up.

The condition is `returned_entry_ids` being non-empty, **not** `final_status == "failed"`. A failed
run that carried nothing — or whose entries were all abandoned on this attempt — has genuinely
dropped its work, and that is a divergence worth evaluating. Abandoned ids are not in the returned
set, which makes this fall out correctly without a second check.

## D5. The re-delivery note goes in the entry's block, not the preamble

`format_turn_prompt` (`hub/hub/inbound_queue.py:94-104`) renders one block per entry, headed with its
origin and hop. The note belongs in that head, because `delivery_attempts` is per entry: a turn can
carry one entry on its second attempt alongside one that has never been tried, and a preamble
sentence would misdescribe the second.

Wording states the fact and nothing else — the number of the attempt and that the previous one did
not finish. It does not instruct the agent to check the worktree or to redo anything: what to do
about half-finished work depends on what the work was, and an instruction that is wrong half the time
is worse than the fact alone.

`delivery_attempts` is `0` for a first delivery, so the note is absent for the overwhelmingly common
case and no existing prompt changes.

## D6. Pre-spawn requeue must schedule, and `redrain` is not the answer

Finding 2's cause is structural: both pre-spawn branches `return` before reaching the
`schedule_agent` at the end of their function. Nothing else runs on a timer —
`hub/hub/scheduler.py` is the jobs scheduler, and `redrain_queued_agents` is reachable only from
project open, settings save, and relocate.

Adding a periodic drain was rejected as a non-goal: it would make this bug and every future
instance of it invisible rather than fixed. The path that returns an entry to the queue is the path
that knows the agent has work again, and it is where the call belongs.

Both branches gain `schedule_agent(project_id, agent)` after their entries are committed back and
their events broadcast — the same position, relative to the commit, that the normal path uses.

## D7. What tells us this went wrong

Two observable failure modes, both readable from `inbound_queue_entries.delivery_attempts`:

- A run that fails three times and never abandons its entry means `return_run_entries` is not being
  reached — the same silence as today, one layer down.
- An agent that loops on a genuinely broken input means the attempt is not being counted; the entry
  would sit at a `delivery_attempts` that does not climb.

Neither is subtle once the column is looked at, which is why the human verification step below is
written against the database rather than the UI.

## D8. Tests must be mutation-checked

A vacuous assertion has bitten this codebase three times. Every claim in phase 5 is paired with a
mutation that must break a **named** test: deleting either `return_run_entries` call, deleting either
new `schedule_agent` call, and removing the divergence condition.
