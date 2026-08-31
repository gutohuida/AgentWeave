# Tasks

Every file named below was confirmed to exist by listing it, not recalled. A round that cites a test
file and does not `ls` it is how `approval-refuses-unaccepted-evidence` shipped a task pointing at
`hub/tests/test_spec_evidence.py`, which does not exist.

## 1. Reproduce break 1 first

- [ ] 1.1 New file `hub/tests/test_loop_lands_its_work.py`. Not `test_task_integration.py` (which is
  about the evidence route and is already 900 lines) and not `test_loop_*.py` (which are about
  scheduling).
- [ ] 1.2 **Reuse the fixture, do not build one.** `hub/tests/test_task_integration.py` has
  `make_repo`, `commit_on_branch`, `commits_on`, `files_on`, the `builder` fixture, `set_main_branch`,
  `drive_to`, `approve` and `integrations` working against a real git repository (lines 41-183). Copy
  or import them; the fixture risk in this change is the *task branch*, and that is the only new part.
- [ ] 1.3 **The reproduction is a loop task with real work on its own branch.** Create a loop
  (`POST /jobs` with a stop condition), a task carrying its `loop_id`, real commits on
  `agentweave/task/<task_id>` cut from the main branch, and **no requirement link and no evidence at
  all**. Read the rows and the branch back and assert they are what they claim before asserting
  anything about behaviour — B-IMPL found two fixture defects this way, each of which would have made
  an assertion pass without the behaviour existing.
- [ ] 1.4 Drive it to `approved` and assert **today's** behaviour: the transition succeeds, and a
  `TaskIntegration` row records `outcome='skipped'` with `reason == task_integration.NOTHING_TO_MERGE`
  while the commits sit on the task branch, unreachable from the main branch. Confirm it passes
  against unmodified code. A reproduction that does not pass first is not a reproduction.
- [ ] 1.5 Reproduce break 7 in the same file at the API level: `POST
  /tasks/{id}/integrations/retry` on that task succeeds and appends a **second identical skip**.
  That is the button, measured, without a browser.
- [ ] 1.6 Reproduce break 7 in the UI. `hub/ui/src/__tests__/taskIntegrationRetry.test.tsx` exists;
  add a case asserting today's behaviour — a row with `reason` = the nothing-to-merge sentence renders
  the "Try again" button. It must **fail** after group 6, which is the point of writing it now.
- [ ] 1.7 The guards that must still pass afterwards, written now as assertions about today: a task on
  a loop that declares evidence **is** needed merges nothing without accepted evidence; a task with no
  loop at all is untouched by everything in this change; and — **the guard round 2 added, and the one
  that would have caught D10** — a task on a **flow** (a `Loop` row with a `spec_document_id`, field
  NULL) merges the commit its accepted evidence names, with a different commit at its branch tip so
  the two answers cannot be confused. Write it against today's code, where it passes, and it fails the
  moment 4.3 is implemented with a flat default.
- [ ] 1.7a **The guard round 3 added, and the one that would have caught D11** — the same shape one
  step further in. A task on a **documentless loop** (`spec_document_id` NULL, `work_needs_evidence`
  NULL) created with `requirement_ids`, carrying a real `TaskRequirementLink` and accepted evidence,
  merges **the commit that evidence names** — again with a different commit at its branch tip.
  It passes against today's code, because that task merges today through the ordinary evidence
  route, and it fails the moment 4.3 stops at `loop.spec_document_id is not None`. Assert the linked
  row exists before asserting the merge (1.3's rule): a fixture that silently failed to link would
  make this pass for the wrong reason.

## 2. The column and the migration

- [ ] 2.1 `Loop.work_needs_evidence: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)`
  in `hub/hub/db/models.py`, with the comment carrying design D2's reasoning: NULL means "the
  product's current default", the same reasoning `Loop.control` states twenty lines above it. **No
  `default=` and no `server_default=`** — a default on the column is the thing D2 rejects.
- [ ] 2.2 Migration `hub/hub/migrations/versions/0100_loop_work_needs_evidence.py`, `down_revision =
  "0099"`. **Guard for a missing `loops` table** the way `0033`/`0034` do: an upgrade starting from an
  early revision reaches `0100` with only that revision's tables.
- [ ] 2.3 Bump the head assertions in `hub/tests/test_migrations.py` **and**
  `hub/tests/test_project_persistence.py`. Both exist and both assert the head by string.
- [ ] 2.4 Add the `0100`-is-guarded test beside `test_migration_0098_is_guarded_when_the_queue_table_does_not_exist`
  (`hub/tests/test_migrations.py:3062`), which is the pattern to copy.

## 3. The declaration on the way in

- [ ] 3.1 `JobCreate.work_needs_evidence: Optional[bool] = None` in `hub/hub/schemas/jobs.py`, beside
  the three loop-opt-in fields, with a comment saying it is a loop field that does **not** opt a job
  in (design D4).
- [ ] 3.2 `hub/hub/api/v1/jobs.py` `create_job`: write it onto the `Loop` row inside the existing
  `if _loop_opts_in(...)` block. **Do not touch `_loop_opts_in` itself** (`jobs.py:103-105`).
- [ ] 3.3 Same route: **refuse** the field where it is supplied and the job is not opting into a
  loop (design D4). There is no existing check to extend — `create_job` reads `spec_document_id` only
  inside `if _loop_opts_in(...)`, so a loop field on a non-loop create is silently dropped today, and
  only the `PATCH` path rejects. Write the refusal here, and do **not** change how
  `spec_document_id` is treated; if that asymmetry looks wrong while implementing, file it.
- [ ] 3.4 `JobUpdate.work_needs_evidence: Optional[bool] = None` **and a refusal in the PATCH route**
  (design D3), naming why the declaration is fixed at creation. Accepting it silently, or 422-ing on
  an unexpected field, are both worse: the first changes what approval writes mid-queue, the second
  says nothing about what to do instead.
- [ ] 3.5 `LoopSummary` in `hub/hub/schemas/jobs.py` gains `work_needs_evidence: Optional[bool] =
  None`, populated by `_batch_loop_summaries` — the operator cannot see a fact that decides what their
  main branch receives unless it is on the shape every loop route already returns.
- [ ] 3.6 Tests in `hub/tests/test_jobs_crud.py`: created with `True`, with `False`, and omitted (NULL
  in all three columns' sense — assert the stored value is `None`, not `False`); the PATCH refusal;
  the not-a-loop refusal.

## 4. The merge target

- [ ] 4.1 In `hub/hub/task_integration.py`: `NO_TASK_BRANCH = "this task has no branch of its own, so
  there is nothing to merge"`, beside the other reason constants.
- [ ] 4.2 `def task_branch_tip(root: Path, task_id: str) -> Optional[str]` — `git rev-parse --verify
  refs/heads/<task_branch_name(task_id)>`, `None` on any non-zero exit. `worktrees.task_branch_name`
  validates the id and raises `ValueError` for one it did not mint; catch that and return `None`
  rather than letting it out, for the reason `task_workspace` already gives about ids the product did
  not mint.
- [ ] 4.3 `async def merge_targets(session, task, root) -> List[Target]` — design D5, **D10 and
  D11**. It asks *does evidence govern this task's merge*, which has **five** answers and not two.
  In order, and the order is the design:

  1. `task.loop_id is None` → evidence governs. An ordinary task is untouched by this change.
  2. the loop row does not resolve → evidence governs. A dangling id decides nothing.
  3. `loop.work_needs_evidence is not None` → **the operator said, and the operator wins**, in
     either direction and against both defaults below.
  4. `loop.spec_document_id is not None` → evidence governs. **A flow.** (Round 2's D10: `Loop` is
     a flow's row too and `create_flow` never sets the field (7.5), so a flat
     `False if ... is None else ...` would make every flow merge branch tips and degrade
     `approval-refuses-unaccepted-evidence` to an advisory product-wide.)
  5. otherwise → **`await task_has_requirement_links(session, task)`** (4.3c). (Round 3's D11: a
     documentless loop's task created with `requirement_ids` gets real links at `tasks.py:790`,
     `record_evidence` resolves against the *project's* index and does not 404, and that task
     **merges today**. Stopping at step 4 would silently switch it to its branch tip — and because
     `_targets` deliberately includes evidence another task recorded against a shared requirement,
     a per-task branch tip cannot carry that commit at all, so work that merges today would stop
     merging with no record of the loss.)

  Then returns `integration_targets(session, task)` or at most one branch-tip `Target`.
  **`integration_targets` is not modified.** The branch tip is the answer for exactly one
  population: a task on a documentless loop with no requirement link of any kind — the set for
  which `integration_targets` is structurally empty forever, and the set the proposal's Why
  describes.
- [ ] 4.3c `async def task_has_requirement_links(session, task) -> bool` in
  `hub/hub/task_integration.py`, beside `_targets` — a `SELECT 1` existence check on
  `TaskRequirementLink.task_id == task.id`, which is already imported there. Reached only from
  step 5, so an ordinary task, a flow task and a declared loop never pay for it. Do **not** answer
  it by calling `_targets` or counting evidence: the question is whether the task is wired into the
  chain, not whether anything has been recorded yet, and answering it from evidence is D10's
  rejected timing-dependent alternative.
- [ ] 4.3a Use `session.get(Loop, task.loop_id)`, not `select(Loop).where(...)`. `_merge_situation`
  and `integrate_task` both call `merge_targets` within one approval and one session, so the PK get
  is answered from the identity map the second time and a `select` would not be. One line, and it is
  the difference between one query per approval and two.
- [ ] 4.3b Tests for the resolver itself, and the first is the one that matters: **a flow task with
  accepted evidence merges the commit that evidence names, not its branch tip** — assert the merged
  sha equals the evidence footprint's, with a *different* commit sitting at the branch tip so the two
  answers are distinguishable. Then: a flow task with awaiting-only evidence is still **refused**
  approval by `approval-refuses-unaccepted-evidence` (the regression D10 describes, caught at the
  gate); a documentless loop with the field NULL uses its branch tip; either kind with the field set
  explicitly obeys the field against its own default.
- [ ] 4.3d **The test that would have caught D11**, and it is the one that matters most here: a task
  on a **documentless loop with the field NULL** that carries a requirement link and accepted
  evidence merges **the commit that evidence names**, not its branch tip — again with a different
  commit at the tip so the two answers cannot be confused. Then the same task with the loop
  declaring `work_needs_evidence=False` merges the tip, because the operator's declaration wins
  (step 3). Write the first half against today's code, where it **passes**, so it is a regression
  guard rather than a new assertion: this is the population D4's `raise_it_if` is about.
- [ ] 4.4 `hub/hub/task_transition_service.py` `integrate_task`: `merge_targets(session, task, root)`
  in place of `integration_targets(session, task)` (line ~773), and the empty case records
  `NO_TASK_BRANCH` rather than `NOTHING_TO_MERGE` **only** where evidence does not govern the task.
  Two reasons, one branch — do not collapse them, the spec delta enumerates both separately.
- [ ] 4.5 Do **not** touch the ordering of `release_task_workspace` relative to `integrate_task`
  (`task_transition_service.py:606-613`). That comment predicts this exact change; read it before
  editing anything near it, and add a test asserting the merged sha is the tip the gate saw, which is
  what `test_release_happens_after_integration` (`hub/tests/test_task_release.py:278`) could not
  discriminate before now.
- [ ] 4.7 `task_integration_preview` (`hub/hub/api/v1/tasks.py:1039-1089`) resolves a root and calls
  `merge_targets`, so the drawer stops reporting no target for the one task shape whose target is not
  in the database. **Amend its docstring** where it says "no git subprocess, no conflict probe" — the
  second half stays true and the first no longer is (design D5). Do not add a conflict probe.
- [ ] 4.8 Test: the preview for an evidence-free loop task names the branch-tip commit and its
  branch, and the preview for a loop that declares evidence is needed is unchanged.
- [ ] 4.6 Tests: the branch tip merges; a second commit made after approval does not; a grandfathered
  task (`workspace_scheme='agent'`) skips with `NO_TASK_BRANCH` and **no agent branch is merged** —
  assert the agent branch's commits are absent from the main branch, not merely that the outcome was
  a skip; a tip already on the main branch records `ALREADY_INTEGRATED`.
- [ ] 4.9 **`_prerequisite_commits` asks the same question — design D12, the decision round 2 left
  open and round 3 took.** `hub/hub/task_workspace.py:121` takes `repo_root` (which
  `resolve_turn_workspace_inputs` already holds at `:62` and already passes to `_integration_base`
  at `:99`), skips any prerequisite whose `status != dependency_gate.MET_STATUS`
  (`dependency_gate.py:39`, `"approved"`), and calls `merge_targets` instead of
  `integration_targets`. Update the docstring: its stated reason for using `integration_targets` —
  *"would carry work nobody accepted"* — is answered by the status check, and on the evidence-free
  route approval **is** the acceptance.
  **Why this is in scope and not late widening: without it the change breaches a shipped
  requirement.** `task-dependencies:335` — *"A task's isolated checkout SHALL contain the work of
  every prerequisite the task was permitted to start on, whether or not that work reached the
  project's main branch"* — and its rationale at `:337` names the dirty and parked checkouts
  (`task_integration.py:329-335`) as reasons the requirement exists. An evidence-free loop task's
  prerequisite work would reach its successor only through the main branch, which is the exact
  dependence that sentence forbids. This change creates that shape; it does not inherit it.
  The MODIFIED delta for `task-dependencies` in this change's `specs/` is the other half of 4.9 and
  must land with it.
- [ ] 4.9a Test: two evidence-free loop tasks, A → B, A approved while the primary checkout is
  **dirty** so its integration skips. Assert A's commit is *not* on the main branch, and that B's
  branch — cut after A's approval — nevertheless carries A's commit. That test fails without 4.9
  and is the whole argument for it.
- [ ] 4.9b Test the cost, so it is a known behaviour rather than a surprise: a prerequisite whose
  branch tip conflicts with the successor's base makes `ensure_task_worktree` refuse the turn and
  leave no branch behind (`worktrees.py:451-452`, the unwind at `:492-493`). Assert the refusal and
  the absence of the branch. Today, on this route, the situation is silent.
- [ ] 4.9c Test the guard: an **unapproved** prerequisite on an evidence-free loop contributes
  nothing to the successor's branch. Without the status check its in-progress tip would be merged
  into a checkout an agent is about to write in.

## 5. The gate

- [ ] 5.1 `hub/hub/requirement_gate.py` `_merge_situation`: build the target list with `merge_targets`
  and rename the field from `accepted` to what it now holds. The docstring's sentence about `accepted`
  being carried "because both checks need it and it is one query" moves with it.
- [ ] 5.2 Check `_check_unaccepted` reads correctly after the rename: its `if situation.accepted:`
  arm means "something else would merge", which is exactly right for a branch-tip target and is why
  no second rule is needed (design D8). Say so in the comment; a reader will otherwise think the
  advisory arm is firing by accident.
- [ ] 5.3 Test: an evidence-free loop task whose branch conflicts with the main branch is **refused**
  approval with the conflicting paths named — the same assertion
  `test_a_conflicting_branch_refuses_approval` (`hub/tests/test_task_integration.py:389`) makes for
  the evidence route.
- [ ] 5.4 Test: an evidence-free loop task in a project with no configured main branch approves
  exactly as it does today. `_merge_situation` returns `None` and nothing refuses.

## 6. Retryability

- [ ] 6.1 In `hub/hub/task_integration.py`, beside the reason constants: the classification from
  design D7 and `def is_retryable(outcome: str, reason: str) -> bool`. `FAILED` is retryable whatever
  its reason and is answered **on the outcome, before the reason is consulted** (it carries git's own
  stderr and can never be matched). An unclassified skip reason is **not** retryable — the default
  inverts deliberately.
- [ ] 6.2 `CHECKOUT_ELSEWHERE` **and `ALREADY_INTEGRATED`** are format strings
  (`task_integration.py:67-74`, applied at `:326` and `:334`); match each on its invariant stem, not
  by equality. Three of D7's nine rows are not fixed strings, and a dict keyed on the constants would
  drop exactly the dirty-checkout and failed-merge cases into "unclassified" — which under the
  inverted default means no button on the two most retryable outcomes there are. That is the defect
  being removed, reproduced one layer down.
- [ ] 6.2a Add `SKIP_REASONS` to `hub/hub/task_integration.py` — an explicit tuple naming every
  reason a skip can carry — and a **totality test** asserting `is_retryable` answers for each member,
  with the two templates formatted first. A tenth reason added later without a classification then
  fails the suite instead of quietly losing its button. This is the guard that makes the inverted
  default safe; without it the default is just a slower way to lose a button.
- [ ] 6.3 `_integration_view` (`hub/hub/api/v1/tasks.py:1090-1119`) adds `"retryable":
  task_integration.is_retryable(row.outcome, row.reason)` to each row. One shape, both routes, as its
  docstring says.
- [ ] 6.4 `TaskIntegration` in `hub/ui/src/api/tasks.ts` gains `retryable: boolean`.
- [ ] 6.5 `hub/ui/src/components/tasks/TaskIntegrationNote.tsx`: the button renders from
  `rows.some((row) => row.retryable)`; delete the `NO_MAIN_BRANCH` constant and the `wantsABranch`
  derivation. Keep the missing-main-branch case pointing at the setting — check whether that text
  exists anywhere on screen today, and if it does not, say so in the log rather than adding a sentence
  this change did not argue for.
- [ ] 6.8 **The operator can make the declaration.** `hub/ui/src/components/jobs/JobForm.tsx` is the
  only operator-facing surface that creates a loop (the loop toggle at :90-99, its fields at
  :300-330) and it must carry `work_needs_evidence` inside the same `loopEnabled` block, with one
  sentence saying what it decides — that approving this loop's tasks writes their work to the
  project's main branch. `hub/ui/src/api/jobs.ts` gains the field on the create body. **Added in
  round 2 and not optional:** without it the declaration is an agent-only control over the operator's
  own main branch, and the default becomes one the operator can neither see nor opt out of. The
  answered open question at the foot of `design.md` is the argument.
- [ ] 6.9 Test in `hub/ui/src/__tests__/`: submitting the form with the loop toggle off sends no
  `work_needs_evidence`, and with it on sends what the control says — the same shape the existing
  `stop_when_queue_empties` assertions take, and for the same reason its comment at `JobForm.tsx:42`
  gives about a controlled field opting a job in by existing.
- [ ] 6.6 `hub/ui/src/__tests__/taskIntegrationRetry.test.tsx`: 1.6's case now asserts **no** button,
  a retryable reason still renders one, and a row with `retryable` absent renders none.
- [ ] 6.7 Python tests in `hub/tests/test_task_integration_retry.py`: the field is present and correct
  on both the read route and the retry route, and — the one that matters — `POST
  /integrations/retry` still succeeds for a task whose last skip is unretryable (the requirement
  constrains what is offered, not what is permitted).

## 7. The tool surface

- [ ] 7.1 `create_loop` in `hub/hub/mcp_server.py` gains `work_needs_evidence: Optional[bool] = None`
  and passes it in the body dict. **Stdlib + fastmcp only**; nothing new is imported.
- [ ] 7.2 Its docstring says what the declaration decides, in the operator's terms, and says the
  default. An agent creating a loop is the caller who most needs to know that approving its tasks will
  write to the project's main branch.
- [ ] 7.3 `hub/hub/api/v1/agents.py:960-975` restates `create_loop`'s signature as prose in the
  agent's tool inventory. Update it, or the agent reads a signature the Hub no longer has.
- [ ] 7.4 `hub/tests/test_tool_surface_matches_server.py` and `hub/tests/test_mcp_tool_schemas.py`
  both exist and both compare these; run them, and if neither catches a stale inventory line, note
  that in the log as a finding rather than fixing it here.
- [ ] 7.5 `create_flow` is **not** given the parameter. A flow has a document, so evidence always
  governs it — which is true only because 4.3's default is kind-aware. **These two tasks are one
  decision and must not be done separately:** 7.5 without 4.3's `spec_document_id is not None` arm is
  what makes every flow evidence-free forever, since a flow's column can then never be anything but
  NULL. If a later round wants to give a flow the parameter, that is a change of its own.

## 8. Verify

- [ ] 8.1 `py -3.11 -m pytest hub/tests/test_loop_lands_its_work.py hub/tests/test_task_integration.py
  hub/tests/test_task_integration_retry.py hub/tests/test_jobs_crud.py hub/tests/test_migrations.py
  hub/tests/test_requirement_gate.py -q`.
- [ ] 8.2 `cd hub/ui && npm run test` for the two UI test files, then `npm run lint`.
- [ ] 8.3 `cd hub/ui && npm run build`, then `py -3.11 scripts/refresh_ui_bundle.py`. Commit
  `hub/ui/src` and `hub/hub/static/ui` together.
- [ ] 8.4 `ruff check src/ hub/ tests/`, `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`,
  `mypy src/`.
- [ ] 8.5 **Drive it.** A fresh project, a loop created through `create_loop` with the declaration
  omitted, one task, one Haiku turn that writes a file, approval, and then
  `git merge-base --is-ancestor` against the fixture repository — not the Hub's own
  `TaskIntegration` row, which is what the product claims rather than what the repository holds.
  Then the same loop declaring `work_needs_evidence=True` and confirming nothing merges. This belongs
  to `DRIVE-2` and is listed here so the change is not called done without it.
