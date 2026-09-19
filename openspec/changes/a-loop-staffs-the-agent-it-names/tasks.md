# Tasks — a loop staffs the agent it names

**Round 1, 2026-09-19.** Not yet re-derived. `design.md` holds two open questions R2 owns, and
either could move group 2.

**Precondition, and the first thing to check.** This change edits `_agents_that_are_free` and its
callers. `an-unstaffed-review-names-its-holders` **group 1** re-expresses that function as a
projection over a new `_roster_availability`, and is approved to build first. Do not start until it
has landed, and re-read `scheduler.py` before task 1.2 — the shape this list describes is the
post-group-1 one.

**Locate every call site by `grep -n "await _agents_that_are_free("`, never by the line numbers in
this file.** They were correct at `ddf73aa` (`:348`, `:1263`, `:1444`) and the sibling change moves
them. A count other than 3 means the tree has moved further than this list knows — stop and
re-derive rather than guessing which one is missing. This instruction exists because the sibling's
own task 1.2 named three caller lines and all three were wrong (R7, `ddf73aa`).

## 0. Preconditions

- [ ] 0.1 Confirm `an-unstaffed-review-names-its-holders` group 1 is built and its tests are green.
      If it is not, stop: the two changes edit the same function and the merge is not worth the
      round it would cost.
- [ ] 0.2 Record the three call sites of `_agents_that_are_free` as they stand now, by grep, with
      their enclosing function names. Every later task refers to these, not to line numbers.
- [ ] 0.3 Run the current suite for the files this change touches and record the baseline:
      `py -3.11 -m pytest hub/tests/test_flow_width.py hub/tests/test_reviewer_ladder.py
      hub/tests/test_a_task_nothing_will_move_holds_nobody.py hub/tests/test_a_held_agent_is_busy.py -q`.
      A test that is already red is not this change's to fix, and must be known before it is blamed.

## 1. The scope filter (design D1, D2, D7)

- [ ] 1.1 **Test first.** A documentless loop whose job names `gamma`, with `gamma` running a turn
      and `alpha` free and idle: `decide_firing` selects nobody, and the pending task keeps its
      status and gains no assignee. This is finding F128's own reproduction
      (`scripts/drive/t_run_while_busy.py`) as a unit test.
      *Mutation:* remove the filter. The test must fail, and it must fail by selecting `alpha` —
      assert the selected agent, not merely that something was selected.
- [ ] 1.2 **Test:** the same project and the same two agents, with the loop declaring a
      specification document. `alpha` **is** selected. This is the test that keeps the change from
      being a project-wide regression, and it must fail if the filter is applied unconditionally.
- [ ] 1.3 Add `_agents_a_loop_may_staff(session, loop, *, default_agent)` to `hub/hub/scheduler.py`.
      It calls the existing availability read and filters its result; it computes no availability of
      its own. For `loop.spec_document_id is None` it returns an empty list (design D2 — the job's
      own agent is reached through `decide_firing`'s default branch, never through the pool). For a
      flow it returns the availability read unchanged.
      - Its docstring states **why the result is empty rather than `{job.agent}`**, and names the
        default branch that makes it so. A future reader who does not know that will "fix" this.
- [ ] 1.4 Point `decide_firing`'s pool read at it. **Do not touch the default-agent branch**, which
      is tested against `running`/`held_agents`/`taken` and deliberately not against the pool; its
      own comment names the test that caught the alternative.
- [ ] 1.5 **Test:** a documentless loop with two startable tasks, its own agent free and a sibling
      free, starts exactly one task, for its own agent. This is D2's deliberate removal of width
      for loops, and without a test it reads as a regression to whoever meets it next.
      *Mutation:* return `[default_agent]` from the filter instead of an empty list. This test must
      fail — and if it passes, D2's reasoning is wrong and R2's conclusion needs revisiting.

## 2. The busy guard (design D3)

- [ ] 2.1 **Test:** `_loop_flow_busy_reason` returns a reason for a documentless loop whose agent is
      busy **while another agent is free** and the queue holds an open task. Today it returns
      `None`; this is the guard collapsing back to `_loop_agent_busy_reason`, which
      `agent-loops:791`'s unconditional first sentence has always required.
      *Mutation:* leave `_loop_flow_busy_reason` reading the project-wide pool. The test must fail.
- [ ] 2.2 **Test:** the same shape with a document declared returns `None` — a flow is still allowed
      to proceed and staff the free agent.
- [ ] 2.3 Point `_loop_flow_busy_reason`'s pool read at `_agents_a_loop_may_staff`. Update its
      docstring: the paragraph at `:335-338` currently *documents F128 as an open defect* and must
      not survive the change that closes it.
- [ ] 2.4 **Test:** the cron path. `_do_fire_job` on a documentless loop whose agent is busy and
      whose sibling is free writes **no `JobRun` and no event**, and still advances `job.next_run`.
      The guard's existing comment is explicit that a row here would evict real history through
      `_prune_job_history`'s 100-row window.
- [ ] 2.5 **Test:** repeated firings in that state create zero inbound queue entries — the
      accumulation `agent-loops:791` exists to stop, now reachable in a multi-agent project.

## 3. What the operator is told (design D4)

- [ ] 3.1 **Test:** pressing Run on a documentless loop whose agent is busy, with a sibling free,
      answers **409**, and the detail **does not contain** "no other agent is free". Assert the
      absence as well as the presence; the defect being prevented is a true-sounding sentence.
- [ ] 3.2 **Test:** the same press on a flow still answers with today's wording.
- [ ] 3.3 Split the `why` clause in `run_job` (`hub/hub/api/v1/jobs.py`, the branch that re-asks the
      busy guard) so a documentless loop is told the loop runs only the agent its job names, and a
      flow keeps both of today's clauses.
      - The empty-queue clause — *"this loop's queue holds no open task for another agent to take"* —
        drops its trailing five words for a loop. R2 should confirm that reads correctly rather than
        merely parsing.
- [ ] 3.4 **Test:** the board. A documentless loop in this state reports the busy reason as its
      stall reason, not "no claimable task". `_batch_loop_summaries` re-asks the guard only when the
      decision is `DECISION_STALLED` — assert the decision kind as well as the sentence, because the
      sentence can be right for the wrong reason.
- [ ] 3.5 Re-read `resolve_reviewer`'s rung-3 sentence (*"Every agent on the roster is…"*) and
      confirm it is unreachable for a documentless loop. Design D5 says it is, via the
      `awaiting_landing` branch. **If it is reachable, D5 is wrong and this task stops the change**
      rather than editing the sentence.

## 4. What must not move

- [ ] 4.1 `resolve_reviewer` keeps the project-wide pool at both call sites, including
      `hub/hub/run_divergence.py`'s (design D5). Add a test that a divergence recovery on a
      **loop's** task can still resolve a project-wide reviewer, since that is the case narrowing it
      would silently break.
- [ ] 4.2 Run the four files from 0.3 and diff against that baseline. Any newly red test in
      `test_flow_width.py` or `test_reviewer_ladder.py` is a flow regression and is this change's
      fault by default.
- [ ] 4.3 `py -3.11 -m pytest hub/tests/ -q` in full, once, at the end.
- [ ] 4.4 `ruff check src/ hub/ tests/` and `black --check src/ hub/hub/ hub/tests/ tests/
      --target-version py311` and `mypy src/`. No UI bundle: nothing under `hub/ui/` is touched, so
      `make ui` is not required and must not be run.

## 5. Drive it

- [ ] 5.1 Reproduce F128 against a **trial** Hub before the fix, with the finding's own shape: a
      three-agent project, a documentless loop naming one agent, that agent put mid-turn, Run
      pressed. Record the conversation id and the task's assignee. Bind Haiku for every agent turn.
- [ ] 5.2 Repeat after the fix. The press answers 409, no conversation is created, and the task
      keeps its assignee empty.
- [ ] 5.3 Drive a **flow** in the same project through a two-task firing and confirm both start.
      A drive that only shows the refusal has not shown that width survived.

## 6. Close it out

- [ ] 6.1 Set F128's `**Status:**` to fixed, naming the commit, and **keep the entry's account of
      the authority hole** — `charter_id`, `runner_id` and the three flags are why this was not a
      cosmetic finding, and that reasoning is the thing a future reader needs.
- [ ] 6.2 F127 is **already fixed** (`c8e3bbd`, 2026-09-14) and this change does not reopen it.
      Append a note to F127 recording that its 409 *sentence* was re-derived here, and do not change
      its `Status:`.
- [ ] 6.3 Correct `spec-queue/DECISIONS.md:748`, which says *"F127's 500 must be fixed in the same
      change"*. It was fixed five days before that row was written. Leave the row and append the
      correction; a decision log that is silently edited stops being evidence.
- [ ] 6.4 Re-derive `test-guide.md` against the change as built, splitting agent-verifiable checks
      from the ones only the operator can make on `:8000`.
