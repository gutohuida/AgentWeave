## 1. Reproduce it first

- [ ] 1.1 Add `hub/tests/test_a_blocked_agent_workspace_holds_its_input.py`. Seed one agent, one
  conversation, one unbound operator entry, and patch `trigger_agent_directly` to raise today's
  refusal verbatim — `TriggerAgentError(409, "Could not prepare isolated worktree for <agent>: ...")`
  with no flags. Schedule the agent `DELIVERY_ATTEMPT_LIMIT` times and assert the entry ends
  `withdrawn` with `abandoned_reason` claiming it "failed 3 times". **Run it against unmodified code
  and confirm it passes.** A reproduction that does not pass first is not a reproduction, and this
  change's behaviour claim at HEAD is inference from the code, not a fresh drive.
- [ ] 1.2 Assert the asymmetry in the same file: the identical loop with `NO_RUNNER`
  (`agent_wide=True`) leaves the entry `queued` at 0 attempts. Two refusals, same four schedules,
  opposite outcomes — that contrast is the finding, and it belongs in the suite rather than only in
  the proposal.
- [ ] 1.3 Reproduce the two arms at the `worktrees` layer, without the Hub: in a temporary git repo,
  put a plain directory at `.agentweave/worktrees/<agent>` and assert `ensure_worktree` raises
  `IsolationUnavailableError`; then assert the message contains no remedy today. This is the case
  the ledger drove, pinned where it can be asserted cheaply.

## 2. The refusal says which workspace it could not prepare

- [ ] 2.1 `hub/hub/api/v1/agent_trigger.py`: add `agent_workspace_unavailable: bool = False` to
  `TriggerAgentError.__init__` and store it, with a docstring paragraph in the style of its three
  neighbours — what the flag means, why it is not `agent_wide` (design D2), and that it does **not**
  imply `transient`, unlike `workspace_unavailable`.
- [ ] 2.2 Split the `except` at `:879-883` into the two cases, deciding between them with
  `worktrees.takes_task_workspace(repo_root, config, turn_workspace.task_id)` — the same predicate
  `resolve_turn_workspace` obeys and the same call the one-turn-per-task refusal above already makes
  (design D1). Do not inspect the exception type or its message to decide this.
- [ ] 2.3 The agent-workspace arm raises with `agent_workspace_unavailable=True` and a sentence
  naming the agent's own workspace. The task arm keeps today's flags exactly — nothing new, nothing
  removed — and names the **task**, not the agent.
- [ ] 2.4 Add a test asserting the dispatch itself: with a stubbed `resolve_turn_workspace` that
  raises, a turn bound to no task produces a refusal carrying the flag and a turn bound to a task
  produces one without it. Assert the flags, not the wording.

## 3. The scheduler decides whether anything was starving behind it

- [ ] 3.1 `hub/hub/turn_scheduler.py`: add a helper that answers *would other queued input for this
  agent have run in a different workspace?* Inputs are the `entries` and `selected` the function
  already holds. True when an entry outside `selected` names a task or a review, or when its
  conversation carries a task binding (`Conversation.task_id`); one query for the distinct
  conversation ids of the remaining entries, not one per entry.
- [ ] 3.2 Write the reduction down in the helper's docstring rather than leaving it implicit:
  reaching this refusal means the agent writes and the project is a repository, so
  `takes_task_workspace` reduces to `task_id is not None` for every other entry in that queue
  (design D3). Without that sentence the next reader cannot tell why the config and repo_root are
  absent from a workspace question.
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
  count as "could have run elsewhere" (design D3, last bullet) — it will fail here identically on
  the next schedule.

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
- [ ] 5.3 Re-read `TriggerAgentError`'s `agent_wide` docstring, which cites `:756` as the
  entry-specific worktree example. Update the citation and the sentence to the split this change
  makes, so the flag's documented invariant ("only refusals that are certainly agent-wide are
  marked") stays true of the code beneath it.

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
  the task turn then runs. Holding everything would look like success to leg 6.2 alone.
- [ ] 6.4 Third leg: remove the directory, `git worktree prune`, trigger once, and confirm the held
  message from 6.2 is delivered. F96's promise is the whole point of holding it, and it is unproven
  until the repair delivers it.
- [ ] 6.5 Append the drive's result to `scripts/drive/FINDINGS.md` under F188 — retired with the
  evidence, or still open with what was measured. Do not mark it retired on the strength of a green
  suite.
