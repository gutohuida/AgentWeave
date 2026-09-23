# Design — a footprint names the line of work its commit is on

**Built on the recommended answer to D12's third question** (F165: the unknown-branch spelling):
*one spelling, `""`, and the branch resolved wherever git can say which line of work a commit is on*.
If the operator answers otherwise:

- **"Normalise at read, no migration"** — D1's migration is dropped and `_targets`/`detect_drift`
  map `"HEAD"` to `""` when reading; D2-D4 stand.
- **"Leave the spelling; fix only F165's operator case"** — D1 is dropped, D2 applies to the
  named-commit arm only, D3 (F166) stands, and D4 becomes optional: reviewers' rows stay in their
  own `"HEAD"` bucket, so only an operator naming an *older* commit could still displace newer work.

## What the code does today (HEAD `404c7d5`)

| Arm | Where | Branch written when the line of work is unknown |
|---|---|---|
| operator names a commit (F71) | `read_footprint(root, at=…)` → `_branch_at` (`requirement_evidence.py:565-578`) | `""` unless the commit is the tip of exactly one branch |
| ordinary read | `read_footprint` (`:531-535`) → `git rev-parse --abbrev-ref HEAD` | `"HEAD"` — **measured in R1** (git 2.49): a detached checkout answers the literal `HEAD` |
| re-point at run end | `restamp_run_footprints` (`:968`) | `"HEAD"` for a detached checkout |

| Consumer | Treats `""` and `"HEAD"` as |
|---|---|
| `detect_drift` (`:1140-1144`) | one "unknown": skip |
| `integration_targets` (`task_integration.py:283-286`) | two ordinary, distinct keys |
| `commit_for_task_review` (`:785-844`) | passes `branch` through to the review turn |

**A latent bug found in R1.** `_branch_at` runs `git branch --points-at <commit>`. When the checkout
it runs in is itself **detached at that commit**, git lists `(HEAD detached at <sha>)` as a line
(measured, git 2.49), `_branch_at` counts it as the one branch, and the footprint's branch becomes
the string `(HEAD detached at 5c1ee88)`. `git for-each-ref --points-at <commit> refs/heads` lists
only real branches (measured).

## D12 — the unknown-branch spelling: options

| Option | What it releases | What it breaks or leaves |
|---|---|---|
| **(a) one spelling `""`, written everywhere, plus a data migration** (recommended) | one bucket, one meaning; `detect_drift`'s two-value check becomes one | a migration on `:8000`'s real data (an idempotent `UPDATE … SET branch='' WHERE branch='HEAD'`) |
| (b) normalise at read | no migration | two spellings stored forever; every new reader must remember to normalise — the drift/merge split F165 is about is exactly one reader forgetting |
| (c) `NULL` for unknown | SQL-honest | `Target.branch` and `newest` already accept `None`, but every `or ""` in the module and the drive harnesses read `""`; more churn than (a) for no extra meaning |

Recommended **(a)**. Interaction with D12's other questions: none on the spelling itself. F242
(isolation) changes *which directory* a footprint is read in for a read-only agent, never how the
branch is spelled; F141's recommended answer (the preview runs the gate's probe) consumes
`integration_targets`, so it inherits D4 through `merge_targets`.

## D1 — one spelling

`read_footprint` and `restamp_run_footprints` never write `"HEAD"`: where `--abbrev-ref` answers
`HEAD`, they call `line_of_work` (D2). Migration `0106_footprint_branch_one_unknown_spelling`:
`UPDATE evidence_footprints SET branch = '' WHERE branch = 'HEAD'`, guarded for a missing table.
Data-only; no head-assertion bump is needed unless `test_migrations.py` asserts the head id (it
does — bump it per `.claude/rules/db-migrations.md`). `detect_drift`'s `ref == "HEAD"` clause stays
one release as a guard for rows written between deploy and migration, then goes.

## D2 — `line_of_work(root, commit, *, task_branch=None) -> str`

1. Local branches whose tip is `commit` — `git for-each-ref --points-at <commit> refs/heads
   --format=%(refname:short)`. Exactly one → it.
2. Else, if `task_branch` is given and `git merge-base --is-ancestor <commit> <task_branch>`
   succeeds → `task_branch`.
3. Else, local branches containing it — `git for-each-ref --contains <commit> refs/heads`. Exactly
   one → it. (`main` counts: a commit only on `main` is on `main`.)
4. Else `""`.

Step 2 before step 3 because a task's evidence normally sits on its own branch **and**, once merged,
on `main`; step 3 alone would call that ambiguous. The task branch is
`worktrees.task_branch_name(task_id)`, caught for a foreign id exactly as `task_branch_tip` does
(`task_integration.py:307-323`).

Callers:
- `read_footprint(root, *, at=None, task_branch=None)`: the `at` arm always; the ordinary arm when
  `--abbrev-ref` answers `HEAD`.
- `_take_footprint` / `capture_footprint`: pass the evidence's task branch where the row has a
  `task_id` (for `record`, the `task_id` it has already resolved, `:130-133`).
- `restamp_run_footprints`: where `--abbrev-ref` answers `HEAD`, `line_of_work(root, target,
  task_branch=<the run's task branch>)`, reading `Run.task_id` once per run.

Operators' footprints on a non-tip commit now name a branch, so `detect_drift` stops skipping them
and compares them against that branch's tip. That is the designed behaviour for every other
footprint (*"Movement on the branch is drift"*, `spec-document-authority/spec.md:514-517`); R2
should confirm it does not flood a fixture with candidates.

## D3 — an agent whose run directory is gone (F166)

`footprint_root` keeps its first answer (the recorded directory while it exists). New second
answer, for `actor_kind == "agent"` with a task: **the project root read at the task branch's tip**
— `read_footprint(workspace.root, at=task_branch_tip, task_branch=…)` — because release snapshots a
task checkout onto its branch before removing it (`workspace-isolation`: *"A release gives back the
directory and never the work"*). `footprint_root` returns a directory, not a commit, so this lands
in `_take_footprint`/`capture_footprint`, which already special-case the operator's named commit;
R2 decides the cleanest seam. Then the per-agent checkout, then `workspace.root`, as today.

**Reachability, from the code.** `release_task_workspace` runs for both terminal statuses
(`task_transition_service.py:726-727`), and only `approved` is gated on no live turn
(`requirement_gate._check_live_turn`, reached only from `evaluate`). So an operator rejecting a task
mid-turn removes the directory under a live run, and that run's next `record_evidence` falls back.
Not driven in R1.

## D4 — within one line of work, the descendant commit wins

`integration_targets(session, task, root=None)`: where `root` is given, an incoming target
**replaces** the incumbent of its branch unless the incoming commit is an ancestor of the
incumbent's (`requirement_evidence.is_reachable_from(root, incoming, incumbent_commit)` is `True`);
where neither contains the other (a rebase), the newer observation wins as today. Where `root` is
`None`, today's observation-order rule. `merge_targets` passes its `root`; the preview passes one
when it resolves the workspace (see the F141 change).

Why this belongs here: D2 moves reviewers' detached-HEAD footprints into the task branch's bucket.
A reviewer checks the newest evidence's commit (`commit_for_task_review`), but if the author records
again during the review, the reviewer's later footprint names the **older** commit. Keyed by
observation it would displace the author's newer one and approval would merge less than was done.
Today the `"HEAD"` bucket hides that. The awaiting list (`awaiting_targets`) is unreduced by design
(`:289-304`) and is unaffected.

**Cost.** One `merge-base --is-ancestor` per same-branch collision, bounded by the accepted rows of
one task; `refresh_reachability` already caps a similar loop at 200 (`MAX_REACHABILITY_CHECKS`).

## What the routes return when what they call raises

`line_of_work` is built on `_git`, which returns `None` on any failure (`:475-490`); every step
treats `None` as "no answer" and falls through to `""`. So a git failure degrades to today's unknown
rather than raising into `record` (whose routes would 500) or into the restamp (which is wrapped,
`agent_trigger.py:1789-1801`). `is_reachable_from` returns `None` on failure; D4 treats `None` as
"not an ancestor", i.e. observation order.

## Cross-bundle collision — B6's `drift-watches-the-files-its-evidence-is-about`

That change (bundle B6) edits the **same functions**: `read_footprint` (it gains `locator` and
`actor_kind` to compute `entries` from watched files), `_take_footprint`, `capture_footprint`,
`restamp_run_footprints` and `detect_drift` (its drift basis becomes the main branch when
`reachable_from_main is True`, else `footprint.branch`). The fields do not overlap — it moves
`entries` and adds `watched_from`; this change moves `branch` — but the signatures and the
`detect_drift` basis do. Two consequences for sequencing: (1) whichever lands second rebases
`read_footprint`'s signature (both add keyword-only parameters); (2) D2 makes operator footprints on
non-tip commits name a branch, which B6's drift basis then reads, so R2 of **both** changes should
check the combined drift behaviour on one fixture. Recommended order: this change first (it changes
what `branch` means), then B6's.

## Open questions

1. **Step 3's `main`.** A commit on `main` only, named by an operator, gets `branch = main`. It then
   shares a bucket with nothing a task produced. Harmless as far as R1 can see; R2 checks
   `integrate`'s `ALREADY_INTEGRATED` path for it.

## Round log

- **R1, 2026-09-24.** Re-verified F165 (both spellings) and F166 against `404c7d5`; measured git's
  detached answers; found `_branch_at`'s detached-checkout bug and the observation-order hazard D2
  would expose; wrote D1-D4 and D12's options.
