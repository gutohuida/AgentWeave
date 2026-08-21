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
- [ ] 1.5 Remove the now-duplicated runner-merge blocks from `api/v1/agents.py:191-198` and
      `api/v1/inbound_queue.py:157-173`. They are byte-identical to each other and now redundant with
      the root. **Not done in the landing commit** — deliberately, so the fix and the cleanup are
      separately revertible.
- [ ] 1.6 Re-verify live on 8010: an unbound agent's queue status reads the new reason. The "before"
      was measured exactly (`Runner CLI 'probe-norunner' was not found in PATH.`); the "after" is so
      far only asserted in tests, because the probe agent was archived during cleanup.

## 2. A firing that starts no agent is not reported as running

- [ ] 2.1 Reproduce: a loop whose agent cannot be launched fires, and assert the *present* behaviour —
      `JobRun` at `in_progress`, `firing_active` true, no `Run` row. This is the failing test.
- [ ] 2.2 Decide whether the terminal state reuses `skipped` or needs its own word (design, open
      question 3). `skipped` currently means "refused before the claim"; this claimed and then failed
      to start. Record the decision where the state is set.
- [ ] 2.3 Stop discarding `schedule_agent`'s `ScheduleResult` at `scheduler.py:1015`. Record the
      `waiting_reason` on the `JobRun` — it is already an operator-facing sentence, already used by
      `api/v1/checkpoints.py:233-234`.
- [ ] 2.4 Test: a firing that *does* start is completely unaffected — still `in_progress`, still
      finalised when the run ends. This is the regression bar for the whole group.
- [ ] 2.5 Test: the reason recorded is the same one the queue status gives for that agent, so the two
      surfaces cannot drift into two explanations of one fact.

## 3. Clearing a stranded firing without a restart

- [ ] 3.1 Reproduce: a stranded `JobRun` stays `in_progress` for as long as the Hub stays up. Measured
      by restart on 2026-08-21 (`in_progress` → `failed`); this is that, without the restart.
- [ ] 3.2 **Decide the trigger** (design, open question 1) — the APScheduler instance the Hub already
      runs, a lifespan-owned task, or an existing periodic path. Look at what exists before adding
      anything, and record why.
- [ ] 3.3 Wire `reconcile_stale_job_runs` to that trigger. Do not change what the function does; it is
      correct and its docstring already names this case.
- [ ] 3.4 Test: a firing whose run is still `running` is never cleared out from under itself. The
      guard exists (`run_reconciliation.py:131-132`); this pins it against the new caller.
- [ ] 3.5 Confirm the interval is long enough that the window between a firing reaching `in_progress`
      and its `Run` existing is not routinely hit. State the reasoning where the interval is set.

## 4. A refused firing leaves no conversation

- [ ] 4.1 Reproduce: fire a stalled loop three times, assert three conversations exist. Measured
      2026-08-21 — five firings, five conversations, three of them refused.
- [ ] 4.2 Move `new_conversation`/`name_conversation` (`scheduler.py:817-829`) past the stop check
      (~868) and the stall check (~956-985).
- [ ] 4.3 Test the property, not the ordering: **a refused firing creates no conversation** — once for
      the stall refusal, once for the stop refusal. Written this way so
      `loop-notices-and-reacts` cannot reintroduce it silently (design D5).
- [ ] 4.4 Test: a firing that proceeds still gets its conversation, named after the job.
- [ ] 4.5 Check the resume path: a job with `session_mode: "resume"` looks up its conversation by
      provider session before creating one. Confirm moving creation does not change which
      conversation a resumed firing lands in.

## 5. Archiving a job retires its loop

- [ ] 5.1 Reproduce: archive a job, assert its loop is still listed and that archiving it is refused
      as "still running".
- [ ] 5.2 Make `archive_job` retire the loop in the same operation (design D4).
- [ ] 5.3 Test: archiving a running loop *directly* is still refused. D17's protection must survive —
      what changed is that archiving the job satisfies it, not that it was removed.
- [ ] 5.4 Test: a loop retired with its job keeps its purpose, queue history, firings and stop state.
      "Archivable, never deletable" is unchanged.

## 6. The archive refusal names its remedy

- [ ] 6.1 Reproduce: an agent with undelivered queue entries refuses archival, and the message names
      no course of action.
- [ ] 6.2 **Decide the shape** (design, open question 2) — prose naming the endpoint, a structured
      field the UI turns into a button, or an operator-facing "discard queued input" action. The last
      is the most useful and the largest; pick deliberately and record why.
- [ ] 6.3 Implement it. The guard itself does not move.
- [ ] 6.4 Test: the refusal states how the input is cleared, and clearing it allows archiving.

## 7. A second question about a blocked task can release it

- [ ] 7.1 Reproduce: park a task with one question, ask a second about the same task, answer the
      second, assert the task is still blocked. This is §4a of
      `2026-08-21-which-band-blocked-belongs-to.md`, never reproduced.
- [ ] 7.2 Stamp `blocked_task_id` in `park_task_for_question` even when no transition is needed
      (`run_task_binding.py:394`).
- [ ] 7.3 Test: the transition map is untouched — `blocked` is still not a target of itself, and the
      task's status does not change when the second question is asked.
- [ ] 7.4 Test: a question about a *different* task releases nothing. The opposite error is worse.

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
- [ ] 9.5 **The archive refusal teaches.** Attempt to archive an agent with queued input and judge
      whether the message tells you what to do next.
- [ ] 9.6 **Nothing got quieter that should not have.** A real firing that fails for a real reason
      must still be visible; confirm this change did not turn a loud failure into a silent one.

## 10. User test guide

- [ ] 10.1 Write the operator-facing guide: how to tell a loop is stalled from one that is working,
      what each refusal reason means, and how to clear a loop and an agent that have gone wrong.
