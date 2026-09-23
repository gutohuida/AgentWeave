# Design — the approval preview asks the gate's merge question

**Built on the recommended answer to D12's second question** (F141: *is the approval gate's
conflict result persisted?*): **no — the preview asks the same question live instead.** If the
operator answers otherwise:

- **"Persist it"** — replace D1 with: the transition service, on a `gate_unsatisfied` refusal whose
  `unmergeable` is non-empty, appends a `TaskIntegration` row with outcome `refused` in its own
  transaction (the transition's own is rolled back by the refusal), and `latest_integration` /
  `/integrations` show it. The preview is untouched. R2 would have to list every reader that filters
  on `outcome` (`tasks_skipped_for_want_of_a_main_branch`, `tasks_awaiting_this_commit`,
  `is_retryable`, the UI's history rows) and settle what "stale" means for the row.
- **"Let the preview read the last refusal"** — needs the same persisted row (or an event), plus a
  freshness rule; strictly more than either other option.

## D12, second question — options

| Option | Releases | Breaks or leaves |
|---|---|---|
| **(a) the preview runs `would_conflict`** (recommended) | the answer exists **before** the first approve, and after a refusal; always fresh; no new stored state | a `git merge-tree` per target per drawer open where approval is reachable |
| (b) persist the refusal as an integration row | the history names the refusal | a rejected transition writes a row (no other refusal does); the row is stale the moment the branch is rebased or new evidence is accepted; nothing before the first approve |
| (c) the preview reads the last refusal | lands where the operator looks | needs (b)'s storage or an event, and a freshness rule; says nothing before the first approve |
| (d) `/worktrees/conflicts` reports branch-vs-main | catches it before approve, project-wide | largest; a second place to ask the question the drawer is already asking |

**Interaction with D12's other questions.** The preview's targets come from `merge_targets`, whose
per-branch reduction the F165 change (D12 third question) fixes. Under (a) the preview probes
exactly what approval would merge, so any reduction fix reaches it automatically. F242 does not
touch integration.

## D1 — the probe in the preview

Today (`tasks.py:1110-1157`): governed tasks read `integration_targets` without resolving the
workspace; ungoverned ones resolve it for `merge_targets`. New shape:

1. Resolve the workspace **for both** (wrapped as today: any exception → not known,
   `tasks.py:1126-1129`). Governed → `merge_targets(session, task, root)` (which returns
   `integration_targets` for a governed task, `task_integration.py:385-408`).
2. If `main_branch` is set, the root is a repository and the branch exists — the same three
   preconditions `requirement_gate._merge_situation` checks (`:393-418`) — run `would_conflict(root,
   target.commit_sha, main_branch)` per target and build `conflicts`. Otherwise `conflicts = None`.
3. `reason`:
   - `conflicts` non-empty → *"approval will be refused: `<paths>` in commit `<sha12>` conflict with
     `<main>`"* (one clause per conflicting target);
   - `conflicts == []` → *"approval will merge one commit into `<main>`; it merges cleanly as of
     now"*;
   - `conflicts is None` → today's F156 sentence, unchanged.
4. `will_attempt_merge` keeps its meaning (a merge will be tried if approval is accepted).

**Sharing with the gate.** The preconditions are the gate's; R2 decides whether to call
`requirement_gate._merge_situation` directly (it resolves the workspace and the targets once, and is
already the single statement of the four preconditions — its docstring says they "have to be the
same four rather than two lists that can drift") or to extract a public helper from it. Calling it
directly is recommended: it returns `None` exactly where the preview must say "not checked".

**Docstring.** The preview's "deliberately no conflict probe" paragraph (`tasks.py:1090-1092`) is
rewritten to say why it now asks: the gate refuses, and the operator should know before pressing.
"This is a sentence, not a second gate" stays true — the preview refuses nothing.

## D2 — the drawer

`TaskIntegrationPreview` gains `conflicts: { commit_sha: string; source_branch: string | null;
paths: string[] }[] | null`. `ApprovalWritesNote` (`TaskDetailDrawer.tsx:36-…`): when
`conflicts?.length`, render the Hub's `reason` in the red refusal tone, with each path in `<code>`.
Otherwise unchanged.

## What the route returns when what it calls raises

- Workspace resolution raising → caught; `conflicts: null`, today's reason. Unchanged posture.
- `would_conflict` is built on `task_integration._git` (`:136-145`), a bare `subprocess.run(...,
  timeout=60, check=False)` with no `try`: it **raises** `subprocess.TimeoutExpired` or `OSError`.
  So the probe loop is wrapped: any exception → `conflicts: null` and the hedge, never a 500 — the
  preview's docstring already states that posture ("not knowing is an answer here, a 500 is not").
- **Noted, not carried:** the gate itself calls `would_conflict` unwrapped
  (`requirement_gate._check_mergeable`, `:434-436`), so a git timeout during approval propagates out
  of `evaluate`. R2 should trace what the approval route answers then (the transition service's
  caller, `task_transition_service.py:667`) — a candidate finding for the bundle record.
- A non-zero exit with no parsed path returns `["(unknown path)"]` (`:445-447`) and is rendered as
  such, as the gate renders it.

## Open questions

1. **Cost on a large repository.** `merge-tree --write-tree` writes tree objects into the object
   database (not the checkout). R1 has not measured its time on a large repository; the drawer
   fetch is on open only. R2 or IMPL measures on this repo and records it.

## Round log

- **R1, 2026-09-24.** Re-verified F141 against `404c7d5` (changed shape after F156's fix); read the
  preview, gate and probe; wrote D1-D2 and D12's options.
