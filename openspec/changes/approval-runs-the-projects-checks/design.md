## Context

The approval gate (`hub/hub/requirement_gate.py:709-842`, `evaluate`) refuses in five categories, among them `unmergeable` from `git merge-tree` (`_check_mergeable`, :465). It runs synchronously in the request, with a 60s git timeout per spawn (`task_integration.py:148-163`). Nothing in the Hub runs a project's own commands. Only agents do, inside their runs. No project setting names a command (`db/models.py:68-172`; `project.json` holds only the id, `project_workspace.py:18`). Four facts constrain the design:

1. **`evaluate` has many callers.** These are the approval transition (`task_transition_service.py:678-695`), the land route (`api/v1/tasks.py:1679`), and `approval_held_for_operator` (requirement_gate.py:897), which the scheduler (:1876), run divergence (:426) and the review outcome (`review_turn.py:436,440`) call under a 5s git budget.
2. **An agent's tool call times out after 10s** (`mcp_server.py:233`).
3. **"Main plus this commit" has no checkout form.** `would_conflict` discards the merged tree OID (`task_integration.py:492-494`). Review checkouts hold the task's commit alone (`worktrees.py:677-714`).
4. **The real merge happens in the project's root checkout** (`task_integration.integrate`, :520-592), which must stay clean.

Operator decisions, 2026-10-06: openspec, not the trial Hub; commands come from an operator setting only; checks run when work completes; the operator may override a failure with a reason.

## Goals / Non-Goals

Goals: approval cannot land work that fails the project's checks; the gate stays fast and never executes anything; a reviewer and the operator both see the result and what to do.

Non-goals are in `proposal.md`. Briefly: no agent-supplied commands, no checks from the repository, no acceptance-criteria execution, no Docker mode, no sandbox beyond checkout, timeout and environment scrubbing.

## Decisions

**D1. The would-merge commit is built without a checkout or the root.**
- For each merge target in `merge_targets` order: `git merge-tree --write-tree <base> <target>` gives the tree, and `git commit-tree <tree> -p <base> -p <target>` gives a commit, which becomes the next base. The first base is main's tip.
- The resulting commit is unreferenced (it is garbage collected eventually) and identifies exactly what approval would produce.
- A conflict at any step records the run as `error` ("would not merge"). `_check_mergeable` already refuses that case, so this is never the only refusal.
- *Alternative rejected:* a worktree at main plus `git merge --no-commit`. It leaves merge state in a worktree, and its result differs from the gate's view when targets come from other tasks.

**D2. One scratch worktree per task, under `.agentweave/checks/<task_id>`.**
- It is created with `worktree add --detach <commit>`, and the shared dependency directories are symlinked as task checkouts do (`worktrees.py:238-258`). It is removed when the run ends, pass or fail.
- *Alternative rejected:* reusing the reviewer's checkout (`.agentweave/reviews/<agent>`). It is keyed per agent and live during the review, so a run would race the reviewer.

**D3. Results are rows, keyed so that staleness is computable.**
- `task_check_runs(id, project_id, task_id, main_sha, target_shas JSON, merged_sha, state, results JSON, started_at, ended_at, error)`.
- The gate reads the newest row for the task. It is *current* when `main_sha` equals main's tip and `target_shas` equals today's `merge_targets`. Anything else is stale.
- Rows are append-only, as `TaskIntegration` is (`models.py:2705`). The history is the audit trail.

**D4. Runs execute in an in-process queue, two at a time, started at two moments.**
- *Changed while building:* an agent completes its task mid-turn, and the commit holding its work is made only at the turn's end. A run started at that transition would check the old tree. So a run starts at the `completed` transition only when no run made it (`actor.run_id is None`). For a run's task it starts at that run's end, after the snapshot commit (`project_checks.after_run`, in both executors). Both start only when the project has checks.
- Each run is an asyncio task holding a `subprocess` per check (`shell=True`, `cwd` = scratch).
- On timeout the run calls `pty_runner.terminate_process_tree` (:184).
- A run already executing for the task is joined rather than duplicated.
- Startup marks leftover `running` rows `interrupted` (as `main.py`'s other reconcilers do), and the next approval request starts a fresh run.
- *Alternative rejected:* the scheduler's job machinery. Its jobs are agent turns, and a check run is not one.

**D5. The gate reads; only two callers may start a run.**
- `evaluate` gains a keyword `start_checks: bool = False`. With it false, a missing, stale or `interrupted` result refuses as "checks have not run on this work", and nothing starts.
- The approval transition and the land route pass `True`: they enqueue the run (an awaited enqueue only, never the run) and refuse as "checks still running".
- This keeps `approval_held_for_operator`'s 5s budget and every diagnostic caller unchanged.

**D6. The refusal is a sixth category, `checks`.**
- It is added to `refuses`, `detail()`, `to_dict()` and `_operator_only_remedy` (requirement_gate.py:136-164, 352-362, 880-894). The `detail()` docstring requires the explicit composition.
- The sentence carries at most the last 1500 characters per failing check, because agents read only `message` (`mcp_server.py:173-210`).
- It ends with a `REVIEWER_SENDS_BACK_CHECKS` sentence, as F504 and F497 did for the conflict and rejected refusals.

**D7. The operator override is a field on the operator's approval request.**
- The field is `override_checks_reason`. It is honoured only when the actor is the operator (`actor.kind == "operator"`) and the latest result is `failed` or `error`. An agent sending it gets a 403-class refusal.
- It is stored on `task_transitions.override_reason`, so `task_history` shows it.
- It clears the `checks` category only. Every other category still refuses.

**D8. The environment is the Hub's minus the Hub's own configuration.**
- Removed: every `AW_*`, `HUB_*` and `AGENTWEAVE_*` variable, `DATABASE_URL`, and any variable whose value starts `aw_live_` or `aw_run_`. *Changed while building:* `DATABASE_URL` would have pointed a project's tests at the Hub's own database.
- Provider keys stay, because a project's tests may need them, and the operator chose the commands.
- Output is scrubbed of the removed values and of any `aw_live_`/`aw_run_` token before it is stored. `run_secrets.scrub` is per-run and does not apply.

**D9. The UI is the smallest that makes it usable without the API.**
- A Checks list in project settings (name, command, timeout; add, remove, reorder).
- One row in the task drawer: the latest run's state, the failing check's tail, and "Re-run".

## Risks / Trade-offs

- [The Hub executes operator-chosen commands with the Hub's privileges] → Settings are operator-only (`auth.get_operator_project`, `auth.py:121`), no agent route can write them (tested), and the commands run in a scratch checkout with credentials removed. The 09-10 research note's concern (agent-supplied strings) does not apply: no agent string is executed.
- [Environment-specific failures teach people to ignore the check] → The operator override, with a recorded reason, is the release valve, and the reasons are counted.
- [Slow suites delay approval] → Runs start at `completed`, so a review overlaps the run. Two runs at a time bound the machine's load.
- [Symlinked dependencies fail on Windows without symlink rights] → They degrade as task checkouts do. The check fails legibly ("module not found") rather than silently.
- [Merge targets from another task (shared requirement) are included] → This is intentional. The check tests exactly what approval merges, F499's subject.

## Migration Plan

Migration `0119` is additive:
- `projects.checks` JSON, NOT NULL, default `'[]'`;
- the new table `task_check_runs`, guarded for a missing `tasks` table as `0033`/`0034` do;
- `task_transitions.override_reason`, nullable.

Bump the head assertions in `test_migrations.py` and `test_project_persistence.py`. Rollback: drop the table and the two columns. No existing row changes meaning, so `:8000`'s next restart applies it with no behaviour change until checks are configured.

## Acceptance drive (R3: written and failing before the build)

`scripts/drive/d1006_checks_gate.py` runs on a fresh Hub (`e2e.py hub-up`) with a throwaway project whose repo has a passing pytest test and the check `py -3.11 -m pytest -q`. Real Haiku agents:
1. A builder is told to break the test and complete the task, and the check run is recorded `failed`.
2. A reviewer's turn context names the failure, the reviewer's `approved` is refused with the output tail, and it sends the task back.
3. The author fixes the test, the run is recorded `passed`, and approval merges.
4. On a second task: the operator approves over a failure with a reason, and `task_history` shows it.
5. A Hub restart mid-run: the run reads `interrupted`, and approval starts a new run.

Before the build, step 1 fails: no run is recorded.

## Open Questions

- Should a reviewer's turn be delayed until the checks finish, rather than briefed "running"? This is not decided. The briefing sentence covers it for now, and the trial data will show whether it matters.
