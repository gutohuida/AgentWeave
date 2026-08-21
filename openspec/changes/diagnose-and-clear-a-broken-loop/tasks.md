# Tasks — diagnose and clear a broken loop

**Every defect here was measured before it was written down.** Reproduce first, then fix — that order
found all three loop bugs on 2026-08-20 and both of today's, and twice the reproduction taught
something the reading had missed. A task that starts by writing the fix is being done wrong.

**One commit per defect**, each carrying its own reproduction, so that a regression later names which
fix broke.

**Groups 2 and 4 both live in `_do_fire_job`, which `loop-notices-and-reacts` restructures** (design
D5). Assert the *property*, never the line ordering, so a restructure that reintroduces the bug fails
a test instead of passing quietly.

## 1. The unbound runner reason — LANDED

- [x] 1.1 Test: an agent with no bound runner and nothing in its configuration reports that no runner
      is bound, and its own name does not appear in the reason. Landed
      `test_an_unbound_agent_says_so_instead_of_naming_a_cli_after_itself` — `which` is stubbed to
      succeed for everything, so a fallthrough would report *runnable* rather than merely a different
      message, failing loudly instead of subtly.
- [x] 1.2 Test: the bound runner outranks synchronised configuration, and an agent configured through
      session.json with no bound runner stays launchable. Landed
      `test_get_agent_config_reports_the_bound_runner_and_names_the_unbound_case`, which asserts on a
      deliberate disagreement (session.json says `kimi`, bound runner says `claude`) so precedence is
      proven rather than coincidental.
- [x] 1.3 Add `RUNNER_UNBOUND` and its branch in `probe_agent`, shaped like the existing `manual`
      branch for the same reason: there is no CLI to look for, so every question below that point is
      the wrong question.
- [x] 1.4 Make `get_agent_config` read the bound `Runner`. **First attempt was too broad** — keying
      on `runner_id` alone broke `test_agent_with_no_bound_runner_has_no_collaboration_verdict` and
      `test_launchability_endpoint_reports_configured_agents`, both of which were right: a
      CLI-configured agent carries its runner in session.json and legitimately has no `Runner` row.
      Narrowed to *nothing anywhere supplies a runner*.
- [x] 1.5 Remove the now-duplicated runner-merge blocks from `api/v1/agents.py:191-198` and
      `api/v1/inbound_queue.py:157-173`. They are byte-identical to each other and now redundant with
      the root. **Not done in the landing commit** — deliberately, so the fix and the cleanup are
      separately revertible.
- [x] 1.6 Re-verify live on 8010: an unbound agent's queue status reads the new reason. The "before"
      was measured exactly (`Runner CLI 'probe-norunner' was not found in PATH.`); the "after" is so
      far only asserted in tests, because the probe agent was archived during cleanup.

## 2. A firing that starts no agent is not reported as running

- [x] 2.1 Reproduce: a loop whose agent cannot be launched fires, and assert the *present* behaviour —
      `JobRun` at `in_progress`, `firing_active` true, no `Run` row. This is the failing test.
- [x] 2.2 **DECIDED 2026-08-21: reuse `failed`.** No new vocabulary. It is already where these rows
      end up — `reconcile_stale_job_runs` sets exactly `failed` — so this is the same outcome reached
      honestly at the time rather than generically after a restart. And a new value would have hidden
      the reason it was added for: `JobCard.tsx:73` renders `error_summary` for `failed`/`skipped`
      only. Reasoning in design D1; restate it where the status is set.
- [x] 2.3 Stop discarding `schedule_agent`'s `ScheduleResult` at `scheduler.py:1015`. Record the
      `waiting_reason` on the `JobRun` — it is already an operator-facing sentence, already used by
      `api/v1/checkpoints.py:233-234`.
- [x] 2.4 Test: a firing that *does* start is completely unaffected — still `in_progress`, still
      finalised when the run ends. This is the regression bar for the whole group.
- [x] 2.5 Test: the reason recorded is the same one the queue status gives for that agent, so the two
      surfaces cannot drift into two explanations of one fact.

## 3. The card stops depending on the reaper having run

**Rescoped 2026-08-21 by operator decision (design D2), and it got smaller.** This group used to ask
which periodic trigger the reaper should gain. Group 2 removes the thing that produces stranded rows,
so the reaper's existing trigger — Hub start — matches the only failure mode left, a dead process.
What is actually wrong is the *derivation*: the loop card reads a raw status and inherits any stale
row. **No scheduler work, no new mechanism, and `run_reconciliation.py` is not modified at all.**

- [x] 3.1 Reproduce: with a `JobRun` at `in_progress` and no live `Run`, the loop reports
      `firing_active: true`. Measured 2026-08-21 by restart (`in_progress` → `failed`,
      `firing_active` true → false); this is the same state, asserted without restarting.
- [x] 3.2 Make `_batch_loop_summaries` (`api/v1/jobs.py:228-234`) exclude in-progress firings with no
      live `Run` when deriving `firing_active`. Same correlation
      `reconcile_stale_job_runs` uses (`JobRun.conversation_id` → `Run.conversation_id`) — import or
      share it rather than writing a second definition of "is anything actually running".
- [x] 3.3 Test: a firing whose `Run` is genuinely `running` still reports `firing_active: true`. The
      failure mode of this fix is a card that goes quiet during real work.
- [x] 3.4 Test: startup reconciliation is unchanged and still flips the row to `failed`. It stays the
      backstop for a crashed process; this group must not weaken it.
- [ ] 3.5 Measure the cost of the added correlation on a project with many loops before assuming it
      is free — this query runs on every loop listing (design, remaining open question 3).

## 4. A refused firing leaves no conversation

- [x] 4.1 Reproduce: fire a stalled loop three times, assert three conversations exist. Measured
      2026-08-21 — five firings, five conversations, three of them refused.
- [x] 4.2 Move `new_conversation`/`name_conversation` (`scheduler.py:817-829`) past the stop check
      (~868) and the stall check (~956-985).
- [x] 4.3 Test the property, not the ordering: **a refused firing creates no conversation** — once for
      the stall refusal, once for the stop refusal. Written this way so
      `loop-notices-and-reacts` cannot reintroduce it silently (design D5).
- [x] 4.4 Test: a firing that proceeds still gets its conversation, named after the job.
- [x] 4.5 Check the resume path: a job with `session_mode: "resume"` looks up its conversation by
      provider session before creating one. Confirm moving creation does not change which
      conversation a resumed firing lands in.

## 5. Archiving a job retires its loop

- [x] 5.1 Reproduce: archive a job, assert its loop is still listed and that archiving it is refused
      as "still running".
- [x] 5.2 Make `archive_job` retire the loop in the same operation (design D4).
- [x] 5.3 Test: archiving a running loop *directly* is still refused. D17's protection must survive —
      what changed is that archiving the job satisfies it, not that it was removed.
- [x] 5.4 Test: a loop retired with its job keeps its purpose, queue history, firings and stop state.
      "Archivable, never deletable" is unchanged.

## 6. The archive refusal names its remedy

- [x] 6.1 Reproduce: an agent with undelivered queue entries refuses archival, and the message names
      no course of action.
- [x] 6.2 **DECIDED 2026-08-21: a structured field the UI turns into a button.** The refusal reports
      how many entries block it and which; the agent surface offers *"Discard N queued messages and
      archive"*. Cheaper than it looks — `deleteQueueEntry` already exists
      (`hub/ui/src/api/queue.ts:76`) and so does `DELETE /queue/entries/{id}`, so this is wiring plus
      a refusal that carries data rather than only prose. Reasoning and both rejections in design D3.
- [x] 6.3 Return the blocking entry count and ids on the refusal. The guard itself does not move.
- [x] 6.4 Wire the button in the agent surface, reusing `deleteQueueEntry`. Confirm it discards only
      the entries the refusal named, never the whole queue.
- [x] 6.5 Test: the refusal carries the count and ids, and clearing them allows archiving.
- [x] 6.6 Test the confirmation is honest about what is destroyed — discarded input is not
      recoverable, and "archivable, never deletable" does not apply to queue entries.
- [x] 6.7 `make ui` after `npm run build`; commit `hub/ui/src` and `hub/hub/static/ui` together.

## 7. A second question about a blocked task can release it

- [x] 7.1 Reproduce: park a task with one question, ask a second about the same task, answer the
      second, assert the task is still blocked. This is §4a of
      `2026-08-21-which-band-blocked-belongs-to.md`, never reproduced.
- [x] 7.2 Stamp `blocked_task_id` in `park_task_for_question` even when no transition is needed
      (`run_task_binding.py:394`).
- [x] 7.3 Test: the transition map is untouched — `blocked` is still not a target of itself, and the
      task's status does not change when the second question is asked.
- [x] 7.4 Test: a question about a *different* task releases nothing. The opposite error is worse.

## 8. Verification an agent can do

- [ ] 8.1 `cd hub && py -3.11 -m pytest tests/ -q` — no failures. **Use `py -3.11`**: the venv
      interpreter fails three `test_pty_runner` tests and skips 13, which was mistaken for a
      pre-existing environment fault twice on 2026-08-21. Baseline before this change: 2723 passed,
      84 skipped, 1 xpassed (inherited).
- [ ] 8.2 `py -3.11 -m pytest tests/ -q` (CLI) passes.
- [ ] 8.3 `ruff check hub/`, `black --check hub/`, `mypy hub/hub/` clean on touched files.
- [ ] 8.4 `openspec validate diagnose-and-clear-a-broken-loop --strict` reports valid.
- [ ] 8.5 Confirm the existing loop suite passes **unmodified**. Nothing here changes what a
      successful firing does, so any edit to those tests means a fix reached further than intended.

## 9. Verification only a human can do

- [ ] 9.1 **The card stops lying.** Drive a loop at an agent that cannot launch, on a live Hub. The
      loop must not read as firing. This is the defect that started the change.
- [ ] 9.2 **The reason is actionable.** Read what the queue says about that agent. It should send the
      operator to bind a runner, not to look for a binary.
- [ ] 9.3 **A stalled loop does not fill the conversation list.** Leave one stalled across several
      firings and look at the list. Judge whether it reads as quiet or as busy.
- [ ] 9.4 **A broken loop can be cleared in one pass.** Archive the job and confirm nothing else is
      needed. Three undiscoverable steps was the measured cost.
- [x] 9.5 **The archive refusal teaches.** Attempt to archive an agent with queued input and judge
      whether the message tells you what to do next.
- [ ] 9.6 **Nothing got quieter that should not have.** A real firing that fails for a real reason
      must still be visible; confirm this change did not turn a loud failure into a silent one.

## 10. User test guide

- [x] 10.1 Write the operator-facing guide: how to tell a loop is stalled from one that is working,
      what each refusal reason means, and how to clear a loop and an agent that have gone wrong.

      **Operator guide.** A working loop shows the live firing cue only while an actual agent run is
      executing. A stalled loop stays enabled but names what it is waiting for (review, an answer,
      or another non-claimable state); it does not create empty conversations on repeated ticks.
      A failed firing names the same launchability reason as the agent queue: bind a runner when it
      says none is bound, repair the runner when its executable is unavailable, and leave an
      already-running agent alone because its queued work remains durable. To retire a broken loop,
      archive its job; the loop disappears from default listings in that same operation while its
      purpose, history, queue and stop state remain readable. If agent archival is refused because
      input is queued, use **Discard N queued messages and archive — cannot be undone**; that action
      removes only the listed undelivered entries and then retries archival.
