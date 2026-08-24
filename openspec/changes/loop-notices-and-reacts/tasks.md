## 1. The busy guard

- [ ] 1.1 Test: firing a loop five times while its agent has a running `Run` creates zero
      `InboundQueueEntry` rows and zero `JobRun` rows, and leaves every task's status and assignee
      unchanged. This is the measured failure — it currently produces five of each.
- [ ] 1.2 Test: a firing after the agent's run ends claims normally, proving the guard refuses rather
      than disables.
- [ ] 1.3 Add the already-running check to `_do_fire_job`, before the claim and before `new_entry`.
      Same shape as `_job_agent_skip_reason`, which is already in that function.
- [ ] 1.4 Return without writing a `JobRun` — the `JobRun` created earlier in the function must not
      be persisted for this path (design D4). Confirm the early return does not leave a partial row.
- [ ] 1.5 Verify `_prune_job_history` is unaffected and the loop's job stays enabled and scheduled.

## 2. Tick recording

- [ ] 2.1 Test: firing repeatedly against one stalled queue produces exactly one `JobRun` whose tick
      count equals the number of refused firings.
- [ ] 2.2 Test: a stall whose reason text changes starts a new `JobRun` rather than incrementing the
      previous one.
- [ ] 2.3 Test: a loop that alternates between real firings and long refusal periods still shows the
      real firings in the most recent records — the last-ten view stays useful at a fast tick rate.
- [ ] 2.4 Migration adding the tick counter to `JobRun` — **`0087`**, the head being `0086`
      (`0086_queue_entry_review_task`) as of 2026-08-24. Guard for a missing table as `0033`/`0034`
      do; default reads as one for pre-existing rows.
- [ ] 2.5 Bump the head assertions in `hub/tests/test_migrations.py` and
      `hub/tests/test_project_persistence.py`.
- [ ] 2.6 Implement the increment-or-append rule in `_do_fire_job`'s stall path: same job, most recent
      run is a stall, same reason -> increment; otherwise append.
- [ ] 2.7 Expose the count on `JobRunResponse` so the history endpoints can render it.

## 3. The status vocabulary

Do this before group 4 — the shared claim decision is its first consumer, and writing that against
the four-set world means rewriting it immediately (design D9).

- [ ] 3.1 Test: every status appearing in `TRANSITIONS` as an origin or destination is classified
      into exactly one band. Derived from the map, never from a literal list.
- [ ] 3.2 Test: an unclassified status, and a doubly-classified one, each fail at import with the
      status named.
- [ ] 3.3 Test: each of the **five** derived sets equals its current literal, **measured on
      2026-08-24 rather than remembered**:
      - claimable — `in_progress assigned pending revision_needed`
      - current item — the claimable four **plus `blocked`**
      - terminal — `approved rejected`
      - active and live — `pending assigned in_progress under_review revision_needed` (identical)

      **Corrected 2026-08-24, and this correction is the point of the task.** This said the
      claimable set contains `blocked`. It has not since 2026-08-21, when `blocked` left the claim
      so a firing would stop spawning an agent every tick against work that cannot move. Since 3.3
      is explicitly the assertion that stops the refactor smuggling in a behaviour change, writing
      it as it stood would have done the smuggling itself: assert the wrong literal, then "fix" the
      constant to match, and the 2026-08-20 spin bug is back.

      **Write these assertions before deleting any literal.**
- [ ] 3.4 ~~Decide which band `blocked` belongs to~~ — **already decided; record it, do not
      re-decide it.** `openspec/explorations/2026-08-21-which-band-blocked-belongs-to.md` settled it
      and `scheduler.py` carries the reasoning: `blocked` sits with `completed` and `under_review`
      in the *"someone else's turn"* band, its "someone else" being the most literal of the three —
      a person holding an unanswered question. The separating test from `revision_needed`, which
      went the other way a day earlier, is whether firing an agent makes progress *possible*.
      The task's premise was also wrong: it said `blocked` is claimable by the loop. It is not.

      **What this task actually owes now** is the harder half the band alone does not answer: one
      band cannot produce both the claimable set and the current-item set, because `blocked` is in
      one and not the other. Define each set as the union of bands *for its own question*, never a
      single "live" band — see design D9 and the defect it now records.
- [ ] 3.5 Define the bands and the classification.
- [ ] 3.6 Derive `CLAIMABLE_LOOP_TASK_STATUSES` (`hub/hub/scheduler.py`) and delete the literal.
- [ ] 3.6b Derive `CURRENT_ITEM_TASK_STATUSES` (`hub/hub/scheduler.py`) and delete its literal.
      **Added 2026-08-24.** This set did not exist when the change was written; it was added that
      day to fix a live defect where the board used the *claimable* set to answer "what is this loop
      working on" and stopped showing blocked tasks entirely. Its regression tests
      (`hub/tests/test_loop_current_item_includes_blocked.py`) deliberately pin the *relationship*
      between the two sets rather than either literal, so they survive this derivation unchanged and
      must still pass after it.
- [ ] 3.7 Derive `TERMINAL_FOR_BINDING` (`hub/hub/run_task_binding.py:293`), preserving its docstring
      — the reasoning about `completed` and `under_review` being deliberately absent must survive.
- [ ] 3.8 Collapse `_ACTIVE_TASK_STATUSES` (`hub/hub/api/v1/agents.py:60`) and `_LIVE_TASK_STATUSES`
      (`hub/hub/checkpoints.py:62`) into one derived set — they are identical in content and separate
      in code.
- [ ] 3.9 Confirm the derived-gap test added 2026-08-20
      (`test_only_the_awaiting_someone_else_statuses_sit_in_the_claim_stop_gap`,
      `hub/tests/test_scheduler.py:765`) still passes and still derives rather than lists.
- [ ] 3.10 Confirm `hub/tests/test_loop_current_item_includes_blocked.py` still passes — all five
      tests, including the one asserting a firing still refuses to claim a blocked task. That is the
      direction this refactor is most likely to lose.

## 4. The shared claimability decision

- [ ] 4.1 Test: for a stalled queue, `_batch_loop_summaries`' current item and `_do_fire_job`'s
      decision agree. This is human-only check 13.1 made mechanical, and the drift it guards against
      is the one `_loop_queue_order` records.
- [ ] 4.2 Implement the decision as one function returning what this firing should do — claim,
      refuse-stalled, or proceed-empty. **Leave room for a fourth answer**: the flow
      (`openspec/explorations/2026-08-21-the-loop-becomes-a-flow.md`) adds "fire a different agent
      for this task", and this function is where it lands.
- [ ] 4.3 Call it from `_do_fire_job` and from `_batch_loop_summaries` (`hub/hub/api/v1/jobs.py`),
      importing rather than restating, matching the existing convention in that module.
      **Partly done already:** `loop-becomes-a-flow` group 1 extracted `candidate_is_startable`,
      which both now call, so the per-candidate rule is shared. What remains is the surrounding
      decision — claim / refuse-stalled / proceed-empty — which is still inline in `_do_fire_job`.
      Note the two callers legitimately pass different status sets (3.6 and 3.6b); the shared thing
      is the decision, not the candidate set.
- [ ] 4.4 Confirm `completed` is NOT added to `CLAIMABLE_LOOP_TASK_STATUSES` (design D3) — assert it
      in a test, since widening the tuple is the obvious wrong fix.
- [ ] 4.5 Confirm `blocked` is NOT added back to `CLAIMABLE_LOOP_TASK_STATUSES` either. Same shape
      as 4.4 and a live risk rather than a theoretical one: this change's own tasks asserted it was
      there until 2026-08-24.

## 5. Cadence and presentation

Both depend on the busy guard (group 1). Five minutes is only safe once a busy tick is refused.

- [ ] 5.1 Test: a loop created without an explicit cron gets `*/5 * * * *`.
- [ ] 5.2 Give `create_loop`'s `cron` a default of `*/5 * * * *` (`hub/hub/mcp_server.py:547`), and
      say in its `Args:` description that a busy tick is refused, so a frequent schedule is cheap.
      Keep the twin-file discipline — `mcp_server.py` may import only stdlib and fastmcp.
- [ ] 5.3 Add a sub-hourly option to `CRON_EXAMPLES`
      (`hub/ui/src/components/jobs/JobForm.tsx:13-19`), whose five entries bottom out at every six
      hours, and default a loop's form to it. Leave the plain job default alone — a job is not a loop
      and nothing here makes a fast job cheap.
- [ ] 5.4 Test: the loop board labels a stalled loop distinctly from a running one, and the label
      says what is being waited on rather than only that something is (design D10).
- [ ] 5.5 Implement that label, deriving the state from group 4's shared decision rather than
      recomputing it.
- [ ] 5.6 `make ui` after `npm run build`, and commit `hub/ui/src` and `hub/hub/static/ui` together.

## 6. Retroactive specification of what already shipped

- [ ] 6.1 Confirm the `agent-loops` delta's stall-refusal requirement matches the behaviour
      `_loop_stall_reason` already implements, and that its scenarios pass against the shipped code
      before this change adds anything.
- [ ] 6.2 Confirm `revision_needed`'s presence in `CLAIMABLE_LOOP_TASK_STATUSES` is covered by an
      existing test and needs no new requirement here.

## 7. Agent-verifiable checks

- [ ] 7.1 `pytest hub/tests/ -v` passes, with the three pre-existing `test_pty_runner` environment
      failures unchanged and no new failures.
- [ ] 7.2 `openspec validate loop-notices-and-reacts` reports valid.
- [ ] 7.3 `ruff check hub/` and `black --check hub/` pass on every touched file, and
      `cd hub/ui && npm run lint` passes.
- [ ] 7.4 A firing refused for any reason creates no `InboundQueueEntry` — asserted directly, not
      inferred from a `JobRun` status.
- [ ] 7.5 The claim decision function has exactly two call sites, asserted by a source scan in the
      style of `hub/tests/test_task_transitions.py`'s existing origin scan.

## 8. Human-only verification

These cannot be established by an agent and must be checked by the operator against a running Hub.

- [ ] 8.1 With a loop mid-turn, confirm the loop board does not flicker or show the loop as idle
      while firings are being refused.
- [ ] 8.2 Confirm a stalled loop's history entry reads sensibly as its tick count climbs, rather than
      looking like a stuck row.
- [ ] 8.3 Confirm a stalled loop reads as *waiting*, not as *dead* — the distinction is a judgement
      no test can make, and getting it wrong makes a working loop look broken.
- [ ] 8.4 With a five-minute tick, confirm the last-ten runs view still shows the firings that
      claimed work rather than a screen of refusals.

## 9. User test guide

- [ ] 9.1 Write the operator-facing guide covering: creating a loop, watching a firing claim work,
      letting its queue stall, reading the stall from the loop's own history, and resolving it.
- [ ] 9.2 Include how to tell the three refusal reasons apart from the loop's own history, and what
      each one means about what the loop is waiting for.
