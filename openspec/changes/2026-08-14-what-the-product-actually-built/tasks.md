# Tasks — What the product actually built

Phased so the guard that makes the live failure visible lands first and alone. Phases 2's items
**cannot be split**: the root change without the drift change causes a candidate storm, and without
the reachability refresh it replaces a false positive with a permanent false negative.

Migrations: current head is `0070`. The new one guards for a missing table as `0033`/`0034` do, and
**both** head assertions get bumped (`test_migrations.py` **and** `test_project_persistence.py`).

## 1. The guard that makes it visible

- [ ] 1.1 `requirement_evidence.is_reachable_from(root, commit, branch)` extracted;
      `is_reachable_from_main` keeps its behaviour by looping `MAIN_BRANCH_NAMES` and delegating, so
      the existing assertions at `test_task_integration.py:688,691` still hold.
- [ ] 1.2 `task_integration.ALREADY_INTEGRATED` and a guard in `integrate()`, **after**
      `branch_exists` and **before** the working-tree preconditions (D6). `is True` only.
- [ ] 1.3 Test: approving a footprint already on the target records `skipped`, names "already in",
      **and leaves `git rev-parse <target>` unchanged**. The sha assertion is load-bearing — without
      it the test passes on today's code.
- [ ] 1.4 Test: the already-there reason wins over a dirty checkout.

## 2. The footprint names the work

- [ ] 2.1 `worktrees.existing_worktree(repo_root, agent) -> Optional[Path]`, verifying through
      `_registered_worktree_branch` that git tracks the path as that agent's checkout. **Not**
      `.exists()` (D2). Provisions nothing. Invalid names and git failures return `None`.
- [ ] 2.2 `requirement_evidence.footprint_root(workspace, actor_kind, actor)`.
- [ ] 2.3 `capture_footprint` uses it, reading `evidence.actor_kind` / `evidence.actor`. **No
      signature change and no route change** (D1).
- [ ] 2.4 Remove the dead `locator` parameter from `read_footprint`.
- [ ] 2.5 `tree_entries(root, ref)` extracted from the inline `ls-tree` parse; `read_footprint` calls
      it with `HEAD`.
- [ ] 2.6 `detect_drift` compares against each footprint's own `branch`, cached per distinct ref;
      `hash_tree` computed at most once for `paths` footprints; no branch / detached / vanished ref
      raises nothing (D5).
- [ ] 2.7 `refresh_reachability(session, project_id, root, *, main_branch=None)` — bounded, one call
      per distinct commit, writes only what changed (D4).
- [ ] 2.8 Called from `task_transition_service._integrate` after a `MERGED` result, project-wide, and
      from `POST .../spec/drift/detect`.

## 3. Tests for phase 2 — the arrangement the product actually creates

New `hub/tests/test_evidence_footprint_root.py`, built with `_init_repo` + **`bind_project_workspace`**
+ `worktrees.ensure_worktree`, then a **new commit inside the worktree** (the HEADs are identical
straight after provisioning, so an assertion without it is vacuous).

- [ ] 3.1 Agent evidence is footprinted from the agent's worktree — branch, sha, and
      `reachable_from_main is False`. **This test fails on today's code.**
- [ ] 3.2 Operator evidence is footprinted from the project root (D3).
- [ ] 3.3 An agent with no worktree falls back to the root **and no worktree is created**.
- [ ] 3.4 An unregistered directory at the worktree path is not the agent's worktree (D2).
- [ ] 3.5 A non-repository project still footprints `paths`.
- [ ] 3.6 `existing_worktree` unit tests in `test_worktrees.py`, including that it creates nothing.
- [ ] 3.7 End-to-end in `test_task_integration.py`: worktree commit → agent evidence → operator
      accepts → approve → the commit and its file are on main, `source_branch` is the agent's branch,
      the checkout is still on main and clean.
- [ ] 3.8 Coverage reports `integrated` after that merge — the test that catches D4.
- [ ] 3.9 Drift: an unrelated commit on main raises nothing; a commit in the worktree raises exactly
      one candidate. (Agent evidence lands `awaiting`; the operator must accept it first.)
- [ ] 3.10 Drift: a footprint whose branch is gone raises nothing and does not error.

## 4. Statements on task payloads

- [ ] 4.1 New `hub/hub/spec_reading.py` — `payloads_for_documents(session, workspace, document_ids)`,
      one file read per distinct document, never raising; helpers indexing statements and acceptance
      criteria by requirement key.
- [ ] 4.2 `_attach_requirements(session, responses, *, project_id)` adds `key`, `statement`, `modal`.
      All four call sites updated.
- [ ] 4.3 Workspace resolution degrades to "no statements" rather than failing a task board (D8).
- [ ] 4.4 Correct the two docstrings that already claim statements —
      `requirement_links.py:230` and `schemas/tasks.py:202`.
- [ ] 4.5 Tests: statements present via REST and via the agent plane; a retired requirement yields
      `statement: null`; an unavailable workspace still returns tasks; one document is read once for
      a board of many tasks.

## 5. An agent can read a specification

- [ ] 5.1 `GET /spec/documents?path=&include=requirements|full` in `agent_actions.py`, using a query
      parameter so an agent-supplied path cannot become extra path segments.
- [ ] 5.2 Response shape per D7: payload, minted identifiers joined on, acceptance criteria nested,
      `phase` and `rigor` present, diagnostics rather than silent drops, `payload_missing` for a
      document carrying none.
- [ ] 5.3 Any phase (D7).
- [ ] 5.4 `read_spec_document(path, include)` in `mcp_server.py`, after `rename_spec_document` and
      **above** the `__main__` guard, which must remain last in the file.
- [ ] 5.5 Registered in `_tool_surface_lines` (`api/v1/agents.py`) — enforced by
      `test_tool_surface_matches_server.py`.
- [ ] 5.6 Named in the turn context's open-document block, so it is discoverable at the moment it
      applies.
- [ ] 5.7 Tests: the route returns identifiers and nested criteria; an unapproved document is
      readable; a payload-less document reports `payload_missing`; the tool is served over stdio
      (automatic via the existing spawned-equals-imported test).

## 6. Approval creates the work the document declares

- [ ] 6.1 `Task.spec_document_id` and `Task.spec_task_key` + migration `0071`, unique per
      `(project_id, document_id, spec_task_key)`.
- [ ] 6.2 On the transition into `approved`, materialise `payload.tasks`, resolving declared
      requirement **keys** to identifiers through the identity block and linking through the same
      path `create_task` uses.
- [ ] 6.3 Idempotent; an existing task is never modified, reassigned or reverted (D9).
- [ ] 6.4 Created unassigned, in the entry status. No tasks declared creates none, silently.
- [ ] 6.5 A declared task naming an unresolvable requirement is still created, with the reference
      preserved.
- [ ] 6.6 Tests: declared tasks appear with links; re-approval creates no duplicates; a task already
      moved is untouched; a document with no declared tasks approves and creates nothing; head
      assertions bumped to `0071`.

## 7. Housekeeping

- [ ] 7.1 Seed a `.gitignore` at project registration — additive, idempotent, never reordering the
      operator's own rules, never failing registration. Reuse or delete the orphaned
      `AGENTWEAVE_GITIGNORE_PATTERNS` in `src/agentweave/constants.py:43-60` rather than leaving a
      third spelling.
- [ ] 7.2 `spec_service.rename_document` promotes `subject` to `document.title`.
- [ ] 7.3 The UI stops presenting free-text prose as an "unresolved requirement". B3's
      preserve-verbatim rule is unchanged; only the wording of the surface changes.
- [ ] 7.4 `CLAUDE.md`: "21 starter charters" → 9.
- [ ] 7.5 Correct the checkboxes this run disproved in
      `openspec/changes/2026-08-13-approved-means-it-is-in-the-product/tasks.md`, pointing at this
      change.

## 8. Optional

- [ ] 8.1 `footprint: {branch, commit_sha, reachable_from_main}` on `_evidence_view`. A reviewer who
      could see `branch: master` on a builder's evidence would have caught this by eye. Last, because
      it may break exact-dict assertions.

## 9. Verification — agent-verifiable

- [ ] 9.1 `pytest hub/tests/ -q` and `pytest tests/ -q` **separately**.
- [ ] 9.2 `ruff check hub/ src/`; `black --target-version py311` on every file touched (never without
      the flag).
- [ ] 9.3 `npx tsc --noEmit`; `npx vitest run`.
- [ ] 9.4 `npx openspec validate --changes --strict`.
- [ ] 9.5 `npm run build`; `hub/hub/static/ui` replaced and confirmed with `diff -rq`.

## 10. Human-only verification

- [ ] 10.1 **On the real reproduction.** `aw-loop5` (`proj-30d900a7`) is preserved with `master` at
      `init` and the work on `agentweave/builder`. Restart the Hub, re-record evidence as the builder,
      and confirm the footprint names the agent's branch — then approve and watch `habits.py` arrive
      on `master`.
- [ ] 10.2 **Does coverage tell the truth through the whole cycle?** `not_integrated` before the
      merge, `integrated` after, and `skipped — already in master` on a second approval.
- [ ] 10.3 **Does an agent actually use the read tool?** Trigger a builder on a task and judge
      whether it reads the document rather than asking another agent.
- [ ] 10.4 **Are the tasks approval creates the ones you wanted?** Approve a document and judge
      whether its declared decomposition is work you would have written yourself.
- [ ] 10.5 **Re-run `/e2e-loop` from zero.** Every finding here was invisible to the unit suite
      because it lived between features. The run is the check.

## 11. User test guide

**Setup.** A git-backed project, an agent that has done work in its own worktree, and an approved
document that declares tasks.

1. **Record evidence as the agent, then look at what it names.**
   - *Expect:* the agent's branch and the agent's commit — not your own checkout's.
2. **Check coverage before approving.**
   - *Expect:* `verified, not integrated`. True, and previously unsayable.
3. **Approve the task.**
   - *Expect:* the agent's work is on your main branch. `git log` shows the merge.
4. **Check coverage again.**
   - *Expect:* `integrated`.
5. **Approve something else whose work is already merged.**
   - *Expect:* `skipped`, saying it is already in the branch — not "merged".
6. **Run drift detection.**
   - *Expect:* nothing. Merging is not drift.
7. **Ask an agent to read the specification.**
   - *Expect:* it can, and quotes `FR-n` identifiers matching the document.
8. **Approve a document that declares tasks.**
   - *Expect:* those tasks appear on the board, linked to their requirements, unassigned. Approve it
     again and nothing duplicates.

**Where it would go wrong:** if step 3 reports `merged` while `git log` shows nothing new, the
footprint is naming the wrong commit again — which is the defect this whole change exists to fix.
