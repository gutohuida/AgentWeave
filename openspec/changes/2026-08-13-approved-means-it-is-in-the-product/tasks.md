# Tasks — Approved means it is in the product

Phased so the dangerous part comes last and behind a refusal. **Phase 2 alone is useful**: it tells
an operator that a task's work will not merge, before they approve it, which nothing does today.
Nothing writes to a repository until phase 3.

Migrations: current head is `0069`. The new one guards for a missing table as `0033`/`0034` do, and
**both** head assertions get bumped (`test_migrations.py` **and** `test_project_persistence.py`).

## 1. The main branch, named

- [x] 1.1 `Project.main_branch` (nullable) + migration `0070`. Null means "not chosen", which is not
      an error and blocks nothing.
- [x] 1.2 `detect_main_branch(root)` — reuses the existing `MAIN_BRANCH_NAMES` order to *suggest* a
      name. It returns a suggestion and never assigns one.
- [x] 1.3 Operator route to read and set the project's main branch, rejecting a name the repository
      does not have.
- [x] 1.4 **`requirement_evidence.MAIN_BRANCH_NAMES` keeps its current reporting behaviour
      untouched.** A test asserts a project with `main_branch` null reports integration exactly as it
      did before this change — the guess stays legal for reading and becomes illegal for writing.
- [x] 1.5 Surface the setting where a project is configured, offering the detected name for the
      operator to accept.

## 2. Mergeability in the gate

- [x] 2.1 `integration_target(session, task)` — the commits to integrate: the newest `commit_sha`
      among the task's **accepted** evidence footprints, per distinct branch. Awaiting and rejected
      evidence contribute nothing. A `paths` footprint contributes nothing.
- [x] 2.2 `would_conflict(root, commit, main_branch)` wrapping the existing
      `worktrees._merge_tree_conflicts()`. Touches no working tree and no index.
- [x] 2.3 `GateRefusal` gains a third list for unmergeable work, carrying the conflicting paths.
      `detail()` and `to_dict()` include it, and the existing `message` sentence still reads
      correctly for a caller that reads only that.
- [x] 2.4 Called from inside `requirement_gate.evaluate` — **not** a second call site in
      `apply_transition`. B4 §3.1's "one function, one place" property must survive this change.
- [x] 2.5 The conflict refusal fires **regardless of rigor**, including `sketch`. It is a claim about
      possibility, not about verification.
- [x] 2.6 No conflict check where there is nothing to merge: no configured main branch, no accepted
      git footprint, or not a repository.

## 3. The merge

- [x] 3.1 `integrate(root, commit, main_branch)` — `git merge` into the main branch in the primary
      checkout. **Never `push`, never contacts a remote**, asserted by a source-level test as well as
      behaviourally.
- [x] 3.2 Preconditions, each returning a distinct stated reason rather than a silent skip: main
      branch configured; primary checkout clean; primary checkout on the main branch.
- [x] 3.3 Wired into `apply_transition` on the move into `approved`, after the transition is
      recorded. **A merge failure never rolls the transition back** (D6).
- [x] 3.4 Integration runs regardless of rigor (D5).
- [x] 3.5 A project that is not a repository, or has no accepted git footprint, attempts nothing and
      raises nothing.

## 4. The record

- [x] 4.1 `task_integrations` model + the same migration `0070` — task, project, commit, source
      branch, target branch, outcome (`merged`/`skipped`/`failed`), reason, mechanism (`local`),
      approving actor, time.
- [x] 4.2 Append-only: no update path, no delete path, asserted by a source scan the way
      `spec_rigor_events` is.
- [x] 4.3 `mechanism` is stored on every row so a later GitHub-based integration is distinguishable
      in history rather than conflated with this one (D8).
- [x] 4.4 Route to read a task's integration history.

## 5. Navigation

- [x] 5.1 A task shows whether its work was integrated, and where it went — or why it did not.
- [x] 5.2 The gate refusal surface renders the unmergeable case with its conflicting paths, beside
      the unverified-requirement case it already renders.
- [x] 5.3 Coverage surfaces are **not** changed. B3 already reports `verified, not integrated`; this
      change makes that state reachable in the other direction, and needs no new vocabulary for it.

## 6. Tests — agent-verifiable

- [x] 6.1 Target selection: the newest accepted footprint commit wins; awaiting evidence contributes
      nothing; rejected evidence contributes nothing; a `paths` footprint contributes nothing;
      multiple branches yield multiple targets.
- [x] 6.2 **The demonstrable case, one test with three outcomes:** a task approves and its commit is
      on main; the same task with a conflicting commit is refused; the same task approves and merges
      after the conflict is resolved.
- [x] 6.3 Later commits on the agent's branch are **not** merged (D1) — the test that proves the
      commit-not-branch decision.
- [x] 6.4 A `sketch` document's task integrates identically to a `gate` document's task (D5).
- [x] 6.5 A conflict refuses approval at `sketch` rigor (D3's accepted consequence).
- [x] 6.6 Each skip precondition, separately: no main branch; dirty checkout; checkout on another
      branch. Each records its own reason and each leaves the approval standing.
- [x] 6.7 A failed merge leaves the task `approved` and coverage reporting
      `verified, not integrated` (D6).
- [x] 6.8 A non-repository project approves exactly as it did before this change (D7).
- [x] 6.9 A project with `main_branch` null reports integration exactly as it did before this change
      (task 1.4).
- [x] 6.10 **Nothing pushes** — a source-level assertion plus a test with a configured remote that
      fails if the remote is touched.
- [x] 6.11 `task_integrations` appends and never updates.
- [x] 6.12 The gate is still one function called from one place — the B4 §3.1 source check still
      passes and is extended to cover the conflict path.
- [x] 6.13 `test_migrations.py` and `test_project_persistence.py` head assertions bumped to `0070`;
      the migration guards for a missing table.
- [x] 6.14 `pytest hub/tests/ -q` and `pytest tests/ -q` separately; `ruff`; `black
      --target-version py311`; `npx tsc --noEmit`; `npx openspec validate --changes --strict`.
- [x] 6.15 `hub/hub/static/ui` refreshed and confirmed with `diff -rq`.

## 7. Human-only verification

This change writes to the operator's git history automatically. What matters here is whether that
ever feels like something happening *to* you rather than *for* you.

- [ ] 7.1 **Does the first automatic merge feel safe or alarming?** Approve one task on a real
      project and watch what lands on main. This is the judgement the whole change rests on.
- [ ] 7.2 **Is the conflict refusal actionable?** Create a genuine conflict, get refused, and decide
      whether you know what to do without opening a terminal.
- [ ] 7.3 **Is "merges its ancestors too" acceptable in practice?** (D1) Approve a task whose branch
      carries earlier unapproved work and judge whether what landed was what you expected. If it was
      not, per-task branches move from a non-goal to the next change.
- [ ] 7.4 **Are the skip reasons ones you can act on?** Trigger a dirty-checkout skip and judge the
      wording.
- [ ] 7.5 **Is confirming a main branch at setup the right moment**, or does it arrive before you
      have decided how the project works?

## 8. User test guide

**Setup.** A project that is a git repository, with an approved specification, a task linked to its
requirements, and an agent that has done work on its own branch.

1. **Name the main branch.** Open the project's settings.
   - *Expect:* a branch is suggested, and nothing merges until you accept it.
2. **Approve a task with accepted evidence.**
   - *Expect:* the work is on your main branch when the approval returns. `git log` shows the merge.
     Coverage moves the requirement from `verified, not integrated` to `integrated`.
3. **Check what actually landed.** `git log main` for the merged commit.
   - *Expect:* the commit the evidence named, and its ancestors — **not** commits the agent made
     afterwards.
4. **Cause a conflict.** Change the same lines on main that the agent's branch changed, then approve
   another task.
   - *Expect:* refused before anything is merged, naming the conflicting files. Your repository is
     untouched.
5. **Approve with a dirty checkout.** Leave an uncommitted change and approve.
   - *Expect:* the approval succeeds, nothing merges, and the reason says your checkout was dirty.
6. **Approve a sketch-rigor task.**
   - *Expect:* it merges. Rigor decides who can approve; it does not decide whether approval ships.
7. **Confirm nothing left your machine.** Check the remote.
   - *Expect:* unchanged. Pushing is still yours to do.

**Where it would go wrong:** if step 3 shows commits the agent made *after* the evidence was
accepted, the merge took the branch instead of the commit — which design decision D1 forbids, and
which would mean approving one task shipped another task's unreviewed work.
