# Tasks

Verification is split as the operator's standing directive requires: what an agent can check
itself, and what only a person can. Never mark a task complete because a plan for it exists.

Run the suite with **`py -3.11 -m pytest hub/tests/ -q`**. Bare `python` resolves to a venv that has
pytest but produces three false failures in `test_pty_runner.py` on a green tree.

## 1. Worktree machinery

- [x] 1.1 Add `review_path(repo_root, agent)` to `hub/hub/worktrees.py`, returning
      `.agentweave/reviews/<agent>`. Mirror `worktree_path`'s validation of the agent name.
- [x] 1.2 Add `ensure_review_checkout(repo_root, agent, sha)`: create the worktree detached at `sha`
      if absent, otherwise `git checkout --detach <sha>` in the existing one. Idempotent, the same
      way `ensure_worktree` is.
- [x] 1.3 Run `_symlink_shared_dependencies` against the review checkout. Without this the reviewer
      cannot run the suite, which is design D1's entire justification.
- [x] 1.4 Make `release_worktree` / cleanup aware of review checkouts, so a removed agent does not
      leave one behind.
- [x] 1.5 Unit tests: created detached; re-pointed rather than duplicated on a second call; refuses
      an unknown sha with a stated reason; symlinks present.

## 2. Resolving the commit

- [x] 2.1 Add a helper that returns the commit for a task's review from its most recent evidence
      footprint, plus any earlier distinct commits (design D5).
- [x] 2.2 Return a stated refusal — not an exception, not a guess — when the task has no evidence
      naming a commit.
- [x] 2.3 Unit tests: single evidence; two evidence rows naming different commits (the newer wins
      and the older is reported); no evidence at all.

## 3. The review turn

- [x] 3.1 In `agent_trigger.trigger_agent_directly`, resolve the workspace to the review checkout
      when the turn is a review, instead of `resolve_agent_workspace`.
- [x] 3.2 Set `AW_WORKSPACE_DIR` to the review checkout so the boundary moves with it. The value the
      agent is *told* and the value that is *enforced* must remain one value.
- [x] 3.3 Render the turn context for a review: that this is a review, of which task, at which
      commit, and that earlier evidence named a different commit where D5 applies. The boundary
      enforces *where*; this states *what*, and both are required (design D4).
- [x] 3.4 Refuse a review turn whose commit cannot be resolved, with the reason from 2.2.
- [x] 3.5 Tests: workspace is the review checkout; the agent's own worktree is outside the boundary
      for that turn; context names the task and commit.

## 4. Wiring the trigger

- [x] 4.1 Decide and implement how a review turn is requested. `loop-becomes-a-flow` owns automatic
      dispatch; this change needs only an operator-initiated path so the capability is reachable and
      testable before that change lands.
- [x] 4.2 Reject a review turn for an archived reviewer, reusing the existing archived-agent guard.
- [x] 4.3 Where `Task.reviewer` names an agent not on the roster, surface it and fall back to
      operator review. Never silently substitute a different agent.

## 5. Verification an agent can do

- [x] 5.1 `py -3.11 -m pytest hub/tests/ -q` — green, and no new skips.
- [x] 5.2 `cd hub/ui && npm run lint && npx tsc --noEmit` if any UI file changed. **Not applicable** — this change touches no UI file.
- [x] 5.3 `uvx ruff@0.15.22 check src/ hub/ tests/` and `uvx black@26.5.1 --check` at CI's pinned
      versions.
- [x] 5.4 `npx openspec validate --changes --strict`.
- [x] 5.5 An end-to-end run against the trial Hub using `scripts/drive/`: an author completes work
      on its own branch, a reviewer is given a review turn, and the reviewer **reads a file that
      does not exist on the main branch**. This is the assertion that distinguishes this change from
      doing nothing.
- [x] 5.6 The reviewer runs the project's test suite inside its review checkout and reports a result
      it observed rather than one it was told.

## 6. Verification only a person can do

- [ ] 6.1 Re-run the exact scenario that produced finding F10 — `builder` completes FR-2 and FR-3,
      `critic` reviews — and confirm `critic` does **not** have to ask `builder` what changed.
      The transcript in `scripts/drive/FINDINGS.md` is the before-state to compare against.
- [x] 6.2 Read one review turn's context and judge whether an agent would understand it is
      reviewing rather than building. This is the failure D4 names as most likely, and no test
      catches it. **Answered by the operator 2026-08-24: "Yeah the text reads alright."**
- [ ] 6.3 Confirm the review checkouts on disk are what you expected, and that nothing accumulated.

## 7. User test guide

- [x] 7.1 Write the operator-facing walkthrough: how to request a review, what the reviewer can and
      cannot see, what to do when the commit cannot be resolved, and where the review checkouts live.
