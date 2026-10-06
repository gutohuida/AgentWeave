## Why

**Tier 2** (approval gate, a new migration, the Hub running project commands for the first time).

Reviewers approve work without running what CI runs. In the first AgentWeave-on-AgentWeave trial
(2026-10-06, `spec-queue/METRICS.md`, slices 1/1b/1c), every task passed review and still the operator
caught two defects after merge. One was a black failure that would have broken CI (`27e36cd`). The
other was a context snapshot test that both builders and the review missed (`bd68cfa`). Builders ran
only their own tests, and reviewers read diffs. Verification today is agent-run and agent-reported
(`openspec/specs/agent-conversation-workspace/spec.md`, "A reviewer can run the tests it is asked to
trust"). The approval gate already refuses work that cannot merge (`hub/hub/requirement_gate.py`
`_check_mergeable`). It has no way to refuse work that merges and breaks the project.

## What Changes

- A project gains an operator-configured list of **checks**: named shell commands with a timeout,
  set in project settings. With no checks configured nothing changes, for every existing project.
- When a task moves to `completed`, the Hub runs the project's checks **in the background**. It runs
  them on main plus the commit(s) the task's approval would merge, in a Hub-owned scratch checkout,
  and records the result per (main tip, merge targets).
- **Approving a task reads the recorded result**:
  - A failure refuses, with the failing check's output tail in the message and the reviewer's
    move, "send it back".
  - A run that is still going refuses with "checks still running".
  - A missing or stale result (main moved) starts a run and refuses until it finishes.
  - It does all of this without running anything inside the request.
- **Agents can never approve over a failing check. The operator can**, with a stated reason kept on
  the transition.
- The review briefing states the task's check result, so a reviewer knows before deciding (the
  lesson of F497).
- Project settings gain a Checks editor. The task drawer shows the latest check run.

## Capabilities

### New Capabilities
- `project-checks`: what a check is, who may configure it, when and where the Hub runs checks, what
  it records, and how a run is bounded, interrupted and re-run.

### Modified Capabilities
- `task-lifecycle-governance`: approval is refused on a failing, running, missing or stale check
  result, and the operator may approve over a failure with a recorded reason.
- `agent-flows`: a review turn is told the task's check result beside its verdicts.

## Non-Goals

- Agents configuring, editing or suppressing checks, or supplying a command the Hub runs.
- Running checks inside the approval request, or on every call to the gate (`evaluate` has more
  callers than approval: `approval_held_for_operator`, the scheduler, run divergence, the land
  route).
- Reading checks from the repository (CI workflow, a checked-in file).
- Sandboxing the commands beyond a scratch checkout, a timeout and the Hub's own environment minus
  its credentials. The operator chose what runs.
- Running a task's acceptance criteria as executable checks (the 09-16 exploration's gate). That is
  a later change.
- Docker mode (commands must exist in the container). It is native-only in this change, and a
  Docker Hub says so in settings.

## Impact

- `hub/hub/db/models.py` + migration `0119`: `projects.checks` (JSON), a `task_check_runs` table,
  and `task_transitions.override_reason`.
- New `hub/hub/project_checks.py`: building the would-merge commit from `git merge-tree` +
  `commit-tree`, the scratch worktree, the runner, and the background queue.
- `hub/hub/requirement_gate.py`: a new `checks` refusal category, wired into `refuses`, `detail()`,
  `to_dict()` and `_operator_only_remedy`.
- `hub/hub/task_transition_service.py`: start the run on `completed`, and the operator override on
  `approved`.
- `hub/hub/review_turn.py` / `scheduler.py`: the briefing sentence.
- `hub/hub/api/v1/projects.py` (settings) and `tasks.py` (check runs read and re-run routes).
- `hub/ui/src`: the settings editor and the drawer row. The UI bundle is refreshed, and that reaches
  `:8000` on its next reload.
- `:8000` runs this checkout. Migration `0119` reaches the operator's real database on their next
  restart. It is additive only: a nullable column, a new table and a JSON column defaulting to `[]`.
