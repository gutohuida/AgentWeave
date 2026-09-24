# Design — a footprint names the line of work its commit is on

## Operator review, 2026-09-24

The Opus adversarial review (`spec-queue/tracks/reviews/B5-2026-09-24.md`, section 4) returned
**approve with fixes**, and the operator answered D12's third question as recommended (one
spelling `""`, resolved, with the data migration). What changed, and why:

- **The `""` bucket is no longer reduced as a line of work (review MEDIUM).** `integration_targets`
  keys `""` like any branch (`task_integration.py:283-285`), and R3's D4 kept "later observation
  wins" for two commits where neither contains the other. But `""` means *no known line of work*:
  two such commits share nothing but a missing name, so the observation-order rule would drop an
  unrelated piece of accepted work from the merge. D4 gains a second arm (below): among unnamed
  footprints, only a **proper ancestor** of another kept commit is dropped; every commit where
  neither contains the other is kept, and an unanswerable probe keeps both. New tests 1.5d and 1.5e;
  new spec scenarios.
- **The MODIFIED requirement stated two absolute fallbacks side by side (review LOW).** "Where no
  checkout for the agent exists … SHALL fall back to the project's own directory" stood next to the
  new task-branch-tip rule. The delta now states the order: the task-branch tip first, *otherwise*
  the project's own directory, and the two fallback scenarios say they are the no-task-branch case.
- **An existing SHALL this change contradicted without a delta (found while applying the review).**
  `task-lifecycle-governance`, *Approval integrates the approved work*, says what is merged is
  "the newest such commit per distinct branch" (`openspec/specs/task-lifecycle-governance/spec.md:881`).
  D4 (descendant wins) and the new `""` arm both change that sentence, so the change now carries a
  MODIFIED delta for that requirement (`specs/task-lifecycle-governance/spec.md`). The refusal
  requirement's explanatory "keeping the most recently recorded accepted evidence for each"
  (`:965-967`) is descriptive, not a SHALL, and every SHALL around it still holds: a conflict
  resolution committed on the branch is a descendant of the judged commit (D4 keeps it) or, after a
  rewrite, neither contains the other (the later recording wins, as today). Not modified.
- **The migration is a no-op on real data (review, measured read-only).** `:8000` at head `0105`:
  zero rows with `'HEAD'`, zero with `''`, 9 `NULL`, 89 named. The trial DB: 2 rows, both task
  branches. The idempotent `UPDATE` is kept for rows written between now and deploy, and is safe to
  re-run. Recorded under D1.

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
the string `(HEAD detached at 5c1ee88)`. **R2 re-measured (git 2.49.0.windows.1), sharper:** detached
at a branch **tip**, the listing is two lines (`(HEAD detached at …)` and the branch), so
`_branch_at` answers `""`; detached at a **non-tip** commit, it is the one line `(HEAD detached at …)`,
and that string is returned as the branch. `git for-each-ref --points-at <commit> refs/heads` lists
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
`HEAD`, they call `line_of_work` (D2). A data migration, `<next>_footprint_branch_one_unknown_spelling` — the next free revision when
implemented (`0105` is head at `404c7d5`, and four other parked changes also name `0106`):
`UPDATE evidence_footprints SET branch = '' WHERE branch = 'HEAD'`, guarded for a missing table.
Data-only; no head-assertion bump is needed unless `test_migrations.py` asserts the head id (it
does — bump it per `.claude/rules/db-migrations.md`). `detect_drift`'s `ref == "HEAD"` clause stays
one release as a guard for rows written between deploy and migration, then goes.

**Measured on real data (operator review, read-only `mode=ro`).** `:8000` at head `0105` holds
zero footprints with `branch = 'HEAD'`, zero with `''`, 9 `NULL` and 89 named; the trial DB holds 2,
both on task branches. So the `UPDATE` changes nothing today; it exists for rows written between now
and deploy. The 9 `NULL` rows are left as they are; D4's unnamed arm treats `NULL` as `""`.

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
(`task_integration.py:307-323`) — but built on **this module's** `_git`, which returns `None` on
failure, not `task_integration._git`, which raises (and `task_integration` imports this module).

Callers:
- `read_footprint(root, *, at=None, task_branch=None)`: the `at` arm always; the ordinary arm when
  `--abbrev-ref` answers `HEAD`.
- `_take_footprint` / `capture_footprint`: pass the evidence's task branch where the row has a
  `task_id` (for `record`, the `task_id` it has already resolved, `:130-133`).
- `restamp_run_footprints`: where `--abbrev-ref` answers `HEAD`, `line_of_work(root, target,
  task_branch=<the run's task branch>)`, reading `Run.task_id` once per run. (R2: rarely reached — the
  restamp runs only for a run given a non-review isolated workspace, `agent_trigger.py:1033`,
  `:1341`, `:1788`, which is on a branch unless mid-merge; the review checkouts that *are* detached
  are never restamped. Kept so no writer can produce `"HEAD"`.)

Operators' footprints on a non-tip commit now name a branch, so `detect_drift` stops skipping them
and compares them against that branch's tip. That is the designed behaviour for every other
footprint (*"Movement on the branch is drift"*, `spec-document-authority/spec.md:514-517`); R2
should confirm it does not flood a fixture with candidates. **R2:** the new candidates are exactly
rows that used to be skipped and now name a branch — operators' named non-tip commits (the F71 path,
rare) and reviewers' rows (formerly `"HEAD"`) once their task branch moves on. Rows already stored as
`"HEAD"` become `""` and stay skipped, so nothing existing is newly compared. With B6's
`drift-watches-the-files-its-evidence-is-about` (its "Builds on B5" section), each is compared on its
own files only; without it, on the whole tree — the pre-existing basis every branch-named footprint
already has.

## D3 — an agent whose run directory is gone (F166)

`footprint_root` keeps its first answer (the recorded directory while it exists). New second
answer, for `actor_kind == "agent"` with a task: **the project root read at the task branch's tip**
— `read_footprint(workspace.root, at=task_branch_tip, task_branch=…)` — because release snapshots a
task checkout onto its branch before removing it (`workspace-isolation`: *"A release gives back the
directory and never the work"*). `footprint_root` returns a directory, not a commit, so this cannot live in it.

**The seam (decided by R2).** One synchronous function both readers call, so they cannot disagree:
`read_evidence_footprint(workspace, actor_kind, actor, recorded_dir, task_id, *, named=None) ->
Footprint`. In order: (1) `recorded_dir` is an existing directory → `read_footprint(recorded_dir,
at=named, task_branch=…)`; (2) else an agent with a `task_id` whose branch resolves in
`workspace.root` (this module's `_git`, `rev-parse --verify refs/heads/<branch>`) →
`read_footprint(workspace.root, at=<tip>, task_branch=<branch>)`; (3) else today's fallback root
(`footprint_root`, unchanged — the per-agent checkout, then `workspace.root`). `_take_footprint`
(`requirement_evidence.py:248-296`) keeps its operator-named-commit verification and passes `named`;
`capture_footprint` (`:433-472`) passes `evidence.task_id`. `footprint_root` keeps its two callers'
contract and gains none. **Condition (2) is "no usable recorded directory"**, which also covers a
task-bound run predating the column; a pre-isolation task has no branch and falls to (3).

**Reachability, from the code.** `release_task_workspace` runs for both terminal statuses
(`task_transition_service.py:726-727`), and only `approved` is gated on no live turn
(`requirement_gate._check_live_turn`, reached only from `evaluate`). So an operator rejecting a task
mid-turn removes the directory under a live run, and that run's next `record_evidence` falls back.
Not driven in R1. **R2:** `release_task_worktree` snapshots uncommitted work onto the task branch
before `worktree remove --force` (`worktrees.py:987-1020`), so the task branch's tip holds the work
(D3's premise holds). That run's end-of-turn restamp then finds no directory: `snapshot_worktree`
fails, `rev-parse HEAD` in a missing root answers `None`, and `restamp_run_footprints` returns 0
(`:941-943`) — so the footprint D3 wrote at record time is the one that stays.

## D4 — within one line of work, the descendant commit wins

**Moved by R2 from `integration_targets` into `merge_targets`.** R1 gave `integration_targets` an
optional `root`. But `merge_targets`' own docstring states the opposite contract — *"`integration_targets`
itself is **not** modified and stays a pure database query; the branch-tip answer needs a
`rev-parse`, which is why this one takes a repository root and that one does not"*
(`task_integration.py:385-392`) — and every production caller that merges already goes through
`merge_targets` (`requirement_gate._merge_situation` `:417`, `task_transition_service.py:883`,
`task_workspace.py:242`). The one direct caller of `integration_targets` is the preview's governed
path (`api/v1/tasks.py:1122`). So:

- `merge_targets(session, task, root)`, governed path: take `integration_targets`' per-branch list
  **before** its reduction (a private `_accepted_targets` both share), and reduce with the ancestry
  rule — an incoming target **replaces** its branch's incumbent unless the incoming commit is a
  **proper** ancestor of the incumbent's (a different sha, and `requirement_evidence.is_reachable_from(root, incoming,
  incumbent_commit) is True`. R3: *proper*, because `merge-base --is-ancestor X X` succeeds, so a bare
  ancestry test would keep the **older** row for two footprints of one commit where today the newer
  observation wins — changing which `evidence_id` the gate's `unmergeable` entry names, `requirement_gate.py:448-452`; the third argument accepts a sha, since it is `rev-parse --verify`'d
  then passed to `merge-base --is-ancestor`, `:587-612`); where neither contains the other (a
  rebase), the newer observation wins as today. `None` from the probe is "not an ancestor".
  This arm applies to **named** lines of work only.
- **Unnamed footprints (operator review).** A footprint whose branch is `""` — or `NULL`, which
  `_targets` passes through as `None` and today forms its own key (`task_integration.py:283`,
  `EvidenceFootprint.branch` is nullable, `db/models.py:2591`) — names *no* line of work, so the
  unnamed footprints are not one bucket. They are reduced as a set, oldest observation first: an
  incoming commit equal to a kept one **replaces** it (the later row's `evidence_id`, as 1.5c pins for
  named lines); an incoming commit that is a proper ancestor of any kept commit is **dropped**;
  otherwise every kept commit that is a proper ancestor of the incoming one is removed and the
  incoming one is **kept**. Where the probe answers `None`, the two are treated as unrelated and
  **both kept** — the opposite default to the named arm, because there observation order is a
  real rule about one line of work, while here dropping on an unknown answer loses accepted work.
  Every kept unnamed commit becomes its own `Target` (branch `""`).
- **Consequence for merging, stated.** Two kept unnamed commits are merged one after the other, as
  two named branches already are; each is probed against main by the gate separately
  (`requirement_gate._check_mergeable`), so a conflict *between* them surfaces at the merge, not the
  gate. That is the existing multi-branch behaviour, not new to this change.
- `integration_targets` keeps its observation-order reduction and its pure-database contract, for
  any caller without a repository.
- **It fires from the real approval path (R3, traced).** `PATCH /tasks/{id} {"status":"approved"}` →
  `task_transition_service.transition` → `evaluate` → `requirement_gate._merge_situation` →
  `merge_targets` (the conflict probe, `requirement_gate.py:417`), then on acceptance
  `integrate_task` → `merge_targets` (`task_transition_service.py:714`, `:883`) → `integrate` per
  target; an evidence decision's `retry_integration` → `integrate_task` (`:801-824`) takes the same
  list. No merging caller reads `integration_targets` directly. Task 1.5b pins the route, not only
  the function.
- **The preview's governed path switches to `merge_targets`** (resolving the workspace, wrapped as
  its ungoverned path already is, `tasks.py:1126-1129`), so the list the drawer shows is the list
  approval merges. This is one step of `the-approval-preview-asks-the-gates-merge-question`'s D1;
  whichever of the two changes lands first makes it, and the other finds it done.

Why this belongs here: D2 moves reviewers' detached-HEAD footprints into the task branch's bucket.
A reviewer checks the newest evidence's commit (`commit_for_task_review`), but if the author records
again during the review, the reviewer's later footprint names the **older** commit. Keyed by
observation it would displace the author's newer one and approval would merge less than was done.
Today the `"HEAD"` bucket hides that. The awaiting list (`awaiting_targets`) is unreduced by design
(`:289-304`) and is unaffected.

**Cost.** One `merge-base --is-ancestor` per same-branch collision, and for unnamed footprints up to
one per pair (kept × incoming), all bounded by the accepted rows of one task; `refresh_reachability` already caps a similar loop at 200 (`MAX_REACHABILITY_CHECKS`).

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

1. **Step 3's `main`** — **answered by R2: harmless.** A commit on `main` only gets `branch = main`
   and its own bucket. `integrate` asks `is_reachable_from(root, commit, main_branch) is True` before
   anything else and answers `ALREADY_INTEGRATED` without merging (`task_integration.py:481-490`).

## Round log

- **R1, 2026-09-24.** Re-verified F165 (both spellings) and F166 against `404c7d5`; measured git's
  detached answers; found `_branch_at`'s detached-checkout bug and the observation-order hazard D2
  would expose; wrote D1-D4 and D12's options.
- **R2, 2026-09-24.** Re-measured git 2.49 (non-tip is the reachable case). D1-D3 as B6 relies on them
  are **unchanged**: `""` only, `line_of_work(root, commit, *, task_branch=None)`, `read_footprint(root,
  *, at=None, task_branch=None)`, `Run.task_id` read once per restamp, D3 read at the task branch's tip
  in `workspace.root`. Decided D3's seam (`read_evidence_footprint`). **Moved D4** from
  `integration_targets` to `merge_targets` (the documented pure-database contract; every merging
  caller already uses `merge_targets`) and made the preview's governed path use it. Migration number
  made "next free" (0106 is claimed four times). Open Question 1 answered.
- **R3, 2026-09-24.** Re-derived D4 from the approval route down: every merging path (gate probe,
  `integrate_task`, `retry_integration`, prerequisites) goes through `merge_targets`, so the move
  fires in production. One correction: the reduction keeps a newer observation of the **same**
  commit (a *proper*-ancestor test), so today's evidence-id choice is unchanged where no ancestry is
  at stake. `is_reachable_from` is wrapped (`None` on failure), so D4 adds no raise to the gate.
  D1-D3, `line_of_work`, `read_footprint`'s signature and the `read_evidence_footprint` seam are
  **unchanged** (B6 builds on them).
- **Operator review, 2026-09-24** (`spec-queue/tracks/reviews/B5-2026-09-24.md` §4). D4 gains the
  unnamed arm (only proper ancestors dropped; tests 1.5d, 1.5e); the MODIFIED footprint requirement
  orders its fallbacks with "otherwise"; a MODIFIED delta for `task-lifecycle-governance`'s *Approval
  integrates the approved work* replaces "the newest such commit per distinct branch"; the migration's
  no-op on real data recorded. D1-D3 and the B6 seam are **unchanged**; D4's edit stays inside
  `merge_targets`.
