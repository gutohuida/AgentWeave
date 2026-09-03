## 1. Reproduce it first

- [x] 1.1 Add `hub/tests/test_a_blocked_agent_workspace_holds_its_input.py`. Seed one agent, one
  conversation, one unbound operator entry, and patch `trigger_agent_directly` to raise today's
  refusal verbatim — `TriggerAgentError(409, "Could not prepare isolated worktree for <agent>: ...")`
  with no flags. Schedule the agent `DELIVERY_ATTEMPT_LIMIT` times and assert the entry ends
  `withdrawn` with `abandoned_reason` claiming it "failed 3 times". **Run it against unmodified code
  and confirm it passes.** A reproduction that does not pass first is not a reproduction, and this
  change's behaviour claim at HEAD is inference from the code, not a fresh drive.
- [x] 1.2 Assert the asymmetry in the same file: the identical loop with `NO_RUNNER`
  (`agent_wide=True`) leaves the entry `queued` at 0 attempts. Two refusals, same four schedules,
  opposite outcomes — that contrast is the finding, and it belongs in the suite rather than only in
  the proposal.
- [x] 1.3 Reproduce the two arms at the `worktrees` layer, without the Hub: in a temporary git repo,
  put a plain directory at `.agentweave/worktrees/<agent>` and assert `ensure_worktree` raises
  `IsolationUnavailableError`; then assert the message contains no remedy today. This is the case
  the ledger drove, pinned where it can be asserted cheaply.

## 2. The refusal says which workspace it could not prepare

- [x] 2.1 `hub/hub/api/v1/agent_trigger.py`: add `agent_workspace_unavailable: bool = False` to
  `TriggerAgentError.__init__` and store it, with a docstring paragraph in the style of its three
  neighbours — what the flag means, why it is not `agent_wide` (design D2), and that it does **not**
  imply `transient`, unlike `workspace_unavailable`.
- [x] 2.2 Split the `except` at `:879-883` into the two cases, deciding between them with
  `worktrees.takes_task_workspace(repo_root, config, turn_workspace.task_id)` — the same predicate
  `resolve_turn_workspace` obeys and the same call the one-turn-per-task refusal above already makes
  (design D1). Do not inspect the exception type or its message to decide this.
- [x] 2.3 The agent-workspace arm raises with `agent_workspace_unavailable=True` and a sentence
  naming the agent's own workspace. The task arm keeps today's flags exactly — nothing new, nothing
  removed — and names the **task**, not the agent.
- [x] 2.4 Add a test asserting the dispatch itself: with a stubbed `resolve_turn_workspace` that
  raises, a turn bound to no task produces a refusal carrying the flag and a turn bound to a task
  produces one without it. Assert the flags, not the wording.

## 3. The scheduler decides whether anything was starving behind it

- [x] 3.0 `hub/hub/task_workspace.py`: extract `takes_own_checkout(task) -> bool` — a task row exists,
  its `workspace_scheme` is `TASK_SCHEME`, and `worktrees.validate_task_id` accepts its id — and
  refactor `resolve_turn_workspace_inputs` to call it, keeping its `logger.warning` on the invalid-id
  branch (design D8). This is the predicate the scheduler asks, so that "does this task get its own
  checkout" has one implementation rather than a second copy in `turn_scheduler`.
  **Spell the scheme check `!=` with an early `return False`, not `==`.**
  `test_task_workspace_scheme.py`'s source scan substring-matches `.workspace_scheme =` and
  `workspace_scheme=` over lowercased source, and `task.workspace_scheme == TASK_SCHEME` contains the
  first while `task.workspace_scheme==TASK_SCHEME` is the second — measured, both make this file an
  offender and fail that test. Today's resolver passes only because it is already written `!=`. Do
  not relax the scan to accommodate a spelling; its bluntness is the mechanism (design D8).
- [x] 3.0a Re-run `hub/tests/test_task_workspace_scheme.py` immediately after 3.0 and confirm it is
  still 10 passed with migration `0095` the only file the scan matches — the baseline R3 measured at
  HEAD. Add one line to that test file's `test_nothing_outside_the_migration_writes_the_column`
  docstring recording that a *read* of the column is constrained to the negative form for this
  reason, so the next person to write `==` here meets an explanation rather than a mystery.
- [x] 3.1 `hub/hub/turn_scheduler.py`: add a helper that answers *would other queued input for this
  agent have run in a different workspace?* Inputs are the `entries`, `selected` and `hop_budget` the
  function already holds. True for an entry outside `selected` that is **eligible** — `hop_depth <=
  hop_budget`, conversation `lifecycle == "open"` — **and** either names a review that could actually
  have run (`review_task_id`, and `requirement_evidence.commit_for_task_review(...).resolved`, design
  D3b) or is about a task for which `task_workspace.takes_own_checkout` is true and
  `run_task_binding.decided_task_refusal` is `None`. *About a task* means the entry's own `task_id`
  **or** its conversation's `Conversation.task_id` — keep the `or`; design D3 says why collapsing it
  is wrong even though R2's argument implied it could be. Two queries **in this order**: the
  conversations the remaining entries belong to (for `lifecycle` and the inherited `task_id`), then
  one over the union of the task ids the entries name and the task ids those conversations carry. Not
  one query per entry, and not the task query first — its `IN` list is not known until the
  conversation query has run. Entries in the *controlling* conversation need no inheritance lookup at
  all (design D3).
- [x] 3.2 Write the argument down in the helper's docstring, and write down the part R1 got wrong:
  reaching this refusal proves the agent writes and the project is a repository, so those two drop
  out of the comparison — but it does **not** reduce to `entry.task_id is not None`, because a
  grandfathered task and an unmintable task id name a task and still run in the agent's own worktree
  (design D3). State R3's correction in the same breath: a deleted or decided task does **not** always
  do so, because `resolve_bound_task` falls through to `binding_for_conversation` rather than ending
  the resolution, which is exactly why the test is an `or` over the entry's task and its thread's and
  must stay one. Say which direction the approximations err in and why: a false *yes* destroys the
  operator's message, a false *no* only holds it.
- [ ] 3.3 Extend the condition at `:204` so an `agent_workspace_unavailable` refusal skips the
  counter unless 3.1 says something else could have run. Keep the existing `transient` and
  `agent_wide` terms untouched and readable; do not collapse the three questions into one boolean.
- [ ] 3.4 Tests, from `agent-conversation-workspace`'s three new scenarios: held when every other
  entry is unbound; counted-and-withdrawn when a task-bound entry waits in another conversation;
  counted when the refusal is the task-checkout one. The middle test is the one that keeps this
  change from breaching *"where other queued input could have run"* — say so in its docstring.
- [ ] 3.5 A test for the inherited binding: the other conversation's entry names no task but its
  conversation does. It must count. This is the half a scope test built only on `entry.task_id`
  would get wrong, and nothing else in the suite would notice.
- [ ] 3.6 A test that an entry inside `selected` naming a task that no longer resolves does **not**
  count as "could have run elsewhere" (design D3) — reaching this refusal proves the whole resolution
  for that batch, thread binding included, already came back unbound, and nothing about the next
  schedule changes its inputs.
- [ ] 3.7 **The grandfathered test, and it is the one this round exists for.** Another conversation's
  entry names a task whose `workspace_scheme` is `'agent'`. It must **not** count: that turn would run
  in the same blocked worktree, so dropping the head releases nothing. Set the column directly in the
  fixture — no runtime path writes it — and say in the test's docstring that a scope test built on
  `entry.task_id` alone passes every other test in this file and fails this one.
- [ ] 3.8 The same test one row over, for the three siblings that reach the agent worktree by another
  route: a task id `validate_task_id` refuses, a task row that has been deleted, and a task in
  `TERMINAL_FOR_BINDING`. None of them counts. **Bind the other conversation to nothing in those last
  two fixtures, and say in the docstring that this is load-bearing rather than tidy**: a deleted or
  decided task drops the binding and the resolution then inherits the thread's, so with a live
  conversation binding the entry really would take a checkout of its own and counting it would be
  correct (design D3).
- [ ] 3.8a The inverse of 3.8, and the case R3 added: another conversation's entry names a **decided**
  task, and that conversation is bound to a live task-scheme task. It **must** count — the turn would
  have run in the inherited task's checkout. Without this test, an implementer reading R2's "four
  routes" sentence would write the helper as an `and` over the entry's own task and pass every other
  test in the file.
- [ ] 3.8b A review entry whose task has no evidence naming a commit must **not** count (design D3b):
  `prepare_review_turn` would refuse it, and a refused review on a scheduler tick releases nothing
  while the head is destroyed on its behalf. The sibling assertion is that a review entry whose task
  *does* name a commit **does** count.
- [ ] 3.9 Eligibility: an entry outside `selected` that names a task with its own checkout but is
  **over the hop budget**, and one whose **conversation is closed**, each must not count. Neither can
  run, and counting on their behalf destroys the head.

## 4. The refusal says what would clear it

- [ ] 4.1 `hub/hub/worktrees.py`: give `ensure_worktree`'s two refusal branches — a symlink, and a
  path that is not the registered worktree for the expected ref — their own remedies, following
  `_merge_prerequisites`' precedent that this module writes the operator-facing sentence. Name the
  directory to remove and the prune that follows it; do not write one sentence covering both.
- [ ] 4.2 Do the same for the mid-merge refusal reached from the task arm, so the requirement's
  third scenario ("a different obstruction at the same path states a different remedy") is satisfied
  by real branches rather than by two wordings of one.
- [ ] 4.3 Assert the remedies at the `worktrees` layer, per branch, against the obstruction each was
  written for — not by substring-matching one shared phrase.

## 5. Reconcile what already exists

- [ ] 5.1 `hub/tests/test_a_delivery_attempt_means_a_delivery.py` defines `BAD_CHECKOUT` as
  *"Could not prepare isolated worktree for builder: object not found"* — F188's exact sentence,
  used there as the *entry-specific* example. Repoint it at a real task-checkout refusal so the file
  still tests what its docstring says it tests. Its assertion (still counts, still gives up) is
  correct and must not change.
- [ ] 5.2 Grep for other readers of the old sentence — `api/v1/inbound_queue.py`'s status
  derivation, any UI string, any test — and confirm none of them matches on its text. Record what
  the grep found in the change, including "nothing", because the next round should not have to
  re-run it to know.
- [ ] 5.3 Re-read `TriggerAgentError`'s `agent_wide` docstring (`agent_trigger.py:304-318`), which
  cites `:756` as the entry-specific worktree example. Update the citation and the sentence to the
  split this change makes, so the flag's documented invariant ("only refusals that are certainly
  agent-wide are marked") stays true of the code beneath it.
- [ ] 5.4 **The same job one module over, and it is inside the branch being edited.**
  `turn_scheduler.py:225-233`, the comment closing the counting branch, states flatly: *"a task's
  checkout that could not be prepared is the **task's** workspace, not the agent's, so other input
  really could run and the head entry really is in the way (design D3a)."* That is the claim this
  change falsifies for one of the two arms, and 5.2's grep for the refusal's *sentence* does not
  reach it — this comment quotes no sentence. Rewrite it to say which arm each half is about, and
  repoint the citation: `D3a` there means
  `2026-08-28-a-delivery-attempt-means-a-delivery`, and this change's own predicate decision is D8
  precisely so the two do not collide in this file.

## 6. Verify it against the product, not only the suite

- [ ] 6.1 `pytest hub/tests/ -v` under `py -3.11`, plus `ruff check src/ hub/ tests/`,
  `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/` and `mypy src/`.
- [ ] 6.2 Drive it on the trial Hub, on a fresh project, with a real agent bound to
  `claude-haiku-4-5`: block `.agentweave/worktrees/<agent>` with a plain directory, send a message,
  press Continue three times, and confirm the message is **still queued** and the queue reports the
  refusal with its remedy. This is the leg no unit test reaches, and the leg the ledger's own
  reproduction used.
- [ ] 6.3 Second leg, same project: queue a task-bound message for the same agent in another
  conversation behind the blocked one, and confirm the head is still given up on at the limit and
  the task turn then runs. Holding everything would look like success to leg 6.2 alone. The task must
  be an ordinary one — a drive cannot produce a grandfathered task, which is exactly why 3.7 exists
  and why this leg cannot stand in for it.
- [ ] 6.4 Third leg: remove the directory, `git worktree prune`, trigger once, and confirm the held
  message from 6.2 is delivered. F96's promise is the whole point of holding it, and it is unproven
  until the repair delivers it.
- [ ] 6.5 Append the drive's result to `scripts/drive/FINDINGS.md` under F188 — retired with the
  evidence, or still open with what was measured. Do not mark it retired on the strength of a green
  suite.
