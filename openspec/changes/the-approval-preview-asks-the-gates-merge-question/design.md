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

**Sharing with the gate — decided by R2: call it, renamed public.** `requirement_gate._merge_situation`
(`:393-418`) is already the one statement of the preconditions and returns `None` exactly where the
preview must say "not checked". A second module calling it makes it public API, so it is renamed
`merge_situation` (one call site, `requirement_gate.py:618`; three tests mention it by name). The preview then:

- `situation = await requirement_gate.merge_situation(session, task)` — **inside** the same wrap as
  the probe (below): `is_repository`, `branch_exists` and `merge_targets`' `task_branch_tip` are all
  built on `task_integration._git`, which raises;
- situation present → `targets = situation.will_merge`, probe each;
- `None` (no main branch, no workspace, not a repository, no such branch) or the wrap caught →
  today's target computation, `conflicts: null`. That keeps test 1.4's no-repository control
  byte-identical: today it lists the fake commit with the F156 sentence, and `merge_situation` would
  answer `None` there (`is_repository` false), so the fallback is what keeps the listing.

With `a-footprint-names-the-line-of-work-its-commit-is-on` (D4), the governed path's switch to
`merge_targets` is one step of this D1; whichever change lands first makes it.

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
  So `merge_situation` and the probe loop are wrapped together: any exception → `conflicts: null`
  and the hedge, never a 500 — the preview's docstring already states that posture ("not knowing is
  an answer here, a 500 is not").
- **Noted, not carried — traced by R2.** The gate's own git calls are unwrapped: `_merge_situation`'s
  `is_repository`/`branch_exists` (`task_integration.py:149`, `:169`), `merge_targets`'
  `task_branch_tip` (`:320`) and `_check_mergeable`'s `would_conflict` (`requirement_gate.py:434-436`)
  all reach `task_integration._git`. A `TimeoutExpired` (after 60 s) or `OSError` leaves `evaluate`
  (`task_transition_service.py:667`), then `transition()`; the app registers handlers only for
  `TransitionRefusedError` and `TaskBindingError` (`main.py:532-553`), so **every approval surface
  (operator `PATCH /tasks/{id}`, the agent plane, MCP) answers a bare 500** after up to a minute per
  call, with nothing committed. Not carried here, because what approval should do when the question
  cannot be answered (refuse as unknown, or approve and let the merge fail and record itself) is a
  decision; candidate finding for the orchestrator.
- A non-zero exit with no parsed path returns `["(unknown path)"]` (`:445-447`) and is rendered as
  such, as the gate renders it.

## Open questions

1. **Cost on a large repository** — **measured by R2** on this repository (3,576 commits, 2,922
   tracked files, Windows, git 2.49): `git merge-tree --write-tree --name-only master <tip>` took
   **0.03 s** against a near branch and **0.16 s** against a base from seven weeks earlier. One probe
   per target per drawer open is negligible. (It does write tree objects into the object database —
   loose objects `git gc` collects; never the checkout or index.)

## Round log

- **R1, 2026-09-24.** Re-verified F141 against `404c7d5` (changed shape after F156's fix); read the
  preview, gate and probe; wrote D1-D2 and D12's options.
- **R2, 2026-09-24.** Re-derived the preview (`tasks.py:1079-1157`), the gate and the probe — the
  claims hold. Decided the sharing (`merge_situation`, public, wrapped with the probe — R1 wrapped only
  the probe, but the preconditions raise the same way). Traced the gate's unwrapped git calls to a
  500 on every approval surface; left as a candidate finding. Measured the probe (Open Question 1).
- **R3, 2026-09-24.** Re-derived: `task_integration._git` is an unwrapped `subprocess.run(timeout=60)`
  (`:136-145`); `_merge_situation` has one call site (`requirement_gate.py:618`; tests name it only in
  docstrings); the app has exactly two exception handlers (`main.py:532`, `:544`), so R2's
  approval-surface 500 stands as traced. With the footprint change's D4 in `merge_targets`, the
  preview (through `merge_situation`) probes the list approval merges; `is_reachable_from` is
  wrapped, so D4 adds no raise inside the preview's wrap. No claim disagreed; nothing changed.
