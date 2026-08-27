# Tasks

Tests first in every phase. Nothing here is complete on the strength of a plan existing.

**Read before starting phase 1.** The two tests in phase 1 cannot be fixed by flipping an assertion.
Both fixtures build `agentweave/builder` by hand with `commit_on_branch(tmp_path, AGENT_BRANCH, …)`
(`hub/tests/test_task_integration.py:307`, `:342`) and never touch worktree provisioning, so the
shape of the branch is decided by the *test*, not by the product. Inverting
`assert earlier in merged` alone produces a red test that is red for the wrong reason. Each task
below says which fixture change makes the assertion mean what it claims.

## 1. Make the suite able to tell the implementations apart

**Measured during phase 1, and it changed 1.1.** The fixture as written below — both branch names
spelled out in the test — **passes against unmodified production code**, because two branches cut
from `main` by hand are separable whatever the product does. Measured on 2026-08-27: with
`f"agentweave/task/{other}"` and `f"agentweave/task/{task}"` as literals, `1 passed`. So the
literal form is vacuous, and 1.3's "1.1 must fail" was unreachable through it. 1.1 as implemented
takes both names from `worktrees.task_branch_name(...)` instead, so the *product* decides the
branch shape the test asserts on — which is exactly what the preamble above says is missing. It is
red today with `AttributeError: module 'hub.worktrees' has no attribute 'task_branch_name'`, and
goes green at task 2.3. That is red for the right reason: the product has no way to say where a
task's work goes, which is the defect. Full discrimination of *provisioning* is still phases 3 and
7's, not phase 1's, and this phase does not claim it.

- [x] 1.1 In `hub/tests/test_task_integration.py`, rewrite
  `test_rode_along_commits_names_what_actually_landed` (`:329`) as the regression test for F58 and
  rename it `test_another_tasks_commits_do_not_ride_along`. Its docstring today says the F58 bug is
  "deliberately not made here"; that is what changes. **Fixture change:** put `earlier` on a
  *second* task's branch (`agentweave/task/<other-task-id>`) and `demonstrated` on this task's own
  branch, cut from `main`, instead of putting both on one agent branch. **Assertions:** invert
  `assert earlier in merged` to `assert earlier not in merged`, keep `assert demonstrated in
  merged`, and change `rode_along_commits == [earlier]` to `== []`. Record in the docstring that
  this is the inversion of the older test, so the history reads.
- [x] 1.2 In the same file, add to `test_later_commits_on_the_branch_are_not_merged` (`:296`) the
  earlier-commit case its docstring already describes: a commit on **this task's own** branch,
  earlier than the evidence commit, and assert it **does** land. That is the case option (b)
  (squashing the evidence commit's diff) would break, and no test covers it today. Keep the existing
  `later not in merged` assertions unchanged. **One assertion this task did not name had to move:**
  the test asserted `rode_along_commits == []` with the comment "a branch with exactly one commit
  ahead of main has nothing to ride along", which stops being true the moment the groundwork commit
  exists. It is now `== [earlier]` — the groundwork lands *and* the record still says which commit
  was the reviewed one. That is a strengthening, not a weakening: it pins that the two facts stay
  separate.
- [x] 1.3 Run both tests against the **current, unmodified** implementation and confirm 1.1 fails and
  1.2 passes. A 1.1 that passes before any production change means the fixture still does not build
  the case. Record the observed failure text.

## 2. Task workspace paths, names, and provisioning (D1, D6)

**Measured during phase 2, and it removed a line rather than adding one.** 2.5 asks for a
prerequisite "already reachable from `base`" not to be merged a second time, and the obvious
implementation is a `merge-base --is-ancestor` guard before the merge. That guard was written,
then **mutation-tested and deleted**: with it stubbed out to `if False`, all 21 tests still
passed. `git merge --no-ff <ancestor>` is measured to be a no-op — "Already up to date.", exit 0,
no commit — so the guard was a branch no test could fail, which this codebase treats as a defect
source. The guarantee 2.5 names is git's, the test asserts the guarantee rather than our control
flow, and its docstring says so out loud so a later reader does not "restore the missing check".

**What the same mutation pass did find.** `--no-ff` *is* load-bearing and was untested: the task
branch sits at `base` and a prerequisite is typically `base` plus one commit, so a plain `merge`
fast-forwards, two tasks end up sharing a branch tip, and the act of bringing the work in leaves
no record. 2.5's test now pins the commit count at three, and dropping `--no-ff` turns it red.


- [x] 2.1 Add `hub/tests/test_task_worktrees.py`. Assert `worktrees.task_worktree_path` and
  `worktrees.task_branch_name` are pure (create nothing), that they produce
  `.agentweave/tasks/<task_id>` and `agentweave/task/<task_id>`, and that a task id which is not
  `task-` followed by hex is refused — mirroring `test_worktrees.py`'s coverage of
  `validate_agent_name`.
- [x] 2.2 Add a test asserting a task branch name can never collide with an agent branch name: an
  agent literally named `task-ab12cd34ef56` (which `_AGENT_NAME_RE`, `worktrees.py:65`, accepts)
  and a task with id `task-ab12cd34ef56` produce different refs and different directories.
- [x] 2.3 Implement `validate_task_id`, `task_worktree_path`, `task_branch_name` in
  `hub/hub/worktrees.py`, beside `worktree_path`/`branch_name` (`:139`, `:144`).
- [x] 2.4 Add a test asserting `ensure_task_worktree(repo_root, task_id, base, prerequisites=[])`
  creates a checkout whose branch tip is `base`, and that calling it twice is idempotent.
- [x] 2.5 Add a test asserting `ensure_task_worktree` with a prerequisite commit not reachable from
  `base` produces a checkout containing that commit's files, and that a prerequisite already
  reachable from `base` is not merged a second time (assert the commit count).
- [x] 2.6 Add a test asserting a prerequisite whose merge conflicts raises
  `IsolationUnavailableError`, that the error message names the prerequisite's commit, and that **no
  checkout and no branch are left behind** — provisioning is all-or-nothing. Assert the branch is
  gone with `git rev-parse --verify`, not only that the directory is: `worktree add` creates both,
  and a leftover branch is the half that would be reused silently by the next turn.
- [x] 2.6b **Added in R3.** Add a test for the other way the merge fails: a prerequisite commit SHA
  that is not in the repository at all (an operator deleted the branch carrying it). Assert the same
  all-or-nothing unwind, and that the message says the commit is **missing** rather than that it
  conflicts — the two ask the operator for different things. D1 named only conflict.
- [x] 2.7 Implement `ensure_task_worktree` in `hub/hub/worktrees.py`. `base` and `prerequisites` are
  parameters, never resolved from a database inside this module — it states its independence from
  any DB/session layer at `worktrees.py:27-30`. Implement the unwind explicitly, in design D1's
  order — `merge --abort`, `worktree remove --force`, `branch -D`, `worktree prune`, each with
  `check=False`, and only then raise. **Do not reuse `release_worktree`**: it snapshots the dirty
  tree onto the branch first (`worktrees.py:537-538`), which would commit a conflicted merge as the
  agent's work.
- [x] 2.7b Add a test asserting `ensure_task_worktree` refuses a registered task checkout that is
  mid-merge (`MERGE_HEAD` present) rather than returning it, and implement that refusal. This is the
  one state a process killed between `worktree add` and the unwind can leave, and
  `ensure_worktree`'s idempotent path (`worktrees.py:268-275`) returns a correctly-registered
  directory unexamined.
- [x] 2.8 Add `.agentweave/tasks/` to `EXCLUDE_PATTERNS` in `hub/hub/repo_hygiene.py:59`, and extend
  the existing exclude-patterns test to assert it is present. Without it `snapshot_worktree`'s
  `git add -A` (`worktrees.py:459`) commits an entire second checkout.
- [x] 2.9 Add `release_task_worktree` to `hub/hub/worktrees.py`, with a test asserting it snapshots
  uncommitted changes onto the task branch first, removes the checkout, and leaves the branch and
  its commits intact.

## 3. Resolving the task before the workspace (D2)

- [x] 3.1 Add a test in `hub/tests/` asserting that triggering an agent with a `task_id` that does
  not exist in the project returns the `TaskBindingError` refusal **and leaves no worktree
  provisioned** for that agent — the observable consequence of the move.
- [x] 3.2 Add a test asserting that when the project workspace is unavailable *and* the named task
  does not exist, the response is still the workspace 409 with its `directory_state`, not the task
  refusal. This pins the precedence D2 promises to preserve.
- [x] 3.2b Add tests pinning the three precedences that D2 *does* change, so they are chosen rather
  than discovered: a nonexistent `task_id` combined with (a) `work_dir` on a review turn
  (`agent_trigger.py:492-497`), (b) `work_dir` for a writing agent (`:511-516`), and (c) an
  unresolvable review target (`ReviewTurnRefused`, `:506-509`) now each answer with the task
  refusal. R1 named only the workspace-409 precedence; these four answers move together.
- [x] 3.3 Move the `resolve_bound_task` call in `hub/hub/api/v1/agent_trigger.py` from `:558` to
  immediately after `repo_root` is set (`:469`) and before the review-turn block (`:483`). Leave
  `spec_document_for_task`, `_render_hub_agent_context` and the staging block at `:749` reading the
  same `binding` value.
- [x] 3.4 Confirm by reading, not by assuming, that nothing between the old and new call sites
  mutates `conversation`, `queue_entry_ids` or `task_id`. Record what you read.

## 4. Choosing the workspace from the binding (D1, D3, D4)

- [ ] 4.1 Add a test asserting a writing turn **bound to a task** executes in
  `.agentweave/tasks/<task_id>` on `agentweave/task/<task_id>`.
- [ ] 4.2 Add a test asserting a writing turn **with no bound task** executes in
  `.agentweave/worktrees/<agent>` on `agentweave/<agent>`, unchanged from today.
- [ ] 4.3 Add a test asserting a follow-up turn that names no task, in a conversation already bound
  to one, resolves to the **task** workspace — the conversation binding
  (`binding_for_conversation`, `run_task_binding.py:388`) is what stops two schemes coexisting by
  accident.
- [ ] 4.4 Add a test for grandfathering (D4, **corrected in review**): a task stamped
  `workspace_scheme = 'agent'` resolves to the **per-agent** workspace and no task branch is created
  for it, while an unstamped task gets a task workspace. The stamp is read, never recomputed.
- [ ] 4.5 Add a migration test asserting the stamp is applied to exactly the tasks that had at least
  one `Run` at migration time, and to no others — including a task whose runs committed nothing,
  which is grandfathered too. R1's live discriminator (a prior run with a non-null
  `snapshot_commit_sha`) was **wrong** and must not be reintroduced: `snapshot_worktree` returns
  `None` for a clean tree (`worktrees.py:457-458`), so an agent that commits its own work records
  `NULL` and its task would have been restarted from the integration base with its own history
  missing. Assert that case by name.
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
- [ ] 4.10 Implement the grandfathering read and the prerequisite/base resolution in the Hub layer
  (session-aware), passing plain values into `worktrees`. **Confirmed in R3:** the prerequisite
  commits come from `task_integration.integration_targets(session, task)` (`:142`) — already exactly
  this query (newest *accepted* `git` footprint, one per branch, `paths` footprints contributing
  nothing), already async and session-bound, and returning a `list[Target]`. Call it per direct
  prerequisite and pass the `commit_sha` values through; do not write a second implementation of
  "which commit is this task's work", which is the drift this codebase names as a defect source.
- [ ] 4.11 Add the `Task.workspace_scheme` column and its stamping migration, guarded for a missing
  table as `0033`/`0034` are, and bump the head assertions in `hub/tests/test_migrations.py` **and**
  `hub/tests/test_project_persistence.py`. The column's default is `'task'`, and `'agent'` is written
  only by the migration — the design left the default unstated. Nothing outside the migration may
  write this column; assert that by scanning the source in the test, because "only shrinks" is a
  property of that fact alone. **Corrected in R3: name the forms, or the assertion passes against a
  real write.** Scan `hub/hub/` and `src/` for all three of `.workspace_scheme =`, `workspace_scheme=`
  (the `Task(...)` keyword) and `values(workspace_scheme`, allowing only the migration file itself.
  `test_task_attribution.py`'s source scan is the precedent for the shape.
- [ ] 4.12 **Reworded in R3 — it said "refused with a 409", and no caller can observe one.** Add a
  test asserting `trigger_agent_directly` raises `TriggerAgentError` naming the agent that holds the
  task, while a different agent has a `running` run bound to that same task (D8). Assert it at that
  function, not through `/trigger`: `schedule_agent` converts every `TriggerAgentError` into a
  `ScheduleResult` and never re-raises (`turn_scheduler.py:206-209`), so the route answers 200 with
  `status: "queued"`. This is the invariant that used to follow for free from one-checkout-per-agent
  and now has to be stated: `agent_trigger.py:439-445` refuses per agent only, and
  `bind_run_to_task` fills `assignee` only when it is empty (`run_task_binding.py:350-351`), so
  nothing refuses today.
- [ ] 4.13 Add tests for D8's three exemptions: a **review** turn bound to the same task is *not*
  refused (it takes the review checkout, `agent_trigger.py:527-532`), a **read-only** agent is not
  refused, and a **grandfathered** task is not refused. Each is a case where the refusal would
  forbid something that is safe today.
- [ ] 4.14 Implement the D8 refusal in `agent_trigger.py`, in the same shape as the per-agent 409
  but **not** beside it: the per-agent check runs at `:439-445`, before `repo_root` exists and
  before any binding is resolved, so the turn's task is unknown there. It goes immediately after the
  relocated `resolve_bound_task` from task 3.3 — which makes phase 3 a prerequisite of this task,
  not an independent phase.
- [ ] 4.15 **Added in R3, and this is the one that would have lost operator input.** Mark the D8
  refusal *transient* on `TriggerAgentError` — a second flag beside `workspace_unavailable`
  (`agent_trigger.py:234-246`, the flag at `:239`), which is the existing precedent for "this refusal is about a
  condition that clears" — and handle it in `turn_scheduler.schedule_agent` by returning
  `ScheduleResult(waiting_reason=..., terminal_failure=False)` **without** entering the abandonment
  branch at `:165-183`. Add a test asserting a queue entry refused this way keeps
  `delivery_attempts == 0`, stays `queued`, and is delivered on a later `schedule_agent` once the
  holding run ends. Without this the entry is `withdrawn` after `DELIVERY_ATTEMPT_LIMIT`
  (`inbound_queue.py:174`, three) and the message is dropped — that branch exists for refusals its
  own comment describes as repeating "identically forever", which this one does not.
- [ ] 4.16 **Added in R3.** Give the flow scheduler a counterpart to the new refusal, for finding
  F23's reason. `decide_firing` already skips a candidate whose `assignee` is mid-turn and records it
  in `_cannot_staff` rather than dropping it (`scheduler.py:1274-1283`), because a bare `continue`
  made a busy flow report itself stalled. D8 adds a second way to be unstartable that the walk cannot
  see — two loops racing on one task, or a task left `in_progress` with no assignee. Record it the
  same way, with a test, so the collision is visible on the board instead of arriving as an abandoned
  entry.

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

- [ ] 6.1 Add a test asserting `worktrees.list_agent_branches` (`:553`) and `detect_conflicts`
  (`:609`) see task branches. **Two** filters drop them today, not one: the `_AGENT_NAME_RE` match
  on what follows `refs/heads/agentweave/` (`:565-566`), and the comparison of the registered
  worktree path against `worktree_path(repo_root, agent)` (`:567-568`). Relaxing only the regex
  changes nothing — assert both, or the test passes against a half-fix.
- [ ] 6.2 Implement the listing and conflict-detection change, keyed by workspace rather than by
  agent name, and update `ConflictReport.agents` (`worktrees.py:583`) and the API's `ConflictInfo`
  (`api/v1/worktrees.py:43-45`) to name what actually conflicts. Both are fixed two-tuples of agent
  names today.
- [ ] 6.3 Add a test asserting `GET /api/v1/projects/{id}/worktrees` (`api/v1/worktrees.py:57`)
  lists task workspaces as well as agent workspaces, each stating which it is, and that reading it
  provisions nothing — the promise `get_agent_workspace`'s docstring makes at `:103-106`, which this
  endpoint shares and does not state.
- [ ] 6.4 **Corrected in review.** Extend `GET /worktrees/{agent}` (`api/v1/worktrees.py:148-156`)
  and `WorkspaceLocation` in `hub/ui/src/components/agents/AgentSettingsPage.tsx` to list the task
  checkouts belonging to that agent's tasks alongside the agent's own, each naming its branch and
  its task, and to mark a grandfathered task as worked in the agent's own checkout. This — not
  `WorktreesPanel.tsx` — is the surface an operator reads and the one the `agent-configuration`
  delta is written against. Extend `hub/ui/src/__tests__/agentWorkspaceSection.test.tsx`.
- [ ] 6.4b `hub/ui/src/components/environment/WorktreesPanel.tsx` is a **stub**: a hard-coded
  `EmptyState` that calls no API. Building it out is out of scope, but leaving it silently claiming
  "No worktree activity" while task checkouts exist is worse after this change than before. Either
  point it at `GET /worktrees` or say in its own copy that it is not implemented — decide and record
  which, do not leave it as it is by default.
- [ ] 6.5 Add a test asserting the turn context sentence for a task-bound turn names the task branch
  (`api/v1/agents.py:1160` today hardcodes `worktrees.branch_name(agent)`), and that an unbound turn
  still names the agent branch. Also correct the sentence two lines below (`:1162-1164`), "Other
  agents work in separate worktrees on their own branches … they cannot see yours" — true per agent,
  and no longer true as written once a checkout belongs to a task rather than to whoever is holding
  it.
- [ ] 6.6 Add a test asserting `checkpoints.agent_worktree` (`checkpoints.py:363`) resolves a
  checkpoint's paths against the workspace the run actually used, and still returns `None` rather
  than raising for an agent that never ran.
- [ ] 6.7 Change `snapshot_worktree`'s commit message (`worktrees.py:472`) to name the task when
  there is one, and assert it. A branch of identically-messaged snapshots is unreadable, and the
  message is the only per-commit statement of what a turn was.

- [ ] 6.8 Add `.agentweave/tasks` to the nested-project registration refusal
  (`project_workspace.py:175-178`), with a test. It refuses registering a directory inside
  `.agentweave/worktrees` today; a task checkout is the same hazard by a different path.
- [ ] 6.9 Extend the relocation guard (`project_lifecycle.py:240-241`) to count task checkouts, with
  a test. It refuses to relocate a project while `.agentweave/worktrees` is non-empty; a project
  whose only live checkouts are task checkouts would relocate today and break every git worktree
  registration, which stores absolute paths.
- [ ] 6.10 Decide and record what removing an agent from the roster does to the task checkouts of
  tasks it was working. `session_sync.py:131` calls `release_worktree` for the departing agent only,
  which now releases its per-agent checkout and leaves every task checkout behind. Argued correct —
  a task outlives whoever held it — but it is a behaviour nobody has written down, so write it down
  and assert it rather than inheriting it.

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
- [ ] 8.5b Mutation check, by name: remove the D8 one-turn-per-task refusal and confirm test 4.12
  fails. Then, separately, restore it and confirm test 4.13's review-turn case still passes — an
  over-broad refusal that blocks reviews would be invisible to 4.12.
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
