# Proposal — a footprint names the line of work its commit is on

**Round 1, 2026-09-24** (bundle B5, spec track S12 and decision D12's third question). Findings:
**F165 (B)** with its 2026-08-31 addendum, and **F166 (C)**. Both re-verified on HEAD `404c7d5`:
still open; the tests that pin them as non-guarantees still pass as written
(`hub/tests/test_conflict_refusal_names_what_clears_it.py:347-391` and `:474-514`). Nothing here is
implemented.

## Why

A footprint's `branch` is the key the merge groups by: `task_integration.integration_targets`
keeps the newest accepted footprint per branch (`hub/hub/task_integration.py:270-286`,
`newest[target.branch] = target` at `:285`). A fresh footprint displaces a stale one only if both
carry the **same** branch string. Three ways the string comes out wrong:

1. **F165 — an operator names a commit that is not a branch tip.** `_take_footprint` reads a
   locator-named commit with `read_footprint(root, at=resolved)` (`requirement_evidence.py:296`),
   whose branch comes from `_branch_at` (`:565-578`): the one local branch whose **tip** is that
   commit, else `""`. A conflict resolution stops being a tip the moment anything is committed on
   top, so the fresh row lands under `""` beside the stale row under `agentweave/…`, and the
   conflict refusal stands with nothing on screen to say why.
2. **F165 addendum — a detached HEAD is spelled `"HEAD"`.** The ordinary arm reads
   `git rev-parse --abbrev-ref HEAD` (`:531-535`), which answers the literal `HEAD` when detached;
   `restamp_run_footprints` writes the same (`:968`). A review checkout is detached by construction
   (`worktrees.review_path`'s docstring, `worktrees.py:211-216`: *"re-pointed with `git checkout
   --detach` at each review"*), so every reviewer's evidence is keyed `"HEAD"`. `detect_drift` treats `""` and `"HEAD"`
   as one "unknown" (`:1140-1144`); the merge reduction treats them as two different branches.
3. **F166 — an agent whose run directory is gone is footprinted on the main branch.**
   `footprint_root` (`:299-348`) falls back from the run's recorded directory, when it no longer
   exists, to the per-agent checkout and then to `workspace.root` — the operator's checkout, usually
   on the main branch. The recorded directory disappears when a task reaches a terminal status:
   `release_task_workspace` (`task_transition_service.py:739-800`) runs on `approved` **and**
   `rejected`, and rejection is not gated on the turn having ended (only approval is,
   `requirement_gate._check_live_turn`). The resulting footprint names a main-branch commit that
   does not contain the work, merges as a no-op, and displaces nothing.

A fourth problem appears as soon as (2) is fixed, so this change carries it: **the reduction keeps
the newest *observation*, not the newest *commit*.** Today a reviewer's footprint at an older commit
lands in its own `"HEAD"` bucket and does no harm. Once it names the task branch, a review recorded
after the author moved on would displace the author's newer commit, and approval would merge less
than was done.

## What Changes

- **One spelling for "unknown"** (design D1, D12). `""` everywhere. `"HEAD"` is never written, and a
  data migration rewrites stored `evidence_footprints.branch = 'HEAD'` to `''`.
- **The branch a commit belongs to is resolved, not only read** (D2). `line_of_work(root, commit,
  task_branch=None)` answers: the one branch whose tip is the commit; else the task's own branch if
  it contains the commit; else the one local branch that contains it; else `""`. Both of
  `read_footprint`'s arms use it — the named-commit arm always, the ordinary arm when HEAD is
  detached — and so does `restamp_run_footprints`.
- **An agent whose run directory is gone is footprinted at its task's branch** (D3, F166). Before
  falling back to the per-agent checkout or the project checkout, a task-bound agent's footprint is
  read at the tip of `agentweave/task/<id>` — where release snapshotted the work — with that branch
  named.
- **Within one line of work, a descendant commit wins** (D4). `merge_targets` — what approval, the
  gate and prerequisite provisioning already call — keeps, per branch, the target whose commit
  descends from the others, and uses observation order only between commits neither of which
  contains the other. `integration_targets` stays the pure database query `merge_targets`' docstring
  says it is. The preview's governed path switches to `merge_targets`, so the drawer lists what
  approval merges.

## Out of scope

- Whether a footprint's `entries` should be the changed paths rather than the whole tree
  (`read_footprint`'s own note, `:520-523`) — drift, B6.
- The approval preview's conflict answer — `the-approval-preview-asks-the-gates-merge-question`.

## Impact

- `hub/hub/requirement_evidence.py` (`read_footprint`, `_branch_at` → `line_of_work`,
  `_take_footprint`, `footprint_root`, `capture_footprint`, `restamp_run_footprints`)
- `hub/hub/task_integration.py` (`merge_targets`' governed path reduces by ancestry;
  `integration_targets` unchanged), `hub/hub/api/v1/tasks.py` (the preview's governed path)
- A data-only migration (`.claude/rules/db-migrations.md`: it reaches `:8000`'s real database on
  its next restart; it is an idempotent `UPDATE`)
- Tests that pin today's behaviour as a non-guarantee flip on purpose:
  `test_an_operator_naming_the_resolved_sha_does_not_supersede` (asserts `branch == ""`)
- `openspec/specs/spec-document-authority` (MODIFIED: *Evidence is footprinted against the work it
  describes*; ADDED: one requirement on the reduction)
