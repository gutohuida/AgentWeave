## 1. The busy guard

- [x] 1.1 Test: firing a loop five times while its agent has a running `Run` creates zero
      `InboundQueueEntry` rows and zero `JobRun` rows, and leaves every task's status and assignee
      unchanged. This is the measured failure — it currently produces five of each.
      `hub/tests/test_loop_busy_guard.py`. **The measurement was re-reproduced on 2026-08-24 rather
      than taken on trust: five busy firings produced exactly 5 queue entries** before the guard,
      matching the proposal. The test asserts the counts before the return value, so a regression
      names the number it produced rather than only that something was true.
- [x] 1.2 Test: a firing after the agent's run ends claims normally, proving the guard refuses rather
      than disables.
      `test_a_firing_after_the_turn_ends_claims_normally`, which ends the run and asserts the next
      firing reaches the claim (observable on the task's assignee). Plus
      `test_a_run_for_another_agent_does_not_refuse_this_loop` — the guard is per agent, and a
      project-wide reading would make a busy project look like a stopped one.
- [x] 1.3 Add the already-running check to `_do_fire_job`, before the claim and before `new_entry`.
      Same shape as `_job_agent_skip_reason`, which is already in that function.
      `_loop_agent_busy_reason`, written next to `_job_agent_skip_reason` so the pair reads
      together. It reads the same fact `schedule_agent` reads — a `Run` for this agent in
      `running` — so the two cannot disagree, but deliberately does not call into
      `turn_scheduler`: that function takes the per-agent lock and *starts* a turn, the opposite of
      what a guard wants.
      **Scoped to loops, by the caller.** A plain scheduled job firing while its agent is busy is a
      different situation: its message is a standing instruction still true when the agent frees
      up, so queuing it is the inbound queue working as designed. A loop's briefing re-briefs the
      task it just claimed and is stale before it is read.
- [x] 1.4 Return without writing a `JobRun` — the `JobRun` created earlier in the function must not
      be persisted for this path (design D4). Confirm the early return does not leave a partial row.
      Solved by ordering rather than by cleanup: the `Loop` row is now loaded **above** the
      `JobRun` construction, so the guard returns before any run object exists and there is no
      partial row to leave. The one thing it does commit is `job.next_run`, advanced further up — a
      refused firing that left `next_run` in the past would be its own lie. No event is emitted
      either: the agent's running `Run` already carries the fact, and `_batch_loop_summaries` reads
      exactly that row to report the loop as firing.
- [x] 1.5 Verify `_prune_job_history` is unaffected and the loop's job stays enabled and scheduled.
      `_prune_job_history` is unreachable on this path — it runs after the `JobRun` block the guard
      returns above — which is the point: a busy tick that wrote a row would evict real history
      through its 100-row window at a five-minute cron, reintroducing by bookkeeping the problem
      the guard exists to prevent. `test_the_job_stays_enabled_and_keeps_its_schedule` asserts
      `enabled`, an advanced `next_run`, and `run_count`/`last_run` untouched;
      `test_a_busy_refusal_does_not_stamp_the_loop_as_stopped` asserts busy never becomes a stop
      condition — a loop that acquired a `stop_reason` here would need an operator to restart it,
      which `remove_job` cannot undo.

## 2. Tick recording

- [x] 2.1 Test: firing repeatedly against one stalled queue produces exactly one `JobRun` whose tick
      count equals the number of refused firings.
      `hub/tests/test_loop_stall_ticks_in_place.py`, five firings → one row reading 5. Plus the
      boundary the default has to get right: a stall seen once reads 1, not 0.
- [x] 2.2 Test: a stall whose reason text changes starts a new `JobRun` rather than incrementing the
      previous one.
      Driven by adding a second unclaimable task, which changes what the reason says about how many
      tasks are open and in which statuses. Asserts the earlier row keeps its own count rather than
      being absorbed.
- [x] 2.3 Test: a loop that alternates between real firings and long refusal periods still shows the
      real firings in the most recent records — the last-ten view stays useful at a fast tick rate.
      Twenty refusals after a real firing leave **two** rows, not twenty-one, with the real one
      still present. A second test pins the reason that works: an increment does **not** move
      `fired_at`. Kept at the first refusal, the row reads "this stall began then and has been
      re-checked N times", and genuine later firings sort above it in a history ordered by
      `fired_at`. Moving it would send a stalled loop back to the top of the list every five
      minutes — the same burying, by another route.
- [x] 2.4 Migration adding the tick counter to `JobRun` — **`0087`**, the head being `0086`
      (`0086_queue_entry_review_task`) as of 2026-08-24. Guard for a missing table as `0033`/`0034`
      do; default reads as one for pre-existing rows.
      `0087_job_run_tick_count.py`, guarded for a missing `job_runs` table. **Default 1, not 0**,
      and server-side as well as client-side: the column counts firings the row represents, every
      pre-existing row represents exactly one, and a row reading 0 would say a firing that
      demonstrably happened did not.
- [x] 2.5 Bump the head assertions in `hub/tests/test_migrations.py` and
      `hub/tests/test_project_persistence.py`.
      Both bumped to `0087`; the two files' migration suites pass (78 passed, 1 skipped).
- [x] 2.6 Implement the increment-or-append rule in `_do_fire_job`'s stall path: same job, most recent
      run is a stall, same reason -> increment; otherwise append.
      `_stall_run_to_increment`, narrow in both directions deliberately — *most recent*, so a stall
      that resumed and stalled again gets its own row rather than resurrecting a count from before
      the work happened; *same reason*, so a stall that changes shape stays visible.
      **One wrinkle worth naming:** the `JobRun` is already `session.add`ed by the time a firing
      knows it will not record one, so `_discard_unused_run` handles both dispositions — `expunge`
      when it is still pending, `delete` when an intervening query autoflushed it. Which applies
      depends on what else the firing happened to query first, so neither is assumed.
- [x] 2.7 Expose the count on `JobRunResponse` so the history endpoints can render it.
      Defaulting to 1 there too, so a row written before the column existed serialises honestly.
      Asserted through the real route, `GET /projects/{id}/jobs/{job_id}/history`.

      **Three existing scheduler tests asserted the old behaviour** — three stalled firings, three
      rows — and were updated to one row with `tick_count == 3`. Each keeps the fact it was written
      to test (no agent spawned; the reason names what is waited on; `run_count`/`last_run`
      describe firings rather than considerations) and gains a note saying what changed and why.

## 3. The status vocabulary

Do this before group 4 — the shared claim decision is its first consumer, and writing that against
the four-set world means rewriting it immediately (design D9).

- [x] 3.1 Test: every status appearing in `TRANSITIONS` as an origin or destination is classified
      into exactly one band. Derived from the map, never from a literal list.
- [x] 3.2 Test: an unclassified status, and a doubly-classified one, each fail at import with the
      status named.
- [x] 3.3 Test: each of the **five** derived sets equals its current literal, **measured on
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
- [x] 3.4 ~~Decide which band `blocked` belongs to~~ — **already decided; record it, do not
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
- [x] 3.5 Define the bands and the classification.
      `STATUS_BANDS` in `hub/hub/task_transitions.py` — a stdlib-only leaf already imported by four
      of the five consumers, so nothing had to move to reach it. **Five bands, deliberately finer
      than any one set:** `agent_actionable` (firing an agent makes progress possible — the test
      that put `revision_needed` in the claim and kept `blocked` out), `awaiting_person`
      (`blocked`), `awaiting_handoff` (`completed`), `with_reviewer` (`under_review`), `terminal`.
      Each set is then a union of bands **for its own question**: claimable = actionable;
      current-item = actionable + awaiting_person; live = actionable + with_reviewer; terminal =
      terminal. Four bands would not have worked — `blocked` is in current-item but not live, and
      `under_review` is in live but not current-item, so no single "live" band reproduces both.
      `_check_bands()` runs at import and refuses a status with no band, a band that is not one of
      the five, or a band for a status the machine does not define, naming it in each case.
- [x] 3.6 Derive `CLAIMABLE_LOOP_TASK_STATUSES` (`hub/hub/scheduler.py`) and delete the literal.
- [x] 3.6b Derive `CURRENT_ITEM_TASK_STATUSES` (`hub/hub/scheduler.py`) and delete its literal.
      **Added 2026-08-24.** This set did not exist when the change was written; it was added that
      day to fix a live defect where the board used the *claimable* set to answer "what is this loop
      working on" and stopped showing blocked tasks entirely. Its regression tests
      (`hub/tests/test_loop_current_item_includes_blocked.py`) deliberately pin the *relationship*
      between the two sets rather than either literal, so they survive this derivation unchanged and
      must still pass after it.
- [x] 3.7 Derive `TERMINAL_FOR_BINDING` (`hub/hub/run_task_binding.py:293`), preserving its docstring
      — the reasoning about `completed` and `under_review` being deliberately absent must survive.
- [x] 3.8 Collapse `_ACTIVE_TASK_STATUSES` (`hub/hub/api/v1/agents.py:60`) and `_LIVE_TASK_STATUSES`
      (`hub/hub/checkpoints.py:62`) into one derived set — they are identical in content and separate
      in code.
- [x] 3.9 Confirm the derived-gap test added 2026-08-20
      (`test_only_the_awaiting_someone_else_statuses_sit_in_the_claim_stop_gap`,
      `hub/tests/test_scheduler.py:765`) still passes and still derives rather than lists.
- [x] 3.10 Confirm `hub/tests/test_loop_current_item_includes_blocked.py` still passes — all five
      tests, including the one asserting a firing still refuses to claim a blocked task. That is the
      direction this refactor is most likely to lose.

**Group 3 evidence.** `hub/tests/test_task_lifecycle_bands.py`, 16 tests.
3.1 derives the status list from `TRANSITIONS` (origins *and* destinations), never a literal.
3.2 covers all three refusals, each asserting the offending name appears in the message; a status
in *two* bands is unrepresentable rather than merely detected, because the classification maps
status → band — the reason that shape was chosen over band → statuses, which would have made the
invalid state expressible and then needed a check for it.
3.3's four equality assertions were **written and passing before any literal was deleted**, and
still pass after — that is the whole safety property. They spell the members out in full rather
than comparing one derivation against another, which would pass while both were wrong together;
`_loop_queue_order`'s own comment records that exact failure surviving review.
Also added, beyond what the tasks asked: a **source scan** in the style of
`test_task_transitions.py`'s origin scan, so a literal that happens to be *currently correct*
cannot creep back — value equality alone cannot tell a derivation from a lucky literal, and a lucky
literal is what all three stall bugs started as. It inspects individual bracketed literals rather
than whole files, and skips complete enumerations (`mcp_server.TaskStatus`, which may import only
stdlib and fastmcp, and `schemas.tasks._TASK_STATUSES`, already pinned elsewhere) by the fact that
every enumeration contains `approved` and `rejected` while no derived set here contains either.
**Verified the scan can fail**: reintroducing the old literal in `checkpoints.py` was caught, then
reverted. 3.9 and 3.10 both still pass unmodified.

## 4. The shared claimability decision

- [x] 4.1 Test: for a stalled queue, `_batch_loop_summaries`' current item and `_do_fire_job`'s
      decision agree. This is human-only check 13.1 made mechanical, and the drift it guards against
      is the one `_loop_queue_order` records.
      `hub/tests/test_firing_decision_is_shared.py`. Three shapes: they name the same task when
      there is one (with the gated task created *first*, so a derivation ignoring the dependency
      gate would pick the wrong one); a stalled `completed` queue claims nothing and shows no
      current item; and an empty queue proceeds rather than stalling.
      **A fourth case pins where they legitimately differ**, which "agree" must not be read to
      forbid: a `blocked` queue stalls the firing while the board still shows the task. A board
      that agreed with the firing there would show nothing and the loop would read as idle — the
      defect fixed earlier today.
- [x] 4.2 Implement the decision as one function returning what this firing should do — claim,
      refuse-stalled, or proceed-empty. **Leave room for a fourth answer**: the flow
      (`openspec/explorations/2026-08-21-the-loop-becomes-a-flow.md`) adds "fire a different agent
      for this task", and this function is where it lands.
      `decide_firing` returning a frozen `FiringDecision(kind, selections, stall_reason)`.
      **The fourth answer needs no new `kind`:** `loop-becomes-a-flow` group 2 made the agent a
      property of each `LoopSelection`, so "fire a different agent for this task" is a selection
      whose agent differs from the job's — already expressible.
      **It also removed a real inefficiency, not only a structural one.** `_do_fire_job` was
      walking the dependency gate *twice* on a stalled queue: once through the claim to find
      nothing, then again inside `_loop_stall_reason` to find out why — the whole walk repeated to
      produce a sentence, on exactly the firings doing no work. `_stall_reason_from_walk` now takes
      the walk's result; `_loop_stall_reason` stays as the one-call form for callers that have not
      walked.
- [x] 4.3 Call it from `_do_fire_job` and from `_batch_loop_summaries` (`hub/hub/api/v1/jobs.py`),
      importing rather than restating, matching the existing convention in that module.
      **Partly done already:** `loop-becomes-a-flow` group 1 extracted `candidate_is_startable`,
      which both now call, so the per-candidate rule is shared. What remains is the surrounding
      decision — claim / refuse-stalled / proceed-empty — which is still inline in `_do_fire_job`.
      Note the two callers legitimately pass different status sets (3.6 and 3.6b); the shared thing
      is the decision, not the candidate set.
      **Done for `_do_fire_job`, which now takes its whole answer from `decide_firing`.** The board
      shares `candidate_is_startable` — the per-candidate rule — and keeps its own walk, because it
      answers a different question over a different set (`CURRENT_ITEM_STATUSES`, which includes
      `blocked`). Group 5.5's stalled label is what will consume `decision.stall_reason`, and that
      is the point at which the board reads the decision rather than a fact about it.
      *(D7's "six fixed queries, never one per job" no longer describes this function either way:
      `task-dependencies` already added a `dependency_gate.evaluate` per candidate task.)*
      **`_select_for_firing` is gone**, absorbed rather than wrapped. It was `loop-becomes-a-flow`
      group 2's short-lived seam for pairing a task with an agent; keeping it would have left the
      reviewer ladder deciding somewhere the firing decision could not see. Its tests now drive
      `decide_firing`.
- [x] 4.4 Confirm `completed` is NOT added to `CLAIMABLE_LOOP_TASK_STATUSES` (design D3) — assert it
      in a test, since widening the tuple is the obvious wrong fix.
- [x] 4.5 Confirm `blocked` is NOT added back to `CLAIMABLE_LOOP_TASK_STATUSES` either. Same shape
      as 4.4 and a live risk rather than a theoretical one: this change's own tasks asserted it was
      there until 2026-08-24.
      Both asserted, plus the property behind them rather than only the constant: a queue holding
      only `completed` and `under_review` work never yields a selection at all.

## 5. Cadence and presentation

Both depend on the busy guard (group 1). Five minutes is only safe once a busy tick is refused.

- [x] 5.1 Test: a loop created without an explicit cron gets `*/5 * * * *`.
      Asserted off the signature rather than by calling the tool: `mcp_server` may import only
      stdlib and fastmcp, so there is nothing to stub and a live Hub would be needed otherwise.
- [x] 5.2 Give `create_loop`'s `cron` a default of `*/5 * * * *` (`hub/hub/mcp_server.py:547`), and
      say in its `Args:` description that a busy tick is refused, so a frequent schedule is cheap.
      Keep the twin-file discipline — `mcp_server.py` may import only stdlib and fastmcp.
      Done, and the description says both halves of why it is cheap — a busy firing records nothing
      and a repeated stall counts in place — plus when *not* to take the default: work that is
      genuinely periodic. Imports unchanged, still stdlib only.
- [x] 5.3 Add a sub-hourly option to `CRON_EXAMPLES`
      (`hub/ui/src/components/jobs/JobForm.tsx:13-19`), whose five entries bottom out at every six
      hours, and default a loop's form to it. Leave the plain job default alone — a job is not a loop
      and nothing here makes a fast job cheap.
      "Every 5 minutes" added at the top; `describeCron` already renders it, so the plain-English
      preview and the next-three-firings list work with no formatter change. The two defaults are
      named constants (`LOOP_DEFAULT_CRON`, `JOB_DEFAULT_CRON`) rather than repeated literals.
      **Opening the loop section switches the schedule only while it is still the untouched job
      default** — an operator who has already typed one keeps it, and a plain job keeps 9am.
- [x] 5.4 Test: the loop board labels a stalled loop distinctly from a running one, and the label
      says what is being waited on rather than only that something is (design D10).
      Four UI tests: stalled and running are distinguishable and the summary counts both; the line
      names what is waited on (`2 completed`, `no claimable task`); a loop that would fire carries
      no stall line at all; and a **stopped** loop reads as stopped rather than stalled, so a stale
      reason alongside an `ending_state` cannot relabel it. Two backend tests assert the summary
      carries the reason, and that its absence is a real `None` rather than an empty string — the
      UI keys the label off that.
- [x] 5.5 Implement that label, deriving the state from group 4's shared decision rather than
      recomputing it.
      `LoopSummary.stall_reason` comes from `decide_firing`, so the board and the firing cannot say
      different things about why nothing is happening. `endingBucket` gains a `stalled` case ahead
      of `idle` — the reading it must not have, because "idle" says both that nothing is happening
      and that nothing is wrong.
      **This is also where 4.3's board half landed, and it lowered the cost rather than raising
      it.** Computing the label beside the existing candidate walk would have run the dependency
      gate twice per loop. Instead the board's per-candidate `candidate_is_startable` calls are
      gone entirely: the decision answers which task is claimable, and the batched candidate walk
      became a lookup that picks the first candidate in queue order which is either that task or a
      `blocked` one.
      **One thing that had to be caught rather than assumed:** taking the decision's task directly
      inverted `agent-loops` §85 for a queue holding both a blocked task and a pending one — blocked
      outranks oldest-pending, and `_loop_queue_order` is what encodes that. The regression test
      from this morning's blocked fix caught it.
- [x] 5.6 `make ui` after `npm run build`, and commit `hub/ui/src` and `hub/hub/static/ui` together.

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
