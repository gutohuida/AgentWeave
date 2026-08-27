# Tasks

Tests first in every phase. Nothing here is complete on the strength of a plan existing.

**Read before starting phase 1.** The two tests in phase 1 cannot be fixed by flipping an assertion.
Both fixtures build `agentweave/builder` by hand with `commit_on_branch(tmp_path, AGENT_BRANCH, …)`
(`hub/tests/test_task_integration.py:307`, `:342`) and never touch worktree provisioning, so the
shape of the branch is decided by the *test*, not by the product. Inverting
`assert earlier in merged` alone produces a red test that is red for the wrong reason. Each task
below says which fixture change makes the assertion mean what it claims.

## 1. Make the suite able to tell the implementations apart

- [ ] 1.1 In `hub/tests/test_task_integration.py`, rewrite
  `test_rode_along_commits_names_what_actually_landed` (`:329`) as the regression test for F58 and
  rename it `test_another_tasks_commits_do_not_ride_along`. Its docstring today says the F58 bug is
  "deliberately not made here"; that is what changes. **Fixture change:** put `earlier` on a
  *second* task's branch (`agentweave/task/<other-task-id>`) and `demonstrated` on this task's own
  branch, cut from `main`, instead of putting both on one agent branch. **Assertions:** invert
  `assert earlier in merged` to `assert earlier not in merged`, keep `assert demonstrated in
  merged`, and change `rode_along_commits == [earlier]` to `== []`. Record in the docstring that
  this is the inversion of the older test, so the history reads.
- [ ] 1.2 In the same file, add to `test_later_commits_on_the_branch_are_not_merged` (`:296`) the
  earlier-commit case its docstring already describes: a commit on **this task's own** branch,
  earlier than the evidence commit, and assert it **does** land. That is the case option (b)
  (squashing the evidence commit's diff) would break, and no test covers it today. Keep the existing
  `later not in merged` assertions unchanged.
- [ ] 1.3 Run both tests against the **current, unmodified** implementation and confirm 1.1 fails and
  1.2 passes. A 1.1 that passes before any production change means the fixture still does not build
  the case. Record the observed failure text.

## 2. Task workspace paths, names, and provisioning (D1, D6)

- [ ] 2.1 Add `hub/tests/test_task_worktrees.py`. Assert `worktrees.task_worktree_path` and
  `worktrees.task_branch_name` are pure (create nothing), that they produce
  `.agentweave/tasks/<task_id>` and `agentweave/task/<task_id>`, and that a task id which is not
  `task-` followed by hex is refused — mirroring `test_worktrees.py`'s coverage of
  `validate_agent_name`.
- [ ] 2.2 Add a test asserting a task branch name can never collide with an agent branch name: an
  agent literally named `task-ab12cd34ef56` (which `_AGENT_NAME_RE`, `worktrees.py:65`, accepts)
  and a task with id `task-ab12cd34ef56` produce different refs and different directories.
- [ ] 2.3 Implement `validate_task_id`, `task_worktree_path`, `task_branch_name` in
  `hub/hub/worktrees.py`, beside `worktree_path`/`branch_name` (`:139`, `:144`).
- [ ] 2.4 Add a test asserting `ensure_task_worktree(repo_root, task_id, base, prerequisites=[])`
  creates a checkout whose branch tip is `base`, and that calling it twice is idempotent.
- [ ] 2.5 Add a test asserting `ensure_task_worktree` with a prerequisite commit not reachable from
  `base` produces a checkout containing that commit's files, and that a prerequisite already
  reachable from `base` is not merged a second time (assert the commit count).
- [ ] 2.6 Add a test asserting a prerequisite whose merge conflicts raises
  `IsolationUnavailableError`, that the error message names the prerequisite's commit, and that **no
  checkout and no branch are left behind** — provisioning is all-or-nothing.
- [ ] 2.7 Implement `ensure_task_worktree` in `hub/hub/worktrees.py`. `base` and `prerequisites` are
  parameters, never resolved from a database inside this module — it states its independence from
  any DB/session layer at `worktrees.py:27-30`.
- [ ] 2.8 Add `.agentweave/tasks/` to `EXCLUDE_PATTERNS` in `hub/hub/repo_hygiene.py:59`, and extend
  the existing exclude-patterns test to assert it is present. Without it `snapshot_worktree`'s
  `git add -A` (`worktrees.py:459`) commits an entire second checkout.
- [ ] 2.9 Add `release_task_worktree` to `hub/hub/worktrees.py`, with a test asserting it snapshots
  uncommitted changes onto the task branch first, removes the checkout, and leaves the branch and
  its commits intact.

## 3. Resolving the task before the workspace (D2)

- [ ] 3.1 Add a test in `hub/tests/` asserting that triggering an agent with a `task_id` that does
  not exist in the project returns the `TaskBindingError` refusal **and leaves no worktree
  provisioned** for that agent — the observable consequence of the move.
- [ ] 3.2 Add a test asserting that when the project workspace is unavailable *and* the named task
  does not exist, the response is still the workspace 409 with its `directory_state`, not the task
  refusal. This pins the precedence D2 promises to preserve.
- [ ] 3.3 Move the `resolve_bound_task` call in `hub/hub/api/v1/agent_trigger.py` from `:558` to
  immediately after `repo_root` is set (`:469`) and before the review-turn block (`:483`). Leave
  `spec_document_for_task`, `_render_hub_agent_context` and the staging block at `:749` reading the
  same `binding` value.
- [ ] 3.4 Confirm by reading, not by assuming, that nothing between the old and new call sites
  mutates `conversation`, `queue_entry_ids` or `task_id`. Record what you read.

## 4. Choosing the workspace from the binding (D1, D3, D4)

- [ ] 4.1 Add a test asserting a writing turn **bound to a task** executes in
  `.agentweave/tasks/<task_id>` on `agentweave/task/<task_id>`.
- [ ] 4.2 Add a test asserting a writing turn **with no bound task** executes in
  `.agentweave/worktrees/<agent>` on `agentweave/<agent>`, unchanged from today.
- [ ] 4.3 Add a test asserting a follow-up turn that names no task, in a conversation already bound
  to one, resolves to the **task** workspace — the conversation binding
  (`run_task_binding.py:284-289`) is what stops two schemes coexisting by accident.
- [ ] 4.4 Add a test for grandfathering (D4): a task with a prior `Run` carrying a non-null
  `snapshot_commit_sha` (`db/models.py:1078`) and no task branch of its own resolves to the
  **per-agent** workspace, and no task branch is created for it.
- [ ] 4.5 Add a test asserting the complement: a task with prior runs but **no** snapshot commit
  (its turns changed nothing) is *not* grandfathered and gets a task workspace.
- [ ] 4.6 Add a test asserting the base is `Project.main_branch` when set, and the project
  checkout's `HEAD` when it is not.
- [ ] 4.7 Add a test asserting a read-only agent (`config["read_only"]`) still shares the project
  checkout, bound task or not — `is_writing_agent` (`worktrees.py:167`) keeps precedence.
- [ ] 4.8 Add a test asserting a project directory that is not a git repository still runs the turn
  in the project directory rather than refusing it, bound task or not.
- [ ] 4.9 Implement the resolver — `worktrees.resolve_turn_workspace(repo_root, agent, config,
  task=None, base=None, prerequisites=())` or an equivalent seam — and call it from
  `agent_trigger.py` in place of `resolve_agent_workspace` at `:535`. Keep
  `resolve_agent_workspace` as the unbound path so its existing behaviour has one implementation.
- [ ] 4.10 Implement the grandfathering query and the prerequisite/base resolution in the Hub layer
  (session-aware), passing plain values into `worktrees`.

## 5. Release when the task is finished (D5)

- [ ] 5.1 Add a test asserting that approving a task removes its checkout directory and **keeps** its
  branch and every commit on it.
- [ ] 5.2 Add a test asserting release happens **after** `integrate_task`: the integration row for
  the approval records `merged`, and the merged commit is the evidence commit rather than a snapshot
  made during release.
- [ ] 5.3 Add a test asserting a task rejected from `under_review` also has its checkout released and
  its branch kept.
- [ ] 5.4 Add a test asserting a reopened task (`approved -> revision_needed -> in_progress`,
  `task_transitions.py:145-150`) is re-provisioned with its prior work present, because the branch
  survived.
- [ ] 5.5 Add a test asserting the review path still works after release: `commit_for_task_review`
  (`requirement_evidence.py:653`) resolves and `ensure_review_checkout` checks the commit out.
- [ ] 5.6 Implement release in `hub/hub/task_transition_service.py`, after the `integrate_task` call
  at `:434-435`, for both terminal statuses. It must never fail the transition — same rule as
  integration (`hub/tests/test_task_integration.py:14`).
- [ ] 5.7 Add a test asserting a release that raises is swallowed and recorded, and the transition
  still stands.

## 6. Surfaces that assume one workspace per agent (D6, D7)

- [ ] 6.1 Add a test asserting `worktrees.list_agent_branches` (`:551`) and `detect_conflicts`
  (`:608`) see task branches. Today `list_agent_branches` strips `refs/heads/agentweave/` and
  requires `_AGENT_NAME_RE` to match, so `task/<id>` is silently dropped and
  `GET /worktrees/conflicts` would return `[]` forever while looking healthy.
- [ ] 6.2 Implement the listing and conflict-detection change, keyed by workspace rather than by
  agent name, and update `ConflictReport.agents` (`worktrees.py:583`) to name what actually
  conflicts.
- [ ] 6.3 Add a test asserting `GET /api/v1/projects/{id}/worktrees` lists task workspaces as well as
  agent workspaces, each stating which it is, and that reading it provisions nothing
  (`api/v1/worktrees.py:56`, whose docstring already promises that).
- [ ] 6.4 Update `hub/ui/src/components/environment/WorktreesPanel.tsx` to render both kinds, and
  add or extend its test. An operator who cannot see a grandfathered task's workspace will conclude
  the work vanished.
- [ ] 6.5 Add a test asserting the turn context sentence for a task-bound turn names the task branch
  (`api/v1/agents.py:1160` today hardcodes `worktrees.branch_name(agent)`), and that an unbound turn
  still names the agent branch.
- [ ] 6.6 Add a test asserting `checkpoints.agent_worktree` (`checkpoints.py:363`) resolves a
  checkpoint's paths against the workspace the run actually used, and still returns `None` rather
  than raising for an agent that never ran.
- [ ] 6.7 Change `snapshot_worktree`'s commit message (`worktrees.py:471`) to name the task when
  there is one, and assert it. A branch of identically-messaged snapshots is unreadable, and the
  message is the only per-commit statement of what a turn was.

## 7. Evidence footprints follow the run's workspace (D7)

- [ ] 7.1 Add a migration in `hub/hub/migrations/versions/` adding the workspace column to `runs`,
  guarded for a missing table as `0033`/`0034` are. Bump the head assertions in
  `hub/tests/test_migrations.py` **and** `hub/tests/test_project_persistence.py`.
- [ ] 7.2 Write the column at spawn in `agent_trigger.py`, from `effective_work_dir` — the value
  already computed and passed to `_execute_run` — so it cannot disagree with the process's cwd.
- [ ] 7.3 Add a test asserting an agent recording evidence during a task-bound turn is footprinted at
  the task workspace's HEAD, not at the agent workspace's.
- [ ] 7.4 Add a test asserting a **reviewer** recording evidence is footprinted at its review
  checkout, not at its own agent worktree. This is a behaviour change and today's answer is wrong.
- [ ] 7.5 Add a test asserting the fallback holds: a run whose recorded workspace no longer exists
  (released) footprints at the project checkout, as `footprint_root` does today
  (`requirement_evidence.py:285`).
- [ ] 7.6 Implement in `hub/hub/requirement_evidence.py`, changing `footprint_root`'s inputs and its
  two call sites (`:252`, `:339`).

## 8. Prove it, rather than assert it

- [ ] 8.1 Mutation check, by name: delete the prerequisite merge in `ensure_task_worktree` and
  confirm test 2.5 fails. Record the failure text, restore, re-verify green.
- [ ] 8.2 Mutation check, by name: make the task workspace cut from the agent's branch instead of the
  base, and confirm test 1.1 (`test_another_tasks_commits_do_not_ride_along`) fails. This is the
  mutation that reproduces F58; if the test survives it, the test is still wrong.
- [ ] 8.3 Mutation check, by name: remove the release call from `task_transition_service` and confirm
  test 5.1 fails.
- [ ] 8.4 Mutation check, by name: revert the `list_agent_branches` parse change and confirm test 6.1
  fails — the silent-empty-list failure mode is the one a green suite would otherwise hide.
- [ ] 8.5 Mutation check, by name: remove the grandfathering branch and confirm test 4.4 fails.
- [ ] 8.6 Run the full Hub suite with `py -3.11 -m pytest hub/tests/ -q` and the CLI suite with
  `py -3.11 -m pytest tests/ -q`. Record counts.
- [ ] 8.7 Run exactly what CI runs: `ruff check src/ hub/ tests/`,
  `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`, `mypy src/`, and
  `cd hub/ui && npm run lint`.
- [ ] 8.8 Drive it live against the trial Hub on port 8010, in a throwaway project created for the
  purpose — **never** `proj-5e960453` (this repository) or `proj-18e5d4e0` (ledger-stress). Two
  tasks for one agent, work committed on each, approve the first, and confirm by `git log` that the
  second task's commits are not on the main branch. Restart the Hub deliberately first and confirm
  the **project list**, not `/health`.
- [ ] 8.9 Record in `scripts/drive/FINDINGS.md` what the live drive showed, including anything that
  held rather than broke.
