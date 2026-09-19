# Tasks — a loop staffs the agent it names

**Round 1 wrote this list; Round 2 (adversarial) returned DO NOT APPROVE and Round 3 rewrote it.**
Read `design.md`'s `## Round log` before starting — three of R1's four structural claims were wrong,
and a task list that looks reasonable is exactly how the last two changes shipped defects.

**Locate every call site by `grep -n "await _agents_that_are_free("`, never by a line number in this
file.** They were `:348`, `:1263`, `:1444` at `ddf73aa`. **R2-7: after
`an-unstaffed-review-names-its-holders` group 1 lands there will be TWO**, because
`resolve_reviewer` moves to `_roster_availability` — so do not treat a count other than 3 as an
error, which is what R1's version of this instruction said. Two or three are both expected; anything
else means the tree has moved further than this list knows.

## 0. Preconditions

- [ ] 0.1 **Check, do not gate.** If `an-unstaffed-review-names-its-holders` group 1 has landed,
      re-grep the call sites and read the new `_agents_that_are_free`. If it has not, **proceed
      anyway** — R2-7 established there is no collision: that change's own task 1.2 keeps
      `_loop_flow_busy_reason` and `decide_firing` calling `_agents_that_are_free` unchanged, and a
      filter above the pool touches neither. *(R1 made this a hard stop. That change's tasks.md
      still opens with a stale "STOPPED AT REV — do not build any task here" banner, so a window
      obeying a hard stop would have stopped forever.)*
- [ ] 0.2 Record the call sites as they stand now, by grep, with their enclosing function names.
- [ ] 0.3 Baseline the **real** surface, not a quarter of it. `grep -rl --include=*.py
      "decide_firing\|_loop_flow_busy_reason" hub/tests/` returns **16** files; run all of them and
      record which are already red. **Keep `--include=*.py`** — without it the same grep returns 35,
      the extra 19 being `__pycache__` binaries, and R2 quoted the bare form. At minimum it must
      include the ones that build **documentless**
      loops by default: `test_a_loop_does_not_staff_its_own_review.py`,
      `test_actor_aware_claimability.py`, `test_a_review_nobody_is_doing.py`,
      `test_firing_decision_is_shared.py`, `test_task_turn_collision.py`, `test_board_agent_role.py`,
      `test_loop_selection_carries_its_agent.py`, `test_a_flow_names_what_it_cannot_staff.py`,
      `test_review_leaves_the_pool.py`.
      **`test_flow_width.py` defaults to `declares_document=True` (`:54`), so it is not a guard for
      this change** — a green run of it proves nothing here, and R1 listed it as if it did.

## 1. The scope filter (design D1, D2, D7)

- [ ] 1.1 **Test first.** A documentless loop whose job names `gamma`, with `gamma` running a turn
      and `alpha` free and idle, and one **unassigned** pending task: `decide_firing` selects
      nobody, and the task keeps its status and gains no assignee. This is F128's own reproduction
      (`scripts/drive/t_run_while_busy.py`) as a unit test.
      *Mutation:* remove the filter. The test must fail **by selecting `alpha`** — assert the agent,
      not merely that something was selected.
- [ ] 1.2 **Test:** the same project and agents with a specification document declared. `alpha` **is**
      selected. This is what keeps the change from being a project-wide regression, and it must fail
      if the filter is applied unconditionally.
- [ ] 1.3 Add `_agents_a_loop_may_staff(session, loop)` to `hub/hub/scheduler.py`. It calls the
      existing availability read and filters the result; it computes no availability of its own.
      `loop.spec_document_id is None` → empty list; otherwise the read unchanged.
      **No `default_agent` parameter** (R2-8): nothing would read it, and an unused agent name in a
      function about *which agents* invites a future reader to add it to the result.
      - The docstring states **why the result is empty rather than `{job.agent}`** and names
        `decide_firing`'s default branch, which is how the job's own agent is actually reached.
- [ ] 1.4 Point `decide_firing`'s pool read at it. **Do not touch the default-agent branch**
      (`:1601-1618`), which is tested against `running`/`held_agents`/`taken` and deliberately not
      against the pool.
- [ ] 1.5 Extend the `continue` comment at `:1622-1624`. It says *"Width is bounded by available
      agents (design D5)"*; for a documentless loop the bound is now **one agent, permanently**, and
      a reader who does not know that will read the skip as a bug.
- [ ] 1.6 **Test:** a documentless loop with two startable **unassigned** tasks, its own agent free
      and a sibling free, starts exactly one, for its own agent.
      *Mutation:* return `[default_agent]` instead of an empty list. This test must fail — and if it
      passes, D2 is wrong.

## 2. Staffing is not resumption (design D6 — R2-2)

- [ ] 2.1 **Test first, because this is the arm that falsified R1's requirement.** A documentless
      loop naming `gamma`, `task1` assigned to `alpha`, `task2` pending and unassigned, `gamma`
      idle: the firing resumes `task1` for **`alpha`** and starts `task2` for **`gamma`**. Two
      selections, one of them an agent the job does not name — correct, and the requirement must
      permit it.
      *Mutation:* make the filter apply to the resumption arm. This test must fail.
- [ ] 2.2 **Test:** with `gamma` running a turn instead, the firing is refused outright and `task1`
      is **not** resumed either (R2-6 — the guard refuses the whole firing at `:2758-2772` before
      the walk). Assert that no run is started for `alpha`. This is the cost D6 is conditional on,
      and it must be a test rather than a sentence.

## 3. The busy guard (design D3)

- [ ] 3.1 **Test:** `_loop_flow_busy_reason` returns a reason for a documentless loop whose agent is
      busy **while another agent is free** and the queue holds an open task. Today it returns
      `None`.
      *Mutation:* leave it reading the project-wide pool. The test must fail.
- [ ] 3.2 **Test:** the same shape with a document declared returns `None`.
- [ ] 3.3 Point `_loop_flow_busy_reason`'s pool read at `_agents_a_loop_may_staff`. Update its
      docstring: `:335-338` currently **documents F128 as an open defect** and must not survive the
      change that closes it.
- [ ] 3.4 **Test:** the cron path. `_do_fire_job` on a documentless loop whose agent is busy and
      whose sibling is free writes **no `JobRun` and no event**, and still advances `job.next_run`.
- [ ] 3.5 **Test:** repeated firings in that state create zero inbound queue entries.

## 4. The F70 exception (design D5 — R2-1, the blocking finding)

- [ ] 4.1 **Test first.** A **documentless** loop with a task in `under_review` whose assignee is the
      agent that produced the work — the wedged row `_guard_reviewer_is_not_the_author` now blocks
      but legacy data still holds. `decide_firing` reaches the reviewer ladder (`:1738`) and
      resolves a **project-wide** sibling.
      *Mutation:* apply the loop filter to `resolve_reviewer`'s rung-2 pool. The test must fail, and
      the failure must be *no reviewer resolved* — which is the permanent wedge the exception
      exists to prevent.
      **No existing test covers this: every fixture in `test_a_review_nobody_is_doing.py` sets
      `spec_document_id` (`:135`).**
- [ ] 4.2 **Test:** `run_divergence.py:441`'s recovery on a **loop's** task still resolves a
      project-wide reviewer after a verdict-less turn.
- [ ] 4.3 Confirm no code change is needed for 4.1 and 4.2 — `resolve_reviewer` keeps
      `_agents_that_are_free` at both call sites. **If either test passes only after a code change,
      D5 has moved and R3's reasoning needs re-deriving, not patching.**

## 5. What the operator is told (design D4)

- [ ] 5.1 **Test:** pressing Run on a documentless loop whose agent is busy, with a sibling free,
      answers **409** and the detail **does not contain** "no other agent is free". Assert the
      absence as well as the presence; the defect is a true-sounding sentence.
- [ ] 5.2 **Test:** the same press on a flow keeps today's wording.
- [ ] 5.3 Split the `why` clause in `run_job` (`hub/hub/api/v1/jobs.py`, the branch that re-asks the
      busy guard) so a documentless loop is told the loop runs only the agent its job names.
      The empty-queue clause drops its trailing *"for another agent to take"* for a loop.
- [ ] 5.4 **Test:** the board. A documentless loop in this state reports the busy reason, not "no
      claimable task". **Assert the decision kind as well as the sentence** — R2 traced that the
      sentence is only correct because `jobs.py:355` replaces `_stall_reason_from_walk`'s
      *"no claimable task among 1 open (1 pending)"*, so the sentence can be right for the wrong
      reason.

## 6. What must not move

- [ ] 6.1 Re-run the full 0.3 baseline and diff. A newly red test in any file that defaults to
      `declares_document=True` is a flow regression and is this change's fault by default.
- [ ] 6.2 `py -3.11 -m pytest hub/tests/ -q` in full, once, at the end.
- [ ] 6.3 `ruff check src/ hub/ tests/`; `black --check src/ hub/hub/ hub/tests/ tests/
      --target-version py311`; `mypy src/`. Nothing under `hub/ui/` is touched, so `make ui` is not
      required and must not be run.

## 7. Drive it

- [ ] 7.1 Reproduce F128 against a **trial** Hub before the fix, in the finding's own shape: a
      three-agent project, a documentless loop naming one agent, that agent mid-turn, Run pressed.
      Record the conversation id and the task's assignee. Bind Haiku for every agent turn.
- [ ] 7.2 Repeat after the fix: 409, no conversation created, assignee still empty.
- [ ] 7.3 Drive a **flow** in the same project through a two-task firing and confirm both start. A
      drive that only shows the refusal has not shown that width survived.
- [ ] 7.4 **Answer design.md's open question.** Read-only, against the operator's database
      (`mode=ro`, never a write, never a restart): does any task sit in a review status whose
      assignee is the agent that completed it, on a loop with no `spec_document_id`? That decides
      whether task 4.1 is a regression guard or a live repair.

## 8. Close it out

- [ ] 8.1 Write `test-guide.md` (R2-12 — there is none to re-derive), splitting agent-verifiable
      checks from the ones only the operator can make on `:8000`.
- [ ] 8.2 Set F128's `**Status:**` to fixed, naming the commit, and **keep the entry's account of
      the authority hole** — `charter_id`, `runner_id` and the three flags are why this was not a
      cosmetic finding.
- [ ] 8.3 Append a note to F127 recording that its 409 *sentence* was re-derived here. Do not change
      its `Status:` — it was fixed by `c8e3bbd` on 2026-09-14.
- [ ] 8.4 Append a correction to `spec-queue/DECISIONS.md:748`, which requires *"F127's 500 must be
      fixed in the same change"*. It was stale when written. **Append; do not edit the row** — a
      decision log that is silently rewritten stops being evidence.
