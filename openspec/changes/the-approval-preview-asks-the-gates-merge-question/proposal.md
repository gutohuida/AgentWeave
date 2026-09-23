# Proposal — the approval preview asks the gate's merge question

**Round 1, 2026-09-24** (bundle B5, decision D12's second question). Finding: **F141 (C)**.
Re-verified on HEAD `404c7d5`: **changed shape, still open.** Nothing here is implemented.

## Why

When approval is refused because the work conflicts with the main branch, the refusal is excellent
— it names the commit, the branch, the conflicting paths and the remedy
(`requirement_gate._check_mergeable`, `hub/hub/requirement_gate.py:421-472`, probing with
`task_integration.would_conflict`, `hub/hub/task_integration.py:427-447`). Then nothing remembers
it. F141 listed what the operator reads afterwards: `latest_integration: null`, `integrations: []`,
and an integration preview that said `will_merge: true`.

**What changed since F141.** F156's fix (Round 3, 2026-09-23) renamed the field to
`will_attempt_merge` and made the preview's `reason` say *"whether it merges cleanly is checked at
approval, which refuses if it does not"* (`hub/hub/api/v1/tasks.py:1138-1145`). So the preview no
longer promises a clean merge. But it still does not *know*: an operator who has just been refused
reopens the drawer and reads the same hedge beside the same Approve button, and one who has never
pressed Approve cannot learn about the conflict before pressing it. The conflict still exists only
in a discarded 409 body.

The preview's docstring refuses the probe on cost grounds — *"deliberately no conflict probe — that
is `requirement_gate`'s job"* (`tasks.py:1090-1092`). `would_conflict`'s own docstring answers that:
`git merge-tree --write-tree` *"touches neither the working tree nor the index of any checkout, so
asking this question costs nothing and changes nothing"* (`task_integration.py:430-433`). The
preview is fetched only when the drawer is open and approval is reachable
(`useTaskIntegrationPreview(taskId, canApprove)`, `TaskDetailDrawer.tsx:36`), with no polling.

## What Changes

- **The preview runs the gate's probe** (design D1). For each target, where the repository can be
  asked, `integration-preview` adds `conflicts: [{commit_sha, source_branch, paths}]` computed by
  `would_conflict` — the function the gate uses — and says in `reason` whether approval will merge
  cleanly or be refused, naming the paths. Where it cannot ask (no workspace, not a repository, no
  such main branch), `conflicts` is `null` and today's hedge is the reason.
- **Nothing is persisted** (D12). A refused approval writes no row. The answer is recomputed from
  the repository each time, so it cannot go stale after a rebase or new evidence, and there is no
  new outcome value for `task_integrations`' readers to learn.
- **The drawer shows a predicted refusal** (D2). `ApprovalWritesNote` renders the conflicting paths
  in the refusal's tone when `conflicts` is non-empty.

## Out of scope

- `GET /worktrees/conflicts` reporting branch-versus-main (F141's third repair). Largest, and the
  preview now answers the same question where the operator is about to act.
- The branch-bucket reduction the targets come from — `a-footprint-names-the-line-of-work-its-commit-is-on`
  (this change passes the resolved root into `merge_targets` for both routes, so it inherits that
  change's reduction without depending on it).

## Impact

- `hub/hub/api/v1/tasks.py` (`task_integration_preview`); `hub/hub/requirement_gate.py` only if R2
  extracts a shared helper (design D1)
- `hub/ui/src/api/tasks.ts` (type), `hub/ui/src/components/tasks/TaskDetailDrawer.tsx`; the
  committed bundle
- `openspec/specs/task-lifecycle-governance` (one ADDED requirement; the preview has no requirement
  today — F156's fix was not synced into a spec)
